#!/usr/bin/env python3
# Pure contract tests for the Codex capture catcher: four-project routing, documented-event
# normalization, and status/no-leak discipline. No network. Run: python3 -I test_codex_catcher.py
import io, json, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import codex_capture_catcher as c  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def mapping_four(tmp):
    """Four mapped project roots, one with a nested-prefix sibling to catch boundary bugs."""
    rows = [
        {"root": "/w/courses", "project": "uuid-courses", "source_instance": "codex-courses",
         "credential_file": tmp + "/courses.cred.json"},
        {"root": "/w/cargo", "project": "uuid-cargo", "source_instance": "codex-cargo",
         "credential_file": tmp + "/cargo.cred.json"},
        {"root": "/w/cassiopeia/admin-ui", "project": "uuid-cass", "source_instance": "codex-cass",
         "credential_file": tmp + "/cass.cred.json"},
        {"root": "/w/dg", "project": "uuid-dg", "source_instance": "codex-dg",
         "credential_file": tmp + "/dg.cred.json"},
    ]
    p = tmp + "/map.json"
    write(p, {"projects": rows})
    return p


def test_routing():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        rows = c.load_mapping(mapping_four(tmp))
        # longest-prefix: the nested cassiopeia root sorts before shorter roots
        check("mapping loads 4 rows", len(rows) == 4)
        sel = lambda cwd: (c.select_project(cwd, rows) or {}).get("project")
        check("route /w/courses -> courses", sel("/w/courses") == "uuid-courses")
        check("route nested courses subdir", sel("/w/courses/pkg/sub") == "uuid-courses")
        check("route cargo", sel("/w/cargo") == "uuid-cargo")
        check("route cassiopeia nested root", sel("/w/cassiopeia/admin-ui/app") == "uuid-cass")
        check("route dg", sel("/w/dg") == "uuid-dg")
        # isolation: a cwd outside every root is NOT captured
        check("unknown cwd -> no row", c.select_project("/w/elsewhere", rows) is None)
        check("empty cwd -> no row", c.select_project("", rows) is None)
        # boundary: /w/courses-secret must NOT match the /w/courses root
        check("sibling-prefix dir does not match", sel("/w/courses-secret") is None)
        # parent of a root is not under it
        check("parent of root -> no row", sel("/w") is None)


def test_normalize():
    up = {"hook_event_name": "UserPromptSubmit", "session_id": "thr_1", "turn_id": "turn_1",
          "prompt": "hello", "cwd": "/w/courses", "model": "x", "permission_mode": "auto"}
    role, body = c.normalize_event(up)
    check("UserPromptSubmit role=user", role == "user")
    check("prompt body exact keys",
          body == {"hook_event_name": "UserPromptSubmit", "session_id": "thr_1",
                   "turn_id": "turn_1", "prompt": "hello"})
    check("prompt body has no assistant field", "last_assistant_message" not in body)

    stop = {"hook_event_name": "Stop", "session_id": "thr_1", "turn_id": "turn_1",
            "last_assistant_message": "done", "stop_hook_active": False, "cwd": "/w/courses"}
    role, body = c.normalize_event(stop)
    check("Stop role=assistant", role == "assistant")
    check("stop body exact keys",
          body == {"hook_event_name": "Stop", "session_id": "thr_1", "turn_id": "turn_1",
                   "last_assistant_message": "done"})
    check("stop body has no prompt field", "prompt" not in body)

    # SubagentStop carries last_assistant_message but must be ignored (not a top-level turn)
    sub = {"hook_event_name": "SubagentStop", "session_id": "thr_1", "turn_id": "turn_1",
           "last_assistant_message": "sub"}
    check("SubagentStop ignored", c.normalize_event(sub)[1] is None)
    # other lifecycle events ignored
    check("SessionStart ignored", c.normalize_event({"hook_event_name": "SessionStart"})[1] is None)
    check("PostToolUse ignored",
          c.normalize_event({"hook_event_name": "PostToolUse", "session_id": "a", "turn_id": "b"})[1] is None)
    # validation
    check("empty prompt -> None",
          c.normalize_event({"hook_event_name": "UserPromptSubmit", "session_id": "a",
                             "turn_id": "b", "prompt": ""})[1] is None)
    check("empty assistant -> None",
          c.normalize_event({"hook_event_name": "Stop", "session_id": "a", "turn_id": "b",
                             "last_assistant_message": ""})[1] is None)
    check("bad session id -> None",
          c.normalize_event({"hook_event_name": "Stop", "session_id": "bad id!", "turn_id": "b",
                             "last_assistant_message": "x"})[1] is None)
    check("overlong turn id -> None",
          c.normalize_event({"hook_event_name": "Stop", "session_id": "a", "turn_id": "T" * 161,
                             "last_assistant_message": "x"})[1] is None)
    check("non-dict event -> None", c.normalize_event(["x"])[1] is None)
    numeric = c.normalize_event({"hook_event_name": "Stop", "session_id": 123, "turn_id": "b",
                                 "last_assistant_message": "x"})
    check("numeric session id -> clean no-op (not an exception)", numeric[1] is None)
    nullturn = c.normalize_event({"hook_event_name": "UserPromptSubmit", "session_id": "a",
                                  "turn_id": None, "prompt": "x"})
    check("null turn id -> clean no-op", nullturn[1] is None)


