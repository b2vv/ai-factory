"""Archive access for `kit.py project install/remove` (T15 P6): grants, credential files, worker.

Used by tools/projects.py only. The archive configuration (`<kit>/.ai-factory-state/archive.json`,
0600) holds paths, never a secret. With it, installing a project mints the archive project,
turns on claude-code capture consent and issues two separate agent grants (capture-only and
search-only), writes their credential files 0600, adds a search route alias, a search contract
and a launchd worker. Secrets are generated in memory, sent only to the loopback archive and
written only to the 0600 credential files; nothing here prints them.
"""
import json
import os
from pathlib import Path
import plistlib
import secrets
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

CONFIG = 'archive.json'
ENDPOINT = 'http://127.0.0.1:8780'
LAUNCHCTL = '/bin/launchctl'  # tests replace it with a recording fake
BRIDGE = 'runtime/storage/deploy/capture-bridge/capture_bridge.py'
SEARCH_CLIENT = 'runtime/storage/deploy/search-client/archive_search.py'
LABEL = 'local.ai-factory.capture.{name}'
TIMEOUT = 15
RECORD_KEYS = {'principals', 'alias', 'files', 'worker'}


class Blocked(ValueError):
    pass


# --- configuration -------------------------------------------------------------------------

def private_dir(path, label):
    s = path.stat() if path.is_dir() and not path.is_symlink() else None
    if s is None or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) & 0o077:
        raise Blocked(f'{label} must be an existing private (0700) directory owned by you')


def private_file(path, label):
    try:
        s = os.lstat(path)
    except FileNotFoundError:
        raise Blocked(f'{label} is missing') from None
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) & 0o077:
        raise Blocked(f'{label} must be a private (0600) regular file owned by you')


def canonical(value, label):
    p = Path(value)
    if not p.is_absolute() or os.path.normpath(value) != value or str(p.resolve()) != value:
        raise Blocked(f'{label} must be an absolute canonical path')
    return p


def build_config(kit, args):
    worker = args.worker or ('launchd' if sys.platform == 'darwin' else 'none')
    cfg = {'schema': 1, 'endpoint': args.endpoint or ENDPOINT,
           'operator_secret_file': args.operator_secret_file, 'capture_dir': args.capture_dir,
           'search_dir': args.search_dir, 'search_routes': args.search_routes,
           'worker': {'kind': worker}}
    if worker == 'launchd':
        if not (args.agents_dir and args.log_dir and args.python):
            raise Blocked('--worker launchd needs --agents-dir, --log-dir and --python')
        cfg['worker'].update(agents_dir=args.agents_dir, log_dir=args.log_dir, python=args.python)
    return check_config(kit, cfg)


def check_config(kit, cfg):
    if (not isinstance(cfg, dict) or set(cfg) != {'schema', 'endpoint', 'operator_secret_file', 'capture_dir',
                                                  'search_dir', 'search_routes', 'worker'}
            or cfg['schema'] != 1 or not isinstance(cfg['endpoint'], str)):
        raise Blocked('invalid archive configuration')
    u = urllib.parse.urlsplit(cfg['endpoint'])
    if (u.scheme != 'http' or u.hostname != '127.0.0.1' or u.port is None or u.username or u.password
            or u.path or u.query or u.fragment):
        raise Blocked('archive endpoint must be http://127.0.0.1:<port>')
    private_file(canonical(cfg['operator_secret_file'], 'operator secret file'), 'operator secret file')
    private_dir(canonical(cfg['capture_dir'], 'capture dir'), 'capture dir')
    private_dir(canonical(cfg['search_dir'], 'search dir'), 'search dir')
    routes = canonical(cfg['search_routes'], 'search routes file')
    if routes != Path(kit) / SEARCH_CLIENT.replace('archive_search.py', 'search-routes.json'):
        # The client reads only the routes file next to itself (archive_search.py ROUTES).
        raise Blocked('search routes file must be search-routes.json next to the installed search client')
    w = cfg['worker']
    if not isinstance(w, dict) or w.get('kind') not in ('launchd', 'none'):
        raise Blocked('invalid worker configuration')
    if w['kind'] == 'launchd':
        if set(w) != {'kind', 'agents_dir', 'log_dir', 'python'}: raise Blocked('invalid worker configuration')
        if not canonical(w['agents_dir'], 'agents dir').is_dir(): raise Blocked('agents dir is missing')
        private_dir(canonical(w['log_dir'], 'log dir'), 'log dir')
        py = Path(w['python'])
        if not py.is_absolute() or not os.access(py, os.X_OK): raise Blocked('--python must be an absolute executable')
    elif set(w) != {'kind'}:
        raise Blocked('invalid worker configuration')
    return cfg


def load_config(kit, private_json):
    cfg = private_json(Path(kit) / '.ai-factory-state' / CONFIG)
    return None if cfg is None else check_config(kit, cfg)


# --- archive server ------------------------------------------------------------------------

