"""Isolated instruction migration tests: no live home, grants or instruction contents."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


k = load('instructions_kit_fixture', ROOT/'tools/kit.py')
u = load('instructions_fixture', ROOT/'tools/instruction_update.py')
REAL_SIZE_1_HASH = '3772859776cc3c688a5bc654bfbbfbbc00df06d3d72fa2e389347f02921cef52'
FRAGMENT = 'Reviewed synthetic obsolete continuation clause.\nKeep exact fixture boundaries.'


def fixture_policy():
    return patch.dict(u.KNOWN, {'legacy-project-size-1': k.digest(FRAGMENT.encode())})


def fixture_payload(raw):
    # Only disposable package copies substitute an ASCII synthetic commitment.
    # The shipped policy retains the independently reviewed real fragment hash.
    return raw.replace(REAL_SIZE_1_HASH.encode(), k.digest(FRAGMENT.encode()).encode())



class InstructionTests(unittest.TestCase):
    def setUp(self):
        policy=fixture_policy();policy.start();self.addCleanup(policy.stop)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base/'home'; self.home.mkdir()
        self.project = self.home/'project'; (self.project/'.git').mkdir(parents=True)
        self.root = self.home/'managed-kit'; self.package = self.base/'package'
        self.private = self.base/'private'; self.private.mkdir(mode=0o700)
        self.target = self.project/'CLAUDE.local.md'
        self.original = ('Project instructions\n' + FRAGMENT + '\nKeep user text: 5MB 2 compactions ☀.\n').encode()
        self.target.write_bytes(self.original)
        self.spec = {'schema':1, 'home':str(self.home), 'managed_root':str(self.root),
                     'targets':[{'recipe':'legacy-project-size-1','project':str(self.project),'fragment':FRAGMENT}]}
        self.sp = self.private/'spec.json'; self.save_spec()
        self.release('1'); plan = k.plan(self.package,self.root,[])
        k.apply(self.package,self.root,[],plan['plan_id'])
        self.release('2')

    def save_spec(self):
        self.sp.write_bytes(k.encode(self.spec)); self.sp.chmod(0o600)

    def release(self, version, entry=True):
        if self.package.exists(): shutil.rmtree(self.package)
        self.package.mkdir()
        files = {name:fixture_payload((ROOT/name).read_bytes()) for name in ('tools/kit.py','tools/capture_update.py','tools/instruction_update.py')}
        files['docs/version.md'] = version.encode()
        if entry: files['rules/agent-entry.md'] = b'# canonical rules\n'
        entries = []
        for name,raw in files.items():
            path=self.package/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            entries.append({'path':name,'sha256':k.digest(raw),'component':'core'})
        (self.package/'release-manifest.json').write_bytes(k.encode({'schema_version':2,'version':version,'components':{'core':{}},'files':entries}))
        (self.package/'checksums.sha256').write_text(''.join(k.digest(p.read_bytes())+'  '+str(p.relative_to(self.package))+'\n' for p in sorted(self.package.rglob('*')) if p.is_file()))

    def plan(self, explicit=True):
        return u.plan(k,self.package,self.root,[],self.sp if explicit else None)

    def apply(self, explicit=True):
        p=self.plan(explicit)
        return u.apply(k,self.package,self.root,[],self.sp if explicit else None,None,p['plan_id'],True)

    def rollback(self, ident):
        p=u.rollback_plan(k,self.root,ident)
        return u.rollback(k,self.root,ident,p['plan_id'],True)

    def test_recipe_commitment_and_happy_lifecycle(self):
        self.assertEqual(u.KNOWN['legacy-project-size-1'],k.digest(FRAGMENT.encode()))
        before=self.target.read_bytes();p=self.plan()
        self.assertEqual(before,self.target.read_bytes())
        self.assertNotIn(FRAGMENT,json.dumps(u.public(p),ensure_ascii=False))
        result=self.apply();self.assertEqual(result['status'],'APPLIED')
        self.assertIn(b'Keep user text: 5MB 2 compactions',self.target.read_bytes())
        self.assertNotIn(FRAGMENT,self.target.read_text())
        self.assertEqual(self.plan(False)['status'],'NOOP')
        self.assertEqual(self.rollback(result['transaction'])['status'],'ROLLED_BACK')
        self.assertEqual(self.target.read_bytes(),self.original)
        self.assertEqual(k.current(self.root)['version'],'1')
        self.assertEqual(self.rollback(result['transaction'])['status'],'NOOP')

    def test_retired_recipe_ids_still_validate_without_plaintext(self):
        # Retired ids are rebuilt from hex so neither source file carries them in plaintext.
        retired = ['legacy-'+bytes.fromhex(h).decode()+'-size' for h in ('636f7572736573','63617373696f70656961')]
        self.assertEqual([u.known_recipe(r) for r in retired],['legacy-project-size-1','legacy-project-size-2'])
        source=(ROOT/'tools/instruction_update.py').read_text()+(ROOT/'tests/install/test_instruction_update.py').read_text()
        for r in retired: self.assertNotIn(r,source)
        self.assertIsNone(u.known_recipe('legacy-project-size-3'))
        self.assertEqual(u.known_recipe('legacy-project-size-2'),'legacy-project-size-2')
        # Shipped fragment commitments are unchanged by the rename.
        shipped=load('instructions_shipped_policy',ROOT/'tools/instruction_update.py').KNOWN
        self.assertEqual(shipped['legacy-project-size-1'],REAL_SIZE_1_HASH)
        self.assertEqual(shipped['legacy-project-size-2'],'ae2a224321eea03fa5afbff98d45d8f2039a7794e71a26660ec66e602c1deb48')
        # Old and new id of one recipe count as a duplicate.
        dup=dict(self.spec,targets=[dict(self.spec['targets'][0],recipe=retired[0]),self.spec['targets'][0]])
        with self.assertRaises(ValueError):u.validate_spec(k,self.root,dup)
        # A registration naming the retired id validates and runs the full lifecycle unchanged.
        self.spec['targets'][0]['recipe']=retired[0];self.save_spec()
        home,targets=u.validate_spec(k,self.root,self.spec)
        self.assertEqual(targets[0][0]['recipe'],retired[0])
        result=self.apply();self.assertEqual(result['status'],'APPLIED')
        self.assertNotIn(FRAGMENT,self.target.read_text())
        self.assertEqual(self.plan(False)['status'],'NOOP')
        self.assertEqual(self.rollback(result['transaction'])['status'],'ROLLED_BACK')
        self.assertEqual(self.target.read_bytes(),self.original)

    def test_unknown_duplicate_mixed_and_encoding_preserve(self):
        canonical=u.replacement(self.root,'legacy-project-size-1')
        for text in ('unknown',FRAGMENT+FRAGMENT,FRAGMENT+canonical,'\ufeff'+FRAGMENT,FRAGMENT.replace('\n','\r\n'),FRAGMENT+'\n'+FRAGMENT):
            with self.subTest(text=text[:12]):
                self.target.write_text(text);before=self.target.read_bytes()
                with self.assertRaises(ValueError):self.plan()
                self.assertEqual(self.target.read_bytes(),before)
                self.assertEqual(k.current(self.root)['version'],'1')

    def test_target_symlink_hardlink_and_oversize_block(self):
        self.target.unlink();self.target.symlink_to(self.sp)
        with self.assertRaises(ValueError):self.plan()
        self.target.unlink();os.link(self.sp,self.target)
        with self.assertRaises(ValueError):self.plan()
        self.target.unlink();self.target.write_bytes(self.original+b'x'*u.MAX_DOCUMENT)
        with self.assertRaises(ValueError):self.plan()

    def test_private_spec_and_duplicate_json(self):
        self.sp.chmod(0o644)
        with self.assertRaises(ValueError):self.plan()
        self.sp.chmod(0o600);self.sp.write_text('{"schema":1,"schema":1}')
        with self.assertRaises(ValueError):self.plan()

    def test_missing_canonical_entry_blocks_before_child(self):
        self.release('2',entry=False)
        with self.assertRaises(ValueError):self.plan()
        self.assertEqual(k.current(self.root)['version'],'1')
        self.assertEqual(self.target.read_bytes(),self.original)

    def test_stale_plan_and_direct_bypass(self):
        p=self.plan();self.target.write_bytes(self.original+b'owner edit\n')
        with self.assertRaises(ValueError):u.apply(k,self.package,self.root,[],self.sp,None,p['plan_id'],True)
        self.target.write_bytes(self.original);r=self.apply()
        with self.assertRaises(ValueError):k.apply(self.package,self.root,[],k.plan(self.package,self.root,[])['plan_id'])
        with self.assertRaises(ValueError):k.rollback(self.root,r['base_transaction'],'ignored')

    def test_concurrent_change_after_child_preserved_and_rollback_blocked(self):
        original=k.apply
        def edit(*args):
            result=original(*args);self.target.write_bytes(self.original+b'concurrent owner\n');return result
        with patch.object(k,'apply',side_effect=edit):r=self.apply()
        self.assertEqual(r['status'],'BLOCKED')
        self.assertIn(b'concurrent owner',self.target.read_bytes())
        with self.assertRaises(ValueError):self.rollback(r['transaction'])

    def test_crash_after_child_commit_before_result_save(self):
        original=k.apply
        def crash(*args):original(*args);raise KeyboardInterrupt()
        with patch.object(k,'apply',side_effect=crash), self.assertRaises(KeyboardInterrupt):self.apply()
        ident=k.read_json(self.root/k.STATE/u.PENDING)['id']
        self.assertEqual(self.rollback(ident)['status'],'ROLLED_BACK')
        self.assertEqual(self.target.read_bytes(),self.original)

    def test_backups_private_and_verified_before_restore(self):
        r=self.apply();path=self.root/k.STATE/u.RECEIPTS/(r['transaction']+'.json')
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777,0o700)
        tx=k.read_tx(path);tx['plan']['_instructions']['files'][0]['old']=base64.b64encode(b'corrupt').decode();k.write_tx(path,tx)
        before=self.target.read_bytes()
        with self.assertRaises(ValueError):self.rollback(r['transaction'])
        self.assertEqual(before,self.target.read_bytes())

    def test_old_outer_receipt_cannot_rollback_newer_update(self):
        first=self.apply();self.release('3');second=self.apply(False)
        self.assertEqual(second['status'],'APPLIED')
        with self.assertRaises(ValueError):self.rollback(first['transaction'])
        self.assertEqual(self.rollback(second['transaction'])['status'],'ROLLED_BACK')
        self.assertEqual(self.rollback(first['transaction'])['status'],'ROLLED_BACK')

    def test_rolledback_cleanup_checks_all_outputs(self):
        r=self.apply();self.rollback(r['transaction'])
        k.atomic(self.root/k.STATE/u.PENDING,k.encode({'id':r['transaction']}))
        self.assertEqual(self.rollback(r['transaction'])['status'],'NOOP')
        self.assertFalse((self.root/k.STATE/u.PENDING).exists())
        self.target.write_bytes(self.original+b'owner\n')
        with self.assertRaises(ValueError):self.rollback(r['transaction'])

    def add_fixture_global(self):
        fragment = '# fixture global legacy body\n'
        path = self.home/'.agents/AGENTS.md';path.parent.mkdir(exist_ok=True);path.write_text(fragment+'Owner suffix 42 MB\n')
        self.spec['targets'].append({'recipe':'legacy-agents-entry','project':None,'fragment':fragment});self.save_spec()
        return path, patch.dict(u.KNOWN, {'legacy-agents-entry':k.digest(fragment.encode())})

    def test_exact_global_prefix_preserves_suffix_and_parity(self):
        path, policy=self.add_fixture_global()
        with policy:
            r=self.apply();text=path.read_text()
            for marker in ('Before work, skills or delegation', 'single source', 'bounded progress/results', 'full raw agent', 'launched versus returned', 'same model', 'task-resume and archive-search'):
                self.assertIn(marker,text)
            self.assertTrue(text.endswith('Owner suffix 42 MB\n'))
            self.assertEqual(self.plan(False)['status'],'NOOP')
            self.rollback(r['transaction'])
            path.write_text('unknown prefix\n'+path.read_text())
            with self.assertRaises(ValueError):self.plan()

    def test_preimages_durable_before_delegation(self):
        original=k.apply
        def inspect(*args):
            pending=k.read_json(self.root/k.STATE/u.PENDING)
            tx=u.read_receipt(k,self.root/k.STATE/u.RECEIPTS/(pending['id']+'.json'))
            self.assertEqual(tx['status'],'DELEGATING')
            self.assertEqual(u.decode(k,tx['plan']['_instructions']['files'][0]['old'],tx['plan']['_instructions']['files'][0]['before']),self.original)
            return original(*args)
        with patch.object(k,'apply',side_effect=inspect):self.assertEqual(self.apply()['status'],'APPLIED')

    def test_second_document_failure_restores_first(self):
        path,policy=self.add_fixture_global();before=path.read_bytes();real=k.guarded_write
        def fail(target,*args):
            if Path(target)==path:raise OSError('injected document failure')
            return real(target,*args)
        with policy:
            with patch.object(k,'guarded_write',side_effect=fail):r=self.apply()
            self.assertEqual(r['status'],'BLOCKED')
            self.assertNotEqual(self.target.read_bytes(),self.original)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(self.rollback(r['transaction'])['status'],'ROLLED_BACK')
            self.assertEqual(self.target.read_bytes(),self.original)

    def test_rollback_crash_at_document_and_after_child(self):
        for stage in ('document','child'):
            with self.subTest(stage=stage):
                r=self.apply();real_write=k.guarded_write;real_rb=k.rollback
                def crash_write(path,*args):
                    result=real_write(path,*args)
                    if Path(path)==self.target:raise KeyboardInterrupt()
                    return result
                def crash_rb(*args):real_rb(*args);raise KeyboardInterrupt()
                manager=patch.object(k,'guarded_write',side_effect=crash_write) if stage=='document' else patch.object(k,'rollback',side_effect=crash_rb)
                with manager,self.assertRaises(KeyboardInterrupt):self.rollback(r['transaction'])
                self.assertEqual(self.rollback(r['transaction'])['status'],'ROLLED_BACK')
                self.assertEqual(self.target.read_bytes(),self.original)

    def test_prepared_crash_without_delegation_is_recoverable(self):
        real=k.atomic
        def crash(path,*args,**kw):
            result=real(path,*args,**kw)
            if Path(path)==self.root/k.STATE/u.PENDING:raise KeyboardInterrupt()
            return result
        with patch.object(k,'atomic',side_effect=crash),self.assertRaises(KeyboardInterrupt):self.apply()
        ident=k.read_json(self.root/k.STATE/u.PENDING)['id']
        self.assertEqual(self.rollback(ident)['status'],'ROLLED_BACK')

    def test_delegating_zero_new_receipts_is_uncertain_not_replayed(self):
        with patch.object(k,'apply',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):self.apply()
        ident=k.read_json(self.root/k.STATE/u.PENDING)['id']
        with self.assertRaises(ValueError):self.rollback(ident)
        self.assertEqual(self.target.read_bytes(),self.original)

    def test_home_binding_and_same_home_lock(self):
        import fcntl
        self.apply();other=self.home/'other-kit';other.mkdir()
        with self.assertRaises(ValueError):u.check_home(k,self.home,other)
        with u.locks(k,self.root,self.home):
            with self.assertRaises(BlockingIOError):
                with u.locks(k,self.root,self.home):pass

    def test_outer_only_child_noop_lineage(self):
        # Install current package before initial registration: child is NOOP.
        p=k.plan(self.package,self.root,[]);k.apply(self.package,self.root,[],p['plan_id'])
        r=self.apply();self.assertIsNone(r['base_transaction'])
        self.assertEqual(self.rollback(r['transaction'])['status'],'ROLLED_BACK')
        self.assertEqual(k.current(self.root)['version'],'2')

    def test_small_receipt_limit_blocks_before_delegation(self):
        with patch.object(k,'MAX',70000),self.assertRaises(ValueError):self.plan()
        self.assertEqual(self.target.read_bytes(),self.original)
        self.assertFalse((self.root/k.STATE/u.PENDING).exists())

    def add_codex(self, content=b''):
        path=self.home/'.codex/AGENTS.md';path.parent.mkdir(exist_ok=True);path.write_bytes(content)
        self.spec['targets'].append({'recipe':'empty-codex-entry','project':None,'fragment':''});self.save_spec()
        return path

    def test_codex_empty_to_explicit_pointer_and_rollback(self):
        path=self.add_codex()
        with patch.dict(os.environ,{},clear=True):
            r=self.apply();text=path.read_text()
            self.assertIn('Before work, skills or delegation',text)
            self.assertIn('verified repository root',text)
            self.assertIn('AGENTS.local.md if present',text)
            self.assertNotIn('\n@',text)
            self.assertEqual(self.plan(False)['status'],'NOOP')
            self.rollback(r['transaction']);self.assertEqual(path.read_bytes(),b'')

    def test_codex_already_canonical_rollback_preserves_preimage(self):
        content=u.replacement(self.root,'empty-codex-entry').encode();path=self.add_codex(content)
        with patch.dict(os.environ,{},clear=True):
            r=self.apply();self.rollback(r['transaction'])
        self.assertEqual(path.read_bytes(),content)

    def test_codex_unknown_missing_override_and_alternate_home(self):
        path=self.add_codex(b'owner instructions')
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ValueError):self.plan()
            path.unlink()
            with self.assertRaises(ValueError):self.plan()
            path.write_bytes(b'')
            override=path.with_name('AGENTS.override.md');override.symlink_to(self.home/'absent')
            with self.assertRaises(ValueError):self.plan()
            override.unlink()
            with patch.dict(os.environ,{'CODEX_HOME':str(self.home/'elsewhere')}):
                with self.assertRaises(ValueError):self.plan()
            with patch.dict(os.environ,{'CODEX_HOME':str(path.parent)}):self.plan()

    def test_codex_discovery_drift_after_child_blocks_hostwrites(self):
        path=self.add_codex();original=k.apply
        def change(*args):
            result=original(*args);path.with_name('AGENTS.override.md').write_text('owner');return result
        with patch.dict(os.environ,{},clear=True),patch.object(k,'apply',side_effect=change):r=self.apply()
        self.assertEqual(r['status'],'BLOCKED');self.assertEqual(path.read_bytes(),b'')
        self.assertEqual(self.target.read_bytes(),self.original)

    def test_codex_env_change_invalidates_dryrun(self):
        self.add_codex()
        with patch.dict(os.environ,{},clear=True):
            p=self.plan()
            with patch.dict(os.environ,{'CODEX_HOME':str(self.home/'.codex')}):
                with self.assertRaises(ValueError):u.apply(k,self.package,self.root,[],self.sp,None,p['plan_id'],True)
        self.assertFalse((self.root/k.STATE/u.PENDING).exists())

    def test_existing_recipes_still_reject_empty_fragment(self):
        self.spec['targets'][0]['fragment']='';self.save_spec()
        with self.assertRaises(ValueError):self.plan()

    def test_rollback_pins_document_and_metadata_before_staging(self):
        for target_kind in ('document', 'registration', 'lineage'):
            with self.subTest(target_kind=target_kind):
                r=self.apply();before=self.target.read_bytes();real=u.save
                changed = self.target if target_kind=='document' else self.root/k.STATE/(u.REG if target_kind=='registration' else u.CURRENT)
                original=changed.read_bytes()
                def edit_after_stage(*args):
                    result=real(*args)
                    if args[2]['status']=='ROLLING_BACK':changed.write_bytes(original+b' ')
                    return result
                with patch.object(u,'save',side_effect=edit_after_stage),self.assertRaises(ValueError):self.rollback(r['transaction'])
                self.assertEqual(changed.read_bytes(),original+b' ')
                if target_kind!='document':self.assertEqual(self.target.read_bytes(),before)
                changed.write_bytes(original)
                self.assertEqual(self.rollback(r['transaction'])['status'],'ROLLED_BACK')

    def test_child_terminal_receipt_before_pending_cleanup_is_recoverable(self):
        r=self.apply();real=k.write_tx
        def crash(path,tx):
            result=real(path,tx)
            if Path(path).parent==self.root/k.STATE/'receipts' and tx['status']=='ROLLED_BACK':raise KeyboardInterrupt()
            return result
        with patch.object(k,'write_tx',side_effect=crash),self.assertRaises(KeyboardInterrupt):self.rollback(r['transaction'])
        self.assertEqual(k.pending(self.root),r['base_transaction'])
        self.assertEqual(self.rollback(r['transaction'])['status'],'ROLLED_BACK')
        self.assertIsNone(k.pending(self.root));self.assertEqual(self.target.read_bytes(),self.original)

    def test_child_terminal_cleanup_refuses_unrelated_change(self):
        r=self.apply();real=k.write_tx
        def crash(path,tx):
            result=real(path,tx)
            if Path(path).parent==self.root/k.STATE/'receipts' and tx['status']=='ROLLED_BACK':raise KeyboardInterrupt()
            return result
        with patch.object(k,'write_tx',side_effect=crash),self.assertRaises(KeyboardInterrupt):self.rollback(r['transaction'])
        (self.root/'docs/version.md').write_text('foreign edit')
        with self.assertRaises(ValueError):self.rollback(r['transaction'])
        self.assertEqual(k.pending(self.root),r['base_transaction'])

    def test_exact_residue_commitment_classifier(self):
        residue='SPECIFIC LEGACY RESIDUE'
        with patch.object(u,'RESIDUES',((len(residue),k.digest(residue.encode())),)):
            self.assertTrue(u.has_residue('prefix '+residue+' suffix'))
            self.assertFalse(u.has_residue('prefix SPECIFIC changed RESIDUE suffix'))
            self.target.write_text(FRAGMENT+' '+residue)
            with self.assertRaises(ValueError):self.plan()

    def test_cli_isolated_mode_from_unrelated_directory(self):
        cmd=[sys.executable,'-I','-B',str(self.package/'tools/kit.py'),'update','--package',str(self.package),'--root',str(self.root)]
        r=subprocess.run(cmd+['--instruction-spec',str(self.sp)],cwd=self.private,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);p=json.loads(r.stdout)
        r=subprocess.run(cmd+['--instruction-spec',str(self.sp),'--execute','--exclusive-window','--plan-id',p['plan_id']],cwd=self.private,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        # Use the actual installed updater without the original spec argument.
        cmd[3]=str(self.root/'tools/kit.py')
        r=subprocess.run(cmd,cwd=self.private,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(json.loads(r.stdout)['status'],'NOOP')


    def test_rollback_verifies_restored_state_strictly(self):
        r=self.apply();real=k.guarded_write
        def skip_target(path,*args):
            if Path(path)==self.target:return None   # a writer that silently leaves the target as it was
            return real(path,*args)
        with patch.object(k,'guarded_write',side_effect=skip_target),self.assertRaisesRegex(ValueError,'did not restore'):
            self.rollback(r['transaction'])
        receipt=json.loads((self.root/k.STATE/u.RECEIPTS/(r['transaction']+'.json')).read_text())
        self.assertNotEqual('ROLLED_BACK',receipt['status'])
        self.assertEqual('ROLLED_BACK',self.rollback(r['transaction'])['status'])
        self.assertEqual(self.target.read_bytes(),self.original)

    def test_hand_edit_names_target_and_accepted_states_without_a_path(self):
        r=self.apply();after=self.target.read_bytes()
        self.target.write_bytes(after+b'owner edit\n')
        with self.assertRaises(ValueError) as cm:u.rollback_plan(k,self.root,r['transaction'])
        msg=str(cm.exception)
        self.assertRegex(msg,r'^instruction user edit blocks rollback: target 1 recipe legacy-project-size-1 sha256 [0-9a-f]{12} expected [0-9a-f]{12} or [0-9a-f]{12}$')
        self.assertIn(k.digest(self.original)[:12],msg);self.assertIn(k.digest(after)[:12],msg)
        reason=k.blocked_reason(ValueError(msg))
        self.assertTrue(reason.startswith('INSTRUCTION_TARGET_EDITED'));self.assertIn('target 1 recipe legacy-project-size-1',reason)
        self.assertNotIn(str(self.base),reason)
        for crafted in (msg+' '+str(self.target),'instruction user edit blocks rollback: '+str(self.target)):
            leaked=k.blocked_reason(ValueError(crafted))
            self.assertTrue(leaked.startswith('INSTRUCTION_TARGET_EDITED'));self.assertNotIn(str(self.base),leaked);self.assertNotIn('target 1',leaked)
        self.target.write_bytes(after);self.assertEqual('ROLLED_BACK',self.rollback(r['transaction'])['status'])
        self.target.write_bytes(self.original+b'later edit\n')
        with self.assertRaises(ValueError) as cm:u.rollback_plan(k,self.root,r['transaction'])
        self.assertRegex(str(cm.exception),r'expected [0-9a-f]{12}$')   # terminal: only the before state is accepted


class CaptureInstructionTests(unittest.TestCase):
    def setUp(self):
        policy=fixture_policy();policy.start();self.addCleanup(policy.stop)
        fixture=load('capture_instruction_fixture',ROOT/'tests/install/test_capture_update.py')
        self.ck=fixture.k;self.cf=fixture.UpdateTests();self.cf.setUp();self.addCleanup(self.cf.doCleanups)
        self.add_payload()
        result=self.cf.apply();self.assertEqual(result['status'],'APPLIED')
        self.cf.release('3');self.add_payload()
        self.project=self.cf.home/'instruction-project';(self.project/'.git').mkdir(parents=True)
        self.target=self.project/'CLAUDE.local.md';self.target.write_text(FRAGMENT)
        self.spec={'schema':1,'home':str(self.cf.home),'managed_root':str(self.cf.root),
                   'targets':[{'recipe':'legacy-project-size-1','project':str(self.project),'fragment':FRAGMENT}]}
        self.sp=self.cf.private/'instructions.json';self.sp.write_bytes(self.ck.encode(self.spec));self.sp.chmod(0o600)

    def add_payload(self):
        path=self.cf.pkg/'tools/instruction_update.py';path.write_bytes(fixture_payload((ROOT/'tools/instruction_update.py').read_bytes()))
        manifest=self.ck.read_json(self.cf.pkg/'release-manifest.json')
        manifest['files'].append({'path':'tools/instruction_update.py','sha256':self.ck.digest(path.read_bytes()),'component':'core'})
        (self.cf.pkg/'release-manifest.json').write_bytes(self.ck.encode(manifest))
        (self.cf.pkg/'checksums.sha256').write_text(''.join(self.ck.digest(p.read_bytes())+'  '+str(p.relative_to(self.cf.pkg))+'\n' for p in sorted(self.cf.pkg.rglob('*')) if p.is_file() and p.name!='checksums.sha256'))

    def plan(self):return u.plan(self.ck,self.cf.pkg,self.cf.root,[],self.sp)
    def apply(self):
        p=self.plan();return u.apply(self.ck,self.cf.pkg,self.cf.root,[],self.sp,None,p['plan_id'],True)
    def rollback(self,ident):
        p=u.rollback_plan(self.ck,self.cf.root,ident);return u.rollback(self.ck,self.cf.root,ident,p['plan_id'],True)

    def test_combined_capture_no_hook_change_and_rollback(self):
        settings=self.cf.home/'.claude/settings.json';before=settings.read_bytes()
        result=self.apply();self.assertEqual(result['status'],'APPLIED')
        self.assertEqual(settings.read_bytes(),before)
        self.assertEqual(self.rollback(result['transaction'])['status'],'ROLLED_BACK')
        self.assertEqual(settings.read_bytes(),before)
        self.assertEqual(self.target.read_text(),FRAGMENT)

    def test_capture_child_noop_still_binds_hook_files_and_receipt(self):
        self.cf.apply()  # Candidate installed before instruction registration: child is NOOP.
        result=self.apply();self.assertEqual(result['status'],'APPLIED')
        self.assertIsNone(result['base_transaction'])
        settings=self.cf.home/'.claude/settings.json';original=settings.read_bytes()
        before=self.target.read_bytes();settings.write_bytes(original+b'\n')
        with self.assertRaises(ValueError):self.rollback(result['transaction'])
        self.assertEqual(self.target.read_bytes(),before)
        settings.write_bytes(original)
        spec=self.cf.spec;state=Path(spec['registration_root'])/self.ck.STATE
        current=self.ck.read_tx(state/'current.json');receipt=state/'receipts'/(current['id']+'.json')
        raw=receipt.read_bytes();receipt.write_bytes(raw+b'\n')
        with self.assertRaises(ValueError):self.rollback(result['transaction'])
        self.assertEqual(self.target.read_bytes(),before)

    def test_capture_terminal_receipt_pending_cleanup_is_recoverable(self):
        # A failed combined apply retains its owned pending marker through rollback.
        loader=u.capture.connector
        def fail_connector(*args,**kwargs):
            module=loader(*args,**kwargs)
            if len(args)>3:
                def fail(*a,**kw):raise ValueError('injected post-kit connector failure')
                module.apply=fail
            return module
        with patch.object(u.capture,'connector',side_effect=fail_connector):result=self.apply()
        self.assertEqual(result['status'],'BLOCKED');real=self.ck.write_tx
        def crash(path,tx):
            answer=real(path,tx)
            if Path(path).parent==self.cf.root/self.ck.STATE/u.capture.RECEIPTS and tx['status']=='ROLLED_BACK':raise KeyboardInterrupt()
            return answer
        with patch.object(self.ck,'write_tx',side_effect=crash),self.assertRaises(KeyboardInterrupt):self.rollback(result['transaction'])
        self.assertTrue((self.cf.root/self.ck.STATE/u.capture.PENDING).exists())
        self.assertEqual(self.rollback(result['transaction'])['status'],'ROLLED_BACK')
        self.assertFalse((self.cf.root/self.ck.STATE/u.capture.PENDING).exists())

    def test_capture_changes_block_before_delegation(self):
        real=u.capture.plan
        def changed(*args,**kwargs):
            p=real(*args,**kwargs);p['capture']['changes']=[{'path':'unexpected'}];return p
        with patch.object(u.capture,'plan',side_effect=changed),self.assertRaises(ValueError):self.plan()
        self.assertEqual(self.ck.current(self.cf.root)['version'],'2')
        self.assertEqual(self.target.read_text(),FRAGMENT)

    def test_capture_blocked_return_does_not_publish_instruction(self):
        real=u.capture.apply
        def blocked(*args,**kwargs):
            result=real(*args,**kwargs);return {**result,'status':'BLOCKED'}
        with patch.object(u.capture,'apply',side_effect=blocked):result=self.apply()
        self.assertEqual(result['status'],'BLOCKED')
        self.assertEqual(self.target.read_text(),FRAGMENT)
        self.assertEqual(self.rollback(result['transaction'])['status'],'ROLLED_BACK')

    def test_combined_child_commit_crash_correlates_only_new_receipt(self):
        real=u.capture.apply
        def crash(*args,**kwargs):real(*args,**kwargs);raise KeyboardInterrupt()
        with patch.object(u.capture,'apply',side_effect=crash),self.assertRaises(KeyboardInterrupt):self.apply()
        ident=self.ck.read_json(self.cf.root/self.ck.STATE/u.PENDING)['id']
        self.assertEqual(self.rollback(ident)['status'],'ROLLED_BACK')
        self.assertEqual(self.target.read_text(),FRAGMENT)



if __name__=='__main__':unittest.main()
