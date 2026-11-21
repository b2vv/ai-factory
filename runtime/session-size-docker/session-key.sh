#!/bin/sh
# Small source-free parser phase; shares native.sh's original event clock.
set -eu
host=$1;work=$2
case "$host" in claude|codex) ;;*) exit 2;;esac
case $0 in /*) code=${0%/*};;*) code=$PWD/${0%/*};;esac
start=${AF16_EVENT_STARTED-}
case "$start" in ''|*[!0-9]*) exit 2;;esac
deadline=$((start+7));cleanup_end=$((start+9))
identity_dir=$(mktemp -d "$work/identity.XXXXXXXX") || exit 2
suffix=${identity_dir##*.};rmdir "$identity_dir"
name=ai-factory-$host-parser-$suffix;created=0;active=;timer=;command_limit=
run() {
 remaining=$((deadline-$(date +%s)));[ "$remaining" -gt 0 ] || return 124
 [ -z "${command_limit-}" ] || [ "$remaining" -le "$command_limit" ] || remaining=$command_limit
 exec 3<&0
 (ulimit -f 32;exec "$@" <&3) & active=$!
 (sleep "$remaining" & sleeper=$!;trap 'kill "$sleeper" 2>/dev/null || :;wait "$sleeper" 2>/dev/null || :;exit' TERM;wait "$sleeper";kill -TERM "$active" 2>/dev/null || :;kill -KILL "$active" 2>/dev/null || :) >/dev/null 2>&1 & timer=$!
 set +e;wait "$active";rc=$?;set -e
 kill "$timer" 2>/dev/null || :;wait "$timer" 2>/dev/null || :;active=;timer=
 return "$rc"
}
. "$code/cleanup.sh"

trap 'cleanup || :;exit 2' INT TERM HUP
trap 'cleanup || :' EXIT
image=python@sha256:4cea12ab7d78a3312c85f8cab19b6971d4fe9704da25443986c0bc20a6678850
created=1
run docker create --pull never -i --name "$name" --label com.docker.compose.project=ai-factory --label com.docker.compose.service=parser --label com.docker.compose.oneoff=False --label com.docker.compose.config-hash=ai-factory-ephemeral-v1 --label "ai-factory.invocation=$name" --platform linux/amd64 --network none --read-only --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges --cpus 2 --memory 2g --memory-swap 2g --pids-limit 128 --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16777216 --log-driver none --env PYTHONDONTWRITEBYTECODE=1 --entrypoint python3 "$image" -c "$(cat "$code/session-key.py")" "$host" > "$work/parser-cid.txt" 2>/dev/null || { cleanup || :;exit 2; }
fmt='{{.State.Status}}|{{.Config.Image}}|{{.Config.User}}|{{.HostConfig.NetworkMode}}|{{.HostConfig.ReadonlyRootfs}}|{{.HostConfig.Privileged}}|{{.HostConfig.NanoCpus}}|{{.HostConfig.Memory}}|{{.HostConfig.MemorySwap}}|{{.HostConfig.PidsLimit}}|{{json .HostConfig.CapDrop}}|{{json .HostConfig.SecurityOpt}}|{{index .HostConfig.Tmpfs "/tmp"}}|{{.Path}}|{{len .Mounts}}|{{if .HostConfig.CapAdd}}{{len .HostConfig.CapAdd}}{{else}}0{{end}}|{{if .HostConfig.Devices}}{{len .HostConfig.Devices}}{{else}}0{{end}}|{{if .HostConfig.DeviceRequests}}{{len .HostConfig.DeviceRequests}}{{else}}0{{end}}|{{if .HostConfig.PortBindings}}{{len .HostConfig.PortBindings}}{{else}}0{{end}}|{{.HostConfig.PidMode}}|{{.HostConfig.IpcMode}}|{{.HostConfig.LogConfig.Type}}'
run docker inspect --format "$fmt" "$name" > "$work/parser-policy.txt" 2>/dev/null || { cleanup || :;exit 2; }
expected="created|$image|$(id -u):$(id -g)|none|true|false|2000000000|2147483648|2147483648|128|[\"ALL\"]|[\"no-new-privileges\"]|rw,noexec,nosuid,nodev,size=16777216|python3|0|0|0|0|0||private|none"
[ "$(cat "$work/parser-policy.txt")" = "$expected" ] || { cleanup || :;exit 2; }
# Only native stdin enters this parser. No source, registry, state or transcript mounts.
run docker start -ai "$name" > "$work/parser-projection.tmp" 2>/dev/null || { cleanup || :;exit 2; }
projection=$(cat "$work/parser-projection.tmp")
rm "$work/parser-projection.tmp"
run docker inspect --format '{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}|{{.State.Dead}}' "$name" > "$work/parser-terminal.txt" 2>/dev/null || { cleanup || :;exit 2; }
[ "$(cat "$work/parser-terminal.txt")" = 'exited|0|false|false' ] || { cleanup || :;exit 2; }
[ "$(printf %s "$projection" | wc -c)" -le 16384 ] || { cleanup || :;exit 2; }
cleanup || exit 2
trap - INT TERM HUP
printf '%s\n' "$projection"
