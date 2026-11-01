#!/bin/sh
# Thin Claude Code `Stop` hook wrapper: delegates to capture_bridge.py (same directory).
# All behavior, scope, privacy and fail-safe rules are documented in capture_bridge.py and
# README.md. Configuration is via environment (set by the project-scoped settings that
# install this hook); cwd is NEVER used to infer the project.
#
#   AF_CAPTURE_PROJECT               DG project UUID (explicit operator mapping)   [required]
#   AF_CAPTURE_OPERATOR_SECRET_FILE  path to the 0600 operator.json ({"id","secret"}) [required]
#   AF_CAPTURE_ENDPOINT              default http://127.0.0.1:8780
#   AF_CAPTURE_SOURCE                default claude-code-dg
#   AF_CAPTURE_STATUS_FILE           optional path for an appended, payload/secret-free status log
#
# A Stop hook must never block the session: the bridge always exits 0.
set -u
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 -I "$dir/capture_bridge.py"
