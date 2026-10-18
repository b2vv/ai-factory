#!/usr/bin/env python3
"""Run only isolated stdlib fixture suites. No model sessions or product repositories."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import argparse
ap=argparse.ArgumentParser();ap.add_argument('--previous-release',type=Path);args=ap.parse_args()
root=Path(__file__).resolve().parent.parent
env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
env['PYTHONPATH']=str(root/'tools')+os.pathsep+str(root/'runtime/onboarding')
if args.previous_release: env['AI_FACTORY_PREVIOUS_RELEASE']=str(args.previous_release.resolve())
env.update(GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM='1',PYTHONDONTWRITEBYTECODE='1')
with tempfile.TemporaryDirectory(prefix='ai-factory-fixtures-') as temp:
    env['GIT_TEMPLATE_DIR']=temp
    failures=0
    for directory in ['tests/onboarding','tests/review','tests/session-size','tests/legacy-review','tests/legacy-session','tests/install','tests/collection','tests/checkpoint']:
        print('\n=== isolated suite: '+directory+' ===',flush=True)
        result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(root/directory),'-p','test_*.py','-v'],env=env,cwd=root)
        failures += result.returncode != 0
    raise SystemExit(1 if failures else 0)
