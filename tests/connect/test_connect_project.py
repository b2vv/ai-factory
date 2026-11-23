"""Reproducible project-connection step: content preserved, idempotent, no silent deletions.

Covers the required fixtures: missing local files; existing files with user rules; an already
present import; an old conflicting (unmanaged) connection; a repeat run; a kit update; and a
worktree connection. Proves user text is kept, no duplicates arise, a no-input-change re-run
writes nothing, and hooks/credentials are never touched.
"""
import io
import json
import re
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
    for name in cp.GLOBAL_ROUTES:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# shared workflow\n")
    files={n:cp.installer.signature(root/n) for n in ["rules/agent-entry.md","release-manifest.json","checksums.sha256", *cp.GLOBAL_ROUTES]}
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

    def test_explicit_entry_read_is_portable_beside_claude_import(self):
        rc, _ = run(self.base_args() + ['--apply'])
        self.assertEqual(rc, 0)
        text = (self.proj / 'AGENTS.local.md').read_text()
        self.assertIn(f"Before work, skills or delegation, explicitly read `{self.kit}/rules/agent-entry.md`", text)
        self.assertIn('not a claim that other hosts load it automatically', text)
        self.assertIn(f"@{self.kit}/rules/agent-entry.md", text)

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

    # 6. kit update: the block is bound to no hash or version, so the project needs no rewrite
    def test_kit_update_leaves_block_unchanged(self):
        run(self.base_args() + ["--apply"])
        user_tail = "\n# trailing user note kept\n"
        p = self.proj / "AGENTS.local.md"
        p.write_text(p.read_text() + user_tail)
        before = p.read_bytes()
        # simulate a kit.py update: new version + manifest
        make_kit(self.tmp, version="0.9.0", manifest_body="M2")
        rc, rep = run(self.base_args() + ["--apply"])
        self.assertEqual(rc, 0)
        self.assertEqual(p.read_bytes(), before)
        self.assertEqual([x for x in rep["actions"] if x["file"] == "AGENTS.local.md"][0]["action"], "noop")
        self.assertEqual(rep["kit"]["version"], "0.9.0")   # the report still shows the live identity

    def test_block_points_to_latest_without_hashes(self):
        run(self.base_args() + ["--apply"])
        text = (self.proj / "AGENTS.local.md").read_text()
        block = text.split(cp.BEGIN, 1)[1].split(cp.END, 1)[0]
        self.assertIsNone(re.search(r"[0-9a-f]{32,}", block))
        self.assertNotIn("receipts/", block)
        self.assertNotIn("0.8.0-alpha", block)
        self.assertIn(f"`{self.kit}/.ai-factory-state/installed.json` (`latest`)", block)

    # 7. worktree: same step, adapter referenced by absolute path, no copy
    def test_worktree_absolute_adapter(self):
        wt = self.tmp / "worktree"
        wt.mkdir()
        external = self.tmp / "operator-project"
        external.mkdir()
        abs_adapter = str(external / "adapter.md")
        abs_search = str(external / "capture-search.md")
        Path(abs_adapter).write_text("# local adapter\n")
        Path(abs_search).write_text("# search contract\n")
        rc, rep = run(["--managed-root", str(self.kit), "--project", str(wt), "--git-root", str(wt),
                       "--adapter", abs_adapter, "--search-contract", abs_search, "--apply"])
        txt = (wt / "AGENTS.local.md").read_text()
        self.assertIn(abs_adapter, txt)
        self.assertIn(abs_search, txt)
        self.assertIn(f"@{self.kit}/rules/agent-entry.md", txt)

    def test_explicit_routes_fail_closed(self):
        for flag in ('--adapter', '--search-contract'):
            for kind in ('missing', 'directory', 'unreadable', 'invalid-utf8', 'dangling', 'escape'):
                with self.subTest(flag=flag, kind=kind):
                    path = self.proj / (kind + '.md')
                    if not path.exists() and not path.is_symlink():
                        if kind == 'directory': path.mkdir()
                        elif kind == 'unreadable':
                            path.write_text('private'); path.chmod(0)
                        elif kind == 'invalid-utf8': path.write_bytes(b'\xff')
                        elif kind == 'dangling': path.symlink_to(self.tmp / 'absent.md')
                        elif kind == 'escape':
                            target = self.tmp / 'external.md'; target.write_text('outside')
                            path.symlink_to(target)
                    rc, report = run(self.base_args() + [flag, path.name, '--apply'])
                    self.assertEqual(rc, 1)
                    self.assertEqual(report['status'], 'BLOCKED')
                    self.assertFalse((self.proj / 'AGENTS.local.md').exists())

    def test_autodetected_invalid_routes_block(self):
        for candidate in (*cp.ADAPTER_ROUTES, *cp.SEARCH_ROUTES):
            with self.subTest(candidate=candidate):
                path = self.proj / candidate
                path.parent.mkdir(parents=True, exist_ok=True); path.mkdir()
                rc, report = run(self.base_args() + ['--apply'])
                self.assertEqual(rc, 1)
                self.assertFalse((self.proj / 'AGENTS.local.md').exists())
                path.rmdir()

    def test_dangling_autodetected_routes_block_before_writes(self):
        for candidate in (cp.ADAPTER_ROUTES[0], cp.SEARCH_ROUTES[0]):
            path = self.proj / candidate
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(self.tmp / 'missing-target.md')
            rc, report = run(self.base_args() + ['--apply'])
            self.assertEqual(rc, 1); self.assertEqual(report['status'], 'BLOCKED')
            self.assertFalse((self.proj / 'AGENTS.local.md').exists())
            path.unlink()

    def test_autodiscovery_preserves_candidate_priority(self):
        for candidate in cp.ADAPTER_ROUTES:
            path = self.proj / candidate
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text('# adapter')
        rc, report = run(self.base_args())
        self.assertEqual(rc, 0)
        self.assertEqual(report['routes']['adapter'], cp.ADAPTER_ROUTES[0])

    def test_route_read_races_are_value_errors(self):
        from unittest.mock import patch
        path = self.proj / 'route.md'; path.write_text('# original')
        before = cp.installer.signature(path)
        changed = dict(before, sha256='0' * 64)
        # Mock the read boundary, not the whole validator: independently exercise each
        # check even when the surrounding signatures happen to remain stable (ABA).
        for raw, signatures in ((None, [before, before]),
                                (b'# replacement', [before, before]),
                                (b'# original', [before, changed])):
            with self.subTest(raw=raw, signatures=signatures):
                with patch.object(cp.installer, 'signature', side_effect=signatures), \
                     patch.object(cp.installer, 'regular', return_value=raw):
                    with self.assertRaises(ValueError):
                        cp.route_reference(self.proj, 'route.md')

    def test_route_mode_and_access_checks_are_independent(self):
        from unittest.mock import patch
        path = self.proj / 'route.md'; path.write_text('# original')
        before = cp.installer.signature(path)
        with patch.object(cp.os, 'access', return_value=False):
            with self.assertRaises(ValueError): cp.route_reference(self.proj, 'route.md')
        # Privileged execution can read mode 000; the declared-readable contract must
        # still reject it even if the effective access check succeeds.
        with patch.object(cp.installer, 'signature', return_value=dict(before, mode=0)), \
             patch.object(cp.os, 'access', return_value=True):
            with self.assertRaises(ValueError): cp.route_reference(self.proj, 'route.md')

    def test_four_adapter_layouts_and_ai_directory_only(self):
        (self.proj / '.ai').mkdir()
        rc, report = run(self.base_args())
        self.assertEqual(rc, 0); self.assertIsNone(report['routes']['adapter'])
        for candidate in cp.ADAPTER_ROUTES:
            path = self.proj / candidate
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text('# adapter')
            rc, report = run(self.base_args())
            self.assertEqual(rc, 0); self.assertEqual(report['routes']['adapter'], candidate)
            path.unlink()

    def test_route_drift_before_apply_blocks_all_writes(self):
        from unittest.mock import patch
        for flag in ('--adapter', '--search-contract'):
            for change in ('remove', 'replace'):
                path = self.proj / 'route.md'; path.write_text('# original')
                original = cp.verify_consistency
                def drift(*args):
                    result = original(*args)
                    if change == 'remove': path.unlink()
                    else: path.write_text('# changed')
                    return result
                with patch.object(cp, 'verify_consistency', side_effect=drift):
                    with self.assertRaises(ValueError):
                        run(self.base_args() + [flag, path.name, '--apply'])
                self.assertFalse((self.proj / 'AGENTS.local.md').exists())

    def test_global_only_readable_preserves_local_and_idempotent(self):
        p = self.proj / 'AGENTS.local.md'; p.write_text('# user architecture stays\n')
        args = self.base_args() + ['--global-only', '--search-contract', 'AGENTS.local.md', '--apply']
        rc, report = run(args)
        self.assertEqual(rc, 0)
        content = p.read_text()
        self.assertTrue(content.startswith('# user architecture stays\n'))
        for route in cp.GLOBAL_ROUTES: self.assertIn(str(self.kit / route), content)
        self.assertIn('global-only', content)
        rc, report = run(args)
        self.assertEqual(rc, 0); self.assertEqual(content, p.read_text())
        self.assertEqual(report['routes']['mode'], 'global-only')

    def test_global_only_retained_and_explicit_adapter_overrides(self):
        run(self.base_args() + ['--global-only', '--apply'])
        path = self.proj / cp.ADAPTER_ROUTES[0]
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text('# local')
        rc, report = run(self.base_args() + ['--apply'])
        self.assertEqual(rc, 0); self.assertEqual(report['routes']['mode'], 'global-only')
        self.assertIsNone(report['routes']['adapter'])
        self.assertEqual(report['actions'][0]['action'], 'noop')
        rc, report = run(self.base_args() + ['--adapter', cp.ADAPTER_ROUTES[0], '--apply'])
        self.assertEqual(rc, 0); self.assertEqual(report['routes']['mode'], 'local')
        self.assertNotIn('ai-factory-route: global-only', (self.proj / 'AGENTS.local.md').read_text())

    def test_existing_markup_suffix_and_noncanonical_routes_rejected(self):
        # Real files are essential: an absent target would mask a missing syntax guard.
        for name in ('foo`bar.md', 'foo\nbar.md', 'file.txt', 'file.md', 'credential.md'):
            (self.proj / name).write_text('# valid UTF-8 contents')
        (self.tmp / 'outside.md').write_text('# existing external file')
        values = ('foo`bar.md', 'foo\nbar.md', 'file.txt', './file.md', 'credential.md',
                  '../outside.md', str(self.proj) + '//file.md')
        for value in values:
            for flag in ('--adapter', '--search-contract'):
                with self.subTest(flag=flag, value=repr(value)):
                    rc, report = run(self.base_args() + [flag, value, '--apply'])
                    self.assertEqual(rc, 1)
                    self.assertEqual(report['status'], 'BLOCKED')
                    self.assertFalse((self.proj / 'AGENTS.local.md').exists())
                    self.assertFalse((self.proj / 'CLAUDE.local.md').exists())

    def test_route_cannot_rebaseline_destination(self):
        from unittest.mock import patch
        path = self.proj / 'AGENTS.local.md'; path.write_text('# original')
        original = cp.kit_identity
        def drift(*args):
            result = original(*args); path.write_text('# concurrent edit'); return result
        with patch.object(cp, 'kit_identity', side_effect=drift):
            rc, report = run(self.base_args() + ['--search-contract', path.name, '--apply'])
        self.assertEqual(rc, 1)
        self.assertEqual(path.read_text(), '# concurrent edit')
        self.assertFalse((self.proj / 'CLAUDE.local.md').exists())

    def test_adapter_and_global_only_are_mutually_exclusive(self):
        from contextlib import redirect_stderr
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            run(self.base_args() + ['--adapter', 'adapter.md', '--global-only'])
        self.assertEqual(raised.exception.code, 2)

    def test_managed_routing_marker_validation_and_scope(self):
        path = self.proj / 'AGENTS.local.md'
        for body in ('<!-- ai-factory-route: unknown -->',
                     '<!-- ai-factory-route: global-only -->\n<!-- ai-factory-route: global-only -->'):
            path.write_text(cp.BEGIN + '\n' + body + '\n' + cp.END + '\n')
            before = path.read_bytes()
            rc, report = run(self.base_args() + ['--apply'])
            self.assertEqual(rc, 1); self.assertEqual(report['status'], 'BLOCKED')
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse((self.proj / 'CLAUDE.local.md').exists())
        # Unmanaged text remains user-owned; it must neither activate nor block routing.
        for text in ('<!-- ai-factory-route: global-only -->', '<!-- ai-factory-route: unknown -->'):
            path.write_text(text + '\n')
            rc, report = run(self.base_args())
            self.assertEqual(rc, 0); self.assertEqual(report['routes']['mode'], 'local')
            self.assertEqual(path.read_text(), text + '\n')

    def test_outside_route_marker_with_managed_block_is_preserved_not_adopted(self):
        path = self.proj / 'AGENTS.local.md'
        rc, _ = run(self.base_args() + ['--apply'])
        self.assertEqual(rc, 0)
        original = path.read_text()
        for marker in ('<!-- ai-factory-route: global-only -->', '<!-- ai-factory-route: unknown -->'):
            path.write_text(marker + '\n' + original)
            before = path.read_bytes()
            rc, report = run(self.base_args() + ['--apply'])
            self.assertEqual(rc, 0)
            self.assertEqual(report['routes']['mode'], 'local')
            self.assertEqual(report['actions'][0]['action'], 'noop')
            self.assertEqual(path.read_bytes(), before)

    def test_global_reference_must_belong_to_installed_receipt(self):
        state = self.kit / '.ai-factory-state'
        installed = json.loads((state / 'installed.json').read_text())
        name = cp.GLOBAL_ROUTES[0]
        del installed['files'][name]
        (state / 'installed.json').write_text(json.dumps(installed))
        receipt_path = state / 'receipts' / (installed['latest'] + '.json')
        receipt = cp.installer.read_tx(receipt_path)
        del receipt['plan']['files'][name]
        cp.installer.write_tx(receipt_path, receipt)
        self.assertTrue((self.kit / name).is_file())
        # Consistent install state and valid bytes are not enough: unmanaged references
        # must not be promoted into the global workflow contract.
        cp.kit_identity(self.kit)
        rc, report = run(self.base_args() + ['--global-only', '--apply'])
        self.assertEqual(rc, 1); self.assertEqual(report['status'], 'BLOCKED')
        self.assertFalse((self.proj / 'AGENTS.local.md').exists())

    def test_route_contract_lists_and_metadata(self):
        adapters = ('.ai/project/adapter.md', '.ai/agents/ai-factory.md',
                    'work/rules/ai-factory.md', 'docs/development/ai-factory.md')
        searches = ('.ai/project/capture-search.md', '.ai/agents/capture-search.md')
        globals_ = ('ai-factory/ai-factory-plan.md', 'ai-factory/workflow.md',
                    'ai-factory/pre-code-checkpoint.md', 'ai-factory/review-handoff.md')
        self.assertEqual(cp.ADAPTER_ROUTES, adapters)
        self.assertEqual(cp.SEARCH_ROUTES, searches)
        self.assertEqual(cp.GLOBAL_ROUTES, globals_)
        for candidate in searches:
            path = self.proj / candidate
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text('# contract')
            rc, report = run(self.base_args())
            self.assertEqual(rc, 0)
            self.assertEqual(report['routes'], {
                'mode': 'local', 'adapter': None, 'search_contract': candidate,
                'validation': 'readable-files-only; contents, endpoint and authorization not verified'})
            path.unlink()
        rc, report = run(self.base_args() + ['--global-only', '--apply'])
        self.assertEqual(rc, 0)
        text = (self.proj / 'AGENTS.local.md').read_text()
        for name in globals_: self.assertIn(str(self.kit / name), text)

    def test_installed_global_reference_must_be_utf8(self):
        name = 'ai-factory/workflow.md'
        (self.kit / name).write_bytes(b'\xff')
        signature = cp.installer.signature(self.kit / name)
        state = self.kit / '.ai-factory-state'
        installed = json.loads((state / 'installed.json').read_text())
        installed['files'][name] = signature
        (state / 'installed.json').write_text(json.dumps(installed))
        receipt_path = state / 'receipts' / (installed['latest'] + '.json')
        receipt = cp.installer.read_tx(receipt_path)
        receipt['plan']['files'][name] = signature
        cp.installer.write_tx(receipt_path, receipt)
        cp.kit_identity(self.kit)
        rc, report = run(self.base_args() + ['--global-only', '--apply'])
        self.assertEqual(rc, 1)
        self.assertIn('global workflow', report['conflicts'][0])
        self.assertFalse((self.proj / 'AGENTS.local.md').exists())

    def test_global_only_requires_installed_workflow(self):
        (self.kit / cp.GLOBAL_ROUTES[0]).unlink()
        with self.assertRaises(ValueError):
            run(self.base_args() + ['--global-only', '--apply'])
        self.assertFalse((self.proj / 'AGENTS.local.md').exists())

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
    def test_explicit_search_contract_retained_on_reconnect(self):
        # Regression: a reconnect without --search-contract silently dropped the route.
        (self.proj / 'AGENTS.local.md').write_text('# local\nSearch route: GET only.\n')
        rc, _ = run(self.base_args(search_contract='AGENTS.local.md') + ['--apply'])
        self.assertEqual(rc, 0)
        rc, report = run(self.base_args() + ['--apply'])
        self.assertEqual(rc, 0)
        self.assertEqual(report['routes']['search_contract'], 'AGENTS.local.md')
        self.assertEqual(report['actions'][0]['action'], 'noop')
        self.assertNotIn('not configured', (self.proj / 'AGENTS.local.md').read_text())

    def test_retained_search_contract_wins_over_autodetected_route(self):
        (self.proj / 'AGENTS.local.md').write_text('# local\n')
        run(self.base_args(search_contract='AGENTS.local.md') + ['--apply'])
        auto = self.proj / cp.SEARCH_ROUTES[0]
        auto.parent.mkdir(parents=True, exist_ok=True); auto.write_text('# other contract')
        rc, report = run(self.base_args())
        self.assertEqual(rc, 0)
        self.assertEqual(report['routes']['search_contract'], 'AGENTS.local.md')

    def test_missing_retained_search_contract_blocks_not_drops(self):
        contract = self.proj / 'search.md'; contract.write_text('# contract')
        run(self.base_args(search_contract='search.md') + ['--apply'])
        before = (self.proj / 'AGENTS.local.md').read_text()
        contract.unlink()
        rc, report = run(self.base_args() + ['--apply'])
        self.assertEqual(rc, 1); self.assertEqual(report['status'], 'BLOCKED')
        self.assertEqual((self.proj / 'AGENTS.local.md').read_text(), before)

    def test_clear_search_contract_is_explicit(self):
        contract = self.proj / 'search.md'; contract.write_text('# contract')
        run(self.base_args(search_contract='search.md') + ['--apply'])
        rc, report = run(self.base_args() + ['--clear-search-contract', '--apply'])
        self.assertEqual(rc, 0); self.assertIsNone(report['routes']['search_contract'])
        self.assertIn('not configured', (self.proj / 'AGENTS.local.md').read_text())
        self.assertTrue(contract.exists())

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

    # T28: work/ layout on connect
    ROLES = ("tasks", "in-progress", "archive", "tech-debt")

    def block(self):
        text = (self.proj / "AGENTS.local.md").read_text()
        return text.split(cp.BEGIN, 1)[1].split(cp.END, 1)[0]

    def test_fresh_project_gets_four_work_directories(self):
        rc, plan = run(self.base_args())
        self.assertEqual(rc, 0)
        self.assertEqual("created", plan["work_layout"]["mode"])
        self.assertIn({"file": "work/archive/README.md", "action": "create"}, plan["actions"])
        self.assertFalse((self.proj / "work").exists())            # dry run writes nothing
        rc, rep = run(self.base_args() + ["--apply"])
        self.assertEqual(rc, 0)
        for role in self.ROLES:
            readme = self.proj / "work" / role / "README.md"
            self.assertEqual(0o644, readme.stat().st_mode & 0o777)
            self.assertTrue(readme.read_text().startswith("# "))
        self.assertIn("Work layout: tasks `work/tasks/`; in progress `work/in-progress/`; "
                      "archive `work/archive/`; tech debt `work/tech-debt/`.", self.block())
        self.assertIn("moves to the archive as a pointer", self.block())
        self.assertNotIn("not mapped", self.block())
        before = {p: p.read_bytes() for p in self.proj.rglob("*") if p.is_file()}
        rc, again = run(self.base_args() + ["--apply"])           # reconnect is NOOP
        self.assertEqual(rc, 0)
        self.assertEqual("existing", again["work_layout"]["mode"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.proj.rglob("*") if p.is_file()})
        self.assertTrue(all(x["action"] in ("noop", "present") for x in again["actions"]))

    def test_existing_layout_kept_and_mapped_without_guessing(self):
        for name in ("queue", "backlog", "debt", "archive", "draft", ".hidden"):
            (self.proj / "work" / name).mkdir(parents=True)
        (self.proj / "work" / "archive" / "T1.md").write_text("done\n")
        (self.proj / "work" / "notes.md").write_text("a file is not a role\n")
        rc, rep = run(self.base_args() + ["--apply"])
        self.assertEqual(rc, 0)
        self.assertEqual({"tasks": None, "in-progress": None, "archive": "archive", "tech-debt": "debt"},
                         rep["work_layout"]["roles"])
        self.assertEqual({"tasks": ["queue", "backlog"], "in-progress": []}, rep["work_layout"]["unmapped"])
        self.assertEqual([".hidden", "archive", "backlog", "debt", "draft", "notes.md", "queue"],
                         sorted(p.name for p in (self.proj / "work").iterdir()))      # nothing created or moved
        self.assertEqual("done\n", (self.proj / "work" / "archive" / "T1.md").read_text())
        block = self.block()
        self.assertIn("tasks: not mapped; in progress: not mapped; archive `work/archive/`; tech debt `work/tech-debt/`"
                      .replace("`work/tech-debt/`", "`work/debt/`"), block)
        self.assertIn("ask the owner, do not guess", block)

    def test_empty_role_directories_left_by_rollback_are_completed(self):
        for role in ("tasks", "archive"):
            (self.proj / "work" / role).mkdir(parents=True)
        rc, rep = run(self.base_args() + ["--apply"])
        self.assertEqual("created", rep["work_layout"]["mode"])
        for role in self.ROLES:
            self.assertTrue((self.proj / "work" / role / "README.md").is_file())
        (self.proj / "work" / "tech-debt" / "README.md").unlink()   # a used, non-empty layout is not refilled
        (self.proj / "work" / "tasks" / "T1.md").write_text("open\n")
        rc, rep = run(self.base_args() + ["--apply"])
        self.assertEqual("existing", rep["work_layout"]["mode"])
        self.assertFalse((self.proj / "work" / "tech-debt" / "README.md").exists())

    def test_role_name_wins_over_other_names(self):
        for name in ("tasks", "queue", "done"):
            (self.proj / "work" / name).mkdir(parents=True)
        rc, rep = run(self.base_args())
        self.assertEqual("tasks", rep["work_layout"]["roles"]["tasks"])
        self.assertEqual("done", rep["work_layout"]["roles"]["archive"])

    def test_explicit_work_dir_retained_cleared_and_checked(self):
        for name in ("queue", "backlog"):
            (self.proj / "work" / name).mkdir(parents=True)
        rc, rep = run(self.base_args() + ["--work-dir", "tasks=queue", "--apply"])
        self.assertEqual(rc, 0)
        self.assertEqual("queue", rep["work_layout"]["roles"]["tasks"])
        self.assertIn('<!-- ai-factory-work-layout: {"tasks": "queue"} -->', self.block())
        rc, again = run(self.base_args() + ["--apply"])
        self.assertEqual("queue", again["work_layout"]["roles"]["tasks"])  # retained without the flag
        self.assertEqual("noop", [x for x in again["actions"] if x["file"] == "AGENTS.local.md"][0]["action"])
        (self.proj / "work" / "queue").rmdir()
        before = (self.proj / "AGENTS.local.md").read_bytes()
        rc, gone = run(self.base_args() + ["--apply"])
        self.assertNotEqual(rc, 0)
        self.assertIn("--work-dir tasks=", gone["conflicts"][0])
        self.assertEqual(before, (self.proj / "AGENTS.local.md").read_bytes())
        rc, cleared = run(self.base_args() + ["--work-dir", "tasks=", "--apply"])
        self.assertEqual(rc, 0)
        self.assertNotIn("ai-factory-work-layout", self.block())
        self.assertEqual("backlog", cleared["work_layout"]["roles"]["tasks"])

    def test_bad_work_input_blocks_before_writes(self):
        (self.proj / "work" / "queue").mkdir(parents=True)
        for value in ("tasks", "nope=queue", "tasks=../x", "tasks=a/b", "tasks=missing"):
            with self.subTest(value=value):
                rc, rep = run(self.base_args() + ["--work-dir", value, "--apply"])
                self.assertNotEqual(rc, 0)
                self.assertFalse((self.proj / "AGENTS.local.md").exists())
        (self.proj / "work" / "queue").rmdir(); (self.proj / "work").rmdir()
        (self.proj / "work").write_text("not a directory\n")
        rc, rep = run(self.base_args() + ["--apply"])
        self.assertNotEqual(rc, 0)
        self.assertFalse((self.proj / "AGENTS.local.md").exists())
        (self.proj / "work").unlink()
        elsewhere = self.tmp / "elsewhere"; elsewhere.mkdir()
        (self.proj / "work").symlink_to(elsewhere)
        with self.assertRaises(ValueError):  # like every symlinked target: refused before any write
            run(self.base_args() + ["--apply"])
        self.assertEqual([], list(elsewhere.iterdir()))
        self.assertFalse((self.proj / "AGENTS.local.md").exists())

    def test_malformed_work_marker_blocks(self):
        run(self.base_args() + ["--apply"])
        p = self.proj / "AGENTS.local.md"
        for bad in ('<!-- ai-factory-work-layout: [1] -->', '<!-- ai-factory-work-layout: {"nope": "tasks"} -->'):
            with self.subTest(bad=bad):
                p.write_text(p.read_text().replace(cp.END, bad + "\n" + cp.END))
                rc, rep = run(self.base_args() + ["--apply"])
                self.assertNotEqual(rc, 0)
                p.write_text(p.read_text().replace(bad + "\n", ""))

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
