#!/usr/bin/env python3
# Codex lifecycle-event capture catcher (delivery only) -> AI Factory storage
# POST /v1/capture/codex-event. The vetted Go adapter (internal/capture, provider
# "codex-hook-v1", AdaptCodexEvent) remains the SOLE authority for redaction +
# credential sanitization (known-credentials-v1) before anything reaches the WAL/archive;
# this catcher only selects a project, normalizes the documented event, and transmits.
#
# Hook contract (verified against the official docs, learn.chatgpt.com/docs/hooks, and the
# running server source internal/capture/codex_event.go @ b1c195e):
#   Common stdin fields on every command hook: session_id, transcript_path, cwd,
#   hook_event_name, model.
#   UserPromptSubmit adds: turn_id, prompt, permission_mode.
#   Stop             adds: turn_id, stop_hook_active, last_assistant_message, permission_mode.
#   (SubagentStop also carries last_assistant_message+turn_id; it is deliberately IGNORED here
#    so a sub-agent message is never recorded as a top-level turn.)
# The server accepts ONLY the documented subset below; field names are NOT invented.
#
# Design points enforced here (see README.md):
#  - Codex installs a SINGLE global hooks.json, so project membership cannot come from a
#    per-project env like the Claude bridge. It comes from an EXPLICIT operator-authored
#    mapping file (AF_CODEX_CATCHER_MAP): cwd selects which mapping ROW to use; it never
#    grants authority. The server independently authorizes the row's scoped credential
#    against the row's project UUID (requireCapture -> authz.Authorize ... OpCapture).
#  - A cwd that matches no mapped project root is a NO-OP: nothing is read, nothing is sent.
#  - Least privilege: only an AGENT capture credential {principal_id, epoch>0, secret} is
#    accepted. An operator secret is refused (no-op), so this catcher can never wield
#    control-plane authority even if mis-pointed.
#  - Only the documented prompt / last_assistant_message text is forwarded; the server
#    sanitizes. The catcher's own visible status carries NO message text and NO secret.
#  - Fail-safe: any error -> compact status + exit 0. A Codex command hook must never block
#    or fail the turn.
import sys, json, os, time, re, urllib.request, urllib.parse, urllib.error

EVENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,160}$")  # mirrors server codex_event.go eventID
SUPPORTED_EVENTS = ("UserPromptSubmit", "Stop")


