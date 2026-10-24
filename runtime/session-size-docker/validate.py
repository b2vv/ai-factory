"""Independent container-side bounded result validator; no host JSON runtime."""
import argparse,json,re,sys
from pathlib import Path
LIMIT=16384

def validate(mode,value):
 if not isinstance(value,dict):raise ValueError('object required')
 if mode=='hook':
  if value=={}:return
  if set(value)=={'systemMessage'} and isinstance(value['systemMessage'],str) and len(value['systemMessage'])<=LIMIT:return
  if set(value)=={'hookSpecificOutput'}:
   v=value['hookSpecificOutput']
   if isinstance(v,dict) and set(v)=={'hookEventName','additionalContext'} and v['hookEventName'] in ('SessionStart','UserPromptSubmit','PostToolUse') and isinstance(v['additionalContext'],str) and len(v['additionalContext'])<=LIMIT:return
  raise ValueError('hook schema')
 if set(value)!={'status','result'} or value['status']!='OK' or not isinstance(value['result'],dict):raise ValueError('result schema')
 r=value['result']
 if mode=='checkpoint':
  if set(r)!={'checkpoint_id'} or not isinstance(r['checkpoint_id'],str) or not re.fullmatch(r'[a-f0-9]{32}-[1-9][0-9]*-[a-f0-9]{12}',r['checkpoint_id']):raise ValueError('checkpoint id')
 elif mode=='resume':
  if set(r)!={'context'} or not isinstance(r['context'],str) or len(r['context'])>LIMIT:raise ValueError('resume context')
 else:raise ValueError('mode')

def pairs(items):
 out={}
 for k,v in items:
  if k in out:raise ValueError('duplicate key')
  out[k]=v
 return out

def main():
 p=argparse.ArgumentParser();p.add_argument('--mode',choices=['hook','checkpoint','resume'],required=True);p.add_argument('--input',required=True);a=p.parse_args()
 try:
  with open(a.input,'rb') as f:raw=f.read(65537)
  if len(raw)>65536:raise ValueError('oversize result')
  validate(a.mode,json.loads(raw,object_pairs_hook=pairs));print('VALID');return 0
 except (OSError,ValueError,TypeError,KeyError):print('INVALID',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
