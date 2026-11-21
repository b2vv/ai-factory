#!/usr/bin/env python3
import os,sys,json,subprocess
from pathlib import Path
p=Path(os.environ['FAKE_STATE']);a=sys.argv[1:];op=a[0]
with open(str(p)+'.calls','a') as f:f.write(op+'\n')
if op=='create':
 p.write_text(json.dumps(a));print('c'*64)
elif op=='ps':
 if not p.exists():sys.exit(0)
 c=json.loads(p.read_text());owner=next(x.split('=',1)[1] for x in c if x.startswith('ai-factory.invocation='));print('c'*64+'|'+owner+'|'+owner)
elif op=='inspect':
 if 'ai-factory.invocation' in a[2]:
  c=json.loads(p.read_text());print('c'*64+'|/'+a[-1]+'|'+next(x.split('=',1)[1] for x in c if x.startswith('ai-factory.invocation=')))
 elif '.State.ExitCode' in a[2]:print('exited|0|false|false')
 else:
  c=json.loads(p.read_text());image=c[c.index('--entrypoint')+2];uid=c[c.index('--user')+1]
  print('created|'+image+'|'+uid+'|none|true|false|2000000000|2147483648|2147483648|128|["ALL"]|["no-new-privileges"]|rw,noexec,nosuid,nodev,size=16777216|python3|'+('1' if os.environ.get('BAD_POLICY') else '0')+'|0|0|0|0||private|none')
elif op=='start':
 if os.environ.get('BAD_OUTPUT'):print('not-a-key');sys.exit(0)
 c=json.loads(p.read_text());i=c.index('-c');r=subprocess.run([sys.executable,'-c',c[i+1],c[i+2]],input=sys.stdin.buffer.read(),capture_output=True);sys.stdout.buffer.write(r.stdout);sys.exit(r.returncode)
elif op=='rm':
 if os.environ.get('BAD_CLEANUP'):sys.exit(1)
 p.unlink(missing_ok=True);print('c'*64)
else:sys.exit(2)
