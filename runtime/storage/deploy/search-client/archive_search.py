#!/usr/bin/env python3
"""Bounded read-only Factory search client; installation is a separate operation.

Only the adjacent search-routes.json selects the port, principal and credential.
No environment-variable, arbitrary URL or credential-path CLI override exists.
This process remains subject to the caller's access policy; it is not a bypass.
"""
import argparse
import http.client
import json
import math
import os
from pathlib import Path
import socket
import stat
import sys
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlencode

MODE = "tokenized_simple_nfc_casefold"
ROUTES = Path(__file__).resolve().with_name("search-routes.json")


class Refused(Exception):
    def __init__(self, code, http_status=None):
        self.code, self.http_status = code, http_status
        super().__init__(code)


@dataclass(frozen=True)
class Limits:
    pages: int = 20
    seconds: float = 15.0
    request_seconds: float = 4.0
    page_bytes: int = 16 * 1024 * 1024
    total_bytes: int = 32 * 1024 * 1024


def strict_json(raw):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("duplicate key")
            obj[key] = value
        return obj

    def no_constant(_):
        raise ValueError("non-JSON constant")

    def finite_float(text):
        value = float(text)
        if not math.isfinite(value):
            raise ValueError("non-finite number")
        return value

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=no_constant, parse_float=finite_float)
    except (UnicodeError, ValueError, RecursionError):
        raise Refused("invalid_json") from None


def owned_file(path, cap, private=False):
    """Read a bounded owned regular file without following any path symlinks."""
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts or "\x00" in str(path):
        raise Refused("invalid_configured_path")
    fd = None
    try:
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        for part in path.parts[1:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                          dir_fd=fd)
            os.close(fd)
            fd = nxt
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                          dir_fd=fd)
        with os.fdopen(file_fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            forbidden = 0o077 if private else 0o022
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & forbidden or info.st_size > cap):
                raise Refused("unsafe_configured_file")
            raw = stream.read(cap + 1)
            if len(raw) > cap:
                raise Refused("configured_file_too_large")
            return raw
    except OSError:
        # Never include a file path, credential, exception body or fallback.
        raise Refused("configured_file_unavailable") from None
    finally:
        if fd is not None:
            os.close(fd)


def bounded_string(value, maximum, nonempty=True):
    if not isinstance(value, str) or (nonempty and not value):
        return False
    try:
        return len(value.encode("utf-8")) <= maximum
    except UnicodeError:
        return False


def load_route(alias, routes_path):
    cfg = strict_json(owned_file(routes_path, 64 * 1024))
    if (not isinstance(cfg, dict) or cfg.get("version") != 1
            or isinstance(cfg.get("version"), bool)
            or not isinstance(cfg.get("projects"), dict)):
        raise Refused("invalid_route_config")
    route = cfg["projects"].get(alias)
    if not isinstance(route, dict):
        raise Refused("project_route_unavailable")
    fmt = route.get("credential_format")
    common = {"project_id", "principal_id", "port", "credential_format"}
    paths = {"json": {"credential_file"}, "split": {"secret_file", "epoch_file"}}
    if not isinstance(fmt, str) or fmt not in paths or set(route) != common | paths[fmt]:
        raise Refused("project_route_unavailable")
    if (not bounded_string(route["project_id"], 4096)
            or not bounded_string(route["principal_id"], 256)
            or any(not bounded_string(route[key], 4096) for key in paths[fmt])
            or type(route["port"]) is not int or not 1 <= route["port"] <= 65535):
        raise Refused("invalid_route_config")
    if fmt == "json":
        credential = strict_json(owned_file(route["credential_file"], 16 * 1024, True))
        if not isinstance(credential, dict):
            raise Refused("invalid_credential")
        principal, epoch, secret = (credential.get(k) for k in ("principal_id", "epoch", "secret"))
    else:
        # Existing search-only split files: remove at most one conventional line ending.
        # Never strip arbitrary whitespace, combine formats or retry another binding.
        def line(path, cap):
            raw = owned_file(path, cap, True)
            if raw.endswith(b"\r\n"):
                raw = raw[:-2]
            elif raw.endswith(b"\n"):
                raw = raw[:-1]
            try:
                return raw.decode("ascii")
            except UnicodeError:
                raise Refused("invalid_credential") from None
        secret = line(route["secret_file"], 4098)
        epoch_text = line(route["epoch_file"], 21)
        if not epoch_text or not epoch_text.isascii() or not epoch_text.isdecimal():
            raise Refused("invalid_credential")
        epoch = int(epoch_text)
        principal = route["principal_id"]
    if (principal != route["principal_id"] or type(epoch) is not int or not 0 < epoch <= 2**63 - 1
            or not isinstance(secret, str) or not 16 <= len(secret) <= 4096
            or any(ord(c) < 33 or ord(c) > 126 for c in secret)
            or any(ord(c) < 33 or ord(c) > 126 for c in principal)):
        raise Refused("invalid_credential")
    return route, {"X-Principal-Id": principal, "X-Grant-Epoch": str(epoch),
                   "X-Secret": secret, "Accept": "application/json"}


