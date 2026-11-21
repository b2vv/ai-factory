"""Isolated routing and legacy/global overlap tests; no live archive or native host."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import claude_capture_dispatcher as d
import capture_bridge as bridge
from capture_queue import Queue


class Dispatcher(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name).resolve()
        self.private=self.base/'private';self.private.mkdir(mode=0o700);self.rows=[]
        for i,n in enumerate(['project-c','project-b','project-d','project-a'],1):
            p=self.base/n;p.mkdir();subprocess.run(['/usr/bin/git','init','-q',str(p)],check=True)
            cred=self.private/(n+'.json');cred.write_text(json.dumps({'principal_id':'agent-'+n,'epoch':1,'secret':'fixture-secret'}));cred.chmod(0o600)
            self.rows.append({'root':str(p),'project':f'00000000-0000-4000-8000-{i:012d}','source_instance':'claude-'+n,'credential_file':str(cred),'queue_dir':str(self.private/'capture-queue'),'status_file':str(self.private/(n+'.log'))})
        self.mapping=self.private/'mapping.json';self.mapping.write_text(json.dumps({'schema':1,'projects':self.rows}));self.mapping.chmod(0o600)
        self.transcript=self.private/'transcript.jsonl'
        records=[{'type':'user','uuid':'u1','sessionId':'session','parentUuid':'','message':{'role':'user','content':'fixture prompt'}},{'type':'assistant','uuid':'a1','sessionId':'session','parentUuid':'u1','message':{'role':'assistant','content':'fixture answer'}}]
        self.transcript.write_text('\n'.join(json.dumps(r) for r in records)+'\n');self.transcript.chmod(0o600)

    def event(self,row=None):
        return json.dumps({'hook_event_name':'Stop','cwd':(row or self.rows[0])['root'],'session_id':'session','transcript_path':str(self.transcript)}).encode()

    def env(self,row):
        return {'AF_CAPTURE_ENDPOINT':'http://127.0.0.1:8780','AF_CAPTURE_PROJECT':row['project'],'AF_CAPTURE_SOURCE':row['source_instance'],'AF_CAPTURE_AGENT_CREDENTIAL_FILE':row['credential_file'],'AF_CAPTURE_QUEUE_DIR':row['queue_dir'],'AF_CAPTURE_STATUS_FILE':row['status_file']}

    def test_four_scopes_scrub_inherited_environment(self):
        for row in self.rows:
            with patch.dict(os.environ,{'AF_CAPTURE_OPERATOR_SECRET_FILE':'never','AF_CAPTURE_PROJECT':'wrong'}), patch.object(d.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run:
                self.assertEqual(d.dispatch(self.event(row),str(self.mapping))['status'],'bridge_returned')
                env=run.call_args.kwargs['env'];self.assertNotIn('AF_CAPTURE_OPERATOR_SECRET_FILE',env)
                for k,v in self.env(row).items():self.assertEqual(env[k],v)
                self.assertEqual(run.call_args.kwargs['input'],self.event(row))

    def test_unknown_and_nested_repository_no_bridge_or_credential_open(self):
        nested=Path(self.rows[0]['root'])/'nested';nested.mkdir();subprocess.run(['/usr/bin/git','init','-q',str(nested)],check=True)
        unknown=self.base/'unknown';unknown.mkdir();subprocess.run(['/usr/bin/git','init','-q',str(unknown)],check=True)
        real=d.private_file
        def guard(path,*a,**kw):
            self.assertEqual(str(path),str(self.mapping),'unknown opened credentials');return real(path,*a,**kw)
        for root in [nested,unknown]:
            with patch.object(d,'private_file',side_effect=guard),patch.object(d.subprocess,'run') as run:
                self.assertEqual(d.dispatch(self.event({'root':str(root)}),str(self.mapping)),{'status':'unenrolled'});run.assert_not_called()

    def test_subdirectory_same_repo_allowed(self):
        sub=Path(self.rows[0]['root'])/'folder';sub.mkdir()
        self.assertEqual(d.select_route(d.load_mapping(str(self.mapping)),str(sub)),self.rows[0])

    def test_symlink_cwd_mapping_and_nonprivate_refused(self):
        link=self.base/'alias';link.symlink_to(self.rows[0]['root'])
        with self.assertRaises(ValueError):d.select_route(self.rows,str(link))
        ml=self.private/'maplink';ml.symlink_to(self.mapping)
        with self.assertRaises(ValueError):d.load_mapping(str(ml))
        self.mapping.chmod(0o644)
        with self.assertRaises(ValueError):d.load_mapping(str(self.mapping))

    def test_duplicate_enrollment_and_duplicate_json_keys_refused(self):
        rows=self.rows+[self.rows[0]]
        with self.assertRaises(ValueError):d.validate_mapping({'schema':1,'projects':rows})
        with self.assertRaises(ValueError):d.strict_json('{"schema":1,"schema":1,"projects":[]}')

    def test_parent_fsmonitor_command_is_not_invoked(self):
        marker=self.base/'bad';p=Path(self.rows[0]['root'])
        subprocess.run(['/usr/bin/git','-C',str(p),'config','core.fsmonitor','!touch '+str(marker)],check=True)
        self.assertEqual(d.git_root(str(p)),p);self.assertFalse(marker.exists())

    def test_legacy_global_same_event_one_queue_receipt_offline_restart(self):
        row=self.rows[0];raw=self.event(row);scope={'endpoint':'http://127.0.0.1:8780','project':row['project'],'source':row['source_instance'],'principal':'agent:agent-project-c'}
        posts=[]
        def fail(*args,**kwargs):posts.append(args[4]);return {'delivered':False,'error':'fixture offline'}
        with patch.dict(os.environ,self.env(row),clear=True),patch.object(sys,'stdin',io.StringIO(raw.decode())),patch.object(bridge,'post_body',side_effect=fail):
            first=bridge.run();self.assertTrue(first['queued'])
        def selected_bridge(*args,**kwargs):
            with patch.dict(os.environ,kwargs['env'],clear=True),patch.object(sys,'stdin',io.StringIO(kwargs['input'].decode())),patch.object(bridge,'post_body',side_effect=fail):bridge.run()
            return subprocess.CompletedProcess([],0)
        with patch.object(d.subprocess,'run',side_effect=selected_bridge):d.dispatch(raw,str(self.mapping))
        q=Queue(row['queue_dir'],scope);self.assertEqual(q.status()['pending'],1);self.assertEqual(len(posts),1)
        q.db.execute('UPDATE items SET next=0');q.db.commit();q.close()
        def ack(*args,**kwargs):posts.append(args[4]);return {'delivered':True}
        with patch.dict(os.environ,self.env(row),clear=True),patch.object(bridge,'post_body',side_effect=ack):bridge.run('flush')
        with patch.object(d.subprocess,'run',side_effect=selected_bridge):d.dispatch(raw,str(self.mapping))
        q=Queue(row['queue_dir'],scope);self.assertEqual(q.status()['receipts'],1);self.assertEqual(q.status()['pending'],0);q.close()
        self.assertEqual(len(posts),2);self.assertEqual(posts[0],posts[1]);self.assertEqual(os.stat(row['status_file']).st_mode&0o777,0o600)

    def test_non_stop_does_not_load_mapping(self):
        with patch.object(d,'load_mapping') as load:self.assertEqual(d.dispatch(b'{"hook_event_name":"PreToolUse"}','bad'),{'status':'ignored_event'});load.assert_not_called()

    def test_private_status_644_refused(self):
        p=Path(self.rows[0]['status_file']);p.write_text('');p.chmod(0o644)
        with self.assertRaises(ValueError):d.load_mapping(str(self.mapping))


if __name__=='__main__':unittest.main()
