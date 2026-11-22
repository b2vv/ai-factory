"""Dashboard status publishing for `kit.py project dashboard|status` (T23 Part B).

Used by tools/projects.py only. The host configuration (`<kit>/.ai-factory-state/dashboard.json`,
0600) holds paths only: the dashboard Go module, its projects config and its private feed.
`project status` takes an agent's status JSON on stdin, adds schema, project, the project's
current HEAD and the observation time, and hands it to the dashboard's own publisher
(`go run . -publish [-apply]`), whose checks stay the only gate. It never prints record text.
"""
import datetime
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

CONFIG = 'dashboard.json'
SCHEMA = 'factory-dashboard/status/1'
MAX_INPUT = 16 * 1024
AGENT_FIELDS = {'taskId', 'title', 'state', 'next', 'sources', 'stages', 'markdown'}
FILLED = {'schema', 'project', 'revision', 'updatedAt'}
TIMEOUT = 180


class Blocked(ValueError):
    pass


def canonical(value, label):
    p = Path(value)
    if not p.is_absolute() or os.path.normpath(value) != value or str(p.resolve()) != value:
        raise Blocked(f'{label} must be an absolute canonical path')
    return p


def go_binary(value=None):
    path = value or shutil.which('go') or ('/usr/local/go/bin/go' if os.access('/usr/local/go/bin/go', os.X_OK) else None)
    if not path or not Path(path).is_absolute() or not os.access(path, os.X_OK):
        raise Blocked('Go is required: pass --go with an absolute go executable')
    return path


def check_config(cfg):
    if not isinstance(cfg, dict) or set(cfg) != {'schema', 'source', 'projects', 'feed', 'go'} or cfg['schema'] != 1:
        raise Blocked('invalid dashboard configuration')
    source = canonical(cfg['source'], 'dashboard source')
    if not (source / 'go.mod').is_file() or b'module factory-dashboard' not in (source / 'go.mod').read_bytes():
        raise Blocked('dashboard source must be the factory-dashboard Go module (runtime/dashboard)')
    if not canonical(cfg['projects'], 'projects config').is_file():
        raise Blocked('projects config is missing')
    feed = canonical(cfg['feed'], 'feed directory')
    s = feed.stat() if feed.is_dir() and not feed.is_symlink() else None
    if s is None or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) & 0o077:
        raise Blocked('feed must be an existing private (0700) directory owned by you')
    go_binary(cfg['go'])
    return cfg


def build_config(args):
    return check_config({'schema': 1, 'source': args.source, 'projects': args.projects, 'feed': args.feed,
                         'go': go_binary(args.go)})


def load_config(kit, private_json):
    cfg = private_json(Path(kit) / '.ai-factory-state' / CONFIG)
    return None if cfg is None else check_config(cfg)


def go_env():
    # The host's own Go setup (toolchain selection, caches) is kept; nothing is fetched.
    return {**os.environ, 'GOPROXY': 'off', 'LC_ALL': 'C'}


def run_dashboard(cfg, args, stdin=None):
    try:
        r = subprocess.run([cfg['go'], 'run', '-tags', 'nobundle', '.', '-projects', cfg['projects'], '-feed', cfg['feed'], *args],
                           cwd=cfg['source'], input=stdin, capture_output=True, timeout=TIMEOUT, env=go_env())
    except subprocess.TimeoutExpired:
        raise Blocked('the dashboard publisher did not finish in time') from None
    return r.returncode, r.stdout.decode('utf-8', 'replace'), r.stderr.decode('utf-8', 'replace')


def projects(cfg):
    """Dashboard project ids and roots from its projects config (the publisher validates it again)."""
    try:
        doc = json.loads(Path(cfg['projects']).read_bytes())
    except (OSError, ValueError):
        raise Blocked('the dashboard projects config is not readable JSON') from None
    rows = {}
    for e in doc if isinstance(doc, list) else []:
        if isinstance(e, dict) and isinstance(e.get('id'), str) and isinstance(e.get('root'), str):
            rows[e['id']] = e['root']
    if not rows: raise Blocked('the dashboard projects config lists no project')
    return rows


def validate_projects(cfg):
    """The dashboard's own strict validator, used once when the configuration is written."""
    code, _, _ = run_dashboard(cfg, ['-list-projects'])
    if code != 0: raise Blocked('the dashboard rejected its projects config')
    return projects(cfg)


def dashboard_id(cfg, root):
    """The dashboard id configured for this project root, or None."""
    for ident, path in projects(cfg).items():
        if path == str(root): return ident
    return None


def last_line(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines: return ''
    line = lines[-1]
    # Go's log prefix is a date and time; the publisher's messages carry no record text.
    parts = line.split(' ', 2)
    if len(parts) == 3 and parts[0].count('/') == 2 and parts[1].count(':') == 2: line = parts[2]
    return line[:300]


def head(root, git):
    value = git(root, 'HEAD')
    if not value or len(value) != 40: raise Blocked('could not read the project HEAD')
    return value


def status_record(raw, ident, revision, now):
    if len(raw) > MAX_INPUT: raise Blocked('status input is larger than 16 KiB')
    try:
        doc = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise Blocked('status input is not JSON') from None
    if not isinstance(doc, dict): raise Blocked('status input must be a JSON object')
    filled = sorted(set(doc) & FILLED)
    if filled: raise Blocked('status input must not set ' + ', '.join(filled) + ' (the command fills them)')
    unknown = sorted(set(doc) - AGENT_FIELDS)
    if unknown: raise Blocked('unknown status fields: ' + ', '.join(unknown))
    return {'schema': SCHEMA, 'project': ident, 'revision': revision,
            'updatedAt': now.strftime('%Y-%m-%dT%H:%M:%SZ'), **doc}


def publish(cfg, record, apply):
    code, out, err = run_dashboard(cfg, ['-publish'] + (['-apply'] if apply else []),
                                   stdin=json.dumps(record, ensure_ascii=False).encode('utf-8'))
    message = last_line(out) if code == 0 else last_line(err) or last_line(out) or f'exit {code}'
    return code == 0, message


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)
