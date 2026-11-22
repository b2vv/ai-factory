#!/usr/bin/env python3
# Claude Code Stop-hook capture bridge (delivery only) -> AI Factory storage
# POST /v1/capture/claude-code. The vetted Go adapter (internal/capture, provider
# "claude-code") remains the SOLE authority for redaction + credential sanitization before
# anything reaches the WAL/archive; this bridge only selects, normalizes, and transmits.
#
# Design points enforced here (see README.md):
#  - Scope: project + source_instance are an EXPLICIT operator mapping (argv/env); cwd is
#    never used to infer project membership.
#  - Identity: only transcript lines whose sessionId matches the hook's session_id are
#    considered, so a stale/wrong transcript_path can never capture another session.
#  - Non-text payload never leaves the process: thinking/tool blocks are forwarded as
#    TYPE ONLY (no bytes); the adapter still records the redaction.
#  - Nothing is silently lost: unrecognized top-level line types and unrecognized content
#    block types are COUNTED and surfaced in the visible status (counts only, no content),
#    so a future contentful type is observable rather than dropped in silence.
#  - Visible status carries NO payload text and NO secret.
#  - Fail-safe: any error -> status with an error field + exit 0; a Stop hook never blocks.
import sys, json, os, time, stat, urllib.request, urllib.parse, urllib.error
# -I excludes cwd: import only the reviewed sibling module, never project modules.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_queue import Queue, canonical_body, deadline, DeadlineExpired

# Top-level transcript record types that are known, non-conversation bookkeeping: skipped
# quietly. Anything NOT here and NOT user/assistant is surfaced as unrecognized (never lost).
KNOWN_META_LINE_TYPES = frozenset({
    "summary", "system", "custom-title", "agent-name", "mode", "bridge-session",
    "file-history-snapshot", "file-history-delta", "attachment", "queue-operation",
    "atis-latch", "api-request-shape", "api-request-blob", "api-request", "last-prompt",
    "tools-used", "cost-state", "permission-mode", "ai-title", "x-fallback",
})
# Content block kinds forwarded to the adapter (text carries bytes; the rest type-only).
KNOWN_BLOCK_TYPES = frozenset({"text", "thinking", "tool_use", "tool_result"})
# Content block kinds that are known to be non-text and are dropped quietly (never captured).
KNOWN_NONTEXT_DROP = frozenset({"image"})


def normalize_content(content):
    """Return (blocks, unknown_block_types).

    blocks is the adapter's modeled shape: text blocks keep their text; other KNOWN blocks
    are emitted TYPE-ONLY; image (known non-text) is dropped quietly. Any other block kind is
    dropped but its type name is returned in unknown_block_types so the caller can surface it.
    Returns (None, []) when content is neither a string nor a list of block objects."""
    unknown = []
    if isinstance(content, str):
        return ([{"type": "text", "text": content}] if content else []), unknown
    if isinstance(content, list):
        out = []
        for b in content:
            if not isinstance(b, dict):
                return None, unknown
            t = b.get("type")
            if t == "text":
                txt = b.get("text", "")
                if txt:
                    out.append({"type": "text", "text": txt})
            elif t in KNOWN_BLOCK_TYPES:
                out.append({"type": t})  # type only; no bytes leave the process
            elif t in KNOWN_NONTEXT_DROP:
                pass  # known non-text; never captured
            else:
                unknown.append(t if isinstance(t, str) else "<non-string>")
        return out, unknown
    return None, unknown


def has_visible_text(blocks):
    return any(b.get("type") == "text" for b in blocks)


