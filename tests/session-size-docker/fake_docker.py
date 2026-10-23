#!/usr/bin/env python3
import sys,os,json,time
from pathlib import Path
a=sys.argv[1:];mode=os.environ.get('FAULT','');state=Path(os.environ['FAKE_STATE']);log=state.with_suffix('.log')
with log.open('a') as f:f.write(a[0]+'\n')
if a[0]=='create':
 if mode=='createfail':sys.exit(1)
 mounts=[a[i+1] for i,x in enumerate(a) if x=='--mount'];env=[a[i+1] for i,x in enumerate(a) if x=='--env'];user=a[a.index('--user')+1];image=a[a.index('--entrypoint')+2]
 state.write_text(json.dumps({'mounts':mounts,'env':env,'user':user,'image':image,'validator':'/code/validate.py' in a,'args':a}));print('fixturecid')
elif a[0]=='inspect':
 s=json.loads(state.read_text());fmt=a[a.index('--format')+1] if '--format' in a else ''
 if 'NanoCpus' in fmt:
  for k in ['CapAdd','Devices','DeviceRequests','PortBindings']:
   if '{{len .HostConfig.'+k+'}}' in fmt and '{{if .HostConfig.'+k+'}}' not in fmt:
    print('error calling len: len of nil pointer',file=sys.stderr);sys.exit(1)
  print('created|'+s['image']+'|'+s['user']+'|none|true|'+('true' if mode=='badpolicy' else 'false')+'|2000000000|2147483648|2147483648|128|["ALL"]|["no-new-privileges"]|rw,noexec,nosuid,size=268435456|python3|0|0|0|0||private')
 elif 'range .Mounts' in fmt:
  for m in s['mounts']:
   d=dict(x.split('=',1) for x in m.split(',') if '=' in x);print('bind|'+d['src']+'|'+d['dst']+'|'+('false' if 'readonly' in m else 'true'))
 elif 'range .Config.Env' in fmt:
  for v in s['env']+['PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','SEMGREP_IN_DOCKER=1','SEMGREP_USER_AGENT_APPEND=Docker','PYTHONIOENCODING=utf8','PYTHONUNBUFFERED=1']:print(v)
 elif 'ExitCode' in fmt:print('exited|0|'+('true' if mode=='oom' else 'false')+'|false')
 else:print('[{}]')
elif a[0]=='start':
 if mode=='hang':time.sleep(30)
 if mode=='startfail':sys.exit(2)
 s=json.loads(state.read_text())
 if s['validator']:
  import subprocess
  mounts=[dict(x.split('=',1) for x in m.split(',') if '=' in x) for m in s['mounts']]
  code=next(m['src'] for m in mounts if m['dst']=='/code');result=next(m['src'] for m in mounts if m['dst']=='/result.json')
  sys.exit(subprocess.call([sys.executable,code+'/validate.py','--mode',s['args'][s['args'].index('--mode')+1],'--input',result]))
 if mode=='malformed':print('not-json')
 elif mode=='empty':pass
 elif mode=='wrongshape':print('[]')
 elif mode=='oversize':print('x'*65537)
 else:print(json.dumps({'status':'OK','result':{'checkpoint_id':'a'*32+'-1-'+'b'*12}}))
elif a[0]=='rm':
 if mode=='cleanupfail':sys.exit(1)
 print('fixturecid')
else:sys.exit(2)
