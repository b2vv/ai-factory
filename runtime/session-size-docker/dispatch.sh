#!/bin/sh
# Candidate only: no host registration; requires explicitly authorized canonical roots.
set -eu
now=$(date +%s);start=${AF16_EVENT_STARTED-$now}
case "$start" in ''|*[!0-9]*) exit 2;;esac
[ "${#start}" -le 10 ] && [ "$start" -le "$now" ] || exit 2
deadline=$((start+7));cleanup_end=$((start+9))
mode=${1-};[ "$#" -gt 0 ] && shift
pointer=${AI_FACTORY_HANDOFF-}
if [ "$mode" = optional ]; then
 [ "$#" -eq 0 ] && [ -z "$pointer" ] || { echo 'BLOCKED explicit request in optional mode' >&2;exit 2; }
 exit 0
fi
case "$mode" in hook|checkpoint|resume) ;;*) echo 'BLOCKED mode' >&2;exit 2;;esac
root=;store=;leaf=;work=;host=;session=;transcript=
while [ "$#" -gt 0 ]; do
 [ "$#" -ge 2 ] || exit 2
 case "$1" in
 --root) [ -z "$root" ] || exit 2;root=$2;; --store) [ -z "$store" ] || exit 2;store=$2;;
 --store-leaf) [ -z "$leaf" ] && [ "$2" = state ] || exit 2;leaf=$2;; --work) [ -z "$work" ] || exit 2;work=$2;; --host) [ -z "$host" ] || exit 2;host=$2;;
 --session) [ -z "$session" ] || exit 2;session=$2;; --transcript) [ -z "$transcript" ] || exit 2;transcript=$2;;
 --pointer) [ -z "$pointer" ] || [ "$pointer" = "$2" ] || exit 2;pointer=$2;;*) exit 2;;esac
 shift 2
