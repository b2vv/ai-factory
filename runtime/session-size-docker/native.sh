#!/bin/sh
# Native entrypoint: same original clock includes mapping/preflight/dispatch/cleanup.
set -u
started=$(date +%s);export AF16_EVENT_STARTED=$started
case $0 in /*) code=${0%/*};;*) code=$PWD/${0%/*};;esac
required=0;[ -z "${AI_FACTORY_HANDOFF-}" ] || required=1
exec 3<&0
sh "$code/native-worker.sh" "$@" <&3 & child=$!
# TERM gives the dispatcher the remaining cleanup reserve; KILL is the hard client stop.
(sleep 7 & sleeper=$!;trap 'kill "$sleeper" 2>/dev/null || :;wait "$sleeper" 2>/dev/null || :;exit' TERM
 wait "$sleeper";kill -TERM "$child" 2>/dev/null || :;sleep 2 & sleeper=$!;wait "$sleeper";kill -KILL "$child" 2>/dev/null || :) >/dev/null 2>&1 & timer=$!
trap 'kill -TERM "$child" 2>/dev/null || :' INT TERM HUP
wait "$child";rc=$?
# A signal can interrupt wait before the child exits. The original timer remains active.
if kill -0 "$child" 2>/dev/null;then wait "$child";rc=$?;fi
kill -TERM "$timer" 2>/dev/null || :;wait "$timer" 2>/dev/null || :
if [ "$rc" -ne 0 ];then
 if [ "$required" = 1 ];then echo 'BLOCKED required native handoff' >&2;exit 2;fi
 echo 'UNKNOWN optional native monitoring' >&2;exit 0
fi
exit 0
