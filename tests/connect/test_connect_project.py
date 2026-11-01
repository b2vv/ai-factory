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

    # ---- identity reconciliation (stale pin/adapter/manifest) ----

    def _write_stale_pin(self, rel, schema):
        """Write a stale pin/package file with history + caches that MUST be preserved verbatim."""
        p = self.proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if schema == "pin":
            obj = {
                "schema": "ai-factory-pin/1",
                "note": "Local ignored connection.",
                "source": {
                    "repo": "/some/repo",
                    "commit": "0000000000000000000000000000000000000000",
                    "version": "0.7.0-OLD",
                    "release_manifest_file_sha256": "deadbeef" * 8,
                },
                "managed_root": str(self.kit),
                "previous_pin": {"schema": "ai-factory-pin/1", "source": {"version": "0.6.0-HIST"}},
            }
        else:
            obj = {
                "schema_version": 1,
                "package": {
                    "repository": "https://example/repo",
                    "commit": "1111111111111111111111111111111111111111",
                    "version": "0.7.0-OLD",
                    "release_manifest_sha256": "cafebabe" * 8,
                },
                "cache": {"required_files": {"README.md": "f00df00d" * 8}},
                "previous_connection": {"version": "0.6.0-HIST"},
            }
        p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
        return p

    def _installed_identity(self):
        inst = json.loads((self.kit / ".ai-factory-state" / "installed.json").read_text())
        import hashlib
        mani = hashlib.sha256((self.kit / "release-manifest.json").read_bytes()).hexdigest()
        return inst["version"], mani

    # dry-run shows the identity changes but writes nothing
    def test_reconcile_dry_run_shows_changes_writes_nothing(self):
        p = self._write_stale_pin(".ai/project/ai-factory-pin.json", "pin")
        before = p.read_bytes()
        rc, rep = run(self.base_args() + ["--reconcile-identity"])  # no --apply
        self.assertEqual(p.read_bytes(), before)  # nothing written
        recon = rep["identity_reconcile"]
        self.assertEqual(recon[0]["status"], "would-update")
        keys = {c["key"] for c in recon[0]["changes"]}
        # version + manifest sha refreshed; stale commit demoted (never guessed)
        self.assertEqual(keys, {"source.version", "source.release_manifest_file_sha256", "source.commit"})

    # apply reconciles identity to installed kit; preserves commit, history, notes
    def test_reconcile_apply_updates_identity_preserves_rest(self):
        for rel, schema in ((".ai/project/ai-factory-pin.json", "pin"),
                            ("work/rules/ai-factory-package.json", "pkg")):
            p = self._write_stale_pin(rel, schema)
            run(self.base_args() + ["--reconcile-identity", "--apply"])
            obj = json.loads(p.read_text())
            want_v, want_m = self._installed_identity()
            blk = obj.get("source") or obj.get("package")
            self.assertEqual(blk["version"], want_v)  # identity updated
            mk = "release_manifest_file_sha256" if "source" in obj else "release_manifest_sha256"
            self.assertEqual(blk[mk], want_m)
            # commit NOT guessed: demoted to null + explicit unverified marker, old SHA kept in history
            self.assertIsNone(blk["commit"])
            self.assertIn("UNVERIFIED_FOR_CURRENT_PACKAGE", blk["commit_status"])
            self.assertIn(blk["commit_superseded"][:4], ("0000", "1111"))
            # history + caches preserved
            txt = p.read_text()
            self.assertIn("0.6.0-HIST", txt)
            self.assertNotIn("0.7.0-OLD", txt)  # the only replaced identity value

    # re-run after a successful reconcile writes nothing (idempotent)
    def test_reconcile_idempotent(self):
        p = self._write_stale_pin(".ai/project/ai-factory-pin.json", "pin")
        run(self.base_args() + ["--reconcile-identity", "--apply"])
        after1 = p.read_bytes()
        rc, rep = run(self.base_args() + ["--reconcile-identity", "--apply"])
        self.assertEqual(p.read_bytes(), after1)
        self.assertEqual(rep["identity_reconcile"][0]["status"], "match")

    # no-update mode: MISMATCH is reported, and the file is NOT rewritten
    def test_mismatch_reported_without_reconcile(self):
        p = self._write_stale_pin(".ai/project/ai-factory-pin.json", "pin")
        before = p.read_bytes()
        rc, rep = run(self.base_args() + ["--apply"])  # apply, but NO --reconcile-identity
        self.assertEqual(p.read_bytes(), before)  # not rewritten
        self.assertNotIn("identity_reconcile", rep)  # reconciler not even invoked
        self.assertTrue(any("MISMATCH" in f for f in rep["consistency"]))

    # unknown schema: shown as a conflict before write, never guessed/rewritten
    def test_reconcile_unknown_schema_reported_not_written(self):
        p = self.proj / ".ai/project/ai-factory-pin.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"schema": "something-else/9", "x": 1}, indent=2) + "\n")
        before = p.read_bytes()
        rc, rep = run(self.base_args() + ["--reconcile-identity", "--apply"])
        self.assertEqual(p.read_bytes(), before)  # not written
        self.assertEqual(rep["identity_reconcile"][0]["status"], "conflict")
        self.assertTrue(any("UNKNOWN pin/package schema" in c for c in rep["conflicts"]))

    # non-canonical formatting: reported, not reformatted
    def test_reconcile_noncanonical_reported_not_written(self):
        p = self.proj / ".ai/project/ai-factory-pin.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"schema":"ai-factory-pin/1","source":{"version":"x","release_manifest_file_sha256":"y"}}')
        before = p.read_bytes()
        rc, rep = run(self.base_args() + ["--reconcile-identity", "--apply"])
        self.assertEqual(p.read_bytes(), before)  # not reformatted
        self.assertEqual(rep["identity_reconcile"][0]["status"], "conflict")


if __name__ == "__main__":
    unittest.main()
