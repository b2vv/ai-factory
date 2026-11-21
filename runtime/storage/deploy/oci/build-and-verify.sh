#!/usr/bin/env bash
# M7 OCI packaging: build the digest-pinned image, bundle it for OFFLINE transfer, then prove
# the offline acquisition flow (load without an implicit pull) and that the running image
# serves /health over loopback with the unchanged safe defaults (file-only, capture disabled).
#
# This does NOT push, tag for release, install, or deploy anything. It builds locally and runs
# a throwaway container on a loopback-only port, then removes it.
#
# Usage: deploy/oci/build-and-verify.sh
# Requires: Docker Engine >= 28, an available loopback port (ephemeral by default), curl.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_DIR="$(cd "${HERE}/../.." && pwd)"   # runtime/storage (build context = Go module root)
IMAGE="${OCI_IMAGE:-factory-storage:codex-local-${$}}"
if docker image inspect "$IMAGE" >/dev/null 2>&1; then echo "BLOCKED: output image tag already exists" >&2; exit 2; fi
PORT="${OCI_VERIFY_PORT:-0}"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

echo "==> offline build (pinned linux/amd64 Go toolchain)"
BUILDER="golang@sha256:e87b2a5f6df2dff71ea330d55d54f4979eb380ae58a7e3aabc9d53121243e689"
MODCACHE="${STORAGE_GO_MOD_CACHE:-}"
if [[ -z "$MODCACHE" ]] && command -v go >/dev/null; then MODCACHE="$(go env GOMODCACHE)"; fi
[[ -d "$MODCACHE" ]] || { echo "BLOCKED: offline module cache required" >&2; exit 2; }
docker image inspect "$BUILDER" >/dev/null 2>&1 || { echo "BLOCKED: pinned offline builder missing" >&2; exit 2; }
docker run --rm --pull=never --platform linux/amd64 --network none \
 -v "${MODULE_DIR}:/src:ro" -v "${MODCACHE}:/go/pkg/mod:ro" -v "${WORK}:/out" -w /src \
 -e GOPROXY=off -e GOSUMDB=off -e GOTOOLCHAIN=local -e GOFLAGS=-mod=readonly -e CGO_ENABLED=0 \
 "$BUILDER" go build -trimpath -ldflags="-s -w" -o /out/factory ./cmd/factory
cp "${HERE}/Dockerfile.runtime" "${WORK}/Dockerfile"
docker build --network none --platform linux/amd64 -t "${IMAGE}" "${WORK}"
IMG_ID="$(docker inspect --format '{{.Id}}' "${IMAGE}")"
echo "    image config id: ${IMG_ID}"

echo "==> docker save (offline bundle) + checksum"
docker save "${IMAGE}" -o "${WORK}/image.tar"
shasum -a 256 "${WORK}/image.tar" | awk '{print "    saved tar sha256:",$1}'

echo "==> remove tag then docker load (proves no implicit registry pull)"
docker rmi "${IMAGE}" >/dev/null 2>&1 || true
docker load -i "${WORK}/image.tar"

echo "==> synthetic 0600 operator token (never printed/committed)"
printf '{"id":"operator","secret":"%s"}' "$(head -c 24 /dev/urandom | base64 | tr -d '=+/')" > "${WORK}/operator.token"
chmod 600 "${WORK}/operator.token"
mkdir -p "${WORK}/state"

echo "==> run -init"
docker run --rm --pull=never --platform linux/amd64 -v "${WORK}/state":/state -v "${WORK}/operator.token":/run/secrets/operator_token:ro \
  "${IMAGE}" -state /state -operator-token /run/secrets/operator_token -init

echo "==> run + verify /health over loopback (port ${PORT})"
CID="$(docker run -d --rm --pull=never --platform linux/amd64 -p "127.0.0.1:${PORT}:8777" -v "${WORK}/state":/state \
  -v "${WORK}/operator.token":/run/secrets/operator_token:ro \
  "${IMAGE}" -state /state -operator-token /run/secrets/operator_token -listen 0.0.0.0:8777 -dev-allow-nonloopback)"
trap 'docker stop "${CID}" >/dev/null 2>&1 || true; rm -rf "${WORK}"' EXIT
if [[ "$PORT" == 0 ]]; then PORT="$(docker port "$CID" 8777/tcp | head -1 | awk -F: '{print $NF}')"; fi
code=000
for _ in $(seq 1 30); do
  code="$(curl -s -o "${WORK}/health.json" -w '%{http_code}' "http://127.0.0.1:${PORT}/health" || echo 000)"
  [ "${code}" = "200" ] && break
  sleep 0.5
done
echo "    /health HTTP ${code}: $(cat "${WORK}/health.json" 2>/dev/null)"
[ "${code}" = "200" ] || { echo "!! health check failed" >&2; exit 1; }
echo "==> OK: offline build/save/load/run verified; container stopped on exit"