def select_turn(objs, session_id):
    """Pick this turn's human prompt + final assistant answer from parsed transcript objects,
    restricted to the given session_id. Returns (prompt, assistant, stats). prompt/assistant
    are normalized records or None. stats surfaces everything dropped so nothing is silent."""
    stats = {
        "lines_total": len(objs),
        "unrecognized_line_types": {},   # type name -> count (non user/assistant, non-meta)
        "unknown_block_types": {},       # block type name -> count
        "other_session_lines": 0,        # user/assistant lines of a different session
    }
    convo, by_uuid = [], {}
    for o in objs:
        t = o.get("type")
        if t in ("user", "assistant"):
            sess = o.get("sessionId") or ""
            if session_id and sess and sess != session_id:
                stats["other_session_lines"] += 1
                continue
            uuid = o.get("uuid") or ""
            msg = o.get("message")
            if not uuid or not sess or not isinstance(msg, dict) or msg.get("role") != t:
                continue
            blocks, unknown = normalize_content(msg.get("content"))
            for ut in unknown:
                stats["unknown_block_types"][ut] = stats["unknown_block_types"].get(ut, 0) + 1
            if blocks is None:
                continue
            rec = {"type": t, "uuid": uuid, "parentUuid": o.get("parentUuid", ""),
                   "sessionId": sess, "blocks": blocks}
            convo.append(rec)
            by_uuid[uuid] = rec
        elif t in KNOWN_META_LINE_TYPES or t is None:
            continue  # known bookkeeping, skipped quietly
        else:
            stats["unrecognized_line_types"][t] = stats["unrecognized_line_types"].get(t, 0) + 1

    if not convo:
        return None, None, stats

    assistant = None
    for rec in reversed(convo):
        if rec["type"] == "assistant" and has_visible_text(rec["blocks"]):
            assistant = rec
            break
    if assistant is None:
        return None, None, stats

    prompt = None
    cur = by_uuid.get(assistant["parentUuid"])
    seen = set()
    while cur is not None and cur["uuid"] not in seen:
        seen.add(cur["uuid"])
        if cur["type"] == "user" and has_visible_text(cur["blocks"]):
            prompt = cur
            break
        cur = by_uuid.get(cur["parentUuid"])
    if prompt is None:
        aidx = convo.index(assistant)
        for rec in reversed(convo[:aidx]):
            if rec["type"] == "user" and has_visible_text(rec["blocks"]):
                prompt = rec
                break
    return prompt, assistant, stats


def to_line(r):
    return json.dumps({
        "type": r["type"], "uuid": r["uuid"], "parentUuid": r["parentUuid"],
        "sessionId": r["sessionId"], "message": {"role": r["type"], "content": r["blocks"]},
    }, ensure_ascii=False)


TRANSCRIPT_TAIL = 32 * 1024 * 1024
POST_SOCKET_TIMEOUT = 4   # the server can pause for a couple of seconds behind its own lock
POST_DEADLINE = 5         # read retries (2.4 s) + this stay inside the 8-second process alarm


def read_transcript(path):
    """Return (objs, skipped_unparseable). Independent JSON objects per line; a partial or
    foreign last line is simply not a conversation record and is counted, never fatal."""
    objs, skipped = [], 0
    # A long session's transcript outgrows the bound, but the turn to capture is at its end:
    # read only the last TRANSCRIPT_TAIL bytes and drop the first, partial line.
    size = os.stat(path).st_size
    with open(path, "rb") as f:
        if size > TRANSCRIPT_TAIL:
            f.seek(size - TRANSCRIPT_TAIL)
            f.readline()
        data = f.read(TRANSCRIPT_TAIL)
    for line in data.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            objs.append(json.loads(line))
        except Exception:
            skipped += 1
    return objs, skipped


def emit_status(status, status_file, prefix="af-claude-capture "):
    """Best-effort bounded diagnostics; refuse symlinks/FIFOs/nonprivate log files.

    Independently bounded even after the whole-hook alarm has fired. Never wait for
    a reader on a FIFO. Failure to log cannot hold the host or erase queue contents.
    """
    safe = dict(status)
    if isinstance(safe.get('source'),str):safe['source'] = safe['source'][:128]
    raw = (json.dumps(safe, ensure_ascii=False, sort_keys=True)+"\n").encode()
    if len(raw)>4096:raw=b'{"delivered":false,"error":"status exceeds limit"}\n'
    try:
        with deadline(.2):
            os.write(2,prefix.encode()+raw)
    except (Exception,DeadlineExpired):
        pass
    if status_file:
        fd=None
        try:
            with deadline(.2):
                fd=os.open(status_file,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NONBLOCK|os.O_NOFOLLOW,0o600)
                info=os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_nlink != 1 or stat.S_IMODE(info.st_mode)!=0o600):
                    return
                os.write(fd,raw)
        except (Exception,DeadlineExpired):
            pass
        finally:
            if fd is not None:os.close(fd)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def credentials(agent_file, secret_file):
    if bool(secret_file) == bool(agent_file):
        raise ValueError("exactly one credential file required")
    with open(agent_file or secret_file, "r", encoding="utf-8") as f:
        credential = json.loads(f.read(16385))
    if agent_file:
        if (not isinstance(credential, dict)
                or not isinstance(credential.get("principal_id"), str)
                or not credential["principal_id"].strip()
                or type(credential.get("epoch")) is not int or credential["epoch"] <= 0
                or not isinstance(credential.get("secret"), str) or not credential["secret"].strip()):
            raise ValueError("invalid scoped capture credential")
        return {"X-Principal-Id": credential["principal_id"],
                "X-Grant-Epoch": str(credential["epoch"]), "X-Secret": credential["secret"]}, "agent:"+credential["principal_id"]
    if not isinstance(credential, dict) or not isinstance(credential.get("secret"), str) or not credential["secret"]:
        raise ValueError("invalid operator credential")
    return {"X-Operator-Secret": credential["secret"]}, "operator"