done
required=1;[ "$mode" != hook ] || [ -n "$pointer" ] || required=0
fail() { if [ "$required" = 1 ];then echo 'BLOCKED required handoff' >&2;exit 2;else echo 'UNKNOWN optional monitoring' >&2;exit 0;fi; }
case "$host" in claude|codex) ;;*) fail;;esac
case $0 in /*) code=${0%/*};;*) code=$PWD/${0%/*};;esac
command -v docker >/dev/null 2>&1 || fail
exec 3<&0
umask 077
name=af16-$$-$start;validator=$name-validator;created=0;validator_created=0
cid=;active=;timer=;timedout=0
# Client operations are interrupted before the original aggregate cleanup deadline.
run() {
 now=$(date +%s);remaining=$((deadline-now));[ "$remaining" -gt 0 ] || return 124
 (ulimit -f 1024;exec "$@" <&3) & active=$!
 (sleep "$remaining" & sleeper=$!;trap 'kill "$sleeper" 2>/dev/null || :;wait "$sleeper" 2>/dev/null || :;exit 0' TERM;wait "$sleeper";kill -TERM "$active" 2>/dev/null || :;sleep 0.1;kill -KILL "$active" 2>/dev/null || :) >/dev/null 2>&1 & timer=$!
 set +e;wait "$active";r=$?;set -e
 kill "$timer" 2>/dev/null || :;wait "$timer" 2>/dev/null || :;active=;timer=
 return "$r"
}
cleanup() {
 trap ':' INT TERM HUP
 [ -z "$active" ] || { kill -TERM "$active" 2>/dev/null || :;kill -KILL "$active" 2>/dev/null || :;wait "$active" 2>/dev/null || :; }
 [ -z "$timer" ] || { kill "$timer" 2>/dev/null || :;wait "$timer" 2>/dev/null || :; }
 deadline=$cleanup_end
 # Exact name reconciliation also covers a create whose CID reply was lost.
 [ "$created" = 1 ] || return 0
 set -- "$name";[ "$validator_created" = 0 ] || set -- "$@" "$validator"
 run docker rm -f "$@" > "$work/cleanup.out" 2> "$work/cleanup.err" || return 1
 return 0
}
trap 'cleanup || :; fail' INT TERM HUP
run sh "$code/preflight.sh" "$root" "$store" "$work" "$code" "$transcript" || fail
# Bounded stdin capture. No shell evaluation of payload.
run head -c 8000001 > "$work/input.json" || { cleanup || :;fail; }
image=semgrep/semgrep@sha256:c47e426f7f0cfa19af6d7877560d0a7135f683b8090ad0efc97c4ec7810dc435
set -- create --pull never --name "$name" --platform linux/amd64 --network none --read-only --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges --cpus 2 --memory 2g --memory-swap 2g --pids-limit 128 --tmpfs /tmp:rw,noexec,nosuid,size=268435456 --log-driver local --log-opt max-size=1m --log-opt max-file=1 --log-opt compress=false --env HOME=/tmp --env PYTHONDONTWRITEBYTECODE=1 --env GIT_CONFIG_NOSYSTEM=1 --env DOCKER_OTEL_RESOURCE_ATTRIBUTES= --env DD_SERVICE= --env TSAN_OPTIONS= --mount "type=bind,src=$code,dst=/code,readonly" --mount "type=bind,src=$root,dst=$root,readonly" --mount "type=bind,src=$store,dst=$store" --mount "type=bind,src=$work/input.json,dst=/input.json,readonly"
if [ -n "$transcript" ];then

 set -- "$@" --mount "type=bind,src=$transcript,dst=$transcript,readonly"
fi
set -- "$@" --entrypoint python3 "$image" -B /code/entry.py "$mode" --root "$root" --store "$store" --host "$host" --session "$session" --pointer "$pointer" --input /input.json
[ -z "$transcript" ] || set -- "$@" --transcript "$transcript"
[ -z "$leaf" ] || set -- "$@" --store-leaf "$leaf"
created=1
run docker "$@" > "$work/create.out" 2> "$work/create.err" || { cleanup || :;fail; }
cid=$(cat "$work/create.out")
verify() {
run docker inspect "$cid" > "$work/inspect.json" 2> "$work/inspect.err" || { cleanup || :;fail; }
fmt='{{.State.Status}}|{{.Config.Image}}|{{.Config.User}}|{{.HostConfig.NetworkMode}}|{{.HostConfig.ReadonlyRootfs}}|{{.HostConfig.Privileged}}|{{.HostConfig.NanoCpus}}|{{.HostConfig.Memory}}|{{.HostConfig.MemorySwap}}|{{.HostConfig.PidsLimit}}|{{json .HostConfig.CapDrop}}|{{json .HostConfig.SecurityOpt}}|{{index .HostConfig.Tmpfs "/tmp"}}|{{.Path}}|{{if .HostConfig.CapAdd}}{{len .HostConfig.CapAdd}}{{else}}0{{end}}|{{if .HostConfig.Devices}}{{len .HostConfig.Devices}}{{else}}0{{end}}|{{if .HostConfig.DeviceRequests}}{{len .HostConfig.DeviceRequests}}{{else}}0{{end}}|{{if .HostConfig.PortBindings}}{{len .HostConfig.PortBindings}}{{else}}0{{end}}|{{.HostConfig.PidMode}}|{{.HostConfig.IpcMode}}'
run docker inspect --format "$fmt" "$cid" > "$work/policy.txt" 2> "$work/policy.err" || { cleanup || :;fail; }
expected="created|$image|$(id -u):$(id -g)|none|true|false|2000000000|2147483648|2147483648|128|[\"ALL\"]|[\"no-new-privileges\"]|rw,noexec,nosuid,size=268435456|python3|0|0|0|0||private"
[ "$(cat "$work/policy.txt")" = "$expected" ] || { cleanup || :;fail; }
run docker inspect --format '{{range .Mounts}}{{.Type}}|{{.Source}}|{{.Destination}}|{{.RW}}{{println}}{{end}}' "$cid" > "$work/mounts.raw" 2> "$work/mounts.err" || { cleanup || :;fail; }
sed '/^$/d' "$work/mounts.raw" | LC_ALL=C sort > "$work/mounts.txt"
cmp "$work/mounts.txt" "$work/mounts.expected" || { cleanup || :;fail; }
run docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$cid" > "$work/env.raw" 2> "$work/env.err" || { cleanup || :;fail; }
sed '/^$/d' "$work/env.raw" | LC_ALL=C sort > "$work/env.txt"
printf '%s\n' 'HOME=/tmp' 'PYTHONDONTWRITEBYTECODE=1' 'GIT_CONFIG_NOSYSTEM=1' 'DOCKER_OTEL_RESOURCE_ATTRIBUTES=' 'DD_SERVICE=' 'TSAN_OPTIONS=' 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' 'SEMGREP_IN_DOCKER=1' 'SEMGREP_USER_AGENT_APPEND=Docker' 'PYTHONIOENCODING=utf8' 'PYTHONUNBUFFERED=1' | LC_ALL=C sort > "$work/env.expected"
cmp "$work/env.txt" "$work/env.expected" || { cleanup || :;fail; }
}
{ printf 'bind|%s|/code|false\n' "$code";printf 'bind|%s|%s|false\n' "$root" "$root";printf 'bind|%s|%s|true\n' "$store" "$store";printf 'bind|%s/input.json|/input.json|false\n' "$work";[ -z "$transcript" ] || printf 'bind|%s|%s|false\n' "$transcript" "$transcript"; } | LC_ALL=C sort > "$work/mounts.expected"
verify || { cleanup || :;fail; }
run docker start -a "$cid" > "$work/result.json" 2> "$work/worker.err" || { cleanup || :;fail; }
run docker inspect --format '{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}|{{.State.Dead}}' "$cid" > "$work/terminal.txt" 2> "$work/terminal.err" || { cleanup || :;fail; }
[ "$(cat "$work/terminal.txt")" = 'exited|0|false|false' ] || { cleanup || :;fail; }
# Validate captured bytes in an independent, source-free container before delivery.
set -- create --pull never --name "$validator" --platform linux/amd64 --network none --read-only --user "$(id -u):$(id -g)" --cap-drop ALL --security-opt no-new-privileges --cpus 2 --memory 2g --memory-swap 2g --pids-limit 128 --tmpfs /tmp:rw,noexec,nosuid,size=268435456 --log-driver local --log-opt max-size=1m --log-opt max-file=1 --log-opt compress=false --env HOME=/tmp --env PYTHONDONTWRITEBYTECODE=1 --env GIT_CONFIG_NOSYSTEM=1 --env DOCKER_OTEL_RESOURCE_ATTRIBUTES= --env DD_SERVICE= --env TSAN_OPTIONS= --mount "type=bind,src=$code,dst=/code,readonly" --mount "type=bind,src=$work/result.json,dst=/result.json,readonly" --entrypoint python3 "$image" -B /code/validate.py --mode "$mode" --input /result.json
# Keep worker evidence separate from the validator's inspect evidence.
run mkdir "$work/worker" || { cleanup || :;fail; }
for f in inspect.json policy.txt mounts.txt env.txt terminal.txt;do run cp "$work/$f" "$work/worker/$f" || { cleanup || :;fail; };done
validator_created=1
run docker "$@" > "$work/validator-create.out" 2> "$work/validator-create.err" || { cleanup || :;fail; }
cid=$(cat "$work/validator-create.out")
{ printf 'bind|%s|/code|false\n' "$code";printf 'bind|%s/result.json|/result.json|false\n' "$work"; } | LC_ALL=C sort > "$work/mounts.expected"
verify || { cleanup || :;fail; }
run docker start -a "$cid" > "$work/validation.txt" 2> "$work/validation.err" || { cleanup || :;fail; }
run docker inspect --format '{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}|{{.State.Dead}}' "$cid" > "$work/terminal.txt" 2> "$work/terminal.err" || { cleanup || :;fail; }
[ "$(cat "$work/terminal.txt")" = 'exited|0|false|false' ] && [ "$(cat "$work/validation.txt")" = VALID ] || { cleanup || :;fail; }
cleanup || fail
trap - INT TERM HUP
cat "$work/result.json"
