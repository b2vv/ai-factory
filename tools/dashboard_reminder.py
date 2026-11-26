#!/usr/bin/env python3
"""Stop hook (Claude Code and Codex): remind the agent once per new HEAD to publish the dashboard status (T36).

Registered only by `kit.py project dashboard --apply` (tools/projects.py), never by `project install`:
    python3 -I -B <kit>/tools/dashboard_reminder.py --kit <kit> --host claude|codex
It reads the Stop event JSON on stdin. It stays silent (exit 0, no output) unless the session's Git root is a
project on this kit's dashboard and its HEAD moved past the revision of the project's last published status
(a project never published counts as moved). Then it records that HEAD as reminded and prints one Stop
response, `{"decision": "block", "reason": ...}`: both hosts continue the turn with the reason as the next
prompt. Each HEAD is reminded once per project. Any error is silent (fail-open): it never breaks a session.
It reads files and runs `git rev-parse` only: no network, no dashboard build, no record text in the output.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.dont_write_bytecode = True

STATE = '.ai-factory-state'
CONFIG = 'dashboard.json'
REMINDED = 'dashboard-reminded.json'
MAX_INPUT = 1024 * 1024
MAX_FILE = 1024 * 1024


def git_root_and_head(cwd):
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/', 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'}
    r = subprocess.run(['/usr/bin/git', '-C', cwd, 'rev-parse', '--show-toplevel', 'HEAD'], env=env,
                       capture_output=True, text=True, timeout=5)
    lines = r.stdout.splitlines() if r.returncode == 0 else []
    if len(lines) != 2 or len(lines[1]) != 40: return None, None
    return lines[0], lines[1]


def read_json(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_FILE: return None
    return json.loads(path.read_bytes())


def write_private(path, doc):
    fd, tmp = tempfile.mkstemp(prefix='.reminded-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(doc, f, sort_keys=True); f.flush(); os.fchmod(f.fileno(), 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def reason(ident, head, published):
    where = f'is at {published[:12]}' if published else 'was never published'
    return (f'AI Factory dashboard: project `{ident}` is at commit {head[:12]}, but its last published status {where}. '
            'If a stage of the primary task was recorded in the task record since that publish, publish the status now '
            "with the `kit.py project status` command from this project's managed block (AGENTS.local.md; see "
            "docs/dashboard-status.md in the kit). Otherwise, state in one line why no publish is needed. "
            'This reminder is shown once per commit.')


def decide(kit, event):
    """The Stop response for this event, or None for silence."""
    if not isinstance(event, dict) or event.get('stop_hook_active', False) is not False:
        return None  # a continued Stop (or an unknown flag value) never gets a second prompt
    cwd = event.get('cwd')
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or not os.path.isdir(cwd): return None
    state = Path(kit) / STATE
    cfg = read_json(state / CONFIG)
    if not isinstance(cfg, dict) or not isinstance(cfg.get('projects'), str) or not isinstance(cfg.get('feed'), str):
        return None  # no dashboard on this host
    rows = read_json(cfg['projects'])
    if not isinstance(rows, list): return None
    root, head = git_root_and_head(cwd)
    if root is None: return None
    ident = next((r['id'] for r in rows if isinstance(r, dict) and r.get('root') == root and isinstance(r.get('id'), str)), None)
    if ident is None or '/' in ident or ident.startswith('.'): return None  # not a dashboard project
    record = read_json(Path(cfg['feed']) / (ident + '.json'))
    published = record.get('revision') if isinstance(record, dict) and isinstance(record.get('revision'), str) else None
    if published == head: return None
    seen = read_json(state / REMINDED) if (state / REMINDED).exists() else {'schema': 1, 'heads': {}}
    if not isinstance(seen, dict) or not isinstance(seen.get('heads'), dict): seen = {'schema': 1, 'heads': {}}
    if seen['heads'].get(ident) == head: return None
    seen['heads'][ident] = head
    write_private(state / REMINDED, seen)  # recorded before the prompt, so a failure stays silent next time too
    return {'decision': 'block', 'reason': reason(ident, head, published)}


def main(argv=None):
    try:
        ap = argparse.ArgumentParser(description=__doc__)
        ap.add_argument('--kit', required=True); ap.add_argument('--host', choices=('claude', 'codex'), default='claude')
        a = ap.parse_args(argv)
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT: return 0
        out = decide(a.kit, json.loads(raw))
        if out is not None: sys.stdout.write(json.dumps(out, ensure_ascii=False) + '\n')
    except BaseException:  # fail-open: never break the session, never echo input or paths
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