def safe_value(value, secret, depth=0):
    if depth > 64:
        raise Refused("invalid_response")
    if isinstance(value, str):
        if not bounded_string(value, 32 * 1024 * 1024, False) or secret in value:
            raise Refused("unsafe_response")
    elif isinstance(value, dict):
        for key, item in value.items():
            safe_value(key, secret, depth + 1)
            safe_value(item, secret, depth + 1)
    elif isinstance(value, list):
        for item in value:
            safe_value(item, secret, depth + 1)


def validate_page(page, project, secret):
    safe_value(page, secret)
    if (not isinstance(page, dict) or page.get("project") != project
            or page.get("search_mode") != MODE or page.get("derived") is not True
            or not isinstance(page.get("hits"), list)
            or not bounded_string(page.get("next_cursor"), 8192, False)):
        raise Refused("invalid_response")
    for hit in page["hits"]:
        if not isinstance(hit, dict) or hit.get("Project") != project:
            raise Refused("invalid_response")
        for field in ("Provider", "SourceInstance", "SessionID", "MessageID", "ParentID", "Text"):
            if not isinstance(hit.get(field), str):
                raise Refused("invalid_response")
    if "snippets" in page:
        if not isinstance(page["snippets"], list):
            raise Refused("invalid_response")
        identities = {(h["Project"], h["SourceInstance"], h["SessionID"], h["MessageID"])
                      for h in page["hits"]}
        for snippet in page["snippets"]:
            if not isinstance(snippet, dict) or not isinstance(snippet.get("identity"), str):
                raise Refused("invalid_response")
            if (not isinstance(snippet.get("text"), str)
                    or not isinstance(snippet.get("basis"), str)
                    or type(snippet.get("match")) is not bool
                    or type(snippet.get("truncated")) is not bool):
                raise Refused("invalid_response")
            identity = strict_json(snippet["identity"].encode("utf-8"))
            if (not isinstance(identity, list) or len(identity) != 4
                    or not all(isinstance(item, str) for item in identity)
                    or tuple(identity) not in identities):
                raise Refused("invalid_response")
    return page


