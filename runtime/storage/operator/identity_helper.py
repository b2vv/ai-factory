#!/usr/bin/env python3
"""Operator-only, Docker-free identity/enrollment helper (M8 / PLAN v4 section 9.1, D1).

When Docker is absent the storage server (and its HTTP API) is unavailable, but an operator
still needs to prepare IDENTITY material offline: the bootstrap operator token the server reads
at startup, and project enrollment requests to feed to the API later. This helper does exactly
that and nothing more.

Deliberate NON-goals (it is a helper, not a host distribution):
  - it does NOT start the server, open any socket, or expose an API;
  - it does NOT connect to MongoDB/PostgreSQL or any network endpoint;
  - it does NOT register hooks, install anything, or enable capture;
  - it writes ONLY to operator-chosen output paths and never into the repository.

Secrets are generated locally with `secrets` and written 0600; they are never printed to
stdout and never committed. Run with `python3 -I` when invoked on untrusted working dirs.

Commands:
  init-token    --out PATH [--id operator] [--force]
                Write a {"id","secret"} operator token JSON (0600) that cmd/factory reads via
                -operator-token. Refuses to overwrite unless --force.
  enroll-project --uuid UUID --label LABEL --out PATH [--force]
                Write a reviewable project-enrollment request JSON (no secret, no network) that
                an operator can later POST to /v1/projects. Validates the UUID shape.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import secrets
import stat
import sys
import uuid


def _write_private(path: str, data: dict, force: bool) -> None:
    """Write data as JSON to path with 0600 permissions, failing closed on an existing file."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if not force:
        flags |= os.O_EXCL  # refuse to clobber existing identity material
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        raise SystemExit(f"refusing to overwrite existing file: {path} (pass --force to replace)")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    # Re-assert 0600 in case of a lenient umask on some platforms.
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def cmd_init_token(args: argparse.Namespace) -> int:
    if not args.id:
        raise SystemExit("--id must be non-empty")
    token = {"id": args.id, "secret": secrets.token_urlsafe(32)}
    _write_private(args.out, token, args.force)
    # Never print the secret; report only the path and id.
    print(f"wrote operator token for id={args.id!r} to {args.out} (mode 0600)")
    return 0


def _valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def cmd_enroll_project(args: argparse.Namespace) -> int:
    if not _valid_uuid(args.uuid):
        raise SystemExit(f"--uuid is not a valid UUID: {args.uuid!r}")
    if not args.label.strip():
        raise SystemExit("--label must be non-empty")
    record = {
        "kind": "project-enrollment-request",
        "uuid": args.uuid,
        "label": args.label,
        "created_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "Operator-prepared offline. Apply by POSTing {UUID,Label} to /v1/projects with the operator secret once the server is reachable. This file contains no secret and performs no network action.",
    }
    _write_private(args.out, record, args.force)
    print(f"wrote project enrollment request for uuid={args.uuid} to {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="identity_helper", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    t = sub.add_parser("init-token", help="write a 0600 operator token JSON")
    t.add_argument("--out", required=True, help="output path for the token file")
    t.add_argument("--id", default="operator", help="operator principal id (default: operator)")
    t.add_argument("--force", action="store_true", help="overwrite an existing file")
    t.set_defaults(func=cmd_init_token)

    e = sub.add_parser("enroll-project", help="write a project enrollment request JSON")
    e.add_argument("--uuid", required=True, help="project UUID")
    e.add_argument("--label", required=True, help="human-readable project label")
    e.add_argument("--out", required=True, help="output path for the request file")
    e.add_argument("--force", action="store_true", help="overwrite an existing file")
    e.set_defaults(func=cmd_enroll_project)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
