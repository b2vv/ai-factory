#!/usr/bin/env python3
"""Run only isolated stdlib fixture suites. No model sessions or product repositories."""
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import argparse
ap=argparse.ArgumentParser();ap.add_argument('--previous-release',type=Path);ap.add_argument('--suite',choices=['all','storage','dashboard','web-to-md'],default='all');args=ap.parse_args()

def go_version_tuple(text):
    m=re.match(r'(?:go)?(\d+)(?:\.(\d+))?(?:\.(\d+))?',text.strip())
    return tuple(int(x or 0) for x in m.groups()) if m else None

# Per-binary hang guard, not a speed budget. The storage api package is fsync-bound
# (durable WAL/ledger writes): ~100s alone on macOS, where Go's Sync is F_FULLFSYNC,
# and longer under a parallel ./... run, so 120s killed passing tests.
STORAGE_GO_TIMEOUT='600s'

def run_go_suite(root, env, name, rel, tags=None, note=None, timeout='120s'):
    """Bridge for an optional Go component (storage, dashboard, web-to-md): run its hermetic Go
    unit suite offline (GOPROXY=off, GOSUMDB=off, GOTOOLCHAIN=local, GOFLAGS=-mod=readonly).
    The Go binary is AI_FACTORY_GO if set, else `go` on PATH. The aggregate suite explicitly SKIPS
    when the module or toolchain is absent, or the toolchain is older than the module's `go`
    line; `--suite <name>` instead reports BLOCKED and fails. Returns 0 on pass/optional skip,
    1 on a test failure, 2 on a required-suite dependency blocker. Storage integration/e2e
    suites (real PG/Mongo) are NOT run here; see runtime/storage/deploy/test/run-integration.sh."""
    required=args.suite==name
    def skip(reason):
        print(f'\n=== {name} Go suite: SKIPPED ({reason}) ===',flush=True)
        if required: print(f'{name} required suite: BLOCKED (not executed)',flush=True)
        return 2 if required else 0
    mod=root/rel
    if not (mod/'go.mod').exists(): return skip(f'module {rel} absent')
    go=env.get('AI_FACTORY_GO') or shutil.which('go',path=env.get('PATH'))
    if not go: return skip('no Go toolchain; set AI_FACTORY_GO or PATH')
    test_env=dict(env, GOPROXY='off', GOSUMDB='off', GOTOOLCHAIN='local', GOFLAGS='-mod=readonly')
    need=next((go_version_tuple(l[3:]) for l in (mod/'go.mod').read_text().splitlines() if l.startswith('go ')),None)
    probe=subprocess.run([go,'env','GOVERSION'],env=test_env,cwd=str(mod),capture_output=True,text=True)
    have=go_version_tuple(probe.stdout) if probe.returncode==0 else None
    if have is None: return skip(f'cannot read toolchain version from {go}')
    if need and have<need: return skip(f'toolchain {probe.stdout.strip()} older than go.mod {".".join(map(str,need))}; set AI_FACTORY_GO')
    if note: print(f'{name}: {note}',flush=True)
    cmd=[go,'test','-count=1',f'-timeout={timeout}']+(['-tags',tags] if tags else [])+['./...']
    print(f'\n=== {name} Go suite: go test {"-tags "+tags+" " if tags else ""}./... (hermetic) ===',flush=True)
    result=subprocess.run(cmd,env=test_env,cwd=str(mod))
    print(f'{name} Go suite: '+('FAIL' if result.returncode else 'PASS'),flush=True)
    return 1 if result.returncode else 0

def run_dashboard_suites(root, env):
    """Dashboard: Go suite in the default build when the browser bundle exists, otherwise in the
    test-only `nobundle` build (real HTML/CSS, stub app.js) with the bundle content check reported
    as SKIPPED. The node markdown test runs only when node and installed node_modules exist."""
    mod=root/'runtime/dashboard'
    bundle=(mod/'ui/dist/app.js').is_file()
    note=None if bundle else 'bundle content check SKIPPED (ui/dist/app.js absent; run npm ci && npm run build); Go suite uses -tags nobundle'
    code=run_go_suite(root, env, 'dashboard', 'runtime/dashboard', tags=None if bundle else 'nobundle', note=note)
    if not (mod/'go.mod').exists(): return code
    node=shutil.which('node',path=env.get('PATH'))
    if not node or not (mod/'node_modules/react').is_dir():
        print('\n=== dashboard node suite: SKIPPED ('+('no node on PATH' if not node else 'node_modules absent; run npm ci')+') ===',flush=True)
        if args.suite=='dashboard': print('dashboard required node suite: BLOCKED (not executed)',flush=True)
        return code if code or args.suite!='dashboard' else 2
    print('\n=== dashboard node suite: node --test ui/markdown.test.js ui/queue.test.js ui/status.test.js ===',flush=True)
    result=subprocess.run([node,'--test','ui/markdown.test.js','ui/queue.test.js','ui/status.test.js'],env=env,cwd=str(mod))
    print('dashboard node suite: '+('FAIL' if result.returncode else 'PASS'),flush=True)
    return code or (1 if result.returncode else 0)
