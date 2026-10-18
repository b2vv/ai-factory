#!/usr/bin/env python3
"""Read-only exact payload, source preservation and documented-reference verification."""
import argparse,json,re,sys
from pathlib import Path
import kit,verify_collection

def verify(root):
    root=Path(root).resolve();manifest,_,_=kit.payload(root,[])
    issues=[];links=0
    exceptions=json.loads((root/'provenance/link-exceptions.json').read_text())
    allowed={(x['file'],x['target']) for x in exceptions['references']}
    for item in manifest['files']:
        p=root/item['path']
        try:text=p.read_text()
        except UnicodeDecodeError:continue
        # Source validator checks inherited source payload. This complements it for authored tooling/docs.
        if not p.name.startswith(('verify_','test_')):
            if re.search(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{24,}|AKIA[A-Z0-9]{16}',text):issues.append({'file':item['path'],'kind':'credential_pattern'})
        if p.suffix=='.md':
            for link in re.findall(r'\]\(([^)]+)\)',text):
                path=link.split('#')[0]
                if not path or '://' in path or path.startswith('mailto:'):continue
                links+=1;target=(p.parent/path).resolve()
                if target.is_relative_to(root) and target.exists():continue
                if (item['path'],link) not in allowed:issues.append({'file':item['path'],'kind':'missing_or_escaping_link','target':link})
    c=verify_collection.verify(root);issues.extend({'kind':'collection','detail':x} for x in c['issues'])
    return {'status':'PASS' if not issues else 'FAIL','files':len(manifest['files'])+2,'links_checked':links,'documented_external_or_placeholder_refs':len(allowed),'issues':issues,'limitations':['Heuristic privacy check, not universal secret detection.','Native CLI invocation and independent acceptance remain NOT_TESTED.']}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args()
    try:
        result=verify(kit.absolute(a.root));print(json.dumps(result,indent=2));sys.exit(result['status']!='PASS')
    except (ValueError,OSError,KeyError,TypeError):
        print(json.dumps({'status':'BLOCKED','reason':'invalid release/path/checksum'}));sys.exit(1)
