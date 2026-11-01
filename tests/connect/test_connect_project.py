"""Reproducible project-connection step: content preserved, idempotent, no silent deletions.

Covers the required fixtures: missing local files; existing files with user rules; an already
present import; an old conflicting (unmanaged) connection; a repeat run; a kit update; and a
worktree connection. Proves user text is kept, no duplicates arise, a no-input-change re-run
writes nothing, and hooks/credentials are never touched.
"""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import importlib
connect = importlib.import_module("connect-project") if False else None
# module name has a hyphen; load by path
import importlib.util
_spec = importlib.util.spec_from_file_location("connect_project", ROOT / "tools" / "connect-project.py")
cp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cp)


def make_kit(base, version="0.8.0-alpha.1+codex-events.1", manifest_body="M1"):
    root = base / "managed-kit"
    (root / ".ai-factory-state" / "receipts").mkdir(parents=True, exist_ok=True)
    (root / "rules").mkdir(parents=True, exist_ok=True)
    (root / "rules" / "agent-entry.md").write_text("# entry rules\n")
    (root / "release-manifest.json").write_text(json.dumps({"schema_version": 2, "version": version, "body": manifest_body}))
    txid = "a" * 32
    (root / ".ai-factory-state" / "receipts" / f"{txid}.json").write_text("{}")
    (root / ".ai-factory-state" / "installed.json").write_text(json.dumps(
        {"version": version, "components": ["core", "capture-bridge"], "latest": txid, "files": {}}))
    return root


