"""Private durable Claude capture spool. No credential/header is persisted.

POSIX local-filesystem only, one SQLite partition per route/principal. Completed
receipts form a bounded cache; pending/blocked payload is never evicted. A worker/supervisor
must be explicitly configured for delivery when there are no more hooks.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import stat
import time
import uuid

REDACTED = '[REDACTED: possible credential content]'
# Mirrors internal/capture/sanitize.go known-credentials-v1. Go word boundaries
# and whitespace are ASCII, but case-folding includes Kelvin sign and long s.
INDICATORS = [
    r'(?i)-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----',
    r'''(?i)\b(?:authorization|proxy-authorization|cookie|set-cookie)\b["'\s]*[:=]''',
    r'''(?i)\b(?:[a-z0-9]+[_-])*(?:password|passwd|pwd|secret|secrets|token|credentials|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|session[_-]?token|aws_secret_access_key|aws_session_token)\b["'\s]*[:=]''',
    r'(?i)\b(?:bearer|basic)\s+[A-Za-z0-9+/=_-]{8,}',
    r'(?i)\b[a-z][a-z0-9+.-]*://[^\s/]+@',
    r'\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}|xox[baprs]-[A-Za-z0-9-]{16,}|(?:AKIA|ASIA)[A-Z0-9]{16})\b',
    r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b',
]
ASCII_WORD = r"(?-i:[A-Za-z0-9_])"
BOUNDARY = rf"(?:(?<={ASCII_WORD})(?!{ASCII_WORD})|(?<!{ASCII_WORD})(?={ASCII_WORD}))"

def go_pattern(pattern):
    pattern = pattern.replace(r"\b", BOUNDARY)
    pattern = pattern.replace(r"\s]*", r" \t\n\f\r]*")
    pattern = pattern.replace(r"\s+", r"[ \t\n\f\r]+")
    pattern = pattern.replace(r"[^\s/]", r"[^ \t\n\f\r/]")
    return re.compile(pattern)

PATTERNS = [go_pattern(p) for p in INDICATORS]

def contains_credential(text):
    # Python adds Turkish dotted/dotless I to ASCII-insensitive classes; Go's
    # Unicode SimpleFold does not. Non-ASCII sentinel preserves boundary/wildcard
    # behavior while excluding those two extra Python-only equivalences.
    matched_text = text.replace('İ','\uffff').replace('ı','\uffff')
    return any(p.search(matched_text) for p in PATTERNS)


def canonical_body(records):
    """Withhold entire joined visible text before persistence, preserve identity.

    Not a general secret detector. Unknown/unlabelled secrets may remain, just as
    in the original transcript. Hidden/tool bytes are absent before this point.
    """
    out = []
    for record in records:
        r = json.loads(json.dumps(record))
        text = '\n'.join(b['text'] for b in r['message']['content']
                         if b['type'] == 'text' and b.get('text'))
        if contains_credential(text):
            r['message']['content'] = [b for b in r['message']['content'] if b['type'] != 'text']
            r['message']['content'].append({'type': 'text', 'text': REDACTED})
        out.append(r)
    body = '\n'.join(json.dumps(r, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')) for r in out).encode()
    identities = [(r['sessionId'], r['uuid']) for r in out]
    key = hashlib.sha256(json.dumps(identities).encode()).hexdigest()
    return key, body


class DeadlineExpired(BaseException):
    """Must not be swallowed by parser/transport generic Exception handlers."""


@contextlib.contextmanager
def deadline(seconds):
    """POSIX main-thread wall bound; preserves an enclosing earlier deadline."""
    previous = signal.getsignal(signal.SIGALRM)
    old_delay, old_interval = signal.getitimer(signal.ITIMER_REAL)
    start = time.monotonic()
    def expired(*_):
        raise DeadlineExpired('deadline')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(seconds, old_delay) if old_delay else seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if old_delay:
            signal.setitimer(signal.ITIMER_REAL, max(.000001, old_delay-(time.monotonic()-start)), old_interval)


def private_path(path, directory=False):
    info = os.lstat(path)
    if (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or (not stat.S_ISDIR(info.st_mode) if directory else
                (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))):
        raise ValueError('nonprivate queue path')


class BoundedConnection(sqlite3.Connection):
    """SQLite-native lock waiting, never application transaction/COMMIT replay.

    Each statement waits at most one second, clamped to the enclosing hook alarm.
    Kernel stalls are outside a Python wall-clock guarantee. Expired budget fails
    before entering SQLite; lock exhaustion remains a visible OperationalError.
    """
    def execute(self, sql, parameters=()):
        remaining, _ = signal.getitimer(signal.ITIMER_REAL)
        wait = min(1.0, max(0.0, remaining - .01)) if remaining else 1.0
        if remaining and wait <= 0:
            raise DeadlineExpired('deadline')
        sqlite3.Connection.execute(self, 'PRAGMA busy_timeout=' + str(int(wait * 1000)))
        return sqlite3.Connection.execute(self, sql, parameters)


class Queue:
    def __init__(self, root, scope, max_items=1000, max_bytes=32*1024*1024,
                 max_receipts=10000, max_attempts=20):
        if type(max_receipts) is not int or max_receipts < 1:
            raise ValueError('positive receipt limit required')
        root = Path(root)
        if not root.is_absolute() or os.path.realpath(root) != str(root):
            raise ValueError('canonical queue path required')
        # Parent must already exist; never create unreviewed directory chains.
        if not root.parent.is_dir():
            raise ValueError('queue parent absent')
        created = False
        try:
            root.mkdir(mode=0o700)
            created = True
        except FileExistsError:
            pass
        private_path(root, True)
        if created:
            fd = os.open(root.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        self.scope = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()
        self.path = root / (self.scope + '.sqlite3')
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        os.close(fd)
        private_path(self.path)
        journal = Path(str(self.path)+'-journal')
        try:
            private_path(journal)
        except FileNotFoundError:
            # DELETE-mode commits remove this ephemeral file concurrently. Only
            # absence is normal; every existing journal still passes all guards.
            pass
        except ValueError:
            # macOS can return st_nlink=0 for a journal unlinked during lstat.
            # Accept only confirmed disappearance, never an existing unsafe file.
            if os.path.lexists(journal):
                raise
        self.max_items, self.max_bytes = max_items, max_bytes
        self.max_receipts, self.max_attempts = max_receipts, max_attempts
        self.db = sqlite3.connect(self.path, timeout=0, isolation_level=None, factory=BoundedConnection)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA secure_delete=ON')
        self.db.execute('CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, digest TEXT NOT NULL, body BLOB, count INTEGER NOT NULL, state TEXT NOT NULL, created REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next REAL NOT NULL DEFAULT 0, lease TEXT, reason TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS receipt_stats (singleton INTEGER PRIMARY KEY CHECK(singleton=1), pruned INTEGER NOT NULL)')
        self.db.execute('INSERT OR IGNORE INTO receipt_stats VALUES(1,0)')
        # Persist new directory entry, not merely database pages.
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def close(self):
        self.db.close()

    @contextlib.contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            # A signal/error after COMMIT may leave no active transaction. Never
            # replay it or replace that ambiguous outcome with a rollback error.
            if self.db.in_transaction:
                try:
                    self.db.execute('ROLLBACK')
                except BaseException:
                    pass
            raise

    def _trim_receipts(self):
        """Caller owns write transaction. Only terminal, ACKed rows are disposable."""
        excess = self.db.execute("SELECT count(*) FROM items WHERE state='done'").fetchone()[0] - self.max_receipts
        if excess > 0:
            removed = self.db.execute("DELETE FROM items WHERE state='done' AND id IN (SELECT id FROM items WHERE state='done' ORDER BY created,id LIMIT ?)", (excess,)).rowcount
            self.db.execute('UPDATE receipt_stats SET pruned=pruned+? WHERE singleton=1', (removed,))

    def enqueue(self, key, body, count):
        digest = hashlib.sha256(body).hexdigest()
        with self.transaction():
            self._trim_receipts()
            row = self.db.execute('SELECT * FROM items WHERE id=?', (key,)).fetchone()
            if row:
                if row['digest'] != digest:
                    raise ValueError('identity payload conflict')
                return row['state']
            pending, size = self.db.execute("SELECT count(*), coalesce(sum(length(body)),0) FROM items WHERE state!='done'").fetchone()
            if pending >= self.max_items or size+len(body) > self.max_bytes:
                raise ValueError('queue full; turn not queued')
            self.db.execute("INSERT INTO items(id,digest,body,count,state,created) VALUES(?,?,?,?,'pending',?)", (key,digest,body,count,time.time()))
        return 'pending'

    def claim(self, now=None):
        now = time.time() if now is None else now
        with self.transaction():
            self.db.execute("UPDATE items SET state='blocked',reason='attempt_limit',lease=NULL WHERE state='pending' AND next<=? AND attempts>=?", (now,self.max_attempts))
            row = self.db.execute("SELECT * FROM items WHERE state='pending' AND next<=? ORDER BY created,id LIMIT 1", (now,)).fetchone()
            if row is None:
                return None
            if row['body'] is None or hashlib.sha256(row['body']).hexdigest() != row['digest']:
                self.db.execute("UPDATE items SET state='blocked',reason='corrupt_payload' WHERE id=?", (row['id'],))
                return None
            lease = uuid.uuid4().hex
            self.db.execute('UPDATE items SET attempts=attempts+1,next=?,lease=? WHERE id=?', (now+60,lease,row['id']))
            result = dict(row)
            result.update(lease=lease, attempts=row['attempts']+1)
            return result

    def finish(self, row, result, now=None):
        now = time.time() if now is None else now
        code = result.get('http_status')
        if result.get('delivered'):
            state, reason, due = 'done', None, 0
        elif code is not None and 400 <= code < 500 and code not in (408,429):
            state, reason, due = 'blocked', 'http_'+str(code), 0
        elif row['attempts'] >= self.max_attempts:
            state, reason, due = 'blocked', 'attempt_limit', 0
        else:
            state, reason = 'pending', 'http_'+str(code) if code else 'transport_or_invalid_ack'
            due = now + min(3600, 5*2**min(row['attempts']-1,10))
        with self.transaction():
            self.db.execute('UPDATE items SET state=?,reason=?,next=?,lease=NULL,body=CASE WHEN ?=\'done\' THEN NULL ELSE body END WHERE id=? AND lease=?', (state,reason,due,state,row['id'],row['lease']))
            self._trim_receipts()
        return state

    def status(self):
        counts = dict(self.db.execute('SELECT state,count(*) FROM items GROUP BY state'))
        oldest = self.db.execute("SELECT min(created) FROM items WHERE state!='done'").fetchone()[0]
        return {'pending':counts.get('pending',0),'blocked':counts.get('blocked',0),
                'receipts':counts.get('done',0),
                'receipt_limit':self.max_receipts,
                'receipts_pruned':self.db.execute('SELECT pruned FROM receipt_stats WHERE singleton=1').fetchone()[0],
                'oldest_pending_seconds':int(max(0,time.time()-oldest)) if oldest else 0}

    def retry_blocked(self):
        # Explicit remediation action, never automatic on a later hook/credential change.
        with self.transaction():
            return self.db.execute("UPDATE items SET state='pending',attempts=0,next=0,reason=NULL WHERE state='blocked'").rowcount
