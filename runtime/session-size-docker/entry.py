"""Container-only bounded adapter; exact authorized mounts are supplied by dispatcher."""
import argparse,json,os,sys,time
from pathlib import Path
import guard

def checked_path(value):
    if not isinstance(value,str) or not value.startswith('/') or any(ord(c)<32 for c in value):raise ValueError('invalid absolute input path')
    p=guard.safe_path(value)
    if str(p)!=str(p.resolve()):raise ValueError('noncanonical input path')
    return p

def execute(args,raw):
    if len(raw)>8_000_000:raise ValueError('hook payload too large; checkpoint manually')
    payload=json.loads(raw)
    if not isinstance(payload,dict):raise ValueError('invalid payload shape')
    root=checked_path(args.root);store=checked_path(args.store)
    if not root.is_dir():raise ValueError('required root mount unavailable')
    if root==store or root in store.parents or store in root.parents:raise ValueError('root/store overlap')
    if getattr(args,'store_leaf',None):
        if args.store_leaf!='state':raise ValueError('invalid store leaf')
        store=checked_path(str(store/'state'))
        if not store.is_dir():raise ValueError('private state leaf missing')
    if args.mode=='hook':
        if payload.get('hook_event_name') not in ('SessionStart','UserPromptSubmit','PostToolUse','Stop'):raise ValueError('invalid event')
        cwd=checked_path(payload.get('cwd'))
        if cwd!=root and root not in cwd.parents:raise ValueError('cwd outside declared root')
        if not cwd.is_dir():raise ValueError('required cwd unavailable')
        transcript=payload.get('transcript_path')
        if transcript:
            if not args.transcript or checked_path(transcript)!=checked_path(args.transcript):raise ValueError('transcript not explicitly mounted')
            if not Path(transcript).is_file():raise ValueError('required transcript mount unavailable')
        sid=payload.get('session_id')
        if args.session and sid!=args.session:raise ValueError('session disagrees with trusted mapping')
    else:
        cwd=root;sid=args.session
    with guard.mapped_git_root(root):
        if guard.git(cwd,'rev-parse','--show-toplevel').decode().strip()!=str(root):raise ValueError('actual root disagrees with host mapping')
        guard.identity(args.host,sid,str(cwd))
        if args.mode=='hook':
            # Explicit handoff must not lose LockBusy through optional event handling.
            return (guard.event_locked if args.pointer else guard.event)(store,args.host,payload,args.pointer)
        if args.mode=='checkpoint':
            if len(raw)>16000:raise ValueError('summary too large')
            return {'checkpoint_id':guard.checkpoint(store,args.host,sid,str(cwd),payload)}
        return {'context':guard.resume(store,args.pointer,args.host,sid,str(cwd))}

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['hook','checkpoint','resume']);p.add_argument('--root',required=True);p.add_argument('--store',required=True);p.add_argument('--host',choices=['codex','claude'],required=True);p.add_argument('--session');p.add_argument('--pointer');p.add_argument('--transcript');p.add_argument('--input',required=True);p.add_argument('--store-leaf',choices=['state'])
    a=p.parse_args()
    try:
        with open(a.input,'rb') as f:raw=f.read(8_000_001)
        result=execute(a,raw)
        print(json.dumps(result if a.mode=='hook' else {'status':'OK','result':result},ensure_ascii=True));return 0
    except (OSError,ValueError,TypeError,KeyError,guard.subprocess.SubprocessError,guard.LockBusy) as exc:
        # No raw payload/path/exception echo. UNKNOWN is not handoff success.
        required=a.mode!='hook' or bool(a.pointer)
        diagnostic=guard.handoff_diagnostic(exc)
        print(json.dumps({'systemMessage':diagnostic} if a.mode=='hook' else {'status':'BLOCKED','diagnostic':diagnostic},ensure_ascii=True));return 2 if required else 0
if __name__=='__main__':sys.exit(main())
