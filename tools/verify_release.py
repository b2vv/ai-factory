#!/usr/bin/env python3
"""Read-only release hash, path, skill-reference and privacy-pattern verification."""
import argparse
import json
from pathlib import Path
import re
import sys
import kit


def verify(root):
    manifest, _, _=kit.payload(root,[])
    issues=[];links=0
    for item in manifest['files']:
        p=root/item['path']
        if item['path'].startswith('collection/'):
            continue  # checked by source-preserving collection validator below
        text=p.read_text(encoding='utf-8')
        # Pattern scan complements curated-source review, not a universal secret detector.
        patterns={'machine_absolute_path':r'/Users/[A-Za-z]|/home/[A-Za-z]|[A-Z]:\\Users\\',
                  'credential_pattern':r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----'}
        # The scanner's own pattern vocabulary is not leaked project context.
        if p.name!='verify_release.py':
            for label,pattern in patterns.items():
                if re.search(pattern,text):issues.append({'file':item['path'],'kind':label})
        if p.suffix=='.md':
            for link in re.findall(r'\]\(([^)]+)\)',text):
                if '://' in link or link.startswith('#'):continue
                target=(p.parent/link.split('#')[0]).resolve();links+=1
                if root not in target.parents or not (target.is_file() or target.is_dir()):issues.append({'file':item['path'],'kind':'missing_or_escaping_link'})
        if p.name=='SKILL.md':
            if not text.startswith('---\n'):issues.append({'file':item['path'],'kind':'missing_frontmatter'});continue
            header=text.split('---',2)[1]
            match=re.search(r'^name:\s*([a-z0-9-]+)\s*$',header,re.M)
            if not match or match.group(1)!=p.parent.name or not re.search(r'^description:\s*\S',header,re.M):issues.append({'file':item['path'],'kind':'invalid_skill_frontmatter'})
    if (root/'collection/manifest.json').exists():
        import verify_collection
        result=verify_collection.verify(root)
        issues.extend({'kind':'collection','detail':x} for x in result['issues'])
    return {'status':'PASS' if not issues else 'FAIL','files':len(manifest['files'])+2,'links_checked':links,'issues':issues,'limitations':['heuristic scan is not universal secret detection','skills validated statically, not native invocation','hashes are integrity checks, not authenticity signatures']}

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',type=Path,required=True);a=ap.parse_args()
    try:
        result=verify(kit.absolute(a.root));print(json.dumps(result,indent=2));sys.exit(0 if result['status']=='PASS' else 1)
    except (ValueError,OSError,KeyError,TypeError):
        print(json.dumps({'status':'BLOCKED','reason':'invalid release/path/checksum'}));sys.exit(1)