def fetch_page(route, headers, query, cursor, deadline, limit, limits):
    remaining = min(deadline - time.monotonic(), limits.request_seconds)
    if remaining <= 0:
        raise Refused("time_limit")
    # HTTPConnection uses neither HTTP_PROXY nor redirects. Host/path are fixed.
    conn = http.client.HTTPConnection("127.0.0.1", route["port"], timeout=remaining)
    request_deadline = time.monotonic() + remaining
    expired = threading.Event()
    timer = None
    try:
        conn.connect()
        sock = conn.sock

        def expire():
            expired.set()
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        # Interrupt slow headers and slow bodies, not merely an idle socket.
        timer = threading.Timer(max(0.001, request_deadline - time.monotonic()), expire)
        timer.daemon = True
        timer.start()
        params = {"project": route["project_id"], "q": query}
        if cursor:
            params["cursor"] = cursor
        conn.request("GET", "/v1/search/query?" + urlencode(params), headers=headers)
        response = conn.getresponse()
        if expired.is_set() or time.monotonic() >= min(deadline, request_deadline):
            raise Refused("time_limit")
        if response.status != 200:
            raise Refused("http_error", response.status)
        if (response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json"
                or response.getheader("Content-Encoding", "identity").lower() != "identity"):
            raise Refused("invalid_response_headers")
        lengths = response.headers.get_all("Content-Length", [])
        transfers = response.headers.get_all("Transfer-Encoding", [])
        declared = None
        if len(lengths) > 1 or len(transfers) > 1 or (lengths and transfers):
            raise Refused("invalid_response_headers")
        if lengths:
            value = lengths[0].strip()
            if not value.isascii() or not value.isdigit() or len(value) > 12:
                raise Refused("invalid_response_headers")
            declared = int(value)
            if declared > limit:
                raise Refused("byte_limit")
        if transfers and transfers[0].strip().lower() != "chunked":
            raise Refused("invalid_response_headers")
        raw = bytearray()
        while True:
            if time.monotonic() >= min(deadline, request_deadline):
                raise Refused("time_limit")
            chunk = response.read1(min(65536, limit + 1 - len(raw)))
            if expired.is_set() or time.monotonic() >= min(deadline, request_deadline):
                raise Refused("time_limit")
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > limit:
                raise Refused("byte_limit")
        if declared is not None and len(raw) != declared:
            raise Refused("truncated_response")
        return strict_json(bytes(raw)), len(raw)
    except Refused:
        raise
    except (OSError, http.client.HTTPException):
        if time.monotonic() >= min(deadline, request_deadline):
            raise Refused("time_limit") from None
        raise Refused("transport_error") from None
    finally:
        if timer is not None:
            timer.cancel()
        conn.close()


def search(alias, query, cursor="", *, routes_path=ROUTES, limits=Limits()):
    result = {"status": "error", "traversal_complete": False, "hits": [],
              "snippets": [], "returned_count": 0, "pages": 0,
              "next_cursor": "", "total_exact": False,
              "consistency": "live_non_snapshot", "capture_completeness": "unknown",
              "index_freshness": "unknown"}
    try:
        if (not bounded_string(alias, 128) or not bounded_string(query, 4096, False)
                or not bounded_string(cursor, 8192, False)):
            raise Refused("invalid_input")
        route, headers = load_route(alias, routes_path)
        # Do not echo arbitrary input or a token accidentally supplied as input.
        if headers["X-Secret"] in query or headers["X-Secret"] in cursor:
            raise Refused("unsafe_input")
        safe_value(route["project_id"], headers["X-Secret"])
        result["next_cursor"] = cursor
        result.update(project=route["project_id"], search_mode=MODE)
        deadline = time.monotonic() + limits.seconds
        spent, seen = 0, {cursor}
        for _ in range(limits.pages):
            if time.monotonic() >= deadline:
                raise Refused("time_limit")
            remaining = limits.total_bytes - spent
            if remaining <= 0:
                raise Refused("byte_limit")
            page, size = fetch_page(route, headers, query, cursor, deadline,
                                    min(limits.page_bytes, remaining), limits)
            page = validate_page(page, route["project_id"], headers["X-Secret"])
            nxt = page["next_cursor"]
            if nxt and nxt in seen:
                raise Refused("cursor_cycle")
            result["hits"].extend(page["hits"])
            result["snippets"].extend(page.get("snippets", []))
            result["pages"] += 1
            result["returned_count"] = len(result["hits"])
            result["next_cursor"] = nxt
            spent += size
            if not nxt:
                result.update(status="exhausted", traversal_complete=True, stop_reason="end_of_traversal")
                return result, 0
            cursor = nxt
            seen.add(cursor)
        raise Refused("page_limit")
    except Refused as exc:
        result["stop_reason"] = exc.code
        if exc.http_status is not None:
            result["http_status"] = exc.http_status
        if exc.code in {"page_limit", "time_limit", "byte_limit"}:
            result["status"] = "incomplete"
            return result, 2
        return result, 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="installed project alias")
    parser.add_argument("query", help="plain text; multiple terms are ANDed")
    parser.add_argument("--cursor", default="", help="resume the same project/query traversal")
    args = parser.parse_args()
    result, code = search(args.project, args.query, args.cursor)
    json.dump(result, sys.stdout, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
