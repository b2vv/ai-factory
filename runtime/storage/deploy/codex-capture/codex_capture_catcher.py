#!/usr/bin/env python3
# Codex lifecycle-event capture catcher (delivery only) -> AI Factory storage
# POST /v1/capture/codex-event-v2. The vetted Go adapter (internal/capture, provider
# "codex-hook-v2", AdaptCodexSnapshotEvent) remains the SOLE authority for redaction +
# credential sanitization (known-credentials-v1) before anything reaches the WAL/archive;
# this catcher only selects a project, normalizes the documented event, and transmits.
#
# Hook contract (verified against the official docs, learn.chatgpt.com/docs/hooks, and the
# versioned server contract internal/capture/codex_event.go):
#   Common stdin fields on every command hook: session_id, transcript_path, cwd,
#   hook_event_name, model.
#   UserPromptSubmit adds: turn_id, prompt, permission_mode.
#   Stop             adds: turn_id, stop_hook_active, last_assistant_message, permission_mode.
#   (SubagentStop also carries last_assistant_message+turn_id; it is deliberately IGNORED here
#    so a sub-agent message is never recorded as a top-level turn.)
# Factory adds schema_version=2 to the documented native subset. This is a transport
# envelope field, not a native hook field. The server assigns sanitized snapshot identity.
#
# Design points enforced here (see README.md):
#  - This mapping mode supports global or project-local hooks. Its explicit operator
#    mapping file (AF_CODEX_CATCHER_MAP) selects a row from cwd; it never
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
import sys, json, os, time, re, stat, urllib.request, urllib.parse, urllib.error

EVENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,160}$")  # mirrors server codex_event.go eventID
SUPPORTED_EVENTS = ("UserPromptSubmit", "Stop")
ENDPOINT = "http://127.0.0.1:8780"
MAX_INPUT = 1024 * 1024
MAX_RESPONSE = 64 * 1024

def canonical_path(value):
    if not isinstance(value, str) or not os.path.isabs(value):
        raise ValueError("absolute path required")
    if os.path.normpath(value) != value or os.path.realpath(value) != value:
        raise ValueError("canonical path without symlinks required")
    return value

