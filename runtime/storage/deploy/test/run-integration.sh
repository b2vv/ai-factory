#!/usr/bin/env bash
# Stage 6 E2E runner: bring up the ISOLATED integration-test stack (real PostgreSQL + MongoDB,
# synthetic creds, disposable volumes), run the integration test matrix against it, and tear
# it down completely (including its volumes). It never touches the user's real databases, the
# dev harness (8777/8778) or any other running compose project.
#
# Usage: deploy/test/run-integration.sh [extra `go test` args...]
# Requires: Docker Engine >= 28, Docker Compose v2+, the pinned cached builder and an offline module cache.
set -euo pipefail
command -v docker >/dev/null || { echo "BLOCKED: Docker unavailable" >&2; exit 2; }
docker info >/dev/null 2>&1 || { echo "BLOCKED: Docker daemon unavailable" >&2; exit 2; }
BUILDER="golang@sha256:e87b2a5f6df2dff71ea330d55d54f4979eb380ae58a7e3aabc9d53121243e689"
docker image inspect "$BUILDER" >/dev/null 2>&1 || { echo "BLOCKED: offline amd64 builder missing" >&2; exit 2; }
MODCACHE="${STORAGE_GO_MOD_CACHE:-}"
if [[ -z "$MODCACHE" ]] && command -v go >/dev/null; then MODCACHE="$(go env GOMODCACHE)"; fi
[[ -d "$MODCACHE" ]] || { echo "BLOCKED: set STORAGE_GO_MOD_CACHE to offline module cache" >&2; exit 2; }

# Optional explicit writable compiler cache; never infer or install a host toolchain.
CACHE_ARGS=()
if [[ -n "${STORAGE_GO_BUILD_CACHE:-}" ]]; then
  [[ "${STORAGE_GO_BUILD_CACHE}" = /* && -d "${STORAGE_GO_BUILD_CACHE}" ]] || { echo "BLOCKED: build cache must be an existing absolute directory" >&2; exit 2; }
  CACHE_ARGS=(-v "${STORAGE_GO_BUILD_CACHE}:/build-cache" -e GOCACHE=/build-cache)
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_DIR="$(cd "${HERE}/../.." && pwd)"   # runtime/storage (the Go module root)
PROJECT="factory-storage-inttest-${$}"
PG_PORT="${INTTEST_PG_PORT:-55432}"
MONGO_PORT="${INTTEST_MONGO_PORT:-57017}"

compose() { docker compose -p "${PROJECT}" -f "${HERE}/compose.yaml" "$@"; }

cleanup() {
  echo "==> tearing down ${PROJECT} (containers + dedicated volumes)"
  compose down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> starting isolated test databases (postgres:17.5 + mongo:7.0.16, linux/amd64)"
compose up -d

echo "==> waiting for both backends to report healthy"
deadline=$(( $(date +%s) + 120 ))
while :; do
  pg_state=$(compose ps -a --format '{{.Service}} {{.Health}}' | awk '/^postgres/{print $2}')
  mongo_state=$(compose ps -a --format '{{.Service}} {{.Health}}' | awk '/^mongo/{print $2}')
  if [[ "${pg_state}" == "healthy" && "${mongo_state}" == "healthy" ]]; then
    break
  fi
  if [[ $(date +%s) -ge ${deadline} ]]; then
    echo "!! backends did not become healthy in time (pg=${pg_state} mongo=${mongo_state})" >&2
    compose ps -a >&2
    exit 1
  fi
  sleep 2
done
echo "==> backends healthy (pg=${pg_state}, mongo=${mongo_state})"

export PG_DSN="postgres://factory_test:factory_test_synthetic@127.0.0.1:${PG_PORT}/factory_test?sslmode=disable"
export MONGO_URI="mongodb://factory_test:factory_test_synthetic@127.0.0.1:${MONGO_PORT}/?authSource=admin"

# These suites share one synthetic schema and filesystem free-space measurements.
# Serialize packages so migration probes and executable builds cannot interfere.
echo "==> running integration matrix (go test -tags integration) against the real backends"
cd "${MODULE_DIR}"
docker run --rm --pull=never --platform linux/amd64 --network "${PROJECT}_inttest" \
 "${CACHE_ARGS[@]}" -v "${MODULE_DIR}:/src:ro" -v "${MODCACHE}:/go/pkg/mod:ro" -w /src \
 -e GOPROXY=off -e GOSUMDB=off -e GOTOOLCHAIN=local -e GOFLAGS=-mod=readonly \
 -e PG_DSN="postgres://factory_test:factory_test_synthetic@postgres:5432/factory_test?sslmode=disable" \
 -e MONGO_URI="mongodb://factory_test:factory_test_synthetic@mongo:27017/?authSource=admin" \
 "$BUILDER" go test -p 1 -timeout 180s -tags integration -count=1 "$@" ./...
echo "==> integration matrix completed"