root=Path(__file__).resolve().parent.parent
env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
env['PYTHONPATH']=str(root/'tools')+os.pathsep+str(root/'runtime/onboarding')
if args.previous_release: env['AI_FACTORY_PREVIOUS_RELEASE']=str(args.previous_release.resolve())
env.update(GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_NOSYSTEM='1',PYTHONDONTWRITEBYTECODE='1')
with tempfile.TemporaryDirectory(prefix='ai-factory-fixtures-') as temp:
    env['GIT_TEMPLATE_DIR']=temp
    failures=0
    only=args.suite!='all'
    for directory in ([] if only else ['tests/onboarding','tests/review','tests/session-size','tests/handoff-integration','tests/session-size-docker','tests/legacy-review','tests/legacy-session','tests/install','tests/collection','tests/checkpoint','tests/constraints','tests/ui-measurements','tests/scanners','tests/connect','tests/connect-handoff','tests/connect-capture','tests/projects','tests/packaging']):
        print('\n=== isolated suite: '+directory+' ===',flush=True)
        result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(root/directory),'-p','test_*.py','-v'],env=env,cwd=root)
        failures += result.returncode != 0
    # Also run the operator helper's own Python unittest (M8), which lives beside the helper
    # rather than under tests/ so it ships with the storage component.
    opdir=root/'runtime/storage/operator'
    if args.suite in ('all','storage') and (opdir/'test_identity_helper.py').exists():
        print('\n=== storage operator helper suite ===',flush=True)
        opr=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(opdir),'-p','test_*.py','-v'],env=env,cwd=str(opdir))
        failures += opr.returncode != 0
    if not only:
        catcher=root/'runtime/storage/deploy/codex-capture'
        for name in ['test_codex_catcher.py','test_codex_catcher_auth.py','test_catcher_security.py','test_codex_queue.py']:
            print('\n=== isolated catcher fixture: '+name+' ===',flush=True)
            result=subprocess.run([sys.executable,'-B',str(catcher/name)],env=env,cwd=root)
            failures += result.returncode != 0
    if not only:
        search_client=root/'runtime/storage/deploy/search-client'
        if (search_client/'test_archive_search.py').exists():
            print('\n=== isolated search client fixture ===',flush=True)
            result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(search_client),'-p','test_*.py','-v'],env=env,cwd=root)
            failures += result.returncode != 0
    if not only:
        bridge=root/'runtime/storage/deploy/capture-bridge'
        for name in ['test_capture_bridge.py','test_capture_auth.py','test_capture_queue.py','test_sanitizer_parity.py','test_claude_capture_dispatcher.py']:
            print('\n=== isolated capture bridge fixture: '+name+' ===',flush=True)
            result=subprocess.run([sys.executable,'-B',str(bridge/name)],env=env,cwd=root)
            failures += result.returncode != 0
    archive=root/'runtime/storage/deploy/archive'
    if args.suite in ('all','storage') and (archive/'test_restart_policy.py').exists():
        print('\n=== archive restart policy fixtures ===',flush=True)
        result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(archive),'-p','test_*.py','-v'],env=env,cwd=root)
        failures += result.returncode != 0
    for name,runner in [('storage',lambda: run_go_suite(root, env, 'storage', 'runtime/storage', timeout=STORAGE_GO_TIMEOUT)),
                        ('dashboard',lambda: run_dashboard_suites(root, env)),
                        ('web-to-md',lambda: run_go_suite(root, env, 'web-to-md', 'runtime/web-to-md'))]:
        if args.suite in ('all',name): failures += runner() != 0
    raise SystemExit(1 if failures else 0)
