#!/usr/bin/env python3
# Loopback auth/isolation/denial tests for the Codex capture catcher, against a synthetic
# local HTTP server with SYNTHETIC credentials. Exercises the real urllib POST path: query
# mapping, agent headers, four-project isolation, and denial without secret/payload leak.
# Run: python3 -I test_codex_catcher_auth.py
import json, os, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import codex_capture_catcher as c  # noqa: E402

FAILS = []
RECORDED = []          # one dict per received request
RESPONSE = {"code": 200, "body": {"accepted": 1, "committed": 1, "redactions": []}}


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        q = parse_qs(urlparse(self.path).query)
        RECORDED.append({
            "path": urlparse(self.path).path,
            "project": (q.get("project") or [""])[0],
            "source_instance": (q.get("source_instance") or [""])[0],
            "principal": self.headers.get("X-Principal-Id"),
            "epoch": self.headers.get("X-Grant-Epoch"),
            "secret": self.headers.get("X-Secret"),
            "operator": self.headers.get("X-Operator-Secret"),
            "body": json.loads(raw.decode("utf-8") or "{}"),
        })
        self.send_response(RESPONSE["code"])
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(RESPONSE["body"]).encode("utf-8"))


def start_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def setup(tmp):
    """Four projects, each with its own synthetic agent credential. Returns (map_path, env, creds)."""
    creds = {
        "courses": {"principal_id": "courses-cap", "epoch": 1, "secret": "SECRET-COURSES-xyz"},
        "cargo": {"principal_id": "cargo-cap", "epoch": 2, "secret": "SECRET-CARGO-xyz"},
        "cass": {"principal_id": "cass-cap", "epoch": 1, "secret": "SECRET-CASS-xyz"},
        "dg": {"principal_id": "dg-cap", "epoch": 3, "secret": "SECRET-DG-xyz"},
    }
    rows = []
    for key, root, uuid, src in [
        ("courses", "/w/courses", "uuid-courses", "codex-courses"),
        ("cargo", "/w/cargo", "uuid-cargo", "codex-cargo"),
        ("cass", "/w/cassiopeia/admin-ui", "uuid-cass", "codex-cass"),
        ("dg", "/w/dg", "uuid-dg", "codex-dg"),
    ]:
        cf = os.path.join(tmp, key + ".cred.json")
        with open(cf, "w", encoding="utf-8") as f:
            json.dump(creds[key], f)
        os.chmod(cf, 0o600)
        rows.append({"root": root, "project": uuid, "source_instance": src, "credential_file": cf})
    mp = os.path.join(tmp, "map.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump({"projects": rows}, f)
    return mp, creds


def event(cwd, text="payload-text-SECRET-NEVER-ECHOED"):
    return json.dumps({"hook_event_name": "Stop", "session_id": "thr_x", "turn_id": "turn_x",
                       "last_assistant_message": text, "cwd": cwd})


def main():
    srv = start_server()
    endpoint = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            mp, creds = setup(tmp)
            env = {"AF_CODEX_ENDPOINT": endpoint, "AF_CODEX_CATCHER_MAP": mp}

            # 1. Each of the four projects routes to its OWN uuid + source + credential.
            for key, cwd, uuid, src in [
                ("courses", "/w/courses/sub", "uuid-courses", "codex-courses"),
                ("cargo", "/w/cargo", "uuid-cargo", "codex-cargo"),
                ("cass", "/w/cassiopeia/admin-ui/app", "uuid-cass", "codex-cass"),
                ("dg", "/w/dg", "uuid-dg", "codex-dg"),
            ]:
                RECORDED.clear()
                RESPONSE["code"], RESPONSE["body"] = 200, {"accepted": 1, "committed": 1, "redactions": []}
                s = c.run(event(cwd), env)
                rec = RECORDED[-1] if RECORDED else {}
                check("%s: delivered committed=1" % key, s.get("delivered") and s.get("committed") == 1)
                check("%s: server got own project uuid" % key, rec.get("project") == uuid)
                check("%s: server got own source_instance" % key, rec.get("source_instance") == src)
                check("%s: agent principal = own key" % key, rec.get("principal") == creds[key]["principal_id"])
                check("%s: agent epoch = own key" % key, rec.get("epoch") == str(creds[key]["epoch"]))
                check("%s: agent secret = own key" % key, rec.get("secret") == creds[key]["secret"])
                check("%s: NO operator header sent" % key, rec.get("operator") is None)
                check("%s: endpoint path is codex-event" % key, rec.get("path") == "/v1/capture/codex-event")

            # 2. Isolation: project A's cwd never sends project B's credential.
            RECORDED.clear()
            c.run(event("/w/courses"), env)
            rec = RECORDED[-1]
            check("isolation: courses cwd uses ONLY courses secret",
                  rec["secret"] == creds["courses"]["secret"]
                  and all(rec["secret"] != creds[k]["secret"] for k in ("cargo", "cass", "dg")))

            # 3. Unknown cwd makes NO request at all.
            RECORDED.clear()
            s = c.run(event("/w/not-a-project"), env)
            check("unknown cwd: zero requests", len(RECORDED) == 0)
            check("unknown cwd: skipped, not delivered", s.get("skipped") == "cwd not mapped" and not s.get("delivered"))

            # 4. Denial (403) is recorded WITHOUT leaking secret or payload.
            RECORDED.clear()
            RESPONSE["code"], RESPONSE["body"] = 403, {"error": "capture authorization denied"}
            s = c.run(event("/w/courses", text="DENIAL-PAYLOAD-SECRET"), env)
            blob = json.dumps(s)
            check("denial: http_status 403", s.get("http_status") == 403)
            check("denial: not delivered", not s.get("delivered"))
            check("denial: status has no X-Secret value", creds["courses"]["secret"] not in blob)
            check("denial: status has no payload text", "DENIAL-PAYLOAD-SECRET" not in blob)
            check("denial: server error body not echoed in status", "authorization denied" not in blob)

            # 5. Operator-shaped credential is refused -> no request, no leak.
            opcred = os.path.join(tmp, "op.cred.json")
            with open(opcred, "w", encoding="utf-8") as f:
                json.dump({"secret": "OPERATOR-SECRET-xyz"}, f)
            with open(mp, "w", encoding="utf-8") as f:
                json.dump({"projects": [{"root": "/w/op", "project": "uuid-op",
                                         "source_instance": "codex-op", "credential_file": opcred}]}, f)
            RECORDED.clear()
            s = c.run(event("/w/op"), env)
            check("operator cred refused: zero requests", len(RECORDED) == 0)
            check("operator cred refused: invalid-credential error", s.get("error") == "invalid scoped capture credential")
            check("operator cred refused: secret not leaked", "OPERATOR-SECRET-xyz" not in json.dumps(s))
    finally:
        srv.shutdown()

    print("\nFAILURES: %d" % len(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
