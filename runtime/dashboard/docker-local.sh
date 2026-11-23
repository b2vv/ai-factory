#!/bin/sh
# Build or run the local dashboard with the explicit Kiri engine and builder.
# The project list comes from DASHBOARD_PROJECTS (a JSON file outside the kit);
# the private feed directory comes from DASHBOARD_FEED.
set -eu
cd "$(dirname "$0")"
tag=factory-dashboard:local
action="${1:-}"
if [ "$action" = build ]; then
  context="$(mktemp -d "${TMPDIR:-/tmp}/dashboard-image.XXXXXXXX")"
  trap 'rm -f "$context/factory-dashboard" "$context/Dockerfile"; rmdir "$context"' EXIT HUP INT TERM
  CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOPROXY=off go build -trimpath -o "$context/factory-dashboard" .
  file "$context/factory-dashboard"
  cp Dockerfile "$context/Dockerfile"
  docker --context kiri buildx build --builder kiri-build --platform linux/amd64 --load --network none \
    --build-arg DASHBOARD_UID="$(id -u)" --build-arg DASHBOARD_GID="$(id -g)" --tag "$tag" "$context"
  docker --context kiri image inspect "$tag" --format '{{.Id}} {{.Os}}/{{.Architecture}}'
  exit
fi
case "$action" in
  run|candidate|share) ;;
  *) printf >&2 'Usage: sh docker-local.sh build | run [image-id] | candidate image-id | share image-id\n'; exit 2 ;;
esac

# A mount source must be a plain absolute path: --mount values are comma-separated.
mount_path() {
  case "$2" in
    *,*|*'"'*|*'
'*) echo >&2 "invalid $1 mount path"; exit 2 ;;
    /*) ;;
    *) echo >&2 "$1 must be an absolute path"; exit 2 ;;
  esac
}
: "${DASHBOARD_PROJECTS:?set the absolute path to the projects JSON config (see projects.example.json)}"
: "${DASHBOARD_FEED:?set the absolute path to the private feed directory}"
projects="$DASHBOARD_PROJECTS"
feed="$DASHBOARD_FEED"
mount_path projects "$projects"
mount_path feed "$feed"
test -f "$projects" && test -d "$feed" || { echo >&2 'projects config or feed directory is missing'; exit 2; }
# The dashboard's own strict validator prints one "id<TAB>root" line per project.
list="$(GOPROXY=off go run . -projects "$projects" -list-projects)" || { echo >&2 'invalid projects config'; exit 2; }

image="${2:-$tag}"
network=factory-dashboard
if [ "$action" = share ]; then
  printf '%s\n' "${2:-}" | grep -Eq '^sha256:[0-9a-f]{64}$' &&
    test "${#image}" -eq 71 || { echo >&2 'share requires a full image ID'; exit 2; }
  : "${DASHBOARD_SHARE_HOST:?set the exact assigned share hostname}"
  : "${DASHBOARD_SHARE_DOMAIN:?set the share provider domain the hostname belongs to}"
  share_auth="${DASHBOARD_SHARE_AUTH:-off}"
  case "$share_auth" in
    on)
      : "${DASHBOARD_SHARE_DIGEST:?set the path to the share accounts file}"
      mount_path digest "$DASHBOARD_SHARE_DIGEST"
      test -f "$DASHBOARD_SHARE_DIGEST" || { echo >&2 'share accounts file is missing'; exit 2; } ;;
    off) ;;
    *) echo >&2 'DASHBOARD_SHARE_AUTH must be on or off'; exit 2 ;;
  esac
  network=factory-dashboard-share
fi
if ! docker --context kiri network inspect "$network" >/dev/null 2>&1; then
  docker --context kiri network create --driver bridge --label app=ai-factory-dashboard "$network"
fi
set -- --detach --platform linux/amd64 --label app=ai-factory-dashboard --network "$network" \
 --read-only --cap-drop ALL --security-opt no-new-privileges:true --user "$(id -u):$(id -g)" --pids-limit 32 --memory 128m \
 --mount "type=bind,src=$projects,dst=/inputs/projects.json,readonly"
tab="$(printf '\t')"
while IFS="$tab" read -r id root; do
  printf '%s\n' "$id" | grep -Eq '^[a-z0-9][a-z0-9-]{0,62}$' || { echo >&2 'invalid project id'; exit 2; }
  mount_path "project $id" "$root"
  test -d "$root/.git" || { echo >&2 "project $id has no .git directory"; exit 2; }
  set -- "$@" --mount "type=bind,src=$root/.git,dst=/inputs/projects/$id/.git,readonly"
done <<EOF
$list
EOF
set -- "$@" --mount "type=bind,src=$feed,dst=/inputs/feed,readonly"
inputs="-projects /inputs/projects.json -roots-under /inputs/projects -feed /inputs/feed"
if [ "$action" = share ]; then
  if [ "$share_auth" = on ]; then
    set -- "$@" --mount "type=bind,src=$DASHBOARD_SHARE_DIGEST,dst=/inputs/share-digest,readonly"
  fi
  # $inputs is a fixed, space-separated argument list without user values.
  set -- "$@" --name factory-dashboard-share --no-healthcheck \
    --publish 127.0.0.1:8734:8734 "$image" -container -port 8734 $inputs \
    -share-host "$DASHBOARD_SHARE_HOST" -share-domain "$DASHBOARD_SHARE_DOMAIN"
  if [ "$share_auth" = on ]; then
    set -- "$@" -share-auth -share-digest /inputs/share-digest
  fi
  exec docker --context kiri run "$@"
fi
if [ "$action" = candidate ]; then
  exec docker --context kiri run "$@" --name factory-dashboard-expansion-candidate --no-healthcheck \
    --publish 127.0.0.1:8733:8733 "$image" -container -port 8733 $inputs
fi
exec docker --context kiri run "$@" --name factory-dashboard --restart unless-stopped \
  --publish 127.0.0.1:8732:8732 "$image"
