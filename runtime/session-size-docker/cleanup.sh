#!/bin/sh
# Invocation-scoped reconciliation, bounded by the original cleanup reserve.
cleanup_done=0;cleanup_rc=0
cleanup() {
 [ "$cleanup_done" = 0 ] || return "$cleanup_rc"
 cleanup_done=1;cleanup_rc=0
 trap ':' INT TERM HUP
 [ -z "$active" ] || { kill -TERM "$active" 2>/dev/null || :;kill -KILL "$active" 2>/dev/null || :;wait "$active" 2>/dev/null || :; }
 [ -z "$timer" ] || { kill -TERM "$timer" 2>/dev/null || :;wait "$timer" 2>/dev/null || :; }
 active=;timer=;deadline=$cleanup_end;command_limit=1
 [ "${created-0}" = 1 ] || return 0
 rm -f "$work/parser-projection.tmp"
 printf '{"invocation":"%s","status":"PENDING"}\n' "$name" > "$work/cleanup-status.json"
 worker_pending=1;validator_pending=${validator_created-0}
 while [ "$(date +%s)" -lt "$cleanup_end" ];do
  # One daemon list request avoids serial inspect calls starving another target.
  run docker ps -a --no-trunc --filter "label=ai-factory.invocation=$name" --format '{{.ID}}|{{.Names}}|{{.Label "ai-factory.invocation"}}' > "$work/cleanup-identity.tmp" 2>> "$work/cleanup.err" || :
  worker_id=;validator_id=
  # Treat list output as untrusted; require exact owned names and full IDs.
  while IFS='|' read -r cleanup_id cleanup_object cleanup_owner cleanup_extra;do
   [ -z "$cleanup_extra" ] && [ "$cleanup_owner" = "$name" ] || continue
   case "$cleanup_id" in ''|*[!a-f0-9]*) continue;;esac
   [ "${#cleanup_id}" = 64 ] || continue
   if [ "$cleanup_object" = "$name" ] && [ "$worker_pending" = 1 ];then worker_id=$cleanup_id;fi
   if [ "$validator_pending" = 1 ] && [ "$cleanup_object" = "$validator" ];then validator_id=$cleanup_id;fi
  done < "$work/cleanup-identity.tmp"
  rm -f "$work/cleanup-identity.tmp"
  set --;[ -z "$worker_id" ] || set -- "$@" "$worker_id"
  [ -z "$validator_id" ] || set -- "$@" "$validator_id"
  if [ "$#" -gt 0 ];then
   # Submit all verified IDs together, never a project/name-prefix sweep.
   run docker rm -f "$@" > "$work/cleanup-removed.tmp" 2>> "$work/cleanup.err" || :
   while IFS= read -r removed_id;do
    [ -z "$worker_id" ] || [ "$removed_id" != "$worker_id" ] || worker_pending=0
    [ -z "$validator_id" ] || [ "$removed_id" != "$validator_id" ] || validator_pending=0
   done < "$work/cleanup-removed.tmp"
   cat "$work/cleanup-removed.tmp" >> "$work/cleanup.out"
   rm -f "$work/cleanup-removed.tmp"
  fi
  [ "$worker_pending$validator_pending" != 00 ] || break
  sleep 0.1
 done
 cleanup_status=REMOVED
 if [ "$worker_pending$validator_pending" != 00 ];then cleanup_rc=1;cleanup_status=UNRESOLVED;fi
 printf '{"invocation":"%s","status":"%s"}\n' "$name" "$cleanup_status" > "$work/cleanup-status.json"
 return "$cleanup_rc"
}
