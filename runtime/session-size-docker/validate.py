"""Independent container-side bounded result validator; no host JSON runtime."""
import argparse,json,re,sys
from pathlib import Path
LIMIT=16384
CAND_MAX=8
TOKEN_RE=r'[a-f0-9]{32}-[1-9][0-9]*-[a-f0-9]{12}'

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
 elif mode in ('resume','resolve'):
  if set(r)!={'context'} or not isinstance(r['context'],str) or len(r['context'])>LIMIT:raise ValueError('resume context')
 elif mode=='candidates':
  # Read-only task-selection listing: a bounded page of completed checkpoints, no context/claim.
  if set(r)!={'candidates'} or not isinstance(r['candidates'],dict):raise ValueError('candidates envelope')
  cc=r['candidates']
  if set(cc)!={'total','returned','items'}:raise ValueError('candidates keys')
  if not isinstance(cc['total'],int) or isinstance(cc['total'],bool) or cc['total']<0:raise ValueError('candidates total')
  if not isinstance(cc['returned'],int) or isinstance(cc['returned'],bool):raise ValueError('candidates returned')
  if not isinstance(cc['items'],list) or len(cc['items'])>CAND_MAX:raise ValueError('candidates items')
  if cc['returned']!=len(cc['items']) or cc['returned']>cc['total']:raise ValueError('candidates counts')
  for c in cc['items']:
   if not isinstance(c,dict) or set(c)!={'id','created','snapshot_matches','status','goal'}:raise ValueError('candidate shape')
   if not isinstance(c['id'],str) or not re.fullmatch(TOKEN_RE,c['id']):raise ValueError('candidate id')
   if not isinstance(c['created'],(int,float)) or isinstance(c['created'],bool):raise ValueError('candidate created')
   if not isinstance(c['snapshot_matches'],bool):raise ValueError('candidate snapshot flag')
   if c['status'] not in ('resumable','snapshot_mismatch'):raise ValueError('candidate status')
   if (c['status']=='resumable')!=c['snapshot_matches']:raise ValueError('candidate status/flag disagree')
   if not isinstance(c['goal'],str) or len(c['goal'])>512:raise ValueError('candidate goal')
 else:raise ValueError('mode')

def pairs(items):
 out={}
 for k,v in items:
  if k in out:raise ValueError('duplicate key')
  out[k]=v
 return out

def main():
 p=argparse.ArgumentParser();p.add_argument('--mode',choices=['hook','checkpoint','resume','resolve','candidates'],required=True);p.add_argument('--input',required=True);a=p.parse_args()
 try:
  with open(a.input,'rb') as f:raw=f.read(65537)
  if len(raw)>65536:raise ValueError('oversize result')
  validate(a.mode,json.loads(raw,object_pairs_hook=pairs));print('VALID');return 0
 except (OSError,ValueError,TypeError,KeyError):print('INVALID',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
