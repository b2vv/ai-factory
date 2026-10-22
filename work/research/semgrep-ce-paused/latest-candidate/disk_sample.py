"""One bounded ENOENT-only resample. Partial measurements are never accepted."""
import re,subprocess,time
PREFIX='/work/opam/5.4.0/.opam-switch/build/ocaml-compiler.5.4.0/'
def rows(raw):
 text=raw.decode('ascii',errors='strict')
 match=re.fullmatch(r'(0|[1-9][0-9]*)\t/work\n(0|[1-9][0-9]*)\t/capture\n',text)
 if not match:raise ValueError('invalid disk roots/totals')
 values=[int(x) for x in match.groups()]
 if values[1]*1024>2*1024**3 or sum(values)*1024+128*1024**2>=25*1024**3:raise ValueError('disk partial/clean threshold')
 return values
def enoent(raw):
 text=raw.decode('ascii',errors='strict')
 lines=text.splitlines(keepends=True)
 if not lines:return False
 for line in lines:
  m=re.fullmatch(r"du: cannot access '([A-Za-z0-9_./+-]+)': No such file or directory\n",line)
  if not m or not m[1].startswith(PREFIX):return False
  relative=m[1][len(PREFIX):]
  if not relative or any(x in ('','.','..') for x in relative.split('/')):return False
 return True
def sample(run,record,reserve,remaining,clock=time.perf_counter):
 deadline=clock()+min(3.0,remaining)
 receipts=[]
 for attempt in (1,2):
  reserve();left=deadline-clock()
  if left<=0:raise TimeoutError('disk sample shared deadline')
  try:
   result=run(left);out=result.stdout;err=result.stderr;code=result.returncode;truncated=False
  except subprocess.CalledProcessError as exc:
   out=exc.stdout;err=exc.stderr;code=exc.returncode
   truncated=any(getattr(exc,'truncated',[True,True]))
  except BaseException as exc:
   record({'attempts':receipts,'failed_attempt':attempt,'failure_type':type(exc).__name__,'timeout':getattr(exc,'timeout',None),'stdout':repr(getattr(exc,'stdout',None))[:2048],'stderr':repr(getattr(exc,'stderr',None))[:8192],'decision':'BLOCKED'})
   raise
  receipt={'attempt':attempt,'returncode':code,'stdout':out.decode('ascii',errors='backslashreplace')[:2048],'stderr':err.decode('ascii',errors='backslashreplace')[:8192],'truncated':truncated or len(out)>2048 or len(err)>8192}
  receipts.append(receipt)
  try:
   if receipt['truncated']:raise ValueError('incomplete disk streams')
   values=rows(out)
   if clock()>deadline:raise TimeoutError('disk sample shared deadline')
   if code==0 and err==b'':
    if len(receipts)>1:record({'attempts':receipts,'decision':'CLEAN_RESAMPLE'})
    return values
   if attempt!=1 or code!=1 or not enoent(err):raise ValueError('nonrecoverable disk diagnostics')
   record({'attempts':receipts,'decision':'ONE_RESAMPLE_ALLOWED'})
  except BaseException:
   record({'attempts':receipts,'decision':'BLOCKED'});raise
 raise AssertionError('unreachable')