def post_body(endpoint, project, source, headers, body, expected, opener=None):
    url = "%s/v1/capture/claude-code?project=%s&source_instance=%s" % (
        endpoint, urllib.parse.quote(project, safe=""), urllib.parse.quote(source, safe=""))
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-ndjson")
    for name, value in headers.items():
        req.add_header(name, value)
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open
    try:
        with deadline(POST_DEADLINE):
            with opener(req, timeout=POST_SOCKET_TIMEOUT) as resp:
                raw = resp.read(65537)
                if len(raw) > 65536:
                    return {"error":"invalid acknowledgement"}
                payload = json.loads(raw)
                code = resp.getcode()
        expected_ids = [[project,source,r['sessionId'],r['uuid']]
                        for r in map(json.loads,body.splitlines())]
        receipts = payload.get('receipts') if isinstance(payload,dict) else None
        receipt_ids = [json.loads(r) for r in receipts] if isinstance(receipts,list) else None
        if (code != 200 or not isinstance(payload, dict)
                or receipt_ids != expected_ids
                or type(payload.get("accepted")) is not int or payload["accepted"] != expected
                or type(payload.get("committed")) is not int or payload["committed"] < 0
                or payload.get("drain_error")
                or (payload.get("redactions") is not None and not isinstance(payload["redactions"],list))):
            return {"http_status":code, "error":"incomplete acknowledgement"}
        return {"http_status":code, "accepted":payload["accepted"], "committed":payload["committed"],
                "delivered":True, "redactions":len(payload.get("redactions") or [])}
    except urllib.error.HTTPError as e:
        return {"http_status":e.code, "error":"http %d" % e.code}
    except (Exception, DeadlineExpired) as e:
        # A spent wall budget is a failed attempt to record, not a reason to drop the queue row's state.
        return {"error":"post failed: %s" % type(e).__name__}


def drain(queue, endpoint, project, source, headers):
    row = queue.claim()
    if row is None:
        return {"attempted":False, "delivered":False}
    result = post_body(endpoint, project, source, headers, row['body'], row['count'])
    result['queue_state'] = queue.finish(row, result)
    result['attempted'] = True
    return result


