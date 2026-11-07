import importlib.util, json, unittest, tempfile, os, subprocess, sys
from pathlib import Path
from unittest.mock import patch
s=importlib.util.spec_from_file_location("catcher",Path(__file__).with_name("codex_capture_catcher.py")); c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
class Security(unittest.TestCase):
 def test_endpoint_is_pinned_before_network(self):
  for endpoint in ["https://evil.example", "http://localhost:8780", "http://127.0.0.1:9999", "http://127.0.0.1:8780@evil.example", "http://127.0.0.1:8780/path"]:
   with self.subTest(endpoint=endpoint):
    calls=[]
    def opener(*a,**k): calls.append(a); raise ValueError()
    c.post_event(endpoint,"p","s",{}, {},opener=opener)
    self.assertEqual(calls,[])
 def test_status_does_not_reflect_event_or_identifiers(self):
  canary="PRIVATE_CANARY"
  for event in [{"hook_event_name":canary},{"hook_event_name":"Stop","session_id":canary,"turn_id":canary,"last_assistant_message":canary}]:
   self.assertNotIn(canary,json.dumps(c.run(json.dumps(event),{})))
 def test_continued_stop_is_delivered_with_v2_shape(self):
  for active in [False,True]:
   role,body=c.normalize_event({"hook_event_name":"Stop","session_id":"s","turn_id":"t","last_assistant_message":"visible","stop_hook_active":active})
   self.assertEqual(role,"assistant");self.assertEqual(body,{"schema_version":2,"hook_event_name":"Stop","session_id":"s","turn_id":"t","last_assistant_message":"visible","stop_hook_active":active})
 def test_stop_flag_is_strict(self):
  for flag in [None,0,1,"false",[],{}]:
   self.assertIsNone(c.normalize_event({"hook_event_name":"Stop","session_id":"s","turn_id":"t","last_assistant_message":"visible","stop_hook_active":flag})[1])
 def test_old_server_and_missing_ack_never_claim_v2_delivery(self):
  class Response:
   def __init__(self,ack):self.ack=ack
   def read(self,*a):return b'{"accepted":1,"committed":1,"redactions":[]}'
   def getcode(self):return 200
   def getheader(self,name):return self.ack
  for ack in [None,"1","PRIVATE_CANARY","2"]:
   calls=[]
   def opener(req,**kwargs):calls.append(req.full_url);return Response(ack)
   status=c.post_event(c.ENDPOINT,"p","s",{}, {},opener=opener)
   self.assertEqual(status.get("delivered",False),ack=="2")
   self.assertEqual(calls,[c.ENDPOINT+"/v1/capture/codex-event-v2?project=p&source_instance=s"])
   self.assertNotIn("PRIVATE_CANARY",json.dumps(status))

 def test_go_nil_redactions_means_zero_redactions(self):
  class Response:
   def read(self,*a):return b'{"accepted":1,"committed":1,"redactions":null}'
   def getcode(self):return 200
   def getheader(self,name):return "2"
  status=c.post_event(c.ENDPOINT,"p","s",{},{},opener=lambda *a,**k:Response())
  self.assertTrue(status.get("delivered",False));self.assertEqual(status["redactions"],0)
 def test_missing_redactions_is_not_an_empty_go_slice(self):
  class Response:
   def read(self,*a):return b'{"accepted":1,"committed":1}'
   def getcode(self):return 200
   def getheader(self,name):return "2"
  self.assertFalse(c.post_event(c.ENDPOINT,"p","s",{},{},opener=lambda *a,**k:Response()).get("delivered",False))
 def test_old_server_404_does_not_fallback(self):
  calls=[]
  def opener(req,**kwargs):
   calls.append(req.full_url)
   raise c.urllib.error.HTTPError(req.full_url,404,"not found",{},None)
  status=c.post_event(c.ENDPOINT,"p","s",{},{},opener=opener)
  self.assertFalse(status.get("delivered",False));self.assertEqual(status["http_status"],404)
  self.assertEqual(len(calls),1);self.assertIn("/codex-event-v2?",calls[0])
 def test_untrusted_response_counts_are_not_logged(self):
  class Response:
   def read(self,*a):return b'{"accepted":"PRIVATE_CANARY","committed":{"secret":"PRIVATE_CANARY"},"redactions":[]}'
   def getcode(self):return 200
   def getheader(self,name):return "2"
  status=c.post_event("http://127.0.0.1:8780","p","s",{}, {},opener=lambda *a,**k:Response())
  self.assertNotIn("PRIVATE_CANARY",json.dumps(status))
 def test_transport_disables_proxies_and_redirects(self):
  with patch.object(c.urllib.request,"build_opener") as build:
   c.post_event("http://127.0.0.1:8780","p","s",{}, {})
   handlers=build.call_args.args
   self.assertTrue(any(isinstance(h,c.urllib.request.ProxyHandler) and h.proxies=={} for h in handlers))
   self.assertTrue(any(isinstance(h,c.urllib.request.HTTPRedirectHandler) and type(h) is not c.urllib.request.HTTPRedirectHandler for h in handlers))
 def test_newline_identifier_is_refused(self):
  for field in ['session_id','turn_id']:
   ev={'hook_event_name':'Stop','session_id':'s','turn_id':'t','last_assistant_message':'text'};ev[field]+='\n'
   self.assertIsNone(c.normalize_event(ev)[1])
 def test_mapping_rejects_ambiguous_or_relative_paths(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/"mapping.json"
   row={"root":tmp,"project":"p","source_instance":"s","credential_file":str(Path(tmp)/"credential")}
   for rows in [[row,dict(row,project="other")],[dict(row,root="relative")],[dict(row,credential_file="relative")],[dict(row,root=tmp+"/../"+Path(tmp).name)],[dict(row,root="/")]]:
    p.write_text(json.dumps(rows))
    with self.assertRaises(ValueError):c.load_mapping(p)
 def test_success_counts_and_redactions_are_typed_and_bounded(self):
  class Response:
   def __init__(self,body):self.body=body
   def read(self,*a):return json.dumps(self.body).encode()
   def getcode(self):return 200
   def getheader(self,name):return "2"
  for field in ["accepted","committed"]:
   for value in [-1,1000001,True,1.5,"PRIVATE_CANARY"]:
    body={"accepted":1,"committed":1,"redactions":[]};body[field]=value
    with self.subTest(field=field,value=value):
     result=c.post_event(c.ENDPOINT,"p","s",{},{},opener=lambda *a,**k:Response(body))
     self.assertFalse(result.get("delivered",False));self.assertNotIn("PRIVATE_CANARY",json.dumps(result))
  body={"accepted":1,"committed":1,"redactions":{}}
  self.assertFalse(c.post_event(c.ENDPOINT,"p","s",{},{},opener=lambda *a,**k:Response(body)).get("delivered",False))
 def test_mapping_rejects_symlink_paths(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/"real").mkdir();(root/"alias").symlink_to(root/"real",target_is_directory=True)
   p=root/"map.json";p.write_text(json.dumps([{"root":str(root/"alias"),"project":"p","source_instance":"s","credential_file":str(root/"key")}]))
   with self.assertRaises(ValueError):c.load_mapping(p)
 def test_invalid_response_does_not_claim_delivery(self):
  class Response:
   def read(self,*a):return b'{"accepted":true,"committed":0,"redactions":[]}'
   def getcode(self):return 200
   def getheader(self,name):return "2"
  self.assertFalse(c.post_event(c.ENDPOINT,"p","s",{},{},opener=lambda *a,**k:Response()).get("delivered",False))
 def test_oversized_input_never_parses(self):
  with patch.object(c.json,"loads") as loads:
   status=c.run("x"*(1024*1024+1),{})
   loads.assert_not_called()
   self.assertFalse(status["delivered"])
 def test_mapping_fifo_is_refused_without_blocking(self):
  with tempfile.TemporaryDirectory() as tmp:
   fifo=Path(tmp).resolve()/"pipe";os.mkfifo(fifo)
   code="import sys;sys.path.insert(0,sys.argv[1]);import codex_capture_catcher as c;c.read_json_file(sys.argv[2],100)"
   try:
    result=subprocess.run([sys.executable,"-c",code,str(Path(c.__file__).parent),str(fifo)],capture_output=True,timeout=2)
   except subprocess.TimeoutExpired:self.fail("FIFO open blocked")
   self.assertNotEqual(result.returncode,0);self.assertIn(b"regular",result.stderr)
 def test_json_file_limit_and_hardlink(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp).resolve()/"json";p.write_bytes(b"{}"+b" "*99)
   with self.assertRaises(ValueError):c.read_json_file(p,100)
   p.write_text("{}");link=p.with_name("link");os.link(p,link)
   with self.assertRaisesRegex(ValueError,"regular"):c.read_json_file(p,100)
 def test_open_descriptor_rejects_raced_symlink(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();p=root/"file";p.write_text("{}");target=root/"target";target.write_text("{}")
   def race(value):p.unlink();p.symlink_to(target);return value
   with patch.object(c,"canonical_path",side_effect=race):
    with self.assertRaises(OSError):c.read_json_file(p,100)
 def test_response_read_is_bounded(self):
  class Response:
   def read(self,n):
    self.limit=n;body=b'{"accepted":1,"committed":1,"redactions":[]}';return body+b" "*(n-len(body))
   def getcode(self):return 200
   def getheader(self,name):return "2"
  response=Response()
  result=c.post_event(c.ENDPOINT,"p","s",{},{},opener=lambda *a,**k:response)
  self.assertEqual(response.limit,c.MAX_RESPONSE+1)
  self.assertFalse(result.get("delivered",False))
 def test_real_redirect_does_not_reach_second_listener(self):
  import threading
  from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
  seen=[]
  class Sink(BaseHTTPRequestHandler):
   def log_message(self,*a):pass
   def do_GET(self):seen.append(self.headers);self.send_response(200);self.end_headers()
   def do_POST(self):seen.append(self.headers);self.send_response(200);self.end_headers()
  sink=ThreadingHTTPServer(("127.0.0.1",0),Sink)
  redirect_status={"code":307}
  class Redirect(BaseHTTPRequestHandler):
   def log_message(self,*a):pass
   def do_POST(self):self.send_response(redirect_status["code"]);self.send_header("Location",f"http://127.0.0.1:{sink.server_port}/sink");self.end_headers()
  first=ThreadingHTTPServer(("127.0.0.1",0),Redirect)
  threads=[threading.Thread(target=x.serve_forever,daemon=True) for x in [first,sink]]
  for t in threads:t.start()
  try:
   # Temporary endpoint substitution only inside test; production remains pinned.
   for code in [301,302,303,307,308]:
    redirect_status["code"]=code
    with self.subTest(code=code),patch.object(c,"ENDPOINT",f"http://127.0.0.1:{first.server_port}"),patch.dict(os.environ,{"HTTP_PROXY":f"http://127.0.0.1:{sink.server_port}","NO_PROXY":""}):
     status=c.post_event(c.ENDPOINT,"p","s",{"X-Secret":"synthetic"},{"prompt":"synthetic"})
     self.assertEqual(status["http_status"],code);self.assertEqual(seen,[])
  finally:
   for x in [first,sink]:x.shutdown();x.server_close()
   for t in threads:t.join()

if __name__=="__main__":unittest.main()