class Server:
    """Loopback operator calls. The operator secret is read once, kept in memory, never printed."""

    def __init__(self, cfg):
        self.endpoint = cfg['endpoint']
        self._secret_file = cfg['operator_secret_file']
        self._secret = None

    def _operator(self):
        if self._secret is None:
            private_file(Path(self._secret_file), 'operator secret file')
            try:
                doc = json.loads(Path(self._secret_file).read_bytes())
                value = doc['secret']
            except (ValueError, KeyError, TypeError):
                raise Blocked('operator secret file is not {"secret": ...} JSON') from None
            if not isinstance(value, str) or not value: raise Blocked('operator secret file has no secret')
            self._secret = value
        return self._secret

    def request(self, method, path, body=None, headers=None):
        req = urllib.request.Request(self.endpoint + path, method=method,
                                     data=None if body is None else json.dumps(body).encode())
        for key, value in (headers or {}).items(): req.add_header(key, value)
        if body is not None: req.add_header('Content-Type', 'application/json')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=TIMEOUT) as r:
                raw = r.read(1 << 20)
                return r.status, (json.loads(raw) if raw.strip() else {})
        except urllib.error.HTTPError as e:
            raw = e.read(1 << 16)
            try: detail = json.loads(raw)
            except ValueError: detail = {}
            return e.code, detail if isinstance(detail, dict) else {}
        except (urllib.error.URLError, OSError) as e:
            raise Blocked(f'archive server is not reachable at {self.endpoint} ({type(e).__name__})') from None

    def operator(self, path, body):
        return self.request('POST', path, body, {'X-Operator-Secret': self._operator()})

    def health(self):
        code, _ = self.request('GET', '/health')
        if code != 200: raise Blocked(f'archive server /health answered {code}')

    def mint(self, ident, label, explicit):
        code, d = self.operator('/v1/projects', {'UUID': ident, 'Label': label})
        if code == 201: return 'minted'
        if code == 400 and 'already exists' in str(d.get('error', '')):
            if not explicit: raise Blocked('archive project id already exists; pass --id to reuse it deliberately')
            return 'existing'
        raise Blocked(f'minting the archive project failed (HTTP {code})')

    def consent(self, ident):
        code, _ = self.operator('/v1/consent', {'Project': ident, 'Provider': 'claude-code',
                                                'Capability': 'capture', 'Enabled': True})
        if code != 200: raise Blocked(f'turning on capture consent failed (HTTP {code})')

    def grant(self, principal, ident, op, secret):
        code, d = self.operator('/v1/grants', {'principal_id': principal, 'kind': 'agent', 'projects': [ident],
                                               'ops': [op], 'secret': secret})
        epoch = d.get('epoch')
        if code != 201 or type(epoch) is not int or epoch <= 0 or d.get('principal_id') != principal:
            raise Blocked(f'issuing the {op} grant failed (HTTP {code})')
        return epoch

    def revoke(self, principal):
        code, d = self.operator('/v1/grants/revoke', {'principal_id': principal})
        if code != 200: raise Blocked(f'revoking {principal} failed (HTTP {code}); it may still be live')

    def whoami(self, ident, op, principal, epoch, secret):
        code, _ = self.request('GET', '/v1/whoami?' + urllib.parse.urlencode({'project': ident, 'op': op}),
                               headers={'X-Principal-Id': principal, 'X-Grant-Epoch': str(epoch), 'X-Secret': secret})
        return code == 200


# --- files ----------------------------------------------------------------------------------

def plan_files(cfg, kit, ident, name, capture):
    files = {'search_secret': str(Path(cfg['search_dir']) / f'{name}.search.secret'),
             'search_epoch': str(Path(cfg['search_dir']) / f'{name}.search.epoch'),
             'search_contract': str(Path(kit) / '.ai-factory-state' / 'search-contracts' / f'{ident}.md')}
    if capture:
        files['capture_credential'] = str(Path(cfg['capture_dir']) / f'{name}.cred.json')
    worker = None
    if capture and cfg['worker']['kind'] == 'launchd':
        label = LABEL.format(name=name)
        files['plist'] = str(Path(cfg['worker']['agents_dir']) / f'{label}.plist')
        worker = label
    return files, worker


def new_record(ident, name, files, worker, capture):
    principals = {'search': f'p-{ident}-search'} | ({'capture': f'p-{ident}-capture'} if capture else {})
    return {'principals': principals, 'alias': name, 'files': files, 'worker': worker}


def check_record(rec):
    if (not isinstance(rec, dict) or set(rec) != RECORD_KEYS or not isinstance(rec['principals'], dict)
            or not {'search'} <= set(rec['principals']) <= {'search', 'capture'}
            or not isinstance(rec['files'], dict) or not isinstance(rec['alias'], str)
            or (rec['worker'] is not None and not isinstance(rec['worker'], str))
            or ('capture' in rec['principals']) != ('capture_credential' in rec['files'])
            or (rec['worker'] is not None) != ('plist' in rec['files'])):
        raise Blocked('invalid archive record in the project list')
    return rec


