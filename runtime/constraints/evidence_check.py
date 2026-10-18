"""Offline declared-evidence validator. No shell, network, Git or model execution.
PASS validates record structure/consistency only, never the truth of referenced artifacts.
"""
import argparse
import json
from pathlib import Path


def snapshot_valid(s):
    if not isinstance(s, dict): return False
    if not all(isinstance(s.get(k), str) and s[k].strip() for k in ('root','base','head')): return False
    scope=s.get('scope'); files=s.get('files')
    if not isinstance(scope,list) or not scope: return False
    if not all(isinstance(p,str) and p and not p.startswith('/') and '..' not in p.split('/') for p in scope): return False
    if len(scope)!=len(set(scope)): return False
    if not isinstance(files,dict) or set(files)!=set(scope): return False
    for item in files.values():
        if not isinstance(item,dict) or item.get('state') not in ('tracked','untracked','deleted'): return False
        digest=item.get('sha256')
        if item['state']=='deleted':
            if digest is not None: return False
        elif not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest): return False
    return True


def refs(value):
    return isinstance(value,list) and bool(value) and all(isinstance(v,str) and v.strip() for v in value)


def assess(record):
    blocked=[];failed=[];exceptions=[]
    if not isinstance(record,dict): return {'status':'BLOCKED','reasons':['record must be an object']}
    current=record.get('current')
    if not snapshot_valid(current): blocked.append('incomplete current snapshot')
    if not snapshot_valid(record.get('evidence_snapshot')) or current!=record.get('evidence_snapshot'): blocked.append('stale or incomplete evidence snapshot')
    task=record.get('task')
    if not isinstance(task,str) or not task or record.get('checkpoint_task')!=task: blocked.append('task checkpoint missing or belongs to another task')
    if record.get('resumed') is True and record.get('resume_reconciled') is not True: blocked.append('resume not reconciled')
    graph=record.get('graph')
    if graph not in ('not_used','fresh','stale'): blocked.append('graph use not declared')
    if graph=='stale' and not refs(record.get('file_fallback_evidence')): blocked.append('stale graph without direct file evidence')
    if record.get('review_required') is not False:
        if record.get('review_status')!='PASS' or record.get('review_snapshot')!=current or not refs(record.get('review_evidence')): blocked.append('independent review missing or stale')
    if not refs(record.get('floor_evidence')): blocked.append('floor inspection evidence missing')
    signals=record.get('signals')
    if not isinstance(signals,list): blocked.append('signal inspection not declared');signals=[]
    for signal in signals:
        if not isinstance(signal,dict): blocked.append('invalid signal');continue
        kind=signal.get('disposition')
        if not signal.get('location') or not refs(signal.get('evidence')): blocked.append('signal evidence missing');continue
        if kind=='equivalent':
            if not refs(signal.get('before_after_behavior')): blocked.append('equivalence not supported')
        elif kind=='confirmed_weakening': failed.append('confirmed quality-floor weakening')
        elif kind=='accepted_exception':
            decision=signal.get('owner_decision')
            if not isinstance(decision,dict) or not all(decision.get(k) for k in ('owner','reference','rationale')) or decision.get('snapshot')!=current: blocked.append('exception lacks scoped owner decision')
            else: exceptions.append(signal['location'])
        else: blocked.append('unresolved quality-floor signal')
    required=record.get('required_ui');evidence=record.get('ui_evidence')
    if not isinstance(required,list) or not isinstance(evidence,dict): blocked.append('UI applicability not declared')
    else:
        for name in required:
            row=evidence.get(name,{})
            if not isinstance(row,dict): blocked.append('invalid UI evidence');continue
            if row.get('status')!='PASS' or row.get('snapshot')!=current or not refs(row.get('evidence')) or not row.get('acceptance') or not row.get('existing_scenario'): blocked.append('required UI evidence missing: '+str(name))
            if row.get('surface')=='integration' and row.get('kind') not in ('e2e','authorized_manual'): blocked.append('component story cannot establish entity integration')
            if row.get('kind') not in ('unit_component','storybook','e2e','authorized_manual'): blocked.append('UI evidence route unknown')
    return {'status':'FAIL' if failed else 'BLOCKED' if blocked else 'PASS_WITH_EXCEPTIONS' if exceptions else 'PASS','reasons':failed+blocked,'exceptions':exceptions,'claim':'Declared evidence consistency only; artifact truth and live agent behavior NOT_TESTED'}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('record',type=Path);args=ap.parse_args()
    try: result=assess(json.loads(args.record.read_text()))
    except (OSError,ValueError,TypeError,KeyError): result={'status':'BLOCKED','reasons':['invalid evidence input']}
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['status'] in ('PASS','PASS_WITH_EXCEPTIONS') else 1)
