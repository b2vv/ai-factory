#!/bin/sh
# Operator-only provisioning. Never invoked by hook or supplied a hook payload.
set -eu
[ "$#" -eq 7 ] || [ "$#" -eq 8 ] || { echo 'usage: bind-session registry trusted-roots host session root transcript store' >&2;exit 2; }
registry=$1;roots=$2;host=$3;session=$4;root=$5;transcript=$6;store=$7;leaf=${8-};version=AF16-MAPPING-1
case $0 in /*) code=${0%/*};;*) code=$PWD/${0%/*};;esac
. "$code/mapping-lib.sh"
private_dir "$registry";private_file "$roots";canonical "${roots%/*}"
case "$host" in claude|codex) ;;*) exit 2;;esac
clean_text "$session";canonical "$root";private_dir "$store"
# Exact configured root, never a common ancestor or a payload-discovered path.
LC_ALL=C grep -Fx -- "$root" "$roots" >/dev/null
case "$store/" in "$root/"*) exit 2;;esac;case "$root/" in "$store/"*) exit 2;;esac
[ -f "$transcript" ] && [ ! -L "$transcript" ];canonical "${transcript%/*}"
case "$transcript" in *','*|*'|'*) exit 2;;esac
printf '%s' "$transcript" | LC_ALL=C grep '[[:cntrl:]]' >/dev/null && exit 2
if [ -n "$leaf" ];then [ "$leaf" = state ] || exit 2;private_dir "$store/state";version=AF16-MAPPING-2;fi
key=$(printf '%s\n%s\n' "$host" "$session" | hash_key);key=${key%% *}
umask 077
# Atomic no-overwrite creation; session changes require a different binding, not replacement.
(set -C;{ printf '%s\n' "$version" "$host" "$session" "$root" "$transcript" "$store";[ -z "$leaf" ] || printf '%s\n' "$leaf"; } > "$registry/$key")
printf '%s\n' "$key"
