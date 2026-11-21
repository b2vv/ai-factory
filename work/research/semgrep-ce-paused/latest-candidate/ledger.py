"""Data inventory only; retained-cache bytes are NOT total download traffic."""
import os,stat,hashlib,json,sys,importlib.metadata as md
from pathlib import Path
phase=sys.argv[1]; total=0;count=0;limit=2*1024**3
out=Path('/work/evidence/cache-ledger.jsonl')
with out.open('x') as f:
 for root,dirs,names in os.walk('/capture',followlinks=False):
  dirs.sort();names.sort()
  for n in dirs+names:
   p=Path(root)/n;s=p.lstat()
   if stat.S_ISLNK(s.st_mode):
    f.write(json.dumps({'path':str(p),'type':'symlink','followed':False})+'\n');continue
   if not stat.S_ISREG(s.st_mode):continue
   count+=1
   if count>200000:raise RuntimeError('ledger member cap')
   total+=s.st_size
   if total>limit:raise RuntimeError('2GiB retained-cache target exceeded')
   digest=hashlib.sha256()
   fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
   with os.fdopen(fd,'rb') as inp:
    before=os.fstat(inp.fileno())
    if not stat.S_ISREG(before.st_mode) or (before.st_dev,before.st_ino,before.st_size)!=(s.st_dev,s.st_ino,s.st_size):raise RuntimeError('cache raced')
    for chunk in iter(lambda:inp.read(65536),b''):digest.update(chunk)
    after=os.fstat(inp.fileno())
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError('cache changed')
   f.write(json.dumps({'path':str(p),'bytes':s.st_size,'sha256':digest.hexdigest()})+'\n')
   if f.tell()>8*1024**2:raise RuntimeError('ledger output cap')
Path('/work/evidence/cache-summary.json').write_text(json.dumps({'phase':phase,'retained_regular_bytes':total,'files':count,'full_acquisition_coverage':False,'wire_bytes':None,'transient_fetches_and_hooks':'NOT_MEASURED'})+'\n')
notices=[]
for d in md.distributions():
 notices.append({'name':d.metadata.get('Name'),'version':d.version,'license':d.metadata.get('License'),'license_expression':d.metadata.get('License-Expression'),'license_paths':[str(p) for p in (d.files or []) if 'license' in str(p).lower() or 'notice' in str(p).lower()]})
raw=json.dumps(notices).encode();assert len(raw)<=1024**2
Path('/work/evidence/python-license-metadata.json').write_bytes(raw+b'\n')
