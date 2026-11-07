#!/bin/sh
# Thin Codex command-hook wrapper: delegates to codex_capture_catcher.py (same directory).
# Register for the UserPromptSubmit and Stop events; all behavior, scope, privacy and
# fail-safe rules live in codex_capture_catcher.py and README.md. Configuration is by
# environment; the project is chosen from the EXPLICIT mapping file, keyed by the event's
# own `cwd` field — never by this process's working directory.
#
#   AF_CODEX_CATCHER_MAP   path to the operator mapping JSON (required)   [local, not committed]
#   AF_CODEX_ENDPOINT      default http://127.0.0.1:8780
#   AF_CODEX_STATUS_FILE   optional path for an appended, payload/secret-free status log
#
# A command hook must never block the turn: the catcher always exits 0.
#
# NOTE: installing this into ~/.codex/hooks.json requires establishing per-hook trust
# (config.toml trusted_hash) and must not clobber any existing hook chain. That install is a
# separate, explicitly authorized step and is NOT performed by shipping this file.
set -u
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 -I "$dir/codex_capture_catcher.py"
