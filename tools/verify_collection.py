"""Read-only collection integrity, inventory coverage and safe metadata validation."""
import hashlib,json,re
from pathlib import Path

def verify(root):
    root=Path(root).resolve();m=json.loads((root/'provenance/source-map.json').read_text());issues=[]
    recorded=set()
    for r in m['files']:
        p=root/r['destination']
        if not p.resolve().is_relative_to(root) or p.is_symlink():issues.append('unsafe source destination');continue
        if r['destination'] in recorded:issues.append('duplicate destination')
        recorded.add(r['destination'])
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:issues.append('source hash mismatch: '+r['destination'])
        if not r['transformations'] and r['sha256']!=r['source_sha256']:issues.append('unrecorded transformation')
        if 'license' in p.name.lower() and r['transformations']:issues.append('license transformed')
    additions=json.loads((root/'provenance/authorized-additions.json').read_text())
    if additions['upstream']['commit']!='aeac41d4d005999432bb7312f7ff06383a91d59d' or additions['upstream']['license']!='MIT':issues.append('unrecognized authorized addition source')
    for row in additions['files']:
        name=row['destination'];p=root/name
        if name in recorded or not p.resolve().is_relative_to(root) or p.is_symlink():issues.append('unsafe or duplicate addition');continue
        recorded.add(name)
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:issues.append('addition hash mismatch: '+name)
        if p.name=='LICENSE.addyosmani' and row['sha256']!=next(s['sha256'] for s in additions['upstream']['sources'] if s['path']=='LICENSE'):issues.append('MIT license modified')
    for row in additions['adaptations']:
        p=root/row['destination'];body=p.read_bytes();block=row['append'].encode()
        if not body.endswith(block) or hashlib.sha256(block).hexdigest()!=row['append_sha256'] or hashlib.sha256(body[:-len(block)]).hexdigest()!=row['before_sha256'] or hashlib.sha256(body).hexdigest()!=row['after_sha256']:issues.append('adaptation body mismatch')
    actual_skills={str(p.relative_to(root)) for p in (root/'skills').rglob('*') if p.is_file()}
    recorded_skills={n for n in recorded if n.startswith('skills/')}
    if actual_skills != recorded_skills:issues.append('unrecorded or missing skill payload')
    shared=[b for b in m['bundles'] if b['group']=='shared']
    if len(shared)!=84 or len({b['source'] for b in shared})!=84:issues.append('shared inventory must account for 84 distinct definitions')
    if any(b['name'].lower().startswith('b2b') or Path(b['source']).parent.name.lower().startswith('b2b') for b in m['bundles']):issues.append('b2b bundle forbidden')
    if any(b['group']!='shared' for b in m['bundles']):issues.append('external bundle forbidden')
    if 'host_dependencies' in m:issues.append('host inventory forbidden')
    if any(not r['source'].startswith('~/.agents/') for r in m['files']):issues.append('external source forbidden')
    for b in m['bundles']:
        if b['status']=='INCLUDED' and b['destination'] not in recorded:issues.append('included definition absent')
        if b['status']!='INCLUDED' and (root/b['destination']).exists():issues.append('excluded definition leaked')
    for a in m['aliases']:
        if a['target'] and not (root/a['target']/'SKILL.md').is_file():issues.append('alias target absent')
    if m['blocked_files']:issues.append('blocked files unresolved')
    for l in m['links']:
        if l['status']=='RESOLVED':
            p=(root/l['file']).parent/l['target']
            if not p.resolve().is_relative_to(root) or not p.exists():issues.append('resolved link lost: '+l['file'])
    # All patterns are checked without emitting values. This is heuristic, not exhaustive DLP.
    for name in recorded:
        p=root/name
        try:t=p.read_text()
        except UnicodeDecodeError:continue
        for label,pat in [('absolute-home',r'/Users/[A-Za-z]|/home/[A-Za-z]'),('access-token',r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{24,}|AKIA[A-Z0-9]{16}')]:
            if re.search(pat,t):issues.append(label+': '+name)
        if re.search(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',t) and not (p.name=='test_session_guard.py' and 'MII' not in t):issues.append('private-key marker: '+name)
    return {'status':'PASS' if not issues else 'FAIL','source_files':len(recorded),'accounted_shared':len(shared),'authorized_added_skills':1,'included_skills':sum(b['status']=='INCLUDED' for b in m['bundles']),'excluded_license':sum(b['status']=='EXCLUDED_EXPLICIT_LICENSE_RESTRICTION' for b in m['bundles']),'pending_scope':sum(b['status']=='PENDING_CONFIDENTIAL_SCOPE' for b in m['bundles']),'issues':issues,'runtime':'NOT_TESTED','independent_review':'PENDING'}

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True,type=Path);a=ap.parse_args();result=verify(a.root);print(json.dumps(result,indent=2));raise SystemExit(result['status']!='PASS')
