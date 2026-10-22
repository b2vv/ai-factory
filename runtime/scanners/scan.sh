#!/bin/sh
# Docker-only user entrypoint. Host shell + standard utilities + Docker/Compose.
set -u
umask 077
MODE=${1-}; CONFIG=${2-}; WORK=${3-}; SOCKET=${4-}; COMPOSE=${5-}; COMPOSE_SHA=${6-}
[ "$#" -eq 6 ] && { [ "$MODE" = scan ] || [ "$MODE" = update-db ]; } || { echo 'usage: scan.sh scan|update-db CONFIG_OR_STORE NEW_WORK SOCKET COMPOSE_BINARY COMPOSE_SHA' >&2; exit 3; }
FACTORY=$(CDPATH= cd -P "$(dirname "$0")" && pwd -P) || exit 3
. "$FACTORY/container_control.sh"
for path in "$FACTORY" "$CONFIG" "$SOCKET" "$COMPOSE"; do host_path_check "$path" || exit 3; done
case "$WORK" in /*) ;; *) exit 3;; esac
host_path_check "$(dirname "$WORK")" || exit 3
[ ! -e "$WORK" ] && [ ! -L "$WORK" ] || exit 3
mkdir -m 700 "$WORK" || exit 3
host_path_check "$WORK" || exit 3
UID_NUM=$(id -u); GID_NUM=$(id -g)
[ "$UID_NUM" -gt 0 ] || exit 3
USER_SPEC=$UID_NUM:$GID_NUM
DOCKER_CONFIG=$WORK/docker; HOME=$WORK/home; export DOCKER_CONFIG HOME
mkdir "$DOCKER_CONFIG" "$HOME" || exit 3
printf '{}\n' > "$DOCKER_CONFIG/config.json"
DOCKER_HOST=unix://$SOCKET; COMPOSE_DISABLE_ENV_FILE=1; export DOCKER_HOST COMPOSE_DISABLE_ENV_FILE
unset DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH COMPOSE_FILE COMPOSE_PROFILES COMPOSE_PROJECT_NAME
HELPER=python@sha256:4cea12ab7d78a3312c85f8cab19b6971d4fe9704da25443986c0bc20a6678850
HELPER_ID=sha256:4412cecc4af63502bd64d4b862be90b306d4134759d45cde783514dafdd6d03c
# No host hash utility required.32 random bytes are data; all digest checks run in helper.
TOKEN=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
case "$TOKEN" in ''|*[!a-f0-9]*) exit 3;; esac
[ "${#TOKEN}" -eq 64 ] || exit 3
PROJECT=factory-scan-$(printf %.32s "$TOKEN")
HSEQ=0
cleanup_exact_intents() {
    failed=0
    while IFS= read -r name; do
        [ -n "$name" ] || continue
        # Query by exact anchored name. Empty successful result confirms absence.
        control_call docker ps -aq --no-trunc --filter "name=^/$name$" || { failed=1; continue; }
        id=$(cat "$CONTROL_OUT")
        [ -n "$id" ] || continue
        control_call docker inspect --format '{{index .Config.Labels "ai-factory.run"}}' "$id" || { failed=1; continue; }
        [ "$(cat "$CONTROL_OUT")" = "$TOKEN" ] || { failed=1; continue; }
        control_call docker inspect "$id" || { failed=1; continue; }
        cp "$CONTROL_OUT" "$WORK/cleanup-$name-before.json" || failed=1
        control_call docker stop --time 2 "$id" || :
        control_call docker inspect "$id" || { failed=1; continue; }
        cp "$CONTROL_OUT" "$WORK/cleanup-$name-terminal.json" || failed=1
        control_call docker rm -f "$id" || { failed=1; continue; }
        control_call docker ps -aq --no-trunc --filter "name=^/$name$" || { failed=1; continue; }
        [ ! -s "$CONTROL_OUT" ] || failed=1
    done < "$WORK/container-intents"
    [ "$failed" -eq 0 ]
}
control_init "$WORK" || exit 2
# Soft disk polling. Separate objects remain2GiB; never delete data to make space.
(
    sleeper=; worker=
    trap 'for owned_pid in "$worker" "$sleeper"; do [ -z "$owned_pid" ] || { kill -KILL "$owned_pid" 2>/dev/null || :; wait "$owned_pid" 2>/dev/null || :; }; done; exit 0' TERM INT HUP
    monitor_command() {
        (ulimit -f 1024 || exit 3; exec "$@") > "$WORK/disk-sample.stdout" 2> "$WORK/disk-sample.stderr" &
        worker=$!
        if wait "$worker"; then code=0; else code=$?; fi
        worker=
        return "$code"
    }
    while :; do
        sleep 2 & sleeper=$!; wait "$sleeper" || exit 0; sleeper=
        monitor_command df -Pk "$WORK" || { kill -TERM "$CONTROL_OWNER"; exit; }
        free=$(awk 'NR==2 {print $4}' "$WORK/disk-sample.stdout")
        monitor_command du -sk "$WORK" || { kill -TERM "$CONTROL_OWNER"; exit; }
        used=$(awk '{print $1}' "$WORK/disk-sample.stdout")
        case "$free:$used" in *[!0-9:]*) kill -TERM "$CONTROL_OWNER"; exit;; esac
        [ "$free" -ge 10485760 ] && [ "$used" -le 2097152 ] || { kill -TERM "$CONTROL_OWNER"; exit; }
        if [ "$MODE" = update-db ]; then
            monitor_command df -Pk "$CONFIG" || { kill -TERM "$CONTROL_OWNER"; exit; }
            store_free=$(awk 'NR==2 {print $4}' "$WORK/disk-sample.stdout")
            case "$store_free" in ''|*[!0-9]*) kill -TERM "$CONTROL_OWNER"; exit;; esac
            [ "$store_free" -ge 10485760 ] || { kill -TERM "$CONTROL_OWNER"; exit; }
        fi
        if [ "$MODE" = update-db ] && [ -d "$CONFIG/download-$TOKEN" ]; then
            monitor_command du -sk "$CONFIG/download-$TOKEN" || { kill -TERM "$CONTROL_OWNER"; exit; }
            cache_used=$(awk '{print $1}' "$WORK/disk-sample.stdout")
            case "$cache_used" in ''|*[!0-9]*) kill -TERM "$CONTROL_OWNER"; exit;; esac
            [ "$cache_used" -le 2097152 ] || { kill -TERM "$CONTROL_OWNER"; exit; }
        fi
    done
) &
CONTROL_DISK_TIMER=$!
finish() {
    rc=$1
    control_shutdown || rc=2
    printf '%s\n' "$rc" > "$WORK/entrypoint.exit" || rc=2
    case "$rc" in 0) status=CLEAN;; 1) status=FINDINGS;; 2) status=ERROR;; *) status=BLOCKED;; esac
    printf '{"status":"%s","exit_code":%s,"cleanup":"%s"}\n' "$status" "$rc" "$(cat "$WORK/cleanup-state")" > "$WORK/result.json" || rc=2
    exit "$rc"
}
checked() { control_call "$@" || finish 3; }
image_check() {
    checked docker image inspect --format '{{.Id}}|{{.Os}}/{{.Architecture}}|{{.Size}}' "$HELPER"
    IFS='|' read -r id platform size < "$CONTROL_OUT"
    [ "$id" = "$HELPER_ID" ] && [ "$platform" = linux/amd64 ] && [ "$size" -le 2147483648 ] || finish 3
}
image_check
# hrun PHASE receives only host/target/ro triplets, never arbitrary Docker options.
hrun() {
    phase=$1; shift; HSEQ=$((HSEQ+1)); name=$PROJECT-helper-$HSEQ
    printf '%s\n' "$name" >> "$WORK/container-intents"
    expected=$WORK/helper-$HSEQ.mounts
    printf '%s|/factory|false\n%s|/work|true\n' "$FACTORY" "$WORK" > "$expected"
    # Build argv in this function's positional parameters; mounts checked without eval.
    mounts=$WORK/helper-$HSEQ.input-mounts; : > "$mounts"
    while [ "$#" -gt 0 ]; do
        [ "$#" -ge 3 ] || finish 3
        host_path_check "$1" || finish 3
        case "$2:$3" in /config:ro|/compose-bin:ro|/store:ro|/store:rw|/input/*:ro) ;; *) finish 3;; esac
        printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$mounts"; shift 3
    done
    set -- docker create --pull never --label "ai-factory.run=$TOKEN" --name "$name" --platform linux/amd64 --network none --read-only --cap-drop ALL --security-opt no-new-privileges --cpus 2 --memory 2g --memory-swap 2g --pids-limit 128 --user "$USER_SPEC" --workdir /src --tmpfs /tmp:rw,noexec,nosuid,size=256m --log-driver local --log-opt max-size=1m --log-opt max-file=1 --log-opt compress=false --env HOME=/tmp --env PYTHONDONTWRITEBYTECODE=1 --mount "type=bind,src=$FACTORY,dst=/factory,readonly" --mount "type=bind,src=$WORK,dst=/work" --entrypoint python3
    tab=$(printf '\t')
    while IFS="$tab" read -r source target mode; do
        suffix=;rw=true; [ "$mode" != ro ] || { suffix=,readonly;rw=false; }
        set -- "$@" --mount "type=bind,src=$source,dst=$target$suffix"
        printf '%s|%s|%s\n' "$source" "$target" "$rw" >> "$expected"
    done < "$mounts"
    set -- "$@" "$HELPER" -I -B /factory/container_helper.py "$phase" --host-work "$WORK" --compose-sha "$COMPOSE_SHA" --token "$TOKEN"
    [ "$MODE" != update-db ] || set -- "$@" --host-store "$CONFIG"
    checked "$@"
    cid=$(cat "$CONTROL_OUT")
    checked docker inspect --format '{{index .Config.Labels "ai-factory.run"}}' "$cid"
    [ "$(cat "$CONTROL_OUT")" = "$TOKEN" ] || finish 3
    checked docker inspect "$cid"; cp "$CONTROL_OUT" "$WORK/helper-$HSEQ-inspect.json" || finish 3
    # Literal bootstrap fields; no helper runs before host checks its isolation.
    checked docker inspect --format '{{.Image}}|{{.Config.Image}}|{{.Platform}}|{{.Config.User}}|{{json .Config.Entrypoint}}|{{.Config.WorkingDir}}|{{.HostConfig.NetworkMode}}|{{.HostConfig.ReadonlyRootfs}}|{{.HostConfig.Privileged}}|{{json .HostConfig.CapDrop}}|{{json .HostConfig.CapAdd}}|{{json .HostConfig.SecurityOpt}}|{{.HostConfig.NanoCpus}}|{{.HostConfig.Memory}}|{{.HostConfig.MemorySwap}}|{{.HostConfig.PidsLimit}}|{{.State.Status}}|{{if .HostConfig.Devices}}{{len .HostConfig.Devices}}{{else}}0{{end}}|{{if .HostConfig.DeviceRequests}}{{len .HostConfig.DeviceRequests}}{{else}}0{{end}}|{{if .HostConfig.VolumesFrom}}{{len .HostConfig.VolumesFrom}}{{else}}0{{end}}|{{if .HostConfig.PortBindings}}{{len .HostConfig.PortBindings}}{{else}}0{{end}}|{{.HostConfig.PidMode}}|{{.HostConfig.IpcMode}}' "$cid"
    expected_fields="$HELPER_ID|$HELPER|linux|$USER_SPEC|[\"python3\"]|/src|none|true|false|[\"ALL\"]|null|[\"no-new-privileges\"]|2000000000|2147483648|2147483648|128|created|0|0|0|0||private"
    [ "$(cat "$CONTROL_OUT")" = "$expected_fields" ] || finish 3
    checked docker inspect --format '{{range .Mounts}}{{.Source}}|{{.Destination}}|{{.RW}}{{println}}{{end}}' "$cid"
    sed '/^$/d' "$CONTROL_OUT" | sort > "$WORK/actual.mounts"; sort "$expected" > "$WORK/expected.mounts"
    cmp -s "$WORK/actual.mounts" "$WORK/expected.mounts" || finish 3
    checked docker inspect --format '{{json .HostConfig.Tmpfs}}' "$cid"
    [ "$(cat "$CONTROL_OUT")" = '{"/tmp":"rw,noexec,nosuid,size=256m"}' ] || finish 3
    checked docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$cid"
    printf '%s\n' 'PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' 'GPG_KEY=7169605F62C751356D054A26A821E680E5FA6305' 'PYTHON_VERSION=3.13.17' 'PYTHON_SHA256=6020bd10aff3bf4821be16f088ebb1591beb7b811dcd8fab1da8f7c22a7b27e7' 'HOME=/tmp' 'PYTHONDONTWRITEBYTECODE=1' | sort > "$WORK/expected.env"
    sed '/^$/d' "$CONTROL_OUT" | sort > "$WORK/actual.env"; cmp -s "$WORK/actual.env" "$WORK/expected.env" || finish 3
    # Exact command check uses expected literal JSON from host arguments; no generated commands.
    checked docker inspect --format '{{json .Config.Cmd}}' "$cid"
    # Paths disallow JSON metacharacter quote/backslash through entry validation below.
    expected_cmd="[\"-I\",\"-B\",\"/factory/container_helper.py\",\"$phase\",\"--host-work\",\"$WORK\",\"--compose-sha\",\"$COMPOSE_SHA\",\"--token\",\"$TOKEN\""
    [ "$MODE" != update-db ] || expected_cmd="$expected_cmd,\"--host-store\",\"$CONFIG\""
    expected_cmd="$expected_cmd]"; [ "$(cat "$CONTROL_OUT")" = "$expected_cmd" ] || finish 3
    checked docker inspect --format '{{json .HostConfig.LogConfig}}' "$cid"
    [ "$(cat "$CONTROL_OUT")" = '{"Type":"local","Config":{"compress":"false","max-file":"1","max-size":"1m"}}' ] || finish 3
    checked docker start "$cid"
    checked docker wait "$cid"
    checked docker logs --tail 200 "$cid"; cp "$CONTROL_OUT" "$WORK/helper-$HSEQ.stdout"; cp "$CONTROL_ERR" "$WORK/helper-$HSEQ.stderr"
    checked docker inspect "$cid"; cp "$CONTROL_OUT" "$WORK/helper-$HSEQ-terminal.json" || finish 3
    checked docker inspect --format '{{.State.Status}}|{{.State.ExitCode}}|{{.State.OOMKilled}}|{{.State.Dead}}|{{.State.Error}}' "$cid"
    state=$(cat "$CONTROL_OUT"); HRC=0
    case "$state" in
        exited\|0\|false\|false\|) ;;
        exited\|1\|false\|false\|) [ "$phase" = finalize ] || { [ "$phase" != verify-result ] || finish 2; finish 3; };HRC=1;;
        exited\|2\|false\|false\|) [ "$phase" = finalize ] || { [ "$phase" != verify-result ] || finish 2; finish 3; };HRC=2;;
        *) [ "$phase" != verify-result ] || finish 2; finish 3;;
    esac
    checked docker rm "$cid"
}
# All parameters embedded in literal JSON are restricted before use.
for value in "$WORK" "$CONFIG" "$COMPOSE_SHA"; do case "$value" in *'"'*|*'\'*) finish 3;; esac; done
if [ "$MODE" = scan ]; then
    hrun plan "$CONFIG" /config ro "$COMPOSE" /compose-bin ro
    STORE=$(cat "$WORK/store.txt");host_path_check "$STORE" || finish 3
    ancestor=$STORE
    while [ "$ancestor" != / ]; do [ ! -e "$ancestor/.git" ] || finish 3;ancestor=$(dirname "$ancestor");done
    set -- stage "$STORE" /store ro
    tab=$(printf '\t')
    while IFS="$tab" read -r source target; do set -- "$@" "$source" "$target" ro; done < "$WORK/mounts.tsv"
    hrun "$@"
    for engine in semgrep trivy; do printf '%s\n' "$PROJECT-$engine" >> "$WORK/container-intents"; done
    checked "$COMPOSE" --project-name "$PROJECT" --project-directory "$WORK" -f "$WORK/compose.json" create --pull never --no-build
    for engine in semgrep trivy; do
        checked "$COMPOSE" --project-name "$PROJECT" --project-directory "$WORK" -f "$WORK/compose.json" ps --all --quiet "$engine"
        cid=$(cat "$CONTROL_OUT");case "$cid" in ''|*[!a-f0-9]*) finish 3;; esac
        printf '%s\n' "$cid" > "$WORK/$engine.cid"
        checked docker inspect --format '{{.Name}}' "$cid";name=$(cat "$CONTROL_OUT");[ "$name" = "/$PROJECT-$engine" ] || finish 3
        checked docker inspect "$cid";cp "$CONTROL_OUT" "$WORK/$engine-inspect.json" || finish 3
        checked docker inspect --format '{{.Config.Image}}' "$cid";pin=$(cat "$CONTROL_OUT")
        checked docker image inspect "$pin";cp "$CONTROL_OUT" "$WORK/$engine-image.json" || finish 3
    done
    hrun verify
    for engine in semgrep trivy; do
        cid=$(cat "$WORK/$engine.cid");checked docker start "$cid";checked docker wait "$cid"
        checked docker inspect "$cid";cp "$CONTROL_OUT" "$WORK/$engine-terminal.json" || finish 3
    done
    set -- finalize "$STORE" /store ro
    while IFS="$tab" read -r source target; do set -- "$@" "$source" "$target" ro; done < "$WORK/mounts.tsv"
    hrun "$@"; pending_rc=$HRC
    hrun verify-result
    classification_exit "$WORK" "$TOKEN" "$pending_rc" || finish 2
    finish "$CLASSIFIED_RC"
else
    # Online update explicitly separated. Store must be dedicated and outside Git.
    ancestor=$CONFIG
    while [ "$ancestor" != / ]; do [ ! -e "$ancestor/.git" ] || finish 3;ancestor=$(dirname "$ancestor");done
    hrun lease "$CONFIG" /store rw
    pin=$(cat "$WORK/trivy-pin.txt");dbpin=$(cat "$WORK/db-pin.txt");cache=$CONFIG/download-$TOKEN/cache
    name=factory-db-$(printf %.32s "$TOKEN");printf '%s\n' "$name" >> "$WORK/container-intents"
    checked docker create --pull never --label "ai-factory.run=$TOKEN" --name "$name" --platform linux/amd64 --network bridge --read-only --cap-drop ALL --security-opt no-new-privileges --cpus 2 --memory 2g --memory-swap 2g --pids-limit 128 --user "$USER_SPEC" --tmpfs /tmp:rw,noexec,nosuid,size=1g --env HOME=/tmp --env TRIVY_DISABLE_TELEMETRY=true --log-driver local --log-opt max-size=1m --log-opt max-file=1 --log-opt compress=false --mount "type=bind,src=$cache,dst=/cache" --entrypoint trivy "$pin" fs --download-db-only --db-repository "$dbpin" --cache-dir /cache --disable-telemetry
    cid=$(cat "$CONTROL_OUT");printf '%s\n' "$cid" > "$WORK/updater.cid";checked docker inspect "$cid";cp "$CONTROL_OUT" "$WORK/updater-inspect.json" || finish 3
    checked docker image inspect "$pin";cp "$CONTROL_OUT" "$WORK/trivy-image.json" || finish 3
    hrun update-verify
    cid=$(cat "$WORK/updater.cid")
    checked docker start "$cid";checked docker wait "$cid";checked docker inspect "$cid";cp "$CONTROL_OUT" "$WORK/updater-terminal.json" || finish 3
    checked docker rm "$cid";printf 'CONFIRMED\n' > "$WORK/updater-removed"
    hrun publish "$CONFIG" /store rw
    # release helper is last lease-sensitive action; failed final cleanup still ERROR.
    hrun release "$CONFIG" /store rw
    finish 0
fi