def run(args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cp.main(args)
    return rc, json.loads(buf.getvalue())


class ConnectProject(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.kit = make_kit(self.tmp)
        self.proj = self.tmp / "project"
        self.proj.mkdir()

    def base_args(self, **kw):
        a = ["--managed-root", str(self.kit), "--project", str(self.proj), "--git-root", str(self.proj)]
        for k, v in kw.items():
            a += [f"--{k.replace('_','-')}", v]
        return a

    # 1. missing local files -> created and wired
    def test_missing_files_created(self):
        rc, rep = run(self.base_args() + ["--apply"])
        self.assertEqual(rc, 0)
        agents = (self.proj / "AGENTS.local.md").read_text()
        claude = (self.proj / "CLAUDE.local.md").read_text()
        gi = (self.proj / ".gitignore").read_text()
        self.assertIn(cp.BEGIN, agents)
        self.assertIn(cp.END, agents)
        self.assertIn(f"@{self.kit}/rules/agent-entry.md", agents)
        self.assertIn("@AGENTS.local.md", claude)
        self.assertIn("AGENTS.local.md", gi)
        self.assertIn("CLAUDE.local.md", gi)

    # 2. existing user rules preserved; block appended
    def test_existing_user_content_preserved(self):
        marker = "# MY PROJECT RULE — do not lose\nAlways foo before bar.\n"
        (self.proj / "AGENTS.local.md").write_text(marker)
        run(self.base_args() + ["--apply"])
        txt = (self.proj / "AGENTS.local.md").read_text()
        self.assertIn(marker, txt)             # user text intact
        self.assertIn(cp.BEGIN, txt)           # block appended
        self.assertTrue(txt.index(marker) < txt.index(cp.BEGIN))

    # 3. already-present import is not duplicated
    def test_existing_import_not_duplicated(self):
        (self.proj / "CLAUDE.local.md").write_text("# local\n@AGENTS.local.md\nkeep me\n")
        rc, rep = run(self.base_args() + ["--apply"])
        txt = (self.proj / "CLAUDE.local.md").read_text()
        self.assertEqual(txt.count("@AGENTS.local.md"), 1)
        self.assertIn("keep me", txt)

    # 4. old conflicting unmanaged connection: reported, not deleted, not duplicated
    def test_unmanaged_conflict_reported_not_deleted(self):
        old = "# local\n@/Users/someone/.local/share/ai-factory-kit/rules/agent-entry.md\n"
        (self.proj / "AGENTS.local.md").write_text(old)
        rc, rep = run(self.base_args() + ["--apply"])
        txt = (self.proj / "AGENTS.local.md").read_text()
        self.assertTrue(any("UNMANAGED kit import" in c for c in rep["conflicts"]))
        self.assertIn("/Users/someone/.local/share/ai-factory-kit/rules/agent-entry.md", txt)  # not deleted
        # the old import is not duplicated: it still appears exactly once
        self.assertEqual(txt.count("/Users/someone/.local/share/ai-factory-kit/rules/agent-entry.md"), 1)

    # 5. re-run with unchanged inputs writes nothing
    def test_rerun_idempotent(self):
        run(self.base_args() + ["--apply"])
        before = (self.proj / "AGENTS.local.md").read_bytes()
        gi_before = (self.proj / ".gitignore").read_bytes()
        rc, rep = run(self.base_args() + ["--apply"])
        after = (self.proj / "AGENTS.local.md").read_bytes()
        self.assertEqual(before, after)
        self.assertEqual(gi_before, (self.proj / ".gitignore").read_bytes())
        actions = {x["file"]: x["action"] for x in rep["actions"]}
        self.assertEqual(actions["AGENTS.local.md"], "noop")
        self.assertEqual(actions[".gitignore"], "noop")

    # 6. kit update: only the managed block is refreshed to the new identity
    def test_kit_update_refreshes_block(self):
        run(self.base_args() + ["--apply"])
        user_tail = "\n# trailing user note kept\n"
        p = self.proj / "AGENTS.local.md"
        p.write_text(p.read_text() + user_tail)
        # simulate a kit.py update: new version + manifest
        make_kit(self.tmp, version="0.9.0", manifest_body="M2")
        rc, rep = run(self.base_args() + ["--apply"])
        txt = p.read_text()
        self.assertIn("0.9.0", txt)                    # new identity in block
        self.assertIn(user_tail.strip(), txt)          # user tail still present
        self.assertEqual([x for x in rep["actions"] if x["file"] == "AGENTS.local.md"][0]["action"], "update-block")

    # 7. worktree: same step, adapter referenced by absolute path, no copy
    def test_worktree_absolute_adapter(self):
        wt = self.tmp / "worktree"
        wt.mkdir()
        abs_adapter = "/Users/strelia/projects/dg/.ai/project/adapter.md"
        abs_search = "/Users/strelia/projects/dg/.ai/project/capture-search.md"
        rc, rep = run(["--managed-root", str(self.kit), "--project", str(wt), "--git-root", str(wt),
                       "--adapter", abs_adapter, "--search-contract", abs_search, "--apply"])
        txt = (wt / "AGENTS.local.md").read_text()
        self.assertIn(abs_adapter, txt)
        self.assertIn(abs_search, txt)
        self.assertIn(f"@{self.kit}/rules/agent-entry.md", txt)

    # 8. hooks / credentials are never touched
    def test_hooks_and_credentials_untouched(self):
        claude_dir = self.proj / ".claude"
        claude_dir.mkdir()
        hook = claude_dir / "settings.local.json"
        hook_bytes = json.dumps({"hooks": {"Stop": [{"command": "run-capture"}]}}).encode()
        hook.write_bytes(hook_bytes)
        secret = self.proj / "secret.txt"
        secret.write_bytes(b"TOP-SECRET-VALUE")
        run(self.base_args() + ["--apply"])
        self.assertEqual(hook.read_bytes(), hook_bytes)      # hook config unchanged
        self.assertEqual(secret.read_bytes(), b"TOP-SECRET-VALUE")  # credential unchanged
        # and no secret value leaked into any written file
        for f in ("AGENTS.local.md", "CLAUDE.local.md", ".gitignore"):
            self.assertNotIn("TOP-SECRET-VALUE", (self.proj / f).read_text())

    # search-not-configured is reported honestly
    def test_search_not_configured_honest(self):
        rc, rep = run(self.base_args() + ["--apply"])
        txt = (self.proj / "AGENTS.local.md").read_text()
        self.assertIn("not configured", txt)

    def test_dry_run_writes_nothing(self):
        rc, rep = run(self.base_args())  # no --apply
        self.assertFalse((self.proj / "AGENTS.local.md").exists())
        self.assertIn("PLANNED", rep["status"])


if __name__ == "__main__":
    unittest.main()
