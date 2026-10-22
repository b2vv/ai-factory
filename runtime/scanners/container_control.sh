#!/bin/sh
# Private library for reviewed coordinator integration. Never eval generated data.
# No Docker command is executed by sourcing this file.

host_path_check() {
    cr=$(printf '\r')
    case "$1" in *"$cr"*) return 3;; esac
    case "$1" in
        /*) ;; *) return 3;;
    esac
    case "$1" in
        /|*/|*//*|*/./*|*/../*|*/.|*/..|*','*|*'$'*|*'
'*|*'
'*|*'	'*) return 3;;
    esac
    # Fixed separator; disable globbing. Spaces remain ordinary characters.
    old_ifs=$IFS; IFS=/; set -f
    set -- ${1#/}; IFS=$old_ifs
    prefix=
    for component do
        prefix=$prefix/$component
        [ ! -L "$prefix" ] || return 3
        [ -e "$prefix" ] || return 3
    done
    set +f
}

control_timer() {
    sleeper=
    trap '[ -z "$sleeper" ] || { kill "$sleeper" 2>/dev/null || :; wait "$sleeper" 2>/dev/null || :; }; exit 0' TERM INT HUP
    printf ready > "$2"
    sleep "$1" & sleeper=$!
    wait "$sleeper" || exit 0
    kill -TERM "$CONTROL_OWNER"
}

control_start_timer() {
    CONTROL_TIMER_SEQUENCE=$((CONTROL_TIMER_SEQUENCE + 1))
    ready=$CONTROL_WORK/timer-$CONTROL_TIMER_SEQUENCE.ready
    control_timer "$1" "$ready" >/dev/null 2>&1 &
    CONTROL_NEW_TIMER=$!
    count=0
    while [ ! -s "$ready" ]; do
        kill -0 "$CONTROL_NEW_TIMER" 2>/dev/null || return 2
        count=$((count+1)); [ "$count" -le 5 ] || return 2
        sleep 1
    done
}

# Call only after explicit work directory ownership/bootstrap checks.
control_init() {
    CONTROL_WORK=$1
    CONTROL_OWNER=$$
    CONTROL_CHILD=
    CONTROL_TIMER_SEQUENCE=0
    CONTROL_TIMER=
    CONTROL_CLEAN_TIMER=
    CONTROL_SEQUENCE=0
    CONTROL_EXPIRED=0
    CONTROL_SHUTTING_DOWN=0
    CONTROL_FAILURE=0
    CONTROL_DISK_TIMER=
    # Intents exist before create; caller appends validated exact generated names only.
    : > "$CONTROL_WORK/container-intents" || return 2
    trap 'CONTROL_EXPIRED=1; control_shutdown; printf "%s\n" 2 > "$CONTROL_WORK/entrypoint.exit"; exit 2' INT TERM HUP
    control_start_timer 600 || return 2
    CONTROL_TIMER=$CONTROL_NEW_TIMER
}

control_call() {
    CONTROL_SEQUENCE=$((CONTROL_SEQUENCE + 1))
    CONTROL_OUT=$CONTROL_WORK/command-$CONTROL_SEQUENCE.stdout
    CONTROL_ERR=$CONTROL_WORK/command-$CONTROL_SEQUENCE.stderr
    # POSIX unit is512 bytes; platforms using1024 still stay <=1MiB. Capability test required.
    (ulimit -f 1024 || exit 3; exec "$@") >"$CONTROL_OUT" 2>"$CONTROL_ERR" &
    CONTROL_CHILD=$!
    if wait "$CONTROL_CHILD"; then CONTROL_RC=0; else CONTROL_RC=$?; fi
    CONTROL_CHILD=
    printf '%s\n' "$CONTROL_RC" > "$CONTROL_WORK/command-$CONTROL_SEQUENCE.exit" || return 2
    [ "$CONTROL_EXPIRED" -eq 0 ] || [ "${CONTROL_SHUTTING_DOWN:-0}" -eq 1 ] || return 2
    return "$CONTROL_RC"
}

control_stop_timer() {
    [ -z "$1" ] || { kill "$1" 2>/dev/null || :; wait "$1" 2>/dev/null || :; }
}

control_shutdown() {
    [ "$CONTROL_SHUTTING_DOWN" -eq 0 ] || return 2
    CONTROL_SHUTTING_DOWN=1
    # Start shared cleanup deadline before any child wait or daemon operation.
    trap 'printf "%s\n" UNKNOWN > "$CONTROL_WORK/cleanup-state"; for owned_pid in "$CONTROL_CHILD" "$CONTROL_TIMER" "$CONTROL_DISK_TIMER"; do [ -z "$owned_pid" ] || kill -KILL "$owned_pid" 2>/dev/null || :; done; exit 2' TERM INT HUP
    control_start_timer 15 || return 2
    CONTROL_CLEAN_TIMER=$CONTROL_NEW_TIMER
    control_stop_timer "$CONTROL_TIMER"
    control_stop_timer "$CONTROL_DISK_TIMER"
    if [ -n "$CONTROL_CHILD" ]; then
        kill "$CONTROL_CHILD" 2>/dev/null || :
        wait "$CONTROL_CHILD" 2>/dev/null || :
        CONTROL_CHILD=
    fi
    if cleanup_exact_intents; then
        printf '%s\n' CONFIRMED > "$CONTROL_WORK/cleanup-state" || CONTROL_FAILURE=2
    else
        printf '%s\n' UNKNOWN > "$CONTROL_WORK/cleanup-state"
        CONTROL_FAILURE=2
    fi
    control_stop_timer "$CONTROL_CLEAN_TIMER"
    trap - INT TERM HUP
    [ "$CONTROL_EXPIRED" -eq 0 ] && [ "$CONTROL_FAILURE" -eq 0 ]
}

classification_exit() {
    # Only called after independent verify-result helper exited0.
    receipt=$1/classification-verified.txt
    [ -f "$receipt" ] && [ ! -L "$receipt" ] || return 2
    verified=$(cat "$receipt") || return 2
    case "$verified" in "$2|0") CLASSIFIED_RC=0;; "$2|1") CLASSIFIED_RC=1;; "$2|2") CLASSIFIED_RC=2;; *) return 2;; esac
    [ "$CLASSIFIED_RC" = "$3" ] || return 2
}
