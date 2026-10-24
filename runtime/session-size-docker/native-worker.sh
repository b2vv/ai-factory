#!/bin/sh
set -eu
case $0 in /*) code=${0%/*};;*) code=$PWD/${0%/*};;esac
. "$code/mapping-lib.sh"
[ "$#" -eq 3 ] || exit 2
host=$1;registry=$2;receipts=$3
case "$host" in claude|codex) ;;*) exit 2;;esac
private_dir "$registry";private_dir "$receipts"
explicit_key=${AI_FACTORY_SESSION_BINDING-}
umask 077
selection=$(mktemp -d "$receipts/selection.XXXXXXXX")
trap 'rm -f "$selection/payload.json"' EXIT
projection=$(sh "$code/session-key.sh" "$host" "$selection") || exit 2
key=$(printf '%s\n' "$projection" | head -n 1)
[ -z "$explicit_key" ] || [ "$explicit_key" = "$key" ] || exit 2
case "$key" in ''|*[!a-f0-9]*) exit 2;;esac
[ "${#key}" -eq 64 ] || exit 2
private_file "$registry/$key" || { echo "UNBOUND_OR_INVALID enrolled mapping; existing monitoring registration must remain" >&2;exit 2; }
[ "$(wc -c < "$registry/$key")" -le 8192 ] || exit 2
# Fixed six-line data format, never eval/source. Trailing or missing fields reject.
{ IFS= read -r version;IFS= read -r mapped_host;IFS= read -r session;IFS= read -r root;IFS= read -r transcript;IFS= read -r store;leaf=;case "$version" in AF16-MAPPING-1) ;;AF16-MAPPING-2) IFS= read -r leaf;[ "$leaf" = state ] || exit 2;;*) exit 2;;esac;extra=;if IFS= read -r extra;then exit 2;fi;[ -z "$extra" ]; } < "$registry/$key"
[ "$mapped_host" = "$host" ] || exit 2
clean_text "$session"
expected=$(printf '%s\n%s\n' "$host" "$session" | hash_key);expected=${expected%% *}
[ "$expected" = "$key" ] || exit 2
# Only minimal projected fields persist for an enrolled mapping.
printf '%s\n' "$projection" | tail -n +2 > "$selection/payload.json"
unset projection
exec < "$selection/payload.json"
# Only trusted record paths become argv. The payload is still stdin, never shell data.
umask 077
work=$(mktemp -d "$receipts/event.XXXXXXXX")
set -- hook --root "$root" --store "$store" --work "$work" --host "$host" --session "$session" --transcript "$transcript"

[ -z "$leaf" ] || set -- "$@" --store-leaf "$leaf"
exec sh "$code/dispatch.sh" "$@"