def load_mapping(path):
    """Load the explicit operator mapping. Returns a list of normalized rows
    [{root, project, source_instance, credential_file}] sorted by DESCENDING root length
    (longest-prefix wins). Raises ValueError on a malformed file; the caller turns that into
    a no-op status. The mapping holds UUIDs and credential-file paths and is kept OUT of the
    repository (local, operator-authored)."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    rows = raw.get("projects") if isinstance(raw, dict) else raw
    if not isinstance(rows, list) or not rows:
        raise ValueError("mapping has no projects")
    out = []
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError("mapping row not an object")
        root = r.get("root")
        project = r.get("project")
        source = r.get("source_instance")
        cred = r.get("credential_file")
        if not all(isinstance(v, str) and v.strip() for v in (root, project, source, cred)):
            raise ValueError("mapping row missing root/project/source_instance/credential_file")
        out.append({
            "root": os.path.normpath(root),
            "project": project,
            "source_instance": source,
            "credential_file": cred,
        })
    out.sort(key=lambda r: len(r["root"]), reverse=True)
    return out


def select_project(cwd, rows):
    """Return the single mapping row whose root is cwd or a parent directory of cwd
    (longest-prefix match), else None. A path is 'under' root only on a true directory
    boundary, so /a/courses never matches a root of /a/cours."""
    if not isinstance(cwd, str) or not cwd:
        return None
    c = os.path.normpath(cwd)
    for row in rows:  # already longest-first
        root = row["root"]
        if c == root or c.startswith(root + os.sep):
            return row
    return None


def normalize_event(ev):
    """Map a documented Codex hook event to the exact server body.

    Returns (role, body) on success and (reason, None) on a no-op, so the caller tests
    `body is None`. body is the JSON the server's AdaptCodexEvent accepts:
      UserPromptSubmit -> {hook_event_name, session_id, turn_id, prompt}
      Stop             -> {hook_event_name, session_id, turn_id, last_assistant_message}
    Exactly one of prompt / last_assistant_message is set, as the server requires; every
    other stdin field (cwd, transcript_path, model, permission_mode, stop_hook_active, ...)
    is dropped and never transmitted."""
    if not isinstance(ev, dict):
        return "event not an object", None
    event = ev.get("hook_event_name")
    if event not in SUPPORTED_EVENTS:
        return "unsupported event", None
    session_id = ev.get("session_id")
    turn_id = ev.get("turn_id")
    if (not isinstance(session_id, str) or not isinstance(turn_id, str)
            or not EVENT_ID.match(session_id) or not EVENT_ID.match(turn_id)):
        return "bad session/turn id", None
    if event == "UserPromptSubmit":
        prompt = ev.get("prompt")
        if not isinstance(prompt, str) or prompt == "":
            return "empty prompt", None
        return "user", {"hook_event_name": "UserPromptSubmit", "session_id": session_id,
                        "turn_id": turn_id, "prompt": prompt}
    # Stop
    msg = ev.get("last_assistant_message")
    if not isinstance(msg, str) or msg == "":
        return "empty assistant message", None
    return "assistant", {"hook_event_name": "Stop", "session_id": session_id,
                         "turn_id": turn_id, "last_assistant_message": msg}


def agent_headers(credential):
    """Validate an AGENT capture credential and return its headers, or raise ValueError.
    Operator credentials are intentionally rejected (least privilege)."""
    if (not isinstance(credential, dict)
            or not isinstance(credential.get("principal_id"), str)
            or not credential["principal_id"].strip()
            or type(credential.get("epoch")) is not int
            or credential["epoch"] <= 0
            or not isinstance(credential.get("secret"), str)
            or not credential["secret"].strip()):
        raise ValueError("invalid scoped capture credential")
    return {"X-Principal-Id": credential["principal_id"],
            "X-Grant-Epoch": str(credential["epoch"]),
            "X-Secret": credential["secret"]}


def post_event(endpoint, project, source, headers, body, timeout=5, opener=urllib.request.urlopen):
    """POST one event to the server. Returns a status dict fragment with http_status and the
    server's accepted/committed/redactions counts, or an error (never the response body, which
    could echo input)."""
    url = "%s/v1/capture/codex-event?project=%s&source_instance=%s" % (
        endpoint, urllib.parse.quote(project, safe=""), urllib.parse.quote(source, safe=""))
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    for name, value in headers.items():
        req.add_header(name, value)
    try:
        resp = opener(req, timeout=timeout)
        payload = json.loads(resp.read().decode("utf-8") or "{}")
        return {"http_status": resp.getcode(), "accepted": payload.get("accepted"),
                "committed": payload.get("committed"),
                "redactions": len(payload.get("redactions") or []), "delivered": True}
    except urllib.error.HTTPError as e:
        return {"http_status": e.code, "error": "http %d" % e.code}  # body not echoed
    except Exception as e:
        return {"error": "post failed: %s" % type(e).__name__}


def emit_status(status, status_file):
    """Compact status with NO message text and NO secret. Always stderr; appended to
    status_file when configured."""
    line = json.dumps(status, ensure_ascii=False, sort_keys=True)
    sys.stderr.write("af-codex-capture " + line + "\n")
    if status_file:
        try:
            with open(status_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


def run(stdin_text, env):
    """Pure-ish core: decide and (maybe) deliver one event; return the status dict. Network is
    reached only through post_event. No sys.exit here so tests can assert the status."""
    endpoint = env.get("AF_CODEX_ENDPOINT", "http://127.0.0.1:8780")
    map_path = env.get("AF_CODEX_CATCHER_MAP", "")
    status = {"ts": int(time.time()), "delivered": False}
    try:
        ev = json.loads(stdin_text)
    except Exception:
        status["error"] = "unparseable event"
        return status
    status["event"] = ev.get("hook_event_name") if isinstance(ev, dict) else None

    role, body = normalize_event(ev)
    if body is None:
        status["skipped"] = role  # reason string; no payload
        return status
    status["role"] = role
    status["session_id"] = body["session_id"]
    status["turn_id"] = body["turn_id"]

    if not map_path:
        status["error"] = "no mapping configured"
        return status
    try:
        rows = load_mapping(map_path)
    except Exception as e:
        status["error"] = "bad mapping: %s" % type(e).__name__
        return status

    cwd = ev.get("cwd") or ""
    row = select_project(cwd, rows)
    if row is None:
        status["skipped"] = "cwd not mapped"  # unknown project -> never captured
        return status
    status["project"] = row["project"]
    status["source"] = row["source_instance"]

    try:
        with open(row["credential_file"], "r", encoding="utf-8") as f:
            credential = json.load(f)
        headers = agent_headers(credential)
    except ValueError as e:
        status["error"] = str(e)
        return status
    except Exception as e:
        status["error"] = "credential unreadable: %s" % type(e).__name__
        return status

    status.update(post_event(endpoint, row["project"], row["source_instance"], headers, body))
    return status


def main():
    status_file = os.environ.get("AF_CODEX_STATUS_FILE", "")
    try:
        status = run(sys.stdin.read(), os.environ)
    except SystemExit:
        raise
    except Exception as e:
        status = {"ts": int(time.time()), "delivered": False,
                  "error": "catcher exception: %s" % type(e).__name__}
    emit_status(status, status_file)
    sys.exit(0)  # a command hook must never block the turn


if __name__ == "__main__":
    main()
