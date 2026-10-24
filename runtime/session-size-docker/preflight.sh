#!/bin/sh
# Read-only host filesystem checks, always called under dispatcher's active budget.
set -eu
root=$1;store=$2;work=$3;code=$4;transcript=$5
pathcheck() {
 case "$1" in /*) ;;*) return 1;;esac
 case "$1" in *','*|*'|'*) return 1;;esac
 printf '%s' "$1" | LC_ALL=C grep '[[:cntrl:]]' >/dev/null && return 1
 q=$1;while [ "$q" != / ];do [ ! -L "$q" ] || return 1;q=${q%/*};[ -n "$q" ] || q=/;done
 [ -d "$1" ] && [ "$(CDPATH= cd -- "$1" && pwd -P)" = "$1" ]
}
for p in "$root" "$store" "$work" "$code";do pathcheck "$p";done
for item in "$work"/.[!.]* "$work"/..?* "$work"/*;do [ ! -e "$item" ] && [ ! -L "$item" ] || exit 2;done
for p in "$root" "$store";do case "$work/" in "$p/"*) exit 2;;esac;case "$p/" in "$work/"*) exit 2;;esac;done
case "$root/" in "$store/"*) exit 2;;esac
case "$store/" in "$root/"*) exit 2;;esac
if [ -n "$transcript" ];then [ -f "$transcript" ] && [ ! -L "$transcript" ];pathcheck "${transcript%/*}";fi
