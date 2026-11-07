#!/bin/sh
# Operator convenience front-end over bind-session.sh / dispatch.sh.
#
# It removes repeated manual path configuration and fresh-receipt-dir bookkeeping by
# deriving one private layout from a single base directory and minting a new receipt
# directory per operation. It changes NO safety contract: enrollment still requires an
# explicitly named repository recorded in the trusted-roots file, and every checkpoint,
# resume and resolve still runs through dispatch.sh with its full Docker policy checks.
# It never registers host hooks, grants Git trust, reads transcripts, or selects a
# "latest" checkpoint. Not a hook; never pass it a hook payload.
#
# Layout under the base (AF_HOME env or --home DIR; default $HOME/.agents/ai-factory):
#   registry/        enrolled host+session mappings      (private 0700)
#   receipts/        per-operation receipt parents       (private 0700)
#   store-envelope/  handoff state envelope, "state" leaf (private 0700, outside repo)
#   trusted-roots    newline-list of approved repo roots  (private 0600)
#
# Usage:
#   af.sh enroll     --repo DIR --session ID --transcript FILE [--approve-root] [--host claude|codex] [--home DIR]
#       Naming --repo does not grant trust. The repo must already be in trusted-roots, or
#       approval must be given explicitly with --approve-root (a separate, deliberate action).
#   af.sh checkpoint --repo DIR --session ID               [--host ...] [--home DIR]   # summary JSON on stdin
#   af.sh resume     --repo DIR --session ID [--pointer ID] [--host ...] [--home DIR]   # no --pointer => unambiguous auto-resolve
#   af.sh candidates --repo DIR --session ID [--match STR]  [--host ...] [--home DIR]  # read-only task list
#   af.sh continue   --repo DIR --session ID [--match STR]  [--host ...] [--home DIR]  # post-/clear entry: task list
#       `continue` is the post-/clear (or Codex successor) entry verb and is the SAME read-only
#       task-selection listing as `candidates`. It does NOT auto-resume, claim, or bind by recency
#       or by a lone snapshot match: the agent shows the items (plus Start fresh), the human picks
#       an exact id, and a separate `resume --pointer <id>` binds it with full revalidation.
#       `--match` (id prefix or goal substring) finds an intended older task beyond the first page.
set -eu

