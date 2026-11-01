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
#    block types are COUNTED and surfaced in the visible status (type names only, no content),
#    so a future contentful type is observable rather than dropped in silence.
#  - Visible status carries NO payload text and NO secret.
#  - Fail-safe: any error -> status with an error field + exit 0; a Stop hook never blocks.
import sys, json, os, time, urllib.request, urllib.parse

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


def read_transcript(path):
    """Return (objs, skipped_unparseable). Independent JSON objects per line; a partial or
    foreign last line is simply not a conversation record and is counted, never fatal."""
    objs, skipped = [], 0
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                objs.append(json.loads(line))
            except Exception:
                skipped += 1
    return objs, skipped


def emit_status(status, status_file):
    """Write a compact status with NO payload text and NO secret. Always to stderr; also
    appended to status_file when configured."""
    line = json.dumps(status, ensure_ascii=False, sort_keys=True)
    sys.stderr.write("af-claude-capture " + line + "\n")
    if status_file:
        try:
            with open(status_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def main():
    endpoint = os.environ.get("AF_CAPTURE_ENDPOINT", "http://127.0.0.1:8780")
    project = os.environ.get("AF_CAPTURE_PROJECT", "")
    source = os.environ.get("AF_CAPTURE_SOURCE", "claude-code-dg")
    secret_file = os.environ.get("AF_CAPTURE_OPERATOR_SECRET_FILE", "")
    status_file = os.environ.get("AF_CAPTURE_STATUS_FILE", "")
    status = {"ts": int(time.time()), "source": source, "delivered": False}

    try:
        if not project or not secret_file:
            status["error"] = "missing project/secret_file config"
            emit_status(status, status_file); return
        ev = json.loads(sys.stdin.read())
        status["event"] = ev.get("hook_event_name")
        session_id = ev.get("session_id") or ""
        status["session_id"] = session_id
        tp = ev.get("transcript_path") or ""
        if not tp or not os.path.isfile(tp):
            status["error"] = "no transcript_path"
            emit_status(status, status_file); return

        objs, skipped = read_transcript(tp)
        status["skipped_unparseable_lines"] = skipped
        prompt, assistant, stats = select_turn(objs, session_id)
        status["unrecognized_line_types"] = stats["unrecognized_line_types"]
        status["unknown_block_types"] = stats["unknown_block_types"]
        status["other_session_lines"] = stats["other_session_lines"]
        out_recs = [r for r in (prompt, assistant) if r is not None]
        status["selected"] = [r["type"] for r in out_recs]
        if not out_recs:
            status["error"] = "no capturable user/assistant turn"
            emit_status(status, status_file); return

        body = ("\n".join(to_line(r) for r in out_recs)).encode("utf-8")
        with open(secret_file, "r", encoding="utf-8") as f:
            secret = json.load(f).get("secret") or ""
        if not secret:
            status["error"] = "empty operator secret"
            emit_status(status, status_file); return

        url = "%s/v1/capture/claude-code?project=%s&source_instance=%s" % (
            endpoint, urllib.parse.quote(project, safe=""), urllib.parse.quote(source, safe=""))
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/x-ndjson")
        req.add_header("X-Operator-Secret", secret)
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            payload = json.loads(resp.read().decode("utf-8") or "{}")
            status["http_status"] = resp.getcode()
            status["accepted"] = payload.get("accepted")
            status["committed"] = payload.get("committed")
            status["redactions"] = len(payload.get("redactions") or [])
            status["delivered"] = True
        except urllib.error.HTTPError as e:
            status["http_status"] = e.code
            status["error"] = "http %d" % e.code  # body not echoed (may contain input)
        except Exception as e:
            status["error"] = "post failed: %s" % type(e).__name__
        emit_status(status, status_file)
    except SystemExit:
        raise
    except Exception as e:
        status["error"] = "bridge exception: %s" % type(e).__name__
        emit_status(status, status_file)
    # Never block the session.
    sys.exit(0)


if __name__ == "__main__":
    main()
