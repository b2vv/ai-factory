#!/bin/sh
# Manual operations select the same trusted enrollment as native events.
# stdin is the author's summary (checkpoint) or {} (resume); never mapping data.
set -eu
AF16_EVENT_STARTED=$(date +%s);export AF16_EVENT_STARTED
case $0 in /*) code=${0%/*};;*) code=$PWD/${0%/*};;esac
. "$code/mapping-lib.sh"
[ "$#" -ge 5 ] || exit 2
mode=$1;host=$2;registry=$3;receipts=$4;requested_session=$5;pointer=${6-}
case "$mode:$#" in checkpoint:5|resume:6) ;;*) exit 2;;esac
case "$host" in claude|codex) ;;*) exit 2;;esac
[ "$mode" != resume ] || [ -n "$pointer" ] || exit 2
private_dir "$registry";private_dir "$receipts";clean_text "$requested_session"
key=$(printf '%s\n%s\n' "$host" "$requested_session" | hash_key);key=${key%% *}
private_file "$registry/$key" || { echo 'BLOCKED MANUAL_MAPPING_REQUIRED: use the enrolled host/session and the same registry as native.sh; no checkpoint was created.' >&2;exit 2; }
[ "$(wc -c < "$registry/$key")" -le 8192 ] || exit 2
{ IFS= read -r version;IFS= read -r mapped_host;IFS= read -r session;IFS= read -r root;IFS= read -r transcript;IFS= read -r store;leaf=;case "$version" in AF16-MAPPING-1) ;;AF16-MAPPING-2) IFS= read -r leaf;[ "$leaf" = state ] || exit 2;;*) exit 2;;esac;extra=;if IFS= read -r extra;then exit 2;fi;[ -z "$extra" ]; } < "$registry/$key"
[ "$mapped_host" = "$host" ] && [ "$session" = "$requested_session" ] || exit 2
canonical "$root";private_dir "$store"
[ -z "$leaf" ] || private_dir "$store/state"
umask 077
work=$(mktemp -d "$receipts/manual.XXXXXXXX")
set -- "$mode" --root "$root" --store "$store" --work "$work" --host "$host" --session "$session"
[ -z "$leaf" ] || set -- "$@" --store-leaf "$leaf"
[ "$mode" != resume ] || set -- "$@" --pointer "$pointer"
exec sh "$code/dispatch.sh" "$@"