def credential_bytes(principal, epoch, secret):
    return (json.dumps({'principal_id': principal, 'epoch': epoch, 'secret': secret}) + '\n').encode()


def routes_doc(raw):
    if raw is None: return {'version': 1, 'projects': {}}
    doc = json.loads(raw)
    if not isinstance(doc, dict) or doc.get('version') != 1 or not isinstance(doc.get('projects'), dict):
        raise Blocked('search routes file is not a version-1 routes document')
    return doc


def routes_with(raw, alias, route):
    doc = routes_doc(raw)
    if route is None: doc['projects'].pop(alias, None)
    else: doc['projects'][alias] = route
    return (json.dumps(doc, indent=2, ensure_ascii=False) + '\n').encode()


def search_route(cfg, ident, rec):
    port = urllib.parse.urlsplit(cfg['endpoint']).port
    return {'project_id': ident, 'principal_id': rec['principals']['search'], 'credential_format': 'split',
            'secret_file': rec['files']['search_secret'], 'epoch_file': rec['files']['search_epoch'], 'port': port}


def contract_bytes(kit, alias):
    client = Path(kit) / SEARCH_CLIENT
    return (f'# Conversation-archive search (read-only)\n\n'
            f'Search this project\'s captured conversations with the installed search client:\n\n'
            f'    python3 -I {client} {alias} \'<terms>\'\n\n'
            f'Add `--cursor <next_cursor>` to continue the same query. The alias `{alias}` selects a '
            f'search-only grant; the client reads its own route and credential files. Never pass, print or '
            f'substitute any secret, and never use the operator or capture credential for search. Zero hits '
            f'prove nothing about completeness. Generated by `kit.py project install`.\n').encode()


def plist_bytes(cfg, kit, ident, route, rec, name):
    w = cfg['worker']
    doc = {'Label': rec['worker'],
           'ProgramArguments': [w['python'], '-I', '-B', str(Path(kit) / BRIDGE), '--worker'],
           'EnvironmentVariables': {'AF_CAPTURE_PROJECT': ident, 'AF_CAPTURE_SOURCE': route['source_instance'],
                                    'AF_CAPTURE_AGENT_CREDENTIAL_FILE': route['credential_file'],
                                    'AF_CAPTURE_QUEUE_DIR': route['queue_dir'],
                                    'AF_CAPTURE_ENDPOINT': cfg['endpoint']},
           'StandardErrorPath': str(Path(w['log_dir']) / f'{name}.capture-worker.log'),
           'Umask': 63, 'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 30, 'ProcessType': 'Background'}
    return plistlib.dumps(doc, sort_keys=True)


# --- launchd --------------------------------------------------------------------------------

def launchctl(*args):
    r = subprocess.run([LAUNCHCTL, *args], capture_output=True, text=True, timeout=30)
    return r.returncode


def domain():
    return f'gui/{os.getuid()}'


def worker_loaded(label):
    return launchctl('print', f'{domain()}/{label}') == 0


def bootstrap(plist):
    return launchctl('bootstrap', domain(), plist) == 0


def bootout(label):
    if not worker_loaded(label): return True
    return launchctl('bootout', f'{domain()}/{label}') == 0


# --- probes of an existing enrollment ------------------------------------------------------

def read_search(rec):
    def line(path):
        private_file(Path(path), 'search credential file')
        raw = Path(path).read_bytes()
        return raw[:-1].decode('ascii') if raw.endswith(b'\n') else raw.decode('ascii')
    return int(line(rec['files']['search_epoch'])), line(rec['files']['search_secret'])


def read_capture(rec):
    path = Path(rec['files']['capture_credential'])
    private_file(path, 'capture credential file')
    d = json.loads(path.read_bytes())
    return d['principal_id'], d['epoch'], d['secret']


def probe(server, ident, rec):
    """Problems with a recorded enrollment: missing files or a grant the server no longer accepts."""
    problems = []
    for role, path in sorted(rec['files'].items()):
        if not os.path.lexists(path): problems.append(f'{role} file is missing')
    if problems: return problems
    try:
        epoch, secret = read_search(rec)
        if not server.whoami(ident, 'search', rec['principals']['search'], epoch, secret):
            problems.append(f"search grant {rec['principals']['search']} is not accepted (revoked or replaced)")
        if 'capture' in rec['principals']:
            principal, epoch, secret = read_capture(rec)
            if principal != rec['principals']['capture'] or not server.whoami(ident, 'capture', principal, epoch, secret):
                problems.append(f"capture grant {rec['principals']['capture']} is not accepted (revoked or replaced)")
    except (ValueError, KeyError, TypeError, UnicodeError) as e:
        problems.append(f'a credential file is unreadable ({type(e).__name__})')
    return problems


def new_secret():
    return secrets.token_urlsafe(32)
