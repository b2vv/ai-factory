"""Actual subprocess/loopback transport checks; synthetic credentials only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BRIDGE = Path(__file__).with_name('capture_bridge.py')

class CaptureAuthentication(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.requests = []
        requests = self.requests
        self.response_status = 200
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length']))
                requests.append((self.path, dict(self.headers), body))
                self.send_response(fixture.response_status)
                self.end_headers()
                self.wfile.write(b'{"accepted":2,"committed":2}')
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.transcript = self.root / 'transcript.jsonl'
        records = [
            {'type':'user','uuid':'U1','sessionId':'S','message':{'role':'user','content':'fixture prompt'}},
            {'type':'assistant','uuid':'A1','parentUuid':'U1','sessionId':'S','message':{'role':'assistant','content':[{'type':'text','text':'fixture answer'}]}},
        ]
        self.transcript.write_text('\n'.join(json.dumps(r) for r in records)+'\n')
        self.agent = self.root / 'agent.json'
        self.agent.write_text(json.dumps({'principal_id':'fixture-writer','epoch':7,'secret':'fixture-agent-canary'}))
        self.operator = self.root / 'operator.json'
        self.operator.write_text(json.dumps({'id':'operator','secret':'fixture-operator-canary'}))

    def run_bridge(self, agent=True, operator=False, project="fixture-project"):
        env = {k:v for k,v in os.environ.items() if not k.startswith('AF_CAPTURE_')}
        env.update(AF_CAPTURE_ENDPOINT=f'http://127.0.0.1:{self.server.server_port}', AF_CAPTURE_PROJECT=project, AF_CAPTURE_SOURCE='fixture-source', AF_CAPTURE_READ_ATTEMPTS='1')
        if agent:
            env['AF_CAPTURE_AGENT_CREDENTIAL_FILE'] = str(self.agent)
        if operator:
            env['AF_CAPTURE_OPERATOR_SECRET_FILE'] = str(self.operator)
        result = subprocess.run([sys.executable, '-I', str(BRIDGE)], input=json.dumps({'hook_event_name':'Stop','session_id':'S','transcript_path':str(self.transcript)}), text=True, capture_output=True, env=env, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn('fixture-agent-canary', result.stdout+result.stderr)
        self.assertNotIn('fixture-operator-canary', result.stdout+result.stderr)
        return result

    def test_agent_uses_only_scoped_headers(self):
        self.run_bridge()
        self.assertEqual(len(self.requests), 1)
        path, headers, body = self.requests[0]
        headers = {k.lower():v for k,v in headers.items()}
        self.assertEqual(path, '/v1/capture/claude-code?project=fixture-project&source_instance=fixture-source')
        self.assertEqual(headers.get('x-principal-id'), 'fixture-writer')
        self.assertEqual(headers.get('x-grant-epoch'), '7')
        self.assertEqual(headers.get('x-secret'), 'fixture-agent-canary')
        self.assertNotIn('x-operator-secret', headers)
        self.assertEqual(len(body.splitlines()), 2)

    def test_operator_compatibility(self):
        self.run_bridge(agent=False, operator=True)
        self.assertEqual(len(self.requests), 1)
        headers = {k.lower():v for k,v in self.requests[0][1].items()}
        self.assertEqual(headers.get('x-operator-secret'), 'fixture-operator-canary')
        self.assertNotIn('x-secret', headers)

    def test_conflicting_modes_never_fall_back(self):
        self.run_bridge(agent=True, operator=True)
        self.assertEqual(self.requests, [])

    def test_invalid_agent_credentials_never_send(self):
        good = {'principal_id':'fixture-writer','epoch':7,'secret':'fixture-agent-canary'}
        invalid = [None, [], {}, {**good, 'epoch':0}, {**good, 'epoch':-1},
                   {**good, 'epoch':True}, {**good, 'epoch':1.5}, {**good, 'epoch':'7'},
                   {**good, 'principal_id':''}, {**good, 'principal_id':'  '},
                   {**good, 'principal_id':12}, {**good, 'secret':''},
                   {**good, 'secret':'  '}, {**good, 'secret':12}]
        for credential in invalid:
            with self.subTest(credential=credential):
                self.requests.clear()
                self.agent.write_text(json.dumps(credential))
                self.run_bridge()
                self.assertEqual(self.requests, [])

    def test_unreadable_agent_does_not_use_operator(self):
        self.agent.unlink()
        self.run_bridge()
        self.assertEqual(self.requests, [])

    def test_malformed_json_never_sends(self):
        self.agent.write_text('{"secret":"fixture-agent-canary",')
        self.run_bridge()
        self.assertEqual(self.requests, [])

    def test_http_denial_does_not_retry_or_fall_back(self):
        self.response_status = 403
        result = self.run_bridge()
        self.assertEqual(len(self.requests), 1)
        self.assertIn('"http_status": 403', result.stderr)
        self.assertIn('"delivered": false', result.stderr)
        self.assertNotIn('x-operator-secret', {k.lower() for k in self.requests[0][1]})

    def test_missing_project_or_credential_never_sends(self):
        self.run_bridge(project='')
        self.run_bridge(agent=False, operator=False)
        self.assertEqual(self.requests, [])

if __name__ == '__main__':
    unittest.main()
