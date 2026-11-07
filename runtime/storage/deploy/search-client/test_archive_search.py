import contextlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import archive_search as client

SECRET = "synthetic-search-only-secret-DO-NOT-USE"
PROJECT = "synthetic-courses-project"
PRINCIPAL = "synthetic-courses-search"


def hit(text="staff-tidy ADR-0003 Ångström", message="m1"):
    return {"Project": PROJECT, "Provider": "fixture-provider", "ParentID": "", "SourceInstance": "fixture", "SessionID": "s1",
            "MessageID": message, "Text": text, "Type": "message", "Role": "user"}


def page(hits=None, cursor=""):
    return {"project": PROJECT, "search_mode": client.MODE, "derived": True,
            "hits": [] if hits is None else hits, "snippets": [],
            "next_cursor": cursor, "total_exact": False}


class FixtureServer:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                outer.requests.append((self.command, self.path, dict(self.headers)))
                reply = outer.replies.pop(0) if outer.replies else (500, {}, b"unexpected request")
                try:
                    if callable(reply):
                        reply(self)
                        return
                    status, headers, body = reply if isinstance(reply, tuple) else (200, {}, reply)
                    if not isinstance(body, bytes):
                        body = json.dumps(body, ensure_ascii=True).encode()
                    self.send_response(status)
                    for key, value in {"Content-Type": "application/json", "Content-Length": str(len(body)), **headers}.items():
                        self.send_header(key, value)
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(1)


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="factory-search-fixture-")
        self.root = Path(self.tmp.name).resolve()
        self.credential = self.root / "synthetic-search.json"
        self.routes = self.root / "search-routes.json"
        self.credential.write_text(json.dumps({"principal_id": PRINCIPAL, "epoch": 1, "secret": SECRET}))
        self.credential.chmod(0o600)
        self.configure(1)

    def tearDown(self):
        self.tmp.cleanup()

    def configure(self, port, **updates):
        route = {"project_id": PROJECT, "principal_id": PRINCIPAL,
                 "credential_file": str(self.credential), "port": port, "credential_format": "json"}
        route.update(updates)
        self.routes.write_text(json.dumps({"version": 1, "projects": {"courses": route}}))
        self.routes.chmod(0o600)

    def run_search(self, fixture, query="staff-tidy", **kwargs):
        self.configure(fixture.server.server_port)
        return client.search("courses", query, routes_path=self.routes, **kwargs)

    def split_route(self, port, secret=SECRET + "\n", epoch="1\n", **updates):
        secret_file, epoch_file = self.root / "search.secret", self.root / "search.epoch"
        secret_file.write_text(secret); epoch_file.write_text(epoch)
        secret_file.chmod(0o600); epoch_file.chmod(0o600)
        route = {"project_id": PROJECT, "principal_id": PRINCIPAL, "port": port,
                 "credential_format": "split", "secret_file": str(secret_file),
                 "epoch_file": str(epoch_file)}
        route.update(updates)
        self.routes.write_text(json.dumps({"version": 1, "projects": {"courses": route}}))
        return secret_file, epoch_file

    def test_split_existing_files_use_exact_principal_without_copy(self):
        with FixtureServer([page([hit()])]) as server:
            self.split_route(server.server.server_port, secret=SECRET + "\r\n", epoch="12\n")
            out, code = client.search("courses", "staff-tidy", routes_path=self.routes)
            self.assertEqual(code, 0)
            self.assertEqual(server.requests[0][2]["X-Grant-Epoch"], "12")
            self.assertEqual(server.requests[0][2]["X-Principal-Id"], PRINCIPAL)
            self.assertEqual(server.requests[0][2]["X-Secret"], SECRET)

    def test_split_refuses_ambiguous_whitespace_and_invalid_epoch_without_request(self):
        for secret, epoch in [(SECRET + " ", "1"), (SECRET + "\n\n", "1"),
                              (SECRET, " 1"), (SECRET, "+1"), (SECRET, "0"),
                              (SECRET, "1.0"), (SECRET, str(2**63)), (SECRET, "1\n2")]:
            with self.subTest(secret=secret, epoch=epoch), FixtureServer([]) as server:
                self.split_route(server.server.server_port, secret, epoch)
                out, code = client.search("courses", "x", routes_path=self.routes)
                self.assertEqual(code, 1)
                self.assertEqual(server.requests, [])
                self.assertNotIn(SECRET, json.dumps(out))

    def test_split_missing_or_unsafe_file_never_falls_back_to_json(self):
        for fault in ["missing", "public", "symlink"]:
            with self.subTest(fault=fault), FixtureServer([]) as server:
                secret_file, epoch_file = self.split_route(server.server.server_port)
                if fault == "missing": epoch_file.unlink()
                elif fault == "public": secret_file.chmod(0o644)
                else:
                    epoch_file.unlink(); epoch_file.symlink_to(self.credential)
                out, code = client.search("courses", "x", routes_path=self.routes)
                self.assertEqual(code, 1)
                self.assertEqual(server.requests, [])

    def test_format_is_explicit_and_shapes_cannot_mix(self):
        for fmt in [None, "capture", True, "split"]:
            with self.subTest(fmt=fmt), FixtureServer([]) as server:
                self.configure(server.server.server_port)
                cfg = json.loads(self.routes.read_text())
                if fmt is None: cfg["projects"]["courses"].pop("credential_format", None)
                else: cfg["projects"]["courses"]["credential_format"] = fmt
                self.routes.write_text(json.dumps(cfg))
                out, code = client.search("courses", "x", routes_path=self.routes)
                self.assertEqual(code, 1)
                self.assertEqual(server.requests, [])

    def test_record_provenance_fields_are_required_strings(self):
        for field in ["Provider", "ParentID"]:
            for value in [None, False, 1, []]:
                with self.subTest(field=field, value=value), FixtureServer([]) as server:
                    body = page([hit()]); body["hits"][0][field] = value
                    server.replies.append(body)
                    out, code = self.run_search(server)
                    self.assertEqual((code, out["stop_reason"]), (1, "invalid_response"))
            with FixtureServer([]) as server:
                body = page([hit()]); body["hits"][0].pop(field, None)
                server.replies.append(body)
                out, code = self.run_search(server)
                self.assertEqual(code, 1)

    def test_snippet_scalars_match_actual_wire_types(self):
        good = {"identity": json.dumps([PROJECT, "fixture", "s1", "m1"]),
                "text": "safe", "basis": "literal_match", "match": True, "truncated": False}
        for field in ["text", "basis", "match", "truncated"]:
            for value in [None, 1, [], "bad" if field in ("match", "truncated") else False]:
                with self.subTest(field=field, value=value), FixtureServer([]) as server:
                    snippet = dict(good); snippet[field] = value
                    body = page([hit()]); body["snippets"] = [snippet]
                    server.replies.append(body)
                    out, code = self.run_search(server)
                    self.assertEqual((code, out["stop_reason"]), (1, "invalid_response"))

    def test_split_bounds_and_line_endings(self):
        for ending in ["", "\n", "\r\n"]:
            with self.subTest(ending=ending), FixtureServer([page()]) as server:
                self.split_route(server.server.server_port, "x" * 4096 + ending,
                                 str(2**63 - 1) + ending)
                out, code = client.search("courses", "x", routes_path=self.routes)
                self.assertEqual(code, 0)
                self.assertEqual(server.requests[0][2]["X-Secret"], "x" * 4096)
        for secret, epoch in [("x" * 15, "1"), ("x" * 4097, "1"),
                              ("é" * 16, "1"), (SECRET, "١")]:
            with self.subTest(epoch=epoch), FixtureServer([]) as server:
                self.split_route(server.server.server_port, secret, epoch)
                out, code = client.search("courses", "x", routes_path=self.routes)
                self.assertEqual(code, 1)
                self.assertEqual(server.requests, [])

    def test_no_mixed_format_fields(self):
        for fmt in ["json", "split"]:
            with self.subTest(fmt=fmt), FixtureServer([]) as server:
                if fmt == "json":
                    self.configure(server.server.server_port, secret_file=str(self.credential))
                else:
                    self.split_route(server.server.server_port, credential_file=str(self.credential))
                out, code = client.search("courses", "x", routes_path=self.routes)
                self.assertEqual(code, 1)
                self.assertEqual(server.requests, [])

    def test_rotation_denial_is_single_request_with_no_reread(self):
        with FixtureServer([(403, {}, b"rotation denied")]) as server:
            self.split_route(server.server.server_port)
            with patch.object(client, "owned_file", wraps=client.owned_file) as read:
                out, code = client.search("courses", "x", routes_path=self.routes)
            self.assertEqual(read.call_count, 3)  # config, secret, epoch; no retry
            self.assertEqual(len(server.requests), 1)
            self.assertEqual((code, out["http_status"]), (1, 403))

    def test_missing_snippet_fields_refused(self):
        good = {"identity": json.dumps([PROJECT, "fixture", "s1", "m1"]),
                "text": "safe", "basis": "literal_match", "match": True, "truncated": False}
        for field in good:
            with self.subTest(field=field), FixtureServer([]) as server:
                snippet = dict(good); del snippet[field]
                body = page([hit()]); body["snippets"] = [snippet]
                server.replies.append(body)
                out, code = self.run_search(server)
                self.assertEqual(code, 1)

    def test_split_real_cli_preserves_files_and_emits_only_json(self):
        with FixtureServer([page([hit()])]) as server:
            secret_file, epoch_file = self.split_route(server.server.server_port)
            before = {p: (p.read_bytes(), p.stat().st_mode) for p in self.root.iterdir()}
            script = self.root / "archive_search.py"
            shutil.copyfile(client.__file__, script)
            proc = subprocess.run([sys.executable, "-I", str(script), "courses", "staff-tidy"],
                                  capture_output=True, timeout=5)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stderr, b"")
            out = json.loads(proc.stdout)
            self.assertEqual(out["hits"][0]["MessageID"], "m1")
            self.assertNotIn(SECRET.encode(), proc.stdout)
            for p, expected in before.items():
                self.assertEqual((p.read_bytes(), p.stat().st_mode), expected)
            self.assertEqual(set(self.root.iterdir()), set(before) | {script})

    def test_duplicate_key_in_otherwise_valid_page_is_not_silently_last_wins(self):
        raw = json.dumps(page([hit()])).encode()
        raw = raw[:-1] + b', "hits": []}'
        with FixtureServer([raw]) as server:
            out, code = self.run_search(server)
            self.assertEqual((code, out["stop_reason"]), (1, "invalid_json"))
            self.assertEqual(out["hits"], [])

    def test_public_owned_epoch_is_metadata_and_authenticates(self):
        with FixtureServer([page([hit()])]) as server:
            secret_file, epoch_file = self.split_route(server.server.server_port)
            epoch_file.chmod(0o644)
            before = epoch_file.read_bytes()
            out, code = client.search("courses", "staff-tidy", routes_path=self.routes)
            self.assertEqual(code, 0)
            self.assertEqual(server.requests[0][2]["X-Grant-Epoch"], "1")
            self.assertEqual(epoch_file.read_bytes(), before)
            self.assertEqual(epoch_file.stat().st_mode & 0o777, 0o644)

    def test_writable_epoch_and_public_auth_secrets_are_refused(self):
        for fault in ["epoch-writable", "secret-readable", "json-readable"]:
            with self.subTest(fault=fault), FixtureServer([]) as server:
                secret_file, epoch_file = self.split_route(server.server.server_port)
                if fault == "epoch-writable": epoch_file.chmod(0o666)
                elif fault == "secret-readable": secret_file.chmod(0o644)
                else:
                    self.configure(server.server.server_port)
                    self.credential.chmod(0o644)
                out, code = client.search("courses", "x", routes_path=self.routes)
                self.assertEqual((code, out["stop_reason"]), (1, "unsafe_configured_file"))
                self.assertEqual(server.requests, [])

    def test_empty_intermediate_page_is_followed(self):
        with FixtureServer([page([], "cursor-a"), page([hit()])]) as server:
            out, code = self.run_search(server)
        self.assertEqual(code, 0)
        self.assertEqual(out["pages"], 2)
        self.assertEqual(out["returned_count"], 1)
        self.assertTrue(out["traversal_complete"])
        self.assertEqual(out["capture_completeness"], "unknown")
        self.assertEqual(out["index_freshness"], "unknown")
        self.assertEqual(parse_qs(urlsplit(server.requests[1][1]).query)["cursor"], ["cursor-a"])

    def test_query_and_cursor_are_encoded_without_changing_semantics(self):
        query, cursor = 'staff-tidy ADR-0003 "two words" & #? Ångström', "abc+/=&?"
        with FixtureServer([page()]) as server:
            out, code = self.run_search(server, query, cursor=cursor)
        self.assertEqual(code, 0)
        method, path, headers = server.requests[0]
        self.assertEqual(method, "GET")
        self.assertEqual(urlsplit(path).path, "/v1/search/query")
        self.assertEqual(parse_qs(urlsplit(path).query), {"project": [PROJECT], "q": [query], "cursor": [cursor]})
        self.assertNotIn(SECRET, path)
        self.assertEqual(headers["X-Secret"], SECRET)
        self.assertEqual(headers["X-Principal-Id"], PRINCIPAL)

    def test_all_control_chars_roundtrip_strictly(self):
        text = "".join(chr(i) for i in range(32)) + 'Ångström " \\ \u2028 \u2029'
        with FixtureServer([page([hit(text)])]) as server:
            out, code = self.run_search(server)
        self.assertEqual(code, 0)
        self.assertEqual(out["hits"][0]["Text"], text)
        self.assertEqual(json.loads(json.dumps(out))["hits"][0]["Text"], text)

    def test_raw_newline_is_rejected_not_repaired(self):
        with FixtureServer([b'{"Text":"first\nsecond"}']) as server:
            out, code = self.run_search(server)
        self.assertEqual(code, 1)
        self.assertEqual(out["stop_reason"], "invalid_json")

    def test_duplicate_keys_nan_bad_utf8_and_surrogates_are_rejected(self):
        for body in [b'{"hits":[],"hits":[]}', b'{"x":NaN}', b'{"x":1e309}', b'\xff',
                     json.dumps(page([hit("\ud800")])).encode()]:
            with self.subTest(body=body), FixtureServer([body]) as server:
                out, code = self.run_search(server)
                self.assertEqual(code, 1)

    def test_wrong_project_and_wrong_hit_project_fail(self):
        top = page([hit()]); top["project"] = "foreign"
        item = page([hit()]); item["hits"][0]["Project"] = "foreign"
        for body in [top, item]:
            with self.subTest(body=body), FixtureServer([body]) as server:
                out, code = self.run_search(server)
                self.assertEqual((code, out["stop_reason"]), (1, "invalid_response"))

    def test_snippet_identity_must_match_returned_hit(self):
        body = page([hit()])
        body["snippets"] = [{"identity": json.dumps([PROJECT, "fixture", "s1", "m1"]), "text": "safe",
                             "basis": "literal_match", "match": True, "truncated": False}]
        with FixtureServer([body]) as server:
            out, code = self.run_search(server)
            self.assertEqual(code, 0)
        body["snippets"][0]["identity"] = json.dumps(["foreign", "fixture", "s1", "m1"])
        with FixtureServer([body]) as server:
            out, code = self.run_search(server)
            self.assertEqual((code, out["stop_reason"]), (1, "invalid_response"))

    def test_missing_contract_fields_fail(self):
        for key in ["hits", "next_cursor", "derived", "search_mode"]:
            body = page(); del body[key]
            with self.subTest(key=key), FixtureServer([body]) as server:
                out, code = self.run_search(server)
                self.assertEqual(code, 1)

    def test_redirect_never_follows_or_sends_credentials(self):
        with FixtureServer([page()]) as target:
            with FixtureServer([(302, {"Location": f"http://127.0.0.1:{target.server.server_port}/capture"}, b"")]) as source:
                out, code = self.run_search(source)
            self.assertEqual(target.requests, [])
        self.assertEqual((code, out["http_status"]), (1, 302))

    def test_auth_denial_stops_without_retry_or_body_echo(self):
        for status in [401, 403]:
            with self.subTest(status=status), FixtureServer([(status, {}, SECRET.encode()), page()]) as server:
                out, code = self.run_search(server)
                self.assertEqual(code, 1)
                self.assertEqual(out["http_status"], status)
                self.assertEqual(len(server.requests), 1)
                self.assertNotIn(SECRET, json.dumps(out))

    def test_reflected_credential_never_reaches_output(self):
        with FixtureServer([page([hit(SECRET)])]) as server:
            out, code = self.run_search(server)
        self.assertEqual((code, out["stop_reason"]), (1, "unsafe_response"))
        self.assertNotIn(SECRET, json.dumps(out))

    def test_proxy_environment_is_ignored(self):
        with FixtureServer([page()]) as server, patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "ALL_PROXY": "http://127.0.0.1:1", "NO_PROXY": ""}):
            out, code = self.run_search(server)
        self.assertEqual(code, 0)

    def test_page_limit_preserves_resume_cursor_and_partial_hits(self):
        with FixtureServer([page([hit()], "next")]) as server:
            out, code = self.run_search(server, limits=client.Limits(pages=1))
        self.assertEqual(code, 2)
        self.assertFalse(out["traversal_complete"])
        self.assertEqual((out["next_cursor"], out["returned_count"]), ("next", 1))

    def test_cycle_fails_without_duplicate_results(self):
        with FixtureServer([page([hit()], "same"), page([hit()], "same")]) as server:
            out, code = self.run_search(server)
        self.assertEqual((code, out["stop_reason"], out["returned_count"]), (1, "cursor_cycle", 1))

    def test_byte_limit_preserves_last_completed_cursor(self):
        first = page([], "next")
        with FixtureServer([first, page([hit("x" * 10000)])]) as server:
            out, code = self.run_search(server, limits=client.Limits(page_bytes=1024))
        self.assertEqual((code, out["stop_reason"], out["pages"], out["next_cursor"]), (2, "byte_limit", 1, "next"))

    def test_total_byte_budget_is_independent_of_page_budget(self):
        first = page([], "next")
        first_bytes = len(json.dumps(first).encode())
        with FixtureServer([first, page([hit()])]) as server:
            out, code = self.run_search(server, limits=client.Limits(total_bytes=first_bytes))
        self.assertEqual((code, out["stop_reason"], len(server.requests)), (2, "byte_limit", 1))

    def test_offline_is_error_not_empty_success(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        self.configure(port)
        out, code = client.search("courses", "tidy", routes_path=self.routes)
        self.assertEqual(code, 1)
        self.assertFalse(out["traversal_complete"])
        self.assertEqual(out["stop_reason"], "transport_error")

    def test_slow_headers_have_wall_clock_bound(self):
        def slow(handler):
            for byte in b"HTTP/1.1 200 OK\r\n":
                handler.wfile.write(bytes([byte])); handler.wfile.flush(); time.sleep(.04)
        start = time.monotonic()
        with FixtureServer([slow]) as server:
            out, code = self.run_search(server, limits=client.Limits(seconds=.18, request_seconds=.15))
        self.assertNotEqual(code, 0)
        self.assertLess(time.monotonic() - start, .8)

    def test_truncated_length_rejects_otherwise_valid_json(self):
        body = json.dumps(page()).encode()
        with FixtureServer([(200, {"Content-Length": str(len(body) + 10)}, body)]) as server:
            out, code = self.run_search(server)
        self.assertEqual((code, out["stop_reason"]), (1, "truncated_response"))

    def test_expiring_close_delimited_body_is_not_success(self):
        def linger(handler):
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps(page()).encode()); handler.wfile.flush()
            time.sleep(.5)
        start = time.monotonic()
        with FixtureServer([linger]) as server:
            out, code = self.run_search(server, limits=client.Limits(request_seconds=.12))
        self.assertEqual((code, out["stop_reason"]), (2, "time_limit"))
        self.assertFalse(out["traversal_complete"])
        self.assertLess(time.monotonic() - start, .8)

    def test_complete_chunked_response_is_supported(self):
        def chunked(handler):
            body = json.dumps(page([hit()])).encode()
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Transfer-Encoding", "chunked")
            handler.end_headers()
            handler.wfile.write(f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n")
        with FixtureServer([chunked]) as server:
            out, code = self.run_search(server)
        self.assertEqual(code, 0)

    def test_ambiguous_framing_is_rejected(self):
        with FixtureServer([(200, {"Transfer-Encoding": "chunked"}, page())]) as server:
            out, code = self.run_search(server)
        self.assertEqual((code, out["stop_reason"]), (1, "invalid_response_headers"))

    def test_zero_deadline_does_not_make_request(self):
        with FixtureServer([page()]) as server:
            out, code = self.run_search(server, limits=client.Limits(seconds=0))
        self.assertEqual((code, out["stop_reason"], len(server.requests)), (2, "time_limit", 0))

    def test_content_type_and_compression_fail_closed(self):
        for headers in [{"Content-Type": "text/html"}, {"Content-Encoding": "gzip"}]:
            with self.subTest(headers=headers), FixtureServer([(200, headers, page())]) as server:
                out, code = self.run_search(server)
                self.assertEqual(code, 1)

    def test_unknown_project_does_not_open_credential(self):
        with patch.object(client, "owned_file", wraps=client.owned_file) as opened:
            out, code = client.search("other", "q", routes_path=self.routes)
        self.assertEqual(code, 1)
        self.assertEqual(opened.call_count, 1)

    def test_bad_permissions_and_symlinks_refuse(self):
        self.credential.chmod(0o644)
        out, code = client.search("courses", "q", routes_path=self.routes)
        self.assertEqual((code, out["stop_reason"]), (1, "unsafe_configured_file"))
        self.credential.chmod(0o600)
        link = self.root / "link.json"; link.symlink_to(self.credential)
        self.configure(1, credential_file=str(link))
        out, code = client.search("courses", "q", routes_path=self.routes)
        self.assertEqual((code, out["stop_reason"]), (1, "configured_file_unavailable"))

    def test_symlink_parent_refuses(self):
        directory = self.root / "real"; directory.mkdir()
        actual = directory / "key.json"; actual.write_bytes(self.credential.read_bytes()); actual.chmod(0o600)
        link = self.root / "linked"; link.symlink_to(directory, target_is_directory=True)
        self.configure(1, credential_file=str(link / "key.json"))
        out, code = client.search("courses", "q", routes_path=self.routes)
        self.assertEqual((code, out["stop_reason"]), (1, "configured_file_unavailable"))

    def test_missing_or_denied_credential_does_not_fallback(self):
        self.credential.unlink()
        out, code = client.search("courses", "q", routes_path=self.routes)
        self.assertEqual((code, out["stop_reason"]), (1, "configured_file_unavailable"))

    def test_capture_principal_mismatch_refuses_before_network(self):
        self.credential.write_text(json.dumps({"principal_id": "synthetic-capture", "epoch": 1, "secret": SECRET}))
        out, code = client.search("courses", "q", routes_path=self.routes)
        self.assertEqual((code, out["stop_reason"]), (1, "invalid_credential"))

    def test_header_injection_and_boolean_epoch_refuse(self):
        for epoch, secret in [(True, SECRET), (1, SECRET + "\r\nX: bad")]:
            self.credential.write_text(json.dumps({"principal_id": PRINCIPAL, "epoch": epoch, "secret": secret}))
            out, code = client.search("courses", "q", routes_path=self.routes)
            self.assertEqual(code, 1)

    def test_extra_endpoint_override_in_config_refuses(self):
        self.configure(1, endpoint="https://example.invalid")
        out, code = client.search("courses", "q", routes_path=self.routes)
        self.assertEqual((code, out["stop_reason"]), (1, "project_route_unavailable"))

    def test_nul_configured_path_has_safe_error(self):
        self.configure(1, credential_file="/tmp/invalid\x00.json")
        out, code = client.search("courses", "q", routes_path=self.routes)
        self.assertEqual((code, out["stop_reason"]), (1, "invalid_configured_path"))

    def test_accidental_secret_input_not_echoed(self):
        for query, cursor in [(SECRET, ""), ("q", SECRET)]:
            out, code = client.search("courses", query, cursor, routes_path=self.routes)
            self.assertEqual((code, out["stop_reason"]), (1, "unsafe_input"))
            self.assertNotIn(SECRET, json.dumps(out))

    def test_cli_uses_adjacent_config_and_outputs_valid_json(self):
        script = self.root / "archive_search.py"
        shutil.copyfile(client.__file__, script)
        with FixtureServer([page([hit()])]) as server:
            self.configure(server.server.server_port)
            run = subprocess.run([sys.executable, "-I", str(script), "courses", "staff-tidy"],
                                 capture_output=True, timeout=3)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["returned_count"], 1)
        self.assertNotIn(SECRET.encode(), run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
