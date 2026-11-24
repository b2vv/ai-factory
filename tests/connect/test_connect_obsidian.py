"""Optional Obsidian channel in the project connection (T33): pointer, retention and token-free check.

Disposable fixtures only: a temporary vault directory, a fixture plugin settings file holding a sentinel
API key that must never be printed or written, and a stub HTTP server on an ephemeral 127.0.0.1 port.
"""
import http.server
import importlib.util
import io
import json
import os
import socket
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("connect_obsidian_base", ROOT / "tests" / "connect" / "test_connect_project.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
cp = base.cp

SENTINEL = "SENTINEL-API-KEY-7f3a"
MARKER = "<!-- ai-factory-obsidian: "
FIXED = "obsidian plugin settings are not a readable regular JSON file of the expected shape"


class Stub(http.server.BaseHTTPRequestHandler):
    body = {"status": "OK", "service": "Obsidian Local REST API", "authenticated": False}
    seen = []

    def do_GET(self):
        type(self).seen.append((self.path, self.headers.get("Authorization")))
        data = json.dumps(self.body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Obsidian(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.kit = base.make_kit(self.tmp)
        self.proj = self.tmp / "project"
        self.proj.mkdir()
        self.vault = self.tmp / "vaults" / "demo vault"
        (self.vault / ".obsidian" / "plugins" / "obsidian-local-rest-api").mkdir(parents=True)
        Stub.seen = []
        Stub.body = {"status": "OK", "service": "Obsidian Local REST API", "authenticated": False}
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()

    def serve(self, body=None):
        if body is not None:
            Stub.body = body
        self.server = http.server.HTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self.server.server_address[1]

    def settings(self, port, enabled=True, raw=None):
        path = self.vault / ".obsidian" / "plugins" / "obsidian-local-rest-api" / "data.json"
        path.write_text(raw if raw is not None else json.dumps(
            {"apiKey": SENTINEL, "port": port + 1, "insecurePort": port, "enableInsecureServer": enabled}))
        return path

    def args(self, *extra, vault=None, port=None):
        a = ["--managed-root", str(self.kit), "--project", str(self.proj), "--git-root", str(self.proj)]
        if vault is not None:
            a += ["--obsidian-vault", str(vault), "--obsidian-port", str(port)]
        return a + list(extra)

    def run_cp(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cp.main(argv)
        out = buf.getvalue()
        self.assertNotIn(SENTINEL, out)
        return rc, json.loads(out)

    def block(self):
        text = (self.proj / "AGENTS.local.md").read_text()
        return text.split(cp.BEGIN, 1)[1].split(cp.END, 1)[0]

    def no_secret_written(self):
        for p in self.proj.rglob("*"):
            if p.is_file():
                self.assertNotIn(SENTINEL, p.read_text(errors="replace"))

    # --- pointer and block ---

    def test_ok_pointer_written_with_owner_step_and_retained(self):
        port = self.serve()
        self.settings(port)
        rc, rep = self.run_cp(self.args("--apply", vault=self.vault, port=port))
        self.assertEqual(0, rc, rep)
        self.assertEqual("OK", rep["obsidian"]["state"])
        self.assertEqual(str(self.vault), rep["obsidian"]["vault"])
        block = self.block()
        self.assertIn(MARKER + json.dumps({"port": port, "vault": str(self.vault)}, sort_keys=True) + " -->", block)
        self.assertIn(f"`{self.vault}`", block)
        self.assertIn(f"http://127.0.0.1:{port}/mcp/", block)
        self.assertIn(f'claude mcp add -s local --transport http obsidian http://127.0.0.1:{port}/mcp/ '
                      '--header "Authorization: Bearer <TOKEN>"', block)
        self.assertIn("~/.claude.json", block)
        self.assertIn("GET /vault/", block)
        self.assertIn("NOT_VERIFIED", json.dumps(rep["obsidian"]["checks"]))
        self.assertEqual([("/", None)], Stub.seen)          # one token-free request, root only
        self.no_secret_written()
        before = (self.proj / "AGENTS.local.md").read_bytes()
        rc, again = self.run_cp(self.args("--apply"))       # reconnect without flags keeps it
        self.assertEqual(0, rc, again)
        self.assertEqual("noop", next(a["action"] for a in again["actions"] if a["file"] == "AGENTS.local.md"))
        self.assertEqual(before, (self.proj / "AGENTS.local.md").read_bytes())
        self.assertEqual("OK", again["obsidian"]["state"])
        self.assertFalse(again["obsidian"]["reconciled"])

    def test_no_pointer_no_network_and_identical_block(self):
        rc, plain = self.run_cp(self.args("--apply"))
        self.assertEqual(0, rc)
        self.assertIsNone(plain.get("obsidian"))
        self.assertNotIn("obsidian", self.block().lower())
        self.assertEqual([], Stub.seen)
        orig = cp.obsidian_http
        cp.obsidian_http = lambda port: self.fail("network call without a pointer")
        try:
            rc, again = self.run_cp(self.args("--apply"))
        finally:
            cp.obsidian_http = orig
        self.assertEqual(0, rc)

    def test_clear_removes_only_obsidian_lines(self):
        port = self.serve(); self.settings(port)
        self.run_cp(self.args("--apply", vault=self.vault, port=port))
        rc, rep = self.run_cp(self.args("--clear-obsidian", "--apply"))
        self.assertEqual(0, rc, rep)
        self.assertNotIn("obsidian", self.block().lower())
        self.assertIn("rules/agent-entry.md", self.block())
        self.assertTrue(rep["obsidian"]["reconciled"])
        rc, rep = self.run_cp(self.args("--clear-obsidian", "--apply"))   # clear with nothing recorded = NOOP
        self.assertEqual(0, rc)
        self.assertEqual("noop", next(a["action"] for a in rep["actions"] if a["file"] == "AGENTS.local.md"))

    def test_flags_replace_marker_and_report_reconciled(self):
        port = self.serve(); self.settings(port)
        self.run_cp(self.args("--apply", vault=self.vault, port=port))
        other = self.tmp / "vaults" / "other"
        (other / ".obsidian" / "plugins" / "obsidian-local-rest-api").mkdir(parents=True)
        (other / ".obsidian" / "plugins" / "obsidian-local-rest-api" / "data.json").write_text(
            json.dumps({"insecurePort": port, "enableInsecureServer": True}))
        rc, rep = self.run_cp(self.args("--apply", vault=other, port=port))
        self.assertEqual(0, rc, rep)
        self.assertTrue(rep["obsidian"]["reconciled"])
        self.assertEqual(1, self.block().count(MARKER))
        self.assertIn(str(other), self.block())

    def test_dry_run_reports_check_writes_nothing(self):
        port = self.serve(); self.settings(port)
        rc, rep = self.run_cp(self.args(vault=self.vault, port=port))
        self.assertEqual(0, rc)
        self.assertEqual("OK", rep["obsidian"]["state"])
        self.assertFalse((self.proj / "AGENTS.local.md").exists())

    def test_proxy_environment_is_ignored(self):
        port = self.serve(); self.settings(port)
        saved = {k: os.environ.get(k) for k in ("http_proxy", "HTTP_PROXY", "no_proxy", "NO_PROXY")}
        os.environ.update(http_proxy="http://127.0.0.1:9", HTTP_PROXY="http://127.0.0.1:9", no_proxy="", NO_PROXY="")
        try:
            rc, rep = self.run_cp(self.args(vault=self.vault, port=port))
        finally:
            for k, v in saved.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v
        self.assertEqual("OK", rep["obsidian"]["state"], rep)

    # --- non-blocking states ---

    def test_closed_port_is_pending_and_still_written(self):
        port = free_port(); self.settings(port)
        rc, rep = self.run_cp(self.args("--apply", vault=self.vault, port=port))
        self.assertEqual(0, rc, rep)
        self.assertEqual("PENDING", rep["obsidian"]["state"])
        self.assertIn("open the vault in Obsidian", json.dumps(rep["obsidian"]["checks"]))
        self.assertIn(MARKER, self.block())

    def test_missing_plugin_settings_is_pending(self):
        port = self.serve()
        rc, rep = self.run_cp(self.args("--apply", vault=self.vault, port=port))
        self.assertEqual(0, rc, rep)
        self.assertEqual("PENDING", rep["obsidian"]["state"])
        self.assertIn("install/enable the plugin", json.dumps(rep["obsidian"]["checks"]))

    def test_other_service_is_warn_not_blocked(self):
        port = self.serve({"status": "OK", "service": "something else"}); self.settings(port)
        rc, rep = self.run_cp(self.args("--apply", vault=self.vault, port=port))
        self.assertEqual(0, rc, rep)
        self.assertEqual("WARN", rep["obsidian"]["state"])

    def test_non_http_service_is_warn_not_a_crash(self):
        sock = socket.socket(); sock.bind(("127.0.0.1", 0)); sock.listen(4)
        self.addCleanup(sock.close)
        def answer():
            for _ in range(4):
                try:
                    conn, _ = sock.accept()
                except OSError:
                    return
                with conn:
                    conn.recv(1024); conn.sendall(b"NOT-HTTP GARBAGE\r\n\r\n")
        threading.Thread(target=answer, daemon=True).start()
        port = sock.getsockname()[1]; self.settings(port)
        rc, rep = self.run_cp(self.args("--apply", vault=self.vault, port=port))
        self.assertEqual(0, rc, rep)
        self.assertEqual("WARN", rep["obsidian"]["state"])

    # --- blocking states: nothing written ---

    def assert_blocked(self, argv, needle):
        before = {p: p.read_bytes() for p in self.proj.rglob("*") if p.is_file()}
        rc, rep = self.run_cp(argv)
        self.assertEqual(1, rc, rep)
        self.assertEqual("BLOCKED", rep["status"])
        self.assertIn(needle, json.dumps(rep, ensure_ascii=False))
        self.assertEqual(before, {p: p.read_bytes() for p in self.proj.rglob("*") if p.is_file()})
        return rep

    def test_port_mismatch_and_http_disabled_block(self):
        port = self.serve()
        self.settings(port + 7)
        self.assert_blocked(self.args("--apply", vault=self.vault, port=port), f"port {port} is not this vault's HTTP port")
        self.settings(port, enabled=False)
        self.assert_blocked(self.args("--apply", vault=self.vault, port=port), f"port {port} is not this vault's HTTP port")

    def test_bad_vault_paths_block(self):
        port = self.serve(); self.settings(port)
        plain = self.tmp / "plain"; plain.mkdir()
        self.assert_blocked(self.args("--apply", vault=plain, port=port), "obsidian vault")
        self.assert_blocked(self.args("--apply", vault=self.tmp / "missing", port=port), "obsidian vault")
        self.assert_blocked(self.args("--apply", vault="relative/vault", port=port), "obsidian vault")
        tick = self.tmp / "va`ult"; (tick / ".obsidian").mkdir(parents=True)
        c1 = self.tmp / "va\u0085ult"; (c1 / ".obsidian").mkdir(parents=True)
        self.assert_blocked(self.args("--apply", vault=c1, port=port), "obsidian vault")
        self.assert_blocked(self.args("--apply", vault=tick, port=port), "obsidian vault")
        inside = self.proj / "notes"; (inside / ".obsidian").mkdir(parents=True)
        self.assert_blocked(self.args("--apply", vault=inside, port=port), "inside the project")
        linked = self.tmp / "linked"; linked.mkdir(); (linked / ".obsidian").symlink_to(self.vault / ".obsidian")
        self.assert_blocked(self.args("--apply", vault=linked, port=port), "obsidian vault")
        self.assert_blocked(self.args("--apply", vault=self.vault, port=80), "port")
        self.assert_blocked(self.args("--apply", "--obsidian-vault", str(self.vault)), "together")

    def test_symlinked_vault_path_is_resolved(self):
        port = self.serve(); self.settings(port)
        alias = self.tmp / "alias"; alias.symlink_to(self.vault)
        rc, rep = self.run_cp(self.args("--apply", vault=alias, port=port))
        self.assertEqual(0, rc, rep)
        self.assertEqual(str(self.vault), rep["obsidian"]["vault"])

    def test_plugin_settings_errors_never_leak(self):
        port = self.serve()
        for raw in ('{"apiKey": "' + SENTINEL + '", "insecurePort": ', '["' + SENTINEL + '"]',
                    json.dumps({"apiKey": SENTINEL, "insecurePort": str(port), "enableInsecureServer": True}),
                    json.dumps({"apiKey": SENTINEL, "pad": "x" * 70000, "insecurePort": port, "enableInsecureServer": True})):
            self.settings(port, raw=raw)
            rep = self.assert_blocked(self.args("--apply", vault=self.vault, port=port), "plugin settings")
            self.assertNotIn(SENTINEL, json.dumps(rep))
            self.assertEqual([FIXED], rep["conflicts"])          # exactly the fixed message, no exception text
        path = self.settings(port)
        real = self.tmp / "real.json"; real.write_text(path.read_text()); path.unlink(); path.symlink_to(real)
        rep = self.assert_blocked(self.args("--apply", vault=self.vault, port=port), "plugin settings")
        self.no_secret_written()

    def test_two_markers_block(self):
        port = self.serve(); self.settings(port)
        self.run_cp(self.args("--apply", vault=self.vault, port=port))
        text = (self.proj / "AGENTS.local.md").read_text()
        line = next(l for l in text.splitlines() if l.startswith(MARKER))
        (self.proj / "AGENTS.local.md").write_text(text.replace(line, line + "\n" + line))
        self.assert_blocked(self.args("--apply"), "ambiguous managed obsidian pointer")

    def test_hand_written_section_gets_duplicate_hint(self):
        port = self.serve(); self.settings(port)
        (self.proj / "AGENTS.local.md").write_text("# local\n\n## Obsidian vault (MCP `obsidian`)\nhand text\n")
        rc, rep = self.run_cp(self.args("--apply", vault=self.vault, port=port))
        self.assertEqual(0, rc, rep)
        self.assertIn("duplicate_hint", rep["obsidian"])
        self.assertIn("hand text", (self.proj / "AGENTS.local.md").read_text())   # never edited


if __name__ == "__main__":
    unittest.main()