case $0 in /*) code=${0%/*};; *) code=$PWD/${0%/*};; esac
cmd=${1-}; [ "$#" -gt 0 ] && shift || true
case "$cmd" in enroll|checkpoint|resume|candidates|continue) ;; *)
  echo 'usage: af.sh enroll|checkpoint|resume|candidates|continue --repo DIR --session ID [--host H] [--home DIR] [--transcript FILE] [--pointer ID]' >&2; exit 2;; esac

home=${AF_HOME-}; host=claude; repo=; session=; transcript=; pointer=; approve=0; match=
while [ "$#" -gt 0 ]; do
  # --approve-root is a deliberate value-less approval action, distinct from naming --repo.
  case "$1" in --approve-root) approve=1; shift; continue;; esac
  [ "$#" -ge 2 ] || { echo 'BLOCKED each option needs a value' >&2; exit 2; }
  case "$1" in
    --home) home=$2;; --host) host=$2;; --repo) repo=$2;; --session) session=$2;;
    --transcript) transcript=$2;; --pointer) pointer=$2;; --match) match=$2;;
    *) echo "BLOCKED unknown option: $1" >&2; exit 2;; esac
  shift 2
done
# --match only narrows the read-only candidates/continue listing; never a binding selector.
[ -z "$match" ] || case "$cmd" in candidates|continue) ;; *) echo 'BLOCKED --match only applies to candidates|continue' >&2; exit 2;; esac
[ -n "$home" ] || home=${HOME:?HOME unset}/.agents/ai-factory
case "$host" in claude|codex) ;; *) echo 'BLOCKED host must be claude or codex' >&2; exit 2;; esac
[ -n "$repo" ] || { echo 'BLOCKED --repo is required' >&2; exit 2; }
[ -n "$session" ] || { echo 'BLOCKED --session is required' >&2; exit 2; }
[ -d "$repo" ] || { echo 'BLOCKED --repo is not an existing directory' >&2; exit 2; }
# Canonical physical repo path (no symlink components), as the guards require.
repo=$(cd "$repo" 2>/dev/null && pwd -P) || { echo 'BLOCKED cannot resolve --repo to a canonical path' >&2; exit 2; }

# Validate the entire writable layout before mkdir/chmod/append.
python3 - "$home" <<'AF_PATH_CHECK'
import os, stat, sys
from pathlib import Path
root=Path(sys.argv[1])
if not root.is_absolute() or '..' in root.parts:
    raise SystemExit('BLOCKED canonical absolute --home required')
for p in [root,root/'registry',root/'receipts',root/'store-envelope',root/'trusted-roots']:
    for q in [p,*p.parents]:
        if q.is_symlink():raise SystemExit('BLOCKED symlink in writable layout')
    if not p.exists():continue
    st=p.stat()
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode)&0o077:
        raise SystemExit('BLOCKED writable layout must be private and owned')
    if p==root/'trusted-roots':
        if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:raise SystemExit('BLOCKED unsafe trusted-roots')
    elif not stat.S_ISDIR(st.st_mode):raise SystemExit('BLOCKED directory required')
AF_PATH_CHECK

umask 077
registry=$home/registry
receipts=$home/receipts
store=$home/store-envelope
roots=$home/trusted-roots
mkdir -p "$registry" "$receipts" "$store"
# A fresh, private receipt parent per operation; dispatch/bind create their own subdirs.
# Receipts are retained as private evidence and are not cleaned up here.
work=$(mktemp -d "$receipts/op.XXXXXXXX")

if [ "$cmd" = enroll ]; then
  [ -n "$transcript" ] || { echo 'BLOCKED enroll needs --transcript FILE' >&2; exit 2; }
  [ -f "$transcript" ] || { echo 'BLOCKED --transcript is not an existing file' >&2; exit 2; }
  # Naming --repo is NOT approval. The repo must already be an approved trusted root,
  # or approval must be given here as the separate, explicit --approve-root action.
  # Without that, enrollment is refused rather than trusting a path by itself.
  [ -f "$roots" ] || : > "$roots"
  chmod 600 "$roots"
  if ! LC_ALL=C grep -Fxq -- "$repo" "$roots"; then
    [ "$approve" = 1 ] || { echo "BLOCKED repo is not an approved trusted root. Approving a path to connect it is a separate action: re-run enroll with --approve-root to approve $repo, or add it to $roots first." >&2; exit 2; }
    printf '%s\n' "$repo" >> "$roots"
    echo "approved and recorded trusted root (explicit --approve-root): $repo" >&2
  fi
  # bind-session.sh enforces canonical paths, root membership and private permissions.
  exec sh "$code/bind-session.sh" "$registry" "$roots" "$host" "$session" "$repo" "$transcript" "$store" state
fi

if [ "$cmd" = checkpoint ]; then
  # Summary JSON is read from stdin and passed straight through to dispatch.sh.
  exec sh "$code/dispatch.sh" checkpoint --root "$repo" --store "$store" --store-leaf state --work "$work" --host "$host" --session "$session"
fi

if [ "$cmd" = resume ]; then
  # explicit pointer resumes that exact checkpoint; without one, resolve auto-resumes ONLY an
  # unambiguous completed checkpoint for this repository state (else it asks you).
  if [ -n "$pointer" ]; then
    exec sh "$code/dispatch.sh" resume --root "$repo" --store "$store" --store-leaf state --work "$work" --host "$host" --session "$session" --pointer "$pointer"
  fi
  exec sh -c 'printf "{}\n" | sh "$1" resolve --root "$2" --store "$3" --store-leaf state --work "$4" --host "$5" --session "$6"' _ "$code/dispatch.sh" "$repo" "$store" "$work" "$host" "$session"
fi

# candidates and continue are the SAME read-only task-selection listing (continue is the named
# post-/clear entry verb). Neither resumes, claims, nor auto-binds: the agent presents the items
# (plus Start fresh), the human picks an exact id, and a SEPARATE `resume --pointer <id>` performs
# the bind with its own revalidation. A snapshot_mismatch item is reported, not silently resumed;
# selecting one still hits SNAPSHOT_MISMATCH on resume (recovery, not a dead end). An infrastructure
# failure here surfaces as this command's own non-zero status — it is NOT turned into an empty list.
if [ "$cmd" = candidates ] || [ "$cmd" = continue ]; then
  if [ -n "$match" ]; then
    exec sh -c 'printf "{}\n" | sh "$1" candidates --root "$2" --store "$3" --store-leaf state --work "$4" --host "$5" --session "$6" --match "$7"' _ "$code/dispatch.sh" "$repo" "$store" "$work" "$host" "$session" "$match"
  fi
  exec sh -c 'printf "{}\n" | sh "$1" candidates --root "$2" --store "$3" --store-leaf state --work "$4" --host "$5" --session "$6"' _ "$code/dispatch.sh" "$repo" "$store" "$work" "$host" "$session"
fi
echo "BLOCKED unhandled command: $cmd" >&2; exit 2