def test_credential_least_privilege():
    check("valid agent cred -> headers",
          c.agent_headers({"principal_id": "p", "epoch": 1, "secret": "s"}) ==
          {"X-Principal-Id": "p", "X-Grant-Epoch": "1", "X-Secret": "s"})
    for bad, why in [
        ({"secret": "op-secret"}, "operator-shaped (no principal/epoch) refused"),
        ({"principal_id": "p", "epoch": 0, "secret": "s"}, "epoch 0 refused"),
        ({"principal_id": "p", "epoch": -1, "secret": "s"}, "negative epoch refused"),
        ({"principal_id": "p", "epoch": 1.0, "secret": "s"}, "float epoch refused"),
        ({"principal_id": "", "epoch": 1, "secret": "s"}, "empty principal refused"),
        ({"principal_id": "p", "epoch": 1, "secret": ""}, "empty secret refused"),
    ]:
        try:
            c.agent_headers(bad)
            check(why, False)
        except ValueError:
            check(why, True)


def test_run_no_ops_make_no_network():
    """run() must return a status WITHOUT calling the network for every no-op path. We point the
    endpoint at a black-hole and ensure post is never reached by asserting delivered is False and
    no http_status is set (post_event would set http_status or an http/post error)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        mp = mapping_four(tmp)
        env = {"AF_CODEX_ENDPOINT": "http://127.0.0.1:0", "AF_CODEX_CATCHER_MAP": mp}

        def noop_status(stdin):
            return c.run(stdin, env)

        s = noop_status(json.dumps({"hook_event_name": "SessionStart"}))
        check("unsupported event: no network", s.get("delivered") is False and "http_status" not in s)

        s = noop_status(json.dumps({"hook_event_name": "Stop", "session_id": "a", "turn_id": "b",
                                    "last_assistant_message": "x", "cwd": "/w/elsewhere"}))
        check("cwd not mapped -> skipped, no network",
              s.get("skipped") == "cwd not mapped" and "http_status" not in s)

        s = noop_status(json.dumps({"hook_event_name": "Stop", "session_id": "a", "turn_id": "b",
                                    "last_assistant_message": "x", "cwd": "/w/courses"}))
        # credential_file does not exist yet -> credential error, still no network
        check("missing credential -> error, no network",
              "error" in s and "http_status" not in s)

        s = noop_status("not json")
        check("unparseable stdin -> error, no network", s.get("error") == "unparseable event")


def test_status_no_leak():
    """A no-op status must never contain the prompt text or anything secret-shaped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        mp = mapping_four(tmp)
        env = {"AF_CODEX_CATCHER_MAP": mp}
        secret_prompt = "SENSITIVE-PROMPT-TEXT-SHOULD-NEVER-APPEAR"
        s = c.run(json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "a",
                              "turn_id": "b", "prompt": secret_prompt, "cwd": "/w/elsewhere"}), env)
        blob = json.dumps(s)
        check("status omits prompt text", secret_prompt not in blob)
        # emit_status to a file must also omit it
        sf = tmp + "/status.log"
        c.emit_status(s, sf)
        with open(sf, encoding="utf-8") as f:
            check("status file omits prompt text", secret_prompt not in f.read())


if __name__ == "__main__":
    test_routing()
    test_normalize()
    test_credential_least_privilege()
    test_run_no_ops_make_no_network()
    test_status_no_leak()
    print("\nFAILURES: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)