def run(mode="hook", quiet_idle=False):
    endpoint = os.environ.get("AF_CAPTURE_ENDPOINT", "http://127.0.0.1:8780").rstrip('/')
    project = os.environ.get("AF_CAPTURE_PROJECT", "")
    source = os.environ.get("AF_CAPTURE_SOURCE", "claude-code")
    secret_file = os.environ.get("AF_CAPTURE_OPERATOR_SECRET_FILE", "")
    agent_file = os.environ.get("AF_CAPTURE_AGENT_CREDENTIAL_FILE", "")
    status_file = os.environ.get("AF_CAPTURE_STATUS_FILE", "")
    status = {"ts":int(time.time()), "source":source, "delivered":False, "queued":False}
    queue = None
    try:
        # Credentials must never follow redirects, proxies or leave loopback.
        parsed = urllib.parse.urlsplit(endpoint)
        if (not project or parsed.scheme != 'http' or parsed.hostname != '127.0.0.1'
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("invalid local route")
        headers, principal = credentials(agent_file, secret_file)
        root = os.environ.get("AF_CAPTURE_QUEUE_DIR") or os.path.join(os.path.dirname(os.path.realpath(agent_file or secret_file)), 'capture-queue')
        queue = Queue(root, {'endpoint':endpoint,'project':project,'source':source,'principal':principal})
        if mode == 'status':
            status['queue'] = queue.status()
            return status
        if mode == 'retry-blocked':
            status['requeued'] = queue.retry_blocked()
            status['queue'] = queue.status()
            return status
        if mode == 'hook':
            raw = sys.stdin.read(1024*1024+1)
            if len(raw) > 1024*1024:
                raise ValueError("hook input exceeds limit")
            ev = json.loads(raw)
            session_id = ev.get("session_id") or ""
            if ev.get("hook_event_name") != 'Stop' or not isinstance(session_id,str) or not session_id:
                raise ValueError("Stop event/session required")
            status['event'] = 'Stop'
            tp = ev.get("transcript_path") or ""
            if not tp or not os.path.isfile(tp):
                raise ValueError("no transcript_path")
            attempts = min(6,max(1,int(os.environ.get("AF_CAPTURE_READ_ATTEMPTS", "6"))))
            delay = min(.4,max(0,float(os.environ.get("AF_CAPTURE_READ_DELAY", ".4"))))
            for attempt in range(attempts):
                objs, skipped = read_transcript(tp)
                prompt, assistant, stats = select_turn(objs, session_id)
                if assistant is not None:
                    break
                if attempt+1 < attempts:
                    time.sleep(delay)
            status.update(read_attempts=attempt+1, skipped_unparseable_lines=skipped,
                          other_session_lines=stats['other_session_lines'])
            # Unknown transcript type strings are untrusted, so only counts enter status.
            status['unrecognized_line_types'] = sum(stats['unrecognized_line_types'].values())
            status['unknown_block_types'] = sum(stats['unknown_block_types'].values())
            recs = [r for r in (prompt,assistant) if r is not None]
            status['selected'] = [r['type'] for r in recs]
            if not recs:
                raise ValueError("no capturable turn")
            key, body = canonical_body([json.loads(to_line(r)) for r in recs])
            state = queue.enqueue(key, body, len(recs))
            status.update(queued=True, current_state=state)
            if state == 'done':
                status.update(delivered=True, deduplicated=True, queue=queue.status())
                return status
        # Hook tries at most ONE item, possibly older than this turn. Explicit worker
        # polls this mode repeatedly. Flush remains bounded by the outer deadline.
        result = drain(queue, endpoint, project, source, headers)
        status.update(result)
        if mode == 'hook':
            # Do not misreport delivery of an older item as delivery of this turn.
            current_row = queue.db.execute('SELECT state FROM items WHERE id=?',(key,)).fetchone()
            current = current_row[0] if current_row else 'receipt_evicted'
            if current_row is None:
                status['delivery_confirmation'] = 'not_retained'
            status['drained_delivered'] = status['delivered']
            status['current_state'] = current
            status['delivered'] = current == 'done'
        status['queue'] = queue.status()
        return status
    except Exception as e:
        # Exception messages can contain paths, SQL or payload. Only stable categories.
        status['error'] = 'bridge failure: '+type(e).__name__
        if isinstance(e, ValueError) and str(e) in ('queue full; turn not queued','identity payload conflict'):
            status['error'] = str(e)
        return status
    finally:
        if queue is not None:
            queue.close()
        if not quiet_idle or status.get("attempted") or status.get("error") or status.get("queue",{}).get("blocked"):
            emit_status(status, status_file)


def main():
    os.umask(0o077)
    mode = sys.argv[1].removeprefix('--') if len(sys.argv)==2 else 'hook'
    if len(sys.argv)>2 or mode not in ('hook','flush','status','retry-blocked','worker'):
        emit_status({'delivered':False,'error':'invalid command'},'')
        return
    if mode == 'worker':
        # Supervisor opt-in only. No process spawning/registration by hooks.
        while True:
            with deadline(8):
                run('flush', quiet_idle=True)
            time.sleep(30)
    else:
        with deadline(8):
            run(mode)


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt, DeadlineExpired) as e:
        emit_status({'delivered':False,'error':'bridge stopped: '+type(e).__name__}, '')
    sys.exit(0)
