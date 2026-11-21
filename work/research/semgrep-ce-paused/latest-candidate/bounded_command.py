"""Bounded subprocess diagnostics; no Docker policy or lifecycle decisions."""
import os,select,subprocess,time,threading
class OutputLimit(RuntimeError):pass
def run(argv,*,capture_output=True,text=True,timeout=5,check=True):
 p=None;out=bytearray();err=bytearray();counts=[0,0];start=time.monotonic()
 try:
  p=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  streams=[p.stdout,p.stderr]
  while streams:
   remaining=timeout-(time.monotonic()-start)
   if remaining<=0:raise subprocess.TimeoutExpired(argv,timeout)
   ready,_,_=select.select(streams,[],[],min(remaining,1))
   for stream in ready:
    data=os.read(stream.fileno(),65536)
    if not data:streams.remove(stream);continue
    index=0 if stream is p.stdout else 1;target=out if index==0 else err;cap=1048576 if index==0 else 8192
    counts[index]+=len(data);target.extend(data[:max(0,cap-len(target))])
    if counts[index]>cap:raise OutputLimit('control '+('stdout' if index==0 else 'stderr')+' cap')
  code=p.wait(timeout=max(.1,timeout-(time.monotonic()-start)))
  if check and code:raise subprocess.CalledProcessError(code,argv)
  return subprocess.CompletedProcess(argv,code,out.decode(errors='replace') if text else bytes(out),err.decode(errors='replace') if text else bytes(err))
 except BaseException as exc:
  if p is not None:
   try:
    if p.poll() is None:p.kill()
    p.wait(timeout=3)
   except BaseException:pass
  exc.stdout=bytes(out);exc.stderr=bytes(err);exc.observed_bytes=counts;exc.truncated=[counts[0]>len(out),counts[1]>len(err)]
  raise
 finally:
  if p is not None:
   for stream in [p.stdout,p.stderr]:stream.close()
class Drain:
 """Drain verbose attach streams, retain bounded tails without blocking child."""
 def __init__(self,p):
  self.items=[];self.threads=[]
  for name,cap in [('stdout',2048),('stderr',8192)]:
   stream=getattr(p,name,None);item={'stream':name,'observed_bytes':0,'tail':b'','available':stream is not None};self.items.append(item)
   if stream is not None:
    def worker(stream=stream,item=item,cap=cap):
     try:
      while True:
       data=os.read(stream.fileno(),65536)
       if not data:break
       item['observed_bytes']+=len(data);item['tail']=(item['tail']+data)[-cap:]
     except Exception as e:item['read_error']=type(e).__name__
    t=threading.Thread(target=worker,daemon=True);t.start();self.threads.append(t)
 def snapshot(self):
  for t in self.threads:t.join(timeout=1)
  return [{'stream':x['stream'],'available':x['available'],'observed_bytes':x['observed_bytes'],'tail':x['tail'].decode(errors='replace'),'truncated':x['observed_bytes']>len(x['tail']),'read_error':x.get('read_error')} for x in self.items]
