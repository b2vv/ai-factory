#!/usr/bin/env python3
"""Run only isolated stdlib fixture suites. No model sessions or product repositories."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import argparse
ap=argparse.ArgumentParser();ap.add_argument('--previous-release',type=Path);ap.add_argument('--suite',choices=['all','storage'],default='all');args=ap.parse_args()

def run_storage_go_suite(root, env):
    """Bridge for the optional Go `storage` component: run its hermetic Go unit suite when a Go
    toolchain and the module are present. The kit's own suites are Python/unittest; storage is
    Go, so this is an additive bridge, NOT a unittest line. The aggregate suite explicitly SKIPS when `go` is
    absent or the module is missing; --suite storage instead reports BLOCKED and fails; it runs offline
    (GOPROXY=off, GOSUMDB=off, GOTOOLCHAIN=local, GOFLAGS=-mod=readonly) and only the
    hermetic suite (no -tags integration, so no databases/Docker are required). Returns 0 on
    pass/optional skip, 1 on a test failure, 2 on a required-suite dependency blocker. The integration/e2e suites (real PG/Mongo) are NOT
    run here; they are driven by runtime/storage/deploy/test/run-integration.sh."""
    mod=root/'runtime/storage'
    if not (mod/'go.mod').exists():
        print('\n=== storage Go suite: SKIPPED (module runtime/storage absent) ===',flush=True)
        return 2 if args.suite=='storage' else 0
    go=shutil.which('go')
    if not go:
        print('\n=== storage Go suite: SKIPPED (no Go toolchain on PATH) ===',flush=True)
        return 2 if args.suite=='storage' else 0
    print('\n=== storage Go suite: go test ./... (hermetic, no integration tags) ===',flush=True)
    test_env=dict(env, GOPROXY='off', GOSUMDB='off', GOTOOLCHAIN='local', GOFLAGS='-mod=readonly')
    result=subprocess.run([go,'test','-count=1','-timeout=120s','./...'],env=test_env,cwd=str(mod))
    print('storage Go suite: '+('FAIL' if result.returncode else 'PASS'),flush=True)
    return 1 if result.returncode else 0
root=Path(__file__).resolve().parent.parent
env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
env['PYTHONPATH']=str(root/'tools')+os.pathsep+str(root/'runtime/onboarding')
if args.previous_release: env['AI_FACTORY_PREVIOUS_RELEASE']=str(args.previous_release.resolve())
env.update(GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM='1',PYTHONDONTWRITEBYTECODE='1')
with tempfile.TemporaryDirectory(prefix='ai-factory-fixtures-') as temp:
    env['GIT_TEMPLATE_DIR']=temp
    failures=0
    for directory in ([] if args.suite=='storage' else ['tests/onboarding','tests/review','tests/session-size','tests/session-size-docker','tests/legacy-review','tests/legacy-session','tests/install','tests/collection','tests/checkpoint','tests/constraints','tests/scanners','tests/connect','tests/packaging']):
        print('\n=== isolated suite: '+directory+' ===',flush=True)
        result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(root/directory),'-p','test_*.py','-v'],env=env,cwd=root)
        failures += result.returncode != 0
    # Also run the operator helper's own Python unittest (M8), which lives beside the helper
    # rather than under tests/ so it ships with the storage component.
    opdir=root/'runtime/storage/operator'
    if (opdir/'test_identity_helper.py').exists():
        print('\n=== storage operator helper suite ===',flush=True)
        opr=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(opdir),'-p','test_*.py','-v'],env=env,cwd=str(opdir))
        failures += opr.returncode != 0
    if args.suite != 'storage':
        catcher=root/'runtime/storage/deploy/codex-capture'
        for name in ['test_codex_catcher.py','test_codex_catcher_auth.py','test_catcher_security.py']:
            print('\n=== isolated catcher fixture: '+name+' ===',flush=True)
            result=subprocess.run([sys.executable,'-B',str(catcher/name)],env=env,cwd=root)
            failures += result.returncode != 0
    if args.suite != 'storage':
        search_client=root/'runtime/storage/deploy/search-client'
        if (search_client/'test_archive_search.py').exists():
            print('\n=== isolated search client fixture ===',flush=True)
            result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(search_client),'-p','test_*.py','-v'],env=env,cwd=root)
            failures += result.returncode != 0
    go_result=run_storage_go_suite(root, env)
    failures += go_result != 0
    if go_result==2: print('storage required suite: BLOCKED (not executed)',flush=True)
    raise SystemExit(1 if failures else 0)