def read_json_file(path, limit):
    canonical_path(str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("regular unlinked-once file required")
        text = stream.read(limit + 1)
    if len(text) > limit:
        raise ValueError("file exceeds limit")
    return json.loads(text)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None



def load_mapping(path):
    """Load the explicit operator mapping. Returns a list of normalized rows
    [{root, project, source_instance, credential_file}] sorted by DESCENDING root length
    (longest-prefix wins). Raises ValueError on a malformed file; the caller turns that into
    a no-op status. The mapping holds UUIDs and credential-file paths and is kept OUT of the
    repository (local, operator-authored)."""
    raw = read_json_file(path, 256 * 1024)
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
        canonical_path(root)
        canonical_path(cred)
        if root == os.sep or any(row["root"] == root for row in out):
            raise ValueError("ambiguous mapping root")
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
    try:
        c = canonical_path(cwd)
    except ValueError:
        return None
    for row in rows:  # already longest-first
        root = row["root"]
        if c == root or c.startswith(root + os.sep):
            return row
    return None


def normalize_event(ev):
    """Map a documented Codex hook event to the exact server body.

    Returns (role, body) on success and (reason, None) on a no-op, so the caller tests
    `body is None`. body is the JSON the server's AdaptCodexSnapshotEvent accepts:
      UserPromptSubmit -> {schema_version=2, hook_event_name, session_id, turn_id, prompt}
      Stop -> {schema_version=2, hook_event_name, session_id, turn_id,
               last_assistant_message, stop_hook_active}
    Exactly one text field is set. cwd, transcript_path, model and permission_mode
    are never transmitted. Both initial and continued Stops are snapshot candidates."""
    if not isinstance(ev, dict):
        return "event not an object", None
    event = ev.get("hook_event_name")
    if event not in SUPPORTED_EVENTS:
        return "unsupported event", None
    session_id = ev.get("session_id")
    turn_id = ev.get("turn_id")
    if (not isinstance(session_id, str) or not isinstance(turn_id, str)
            or not EVENT_ID.fullmatch(session_id) or not EVENT_ID.fullmatch(turn_id)):
        return "bad session/turn id", None
    if event == "UserPromptSubmit":
        prompt = ev.get("prompt")
        if not isinstance(prompt, str) or prompt == "":
            return "empty prompt", None
        return "user", {"schema_version": 2, "hook_event_name": "UserPromptSubmit", "session_id": session_id,
                        "turn_id": turn_id, "prompt": prompt}
    # Both initial and continued Stops are distinct snapshot candidates. The server
    # assigns identity after sanitization; this flag is never used as deduplication.
    if type(ev.get("stop_hook_active")) is not bool:
        return "bad stop flag", None
    # Stop
    msg = ev.get("last_assistant_message")
    if not isinstance(msg, str) or msg == "":
        return "empty assistant message", None
    return "assistant", {"schema_version": 2, "stop_hook_active": ev["stop_hook_active"], "hook_event_name": "Stop", "session_id": session_id,
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


def safe_count(value):
    return value if type(value) is int and 0 <= value <= 1000000 else None


def post_event(endpoint, project, source, headers, body, timeout=5, opener=None):
    """POST one event to the server. Returns a status dict fragment with http_status and the
    server's accepted/committed/redactions counts, or an error (never the response body, which
    could echo input)."""
    if endpoint != ENDPOINT:
        return {"error": "endpoint refused"}
    if opener is None:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect()).open
    url = "%s/v1/capture/codex-event-v2?project=%s&source_instance=%s" % (
        endpoint, urllib.parse.quote(project, safe=""), urllib.parse.quote(source, safe=""))
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    for name, value in headers.items():
        req.add_header(name, value)
    try:
        resp = opener(req, timeout=timeout)
        raw = resp.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            return {"error": "response exceeds limit"}
        payload = json.loads(raw.decode("utf-8") or "{}")
        if (not isinstance(payload, dict)
                or safe_count(payload.get("accepted")) is None
                or safe_count(payload.get("committed")) is None
                or not isinstance(payload.get("redactions"), list)):
            return {"error": "invalid capture response"}
        if resp.getheader("X-AF-Codex-Contract") != "2":
            return {"error": "capture contract not acknowledged"}
        return {"http_status": resp.getcode(), "accepted": safe_count(payload.get("accepted")),
                "committed": safe_count(payload.get("committed")),
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
    if len(stdin_text) > MAX_INPUT:
        status["error"] = "event exceeds limit"
        return status
    try:
        ev = json.loads(stdin_text)
    except Exception:
        status["error"] = "unparseable event"
        return status
    event = ev.get("hook_event_name") if isinstance(ev, dict) else None
    status["event"] = event if event in SUPPORTED_EVENTS else "unsupported"

    role, body = normalize_event(ev)
    if body is None:
        status["skipped"] = role  # reason string; no payload
        return status
    status["role"] = role

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

    try:
        credential = read_json_file(row["credential_file"], 16 * 1024)
        headers = agent_headers(credential)
    except ValueError as e:
        status["error"] = "invalid scoped capture credential"
        return status
    except Exception as e:
        status["error"] = "credential unreadable: %s" % type(e).__name__
        return status

    status.update(post_event(endpoint, row["project"], row["source_instance"], headers, body))
    return status


def main():
    status_file = os.environ.get("AF_CODEX_STATUS_FILE", "")
    try:
        status = run(sys.stdin.read(MAX_INPUT + 1), os.environ)
    except SystemExit:
        raise
    except Exception as e:
        status = {"ts": int(time.time()), "delivered": False,
                  "error": "catcher exception: %s" % type(e).__name__}
    emit_status(status, status_file)
    sys.exit(0)  # a command hook must never block the turn


if __name__ == "__main__":
    main()
