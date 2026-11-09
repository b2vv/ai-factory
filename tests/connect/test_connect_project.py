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
    (root / ".ai-factory-state").chmod(0o700)
    (root / "checksums.sha256").write_text("synthetic fixture\n")
    files={n:cp.installer.signature(root/n) for n in ["rules/agent-entry.md","release-manifest.json","checksums.sha256"]}
    installed={"version":version,"components":["core","capture-bridge"],"latest":txid,"files":files}
    manifest=cp.installer.read_json(root/"release-manifest.json")
    plan={"root":str(root),"version":version,"components":installed["components"],"files":files,"release_sha256":cp.installer.digest(cp.installer.encode(manifest))}
    cp.installer.write_tx(root/".ai-factory-state/receipts"/(txid+".json"),{"id":txid,"status":"APPLIED","plan":plan})
    (root/".ai-factory-state/installed.json").write_text(json.dumps(installed))
    return root


def run(args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cp.main(args)
    return rc, json.loads(buf.getvalue())


class ConnectProject(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.kit = make_kit(self.tmp)
        self.proj = self.tmp / "project"
        self.proj.mkdir()

    def base_args(self, **kw):
        a = ["--managed-root", str(self.kit), "--project", str(self.proj), "--git-root", str(self.proj)]
        for k, v in kw.items():
            a += [f"--{k.replace('_','-')}", v]
        return a

    def test_import_comment_and_prefix_are_not_imports(self):
        for text in ["# @AGENTS.local.md\n", "@AGENTS.local.md.other\n"]:
            new, action = cp.ensure_claude_import(text)
            self.assertNotEqual(action, "present")
            self.assertIn("\n@AGENTS.local.md\n", new)

    def test_symlink_target_refused_without_writes(self):
        victim=self.tmp/"victim";victim.write_text("original")
        (self.proj/"AGENTS.local.md").symlink_to(victim)
        with self.assertRaises(ValueError):run(self.base_args()+["--apply"])
        self.assertEqual(victim.read_text(),"original")
        self.assertFalse((self.proj/"CLAUDE.local.md").exists())

    def test_consistent_noncanonical_transaction_refused(self):
        state=self.kit/'.ai-factory-state';original=cp.installer.read_tx(next((state/'receipts').glob('*.json')));current=json.loads((state/'installed.json').read_text())
        current['latest']='not-a-transaction';original['id']=current['latest'];cp.installer.write_tx(state/'receipts/not-a-transaction.json',original);(state/'installed.json').write_text(json.dumps(current))
        with self.assertRaises(ValueError):run(self.base_args()+['--apply'])
        self.assertFalse((self.proj/'AGENTS.local.md').exists())

    def test_kit_baseline_drift_refused(self):
        from unittest.mock import patch
        original=cp.verify_consistency
        def drift(*args):
            result=original(*args);make_kit(self.tmp,version='updated');return result
        with patch.object(cp,'verify_consistency',side_effect=drift):
            with self.assertRaises(ValueError):run(self.base_args()+['--apply'])
        self.assertFalse((self.proj/'AGENTS.local.md').exists())

    def test_state_owner_refused(self):
        from unittest.mock import patch
        uid=cp.os.getuid()
        with patch.object(cp.os,'getuid',return_value=uid+1):
            with self.assertRaises(ValueError):run(self.base_args()+['--apply'])
        self.assertFalse((self.proj/'AGENTS.local.md').exists())

    def test_each_receipt_binding_refused(self):
        receipt=next((self.kit/'.ai-factory-state/receipts').glob('*.json'))
        original=cp.installer.read_tx(receipt)
        from copy import deepcopy
        for field in ['status','id','root','files','version','components']:
            data=deepcopy(original)
            if field in ['status','id']:data[field]='wrong'
            else:data['plan'][field]={'wrong':{}} if field=='files' else ['wrong'] if field=='components' else 'wrong'
            cp.installer.write_tx(receipt,data)
            with self.subTest(field=field),self.assertRaises(ValueError):run(self.base_args()+['--apply'])
            self.assertFalse((self.proj/'AGENTS.local.md').exists())
        cp.installer.write_tx(receipt,original)

    def test_required_inventory_and_manifest_bindings(self):
        state=self.kit/'.ai-factory-state';receipt=next((state/'receipts').glob('*.json'));original=cp.installer.read_tx(receipt);installed=json.loads((state/'installed.json').read_text())
        from copy import deepcopy
        for field in ['required','version','digest']:
            data=deepcopy(original);current=deepcopy(installed)
            if field=='required':
                current['files'].pop('checksums.sha256');data['plan']['files'].pop('checksums.sha256')
            elif field=='version':current['version']='wrong';data['plan']['version']='wrong'
            else:data['plan']['release_sha256']='wrong'
            cp.installer.write_tx(receipt,data);(state/'installed.json').write_text(json.dumps(current))
            with self.subTest(field=field),self.assertRaises(ValueError):run(self.base_args()+['--apply'])
        cp.installer.write_tx(receipt,original);(state/'installed.json').write_text(json.dumps(installed))

    def test_invalid_transaction_and_state_mode_refused(self):
        state=self.kit/'.ai-factory-state';installed=json.loads((state/'installed.json').read_text());bad=dict(installed,latest='../wrong');(state/'installed.json').write_text(json.dumps(bad))
        with self.assertRaises(ValueError):run(self.base_args()+['--apply'])
        (state/'installed.json').write_text(json.dumps(installed));state.chmod(0o755)
        with self.assertRaises(ValueError):run(self.base_args()+['--apply'])
        state.chmod(0o700)

    def test_tampered_file_or_mode_refused(self):
        entry=self.kit/'rules/agent-entry.md';before=entry.read_bytes()
        for mode,body in [(0o600,before),(0o644,b'changed')]:
            entry.chmod(mode);entry.write_bytes(body)
            with self.assertRaises(ValueError):run(self.base_args()+['--apply'])
            self.assertFalse((self.proj/'AGENTS.local.md').exists())
        entry.chmod(0o644);entry.write_bytes(before)

    def test_pending_install_refused(self):
        (self.kit/'.ai-factory-state/pending.json').write_text('{"id":"pending"}')
        with self.assertRaises(ValueError):run(self.base_args()+['--apply'])

    def test_stale_baseline_refused_before_first_write(self):
        from unittest.mock import patch
        target=self.proj/'CLAUDE.local.md';target.write_text('user content')
        original=cp.verify_consistency
        def drift(*args):
            result=original(*args);target.write_text('concurrent edit');return result
        with patch.object(cp,'verify_consistency',side_effect=drift):
            with self.assertRaises(ValueError):run(self.base_args()+['--apply'])
        self.assertFalse((self.proj/'AGENTS.local.md').exists())
        self.assertEqual(target.read_text(),'concurrent edit')

    def test_crlf_prefix_preserved(self):
        prefix=b'user rules  \r\n\r\n';target=self.proj/'AGENTS.local.md';target.write_bytes(prefix)
        run(self.base_args()+['--apply'])
        self.assertTrue(target.read_bytes().startswith(prefix))

    def test_receipt_integrity_refused(self):
        p=next((self.kit/'.ai-factory-state/receipts').glob('*.json'));d=json.loads(p.read_text());d['integrity']='bad';p.write_text(json.dumps(d))
        with self.assertRaises(ValueError):run(self.base_args()+['--apply'])
        self.assertFalse((self.proj/'AGENTS.local.md').exists())

    def test_missing_receipt_refused(self):
        next((self.kit/".ai-factory-state/receipts").glob("*.json")).unlink()
        with self.assertRaises(ValueError):run(self.base_args()+["--apply"])
        self.assertFalse((self.proj/"AGENTS.local.md").exists())

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

    def test_conflict_refuses_all_writes(self):
        old = "@/old/rules/agent-entry.md\n"
        (self.proj / "AGENTS.local.md").write_text(old)
        rc, rep = run(self.base_args() + ["--apply"])
        self.assertNotEqual(rc, 0)
        self.assertEqual((self.proj / "AGENTS.local.md").read_text(), old)
        self.assertFalse((self.proj / "CLAUDE.local.md").exists())
        self.assertFalse((self.proj / ".gitignore").exists())

    def test_malformed_markers_refuse_all_writes(self):
        for old in (cp.BEGIN, cp.END, cp.END + cp.BEGIN,
                    cp.BEGIN + cp.BEGIN + cp.END, cp.BEGIN + cp.END + cp.END):
            with self.subTest(old=old):
                (self.proj / "AGENTS.local.md").write_text(old)
                rc, rep = run(self.base_args() + ["--apply"])
                self.assertNotEqual(rc, 0)
                self.assertEqual((self.proj / "AGENTS.local.md").read_text(), old)
                self.assertFalse((self.proj / "CLAUDE.local.md").exists())

    def test_later_pin_conflict_preserves_earlier_pin(self):
        pin = self._write_stale_pin(cp.PIN_LOCATIONS[0], "pin")
        before = pin.read_bytes()
        other = self.proj / cp.PIN_LOCATIONS[-1]
        other.parent.mkdir(parents=True)
        other.write_text('{"unknown": true}\n')
        rc, rep = run(self.base_args() + ["--apply", "--reconcile-identity"])
        self.assertNotEqual(rc, 0)
        self.assertEqual(pin.read_bytes(), before)
        self.assertFalse((self.proj / "AGENTS.local.md").exists())

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
        abs_adapter = "/fixture/operator-project/.ai/project/adapter.md"
        abs_search = "/fixture/operator-project/.ai/project/capture-search.md"
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


class TaskIndexConnection(unittest.TestCase):
    setUp = ConnectProject.setUp
    base_args = ConnectProject.base_args
    def make_index(self):
        p=self.proj/'work/tasks.md';p.parent.mkdir(exist_ok=True);p.write_text('# Existing task index\n')
        return p

    def test_explicit_index_plan_apply_repeat_and_preserve(self):
        index=self.make_index();before=index.read_bytes()
        rc,rep=run(self.base_args(task_index='work/tasks.md'))
        self.assertEqual(rc,0);self.assertFalse((self.proj/'AGENTS.local.md').exists())
        rc,rep=run(self.base_args(task_index='work/tasks.md')+['--apply'])
        text=(self.proj/'AGENTS.local.md').read_text();self.assertIn('work/tasks.md',text)
        self.assertIn('ai-factory-task-index:',text);self.assertEqual(index.read_bytes(),before)
        # A routine update without the pointer option does not silently discard it.
        rc,rep=run(self.base_args()+['--apply'])
        self.assertEqual((self.proj/'AGENTS.local.md').read_text(),text)
        self.assertEqual([a for a in rep['actions'] if a['file']=='AGENTS.local.md'][0]['action'],'noop')
        rc,rep=run(self.base_args()+['--clear-task-index','--apply'])
        self.assertNotIn('ai-factory-task-index:',(self.proj/'AGENTS.local.md').read_text())
        self.assertEqual(index.read_bytes(),before)

    def test_bad_index_rejected_before_writes(self):
        index=self.make_index();(self.proj/'link.md').symlink_to(index)
        for name in ['missing.md','../outside.md',str(index),'link.md','work/tasks.md`\nextra','AGENTS.local.md']:
            with self.subTest(name=name),self.assertRaises(ValueError):run(self.base_args(task_index=name)+['--apply'])
            self.assertFalse((self.proj/'AGENTS.local.md').exists())

    def test_duplicate_pointer_blocked_without_mutation(self):
        self.make_index();run(self.base_args(task_index='work/tasks.md')+['--apply'])
        path=self.proj/'AGENTS.local.md';text=path.read_text();line=next(l for l in text.splitlines() if 'ai-factory-task-index:' in l)
        path.write_text(text.replace(line,line+'\n'+line));before=path.read_bytes()
        with self.assertRaises(ValueError):run(self.base_args()+['--apply'])
        self.assertEqual(path.read_bytes(),before)

    def test_pointer_target_drift_blocks_apply(self):
        from unittest.mock import patch
        index=self.make_index();original=cp.verify_consistency
        def drift(*args):
            result=original(*args);index.write_text('concurrent edit');return result
        with patch.object(cp,'verify_consistency',side_effect=drift),self.assertRaises(ValueError):
            run(self.base_args(task_index='work/tasks.md')+['--apply'])
        self.assertFalse((self.proj/'AGENTS.local.md').exists())

    def test_outside_managed_pointer_is_not_adopted(self):
        self.make_index();path=self.proj/'AGENTS.local.md';path.write_text('<!-- ai-factory-task-index: "work/tasks.md" -->\n')
        run(self.base_args()+['--apply'])
        body=path.read_text().split(cp.BEGIN,1)[1].split(cp.END,1)[0]
        self.assertNotIn('ai-factory-task-index:',body)

if __name__ == "__main__":
    unittest.main()
