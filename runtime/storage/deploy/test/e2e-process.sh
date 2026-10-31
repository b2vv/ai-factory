#!/usr/bin/env bash
# PROCESS-LEVEL end-to-end: the REAL built factory container (its own composition root, not an
# in-process httptest) runs with capture + real PostgreSQL + real MongoDB ENABLED, and is
# driven over HTTP. Proves: HTTP capture -> persistence -> query; persistence across a process
# RESTART; and backend-down -> recovery. Loopback-only, synthetic data, torn down on exit.
#
# Difference from run-integration.sh: that one runs `go test` (in-process handlers via httptest,
# with the isolated DBs). THIS one launches the compiled container binary as a separate process
# and talks to it over TCP, so the real main.go composition root (real backend open, hard-fail,
# background pinger) is exercised.
#
# Requires: the image factory-storage:oci-local (build via deploy/oci/build-and-verify.sh or
# `docker build -f deploy/oci/Dockerfile`), Docker, curl, python3 (for the M8 token helper).
set -euo pipefail
command -v docker >/dev/null || { echo "BLOCKED: Docker unavailable" >&2; exit 2; }
docker info >/dev/null 2>&1 || { echo "BLOCKED: Docker daemon unavailable" >&2; exit 2; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_DIR="$(cd "${HERE}/../.." && pwd)"
PROJECT="factory-storage-inttest-${$}"
NET="${PROJECT}_inttest"
IMAGE="${PROC_E2E_IMAGE:-factory-storage:oci-local}"
docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "BLOCKED: offline server image missing" >&2; exit 2; }
FACTORY="factory-proc-e2e-${$}"
PORT="${PROC_E2E_PORT:-0}"
WORK="$(mktemp -d)"
DB="procdb_$(date +%s)"

compose() { docker compose -p "${PROJECT}" -f "${HERE}/compose.yaml" "$@"; }
cleanup() {
  docker rm -f "${FACTORY}" "${FACTORY}-old-schema" >/dev/null 2>&1 || true
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "${WORK}"
}
trap cleanup EXIT

curljson() { curl --max-time 10 -s -o "${WORK}/resp.json" -w '%{http_code}' "$@"; }
health() { curl --max-time 5 -s "http://127.0.0.1:${PORT}/health"; }

echo "==> start isolated DBs"
compose up -d
deadline=$(( $(date +%s) + 120 ))
while :; do
  ph=$(compose ps -a --format '{{.Service}} {{.Health}}' | awk '/^postgres/{print $2}')
  mh=$(compose ps -a --format '{{.Service}} {{.Health}}' | awk '/^mongo/{print $2}')
  [[ "$ph" == healthy && "$mh" == healthy ]] && break
  [[ $(date +%s) -ge $deadline ]] && { echo "!! DBs not healthy (pg=$ph mongo=$mh)"; exit 1; }
  sleep 2
done
echo "   DBs healthy"

echo "==> M8 helper mints the operator token (Docker-free)"
python3 -I "${MODULE_DIR}/operator/identity_helper.py" init-token --out "${WORK}/operator.token" --id operator
SECRET="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['secret'])" "${WORK}/operator.token")"
mkdir -p "${WORK}/state"

# Env wiring the REAL composition root to the in-network DBs (service DNS, synthetic creds).
ENVARGS=(
  -e STORAGE_MONGO_ENABLED=1
  -e "STORAGE_MONGO_URI=mongodb://factory_test:factory_test_synthetic@mongo:27017/?authSource=admin"
  -e "STORAGE_MONGO_DB=${DB}"
  -e STORAGE_MONGO_COLLECTION=archive
  -e STORAGE_POSTGRES_ENABLED=1
  -e "STORAGE_POSTGRES_DSN=postgres://factory_test:factory_test_synthetic@postgres:5432/factory_test?sslmode=disable"
  -e STORAGE_CAPTURE_ENABLED=1
)

echo "==> -init the state volume (no DB needed for init)"
docker run --rm --pull=never --platform linux/amd64 -v "${WORK}/state":/state -v "${WORK}/operator.token":/run/secrets/operator_token:ro \
  "${IMAGE}" -state /state -operator-token /run/secrets/operator_token -init >/dev/null

# Exercise the real Docker-free helper binary in an environment with no Docker socket.
BUILDER="golang@sha256:e87b2a5f6df2dff71ea330d55d54f4979eb380ae58a7e3aabc9d53121243e689"
MODCACHE="${STORAGE_GO_MOD_CACHE:-}"
if [[ -z "$MODCACHE" ]] && command -v go >/dev/null; then MODCACHE="$(go env GOMODCACHE)"; fi
[[ -d "$MODCACHE" ]] || { echo "BLOCKED: offline module cache required for helper fixture"; exit 2; }
docker run --rm --pull=never --platform linux/amd64 --network none -v "${MODULE_DIR}:/src:ro" -v "${MODCACHE}:/go/pkg/mod:ro" -v "${WORK}:/out" -w /src -e GOPROXY=off -e GOSUMDB=off -e GOTOOLCHAIN=local -e CGO_ENABLED=0 "$BUILDER" sh -c 'go build -o /out/identity-operator ./cmd/identity-operator && go build -o /out/seed-backlog ./deploy/test/seed-backlog'
helper() { docker run --rm -i --pull=never --platform linux/amd64 --network none -v "${WORK}:/fixture" "$BUILDER" /fixture/identity-operator -state /fixture/state; }
printf '%s' '{"Operation":"project","Project":"offline-project","Label":"Synthetic offline project"}' | helper
printf '%s' '{"Operation":"consent","Project":"offline-project","Provider":"synthetic","Capability":"capture","Enabled":true}' | helper
printf '%s' '{"Operation":"grant","Grant":{"PrincipalID":"offline-agent","Kind":"agent","Projects":{"offline-project":true},"Ops":{"archive.query":true},"Secret":"synthetic-offline"}}' | helper
docker run --rm --pull=never --platform linux/amd64 --network none -e FACTORY_SYNTHETIC_FIXTURE=1 -v "${WORK}:/fixture" "$BUILDER" /fixture/seed-backlog /fixture/state

run_factory() {
  docker run -d --pull=never --platform linux/amd64 --name "${FACTORY}" --network "${NET}" -p "127.0.0.1:${PORT}:8777" \
    -v "${WORK}/state":/state -v "${WORK}/operator.token":/run/secrets/operator_token:ro \
    "${ENVARGS[@]}" "${IMAGE}" \
    -state /state -operator-token /run/secrets/operator_token -listen 0.0.0.0:8777 -dev-allow-nonloopback >/dev/null
}
wait_health_mode() { # $1 expected substring in /health
  for _ in $(seq 1 40); do health | grep -q "$1" && return 0; sleep 0.5; done
  docker logs "$FACTORY" >&2 || true
  echo "!! /health never matched '$1'; last: $(health)"; return 1
}

echo "==> launch the REAL factory container (capture + PG + Mongo enabled)"
run_factory
if [[ "$PORT" == 0 ]]; then PORT="$(docker port "$FACTORY" 8777/tcp | head -1 | awk -F: '{print $NF}')"; fi
wait_health_mode '"mode":"both"'
echo "   health: $(health)"
echo "$(health)" | grep -q '"mongo_up":true' || { echo "!! mongo_up not true"; exit 1; }
echo "$(health)" | grep -q '"postgres_up":true' || { echo "!! postgres_up not true"; exit 1; }

echo "==> startup worker must project existing accepted backlog WITHOUT a new capture"
for _ in $(seq 1 40); do
 curljson -H 'X-Principal-Id: offline-agent' -H 'X-Grant-Epoch: 1' -H 'X-Secret: synthetic-offline' "http://127.0.0.1:${PORT}/v1/archive/query?project=offline-project" >/dev/null
 grep -q 'synthetic accepted backlog' "${WORK}/resp.json" && break
 sleep 0.5
done
grep -q 'synthetic accepted backlog' "${WORK}/resp.json" || { echo '!! startup replay did not project backlog'; exit 1; }
echo "   offline helper authority and startup replay verified"

H=(-H "X-Operator-Secret: ${SECRET}" -H "Content-Type: application/json")
echo "==> operator setup + capture over HTTP"
[[ "$(curljson -X POST "${H[@]}" -d '{"UUID":"proj-A","Label":"A"}' http://127.0.0.1:${PORT}/v1/projects)" == 201 ]] || { echo mint; cat "${WORK}/resp.json"; exit 1; }
[[ "$(curljson -X POST "${H[@]}" -d '{"Project":"proj-A","Provider":"synthetic","Capability":"capture","Enabled":true}' http://127.0.0.1:${PORT}/v1/consent)" == 200 ]] || { echo consent; exit 1; }
EPOCH="$(curljson -X POST "${H[@]}" -d '{"principal_id":"agent-1","kind":"agent","projects":["proj-A"],"ops":["archive.query","search"],"secret":"sek"}' http://127.0.0.1:${PORT}/v1/grants >/dev/null; python3 -c "import json;print(int(json.load(open('${WORK}/resp.json'))['epoch']))")"
CAP='{"provider":"synthetic","source_instance":"inst-1","project":"proj-A","messages":[{"session_id":"s1","message_id":"m1","seq":1,"role":"user","text":"process e2e hello","kind":"message"}]}'
[[ "$(curljson -X POST "${H[@]}" -d "${CAP}" http://127.0.0.1:${PORT}/v1/capture)" == 200 ]] || { echo capture; cat "${WORK}/resp.json"; exit 1; }
echo "   capture: $(cat "${WORK}/resp.json")"

AQ=(-H "X-Principal-Id: agent-1" -H "X-Grant-Epoch: ${EPOCH}" -H "X-Secret: sek")
code=$(curljson "${AQ[@]}" "http://127.0.0.1:${PORT}/v1/archive/query?project=proj-A&q=hello")
echo "   query[$code]: $(cat "${WORK}/resp.json")"
grep -q 'process e2e hello' "${WORK}/resp.json" || { echo "!! capture not queryable"; exit 1; }

echo "==> actual background index publishes a source-verified receipt and search result"
RECEIPT_PATH="$(python3 -c 'import urllib.parse; print(urllib.parse.quote("[\"proj-A\",\"inst-1\",\"s1\",\"m1\"]",safe=""))')"
for _ in $(seq 1 40); do
 curljson "${AQ[@]}" "http://127.0.0.1:${PORT}/v1/ingest/${RECEIPT_PATH}?project=proj-A" >/dev/null
 grep -q '"state":"indexed"' "${WORK}/resp.json" && break
 sleep 0.5
done
grep -q '"state":"indexed"' "${WORK}/resp.json" || { echo '!! process worker never indexed'; cat "${WORK}/resp.json"; exit 1; }
[[ "$(curljson "${AQ[@]}" "http://127.0.0.1:${PORT}/v1/search/query?project=proj-A&q=hello")" == 200 ]] || { echo '!! derived query failed'; exit 1; }
grep -q 'process e2e hello' "${WORK}/resp.json" || { echo '!! derived query omitted verified source'; exit 1; }

echo "==> PG-index outage preserves archive commitment and archive query"
compose stop postgres >/dev/null
for _ in $(seq 1 40); do health | grep -q '"postgres_up":false' && break; sleep 0.5; done
[[ "$(curljson "${AQ[@]}" "http://127.0.0.1:${PORT}/v1/ingest/${RECEIPT_PATH}?project=proj-A")" == 200 ]] || { echo '!! PG outage hid archive receipt'; exit 1; }
grep -q '"state":"archive_committed"' "${WORK}/resp.json" || { echo '!! PG outage undid archive commitment'; exit 1; }
grep -q '"index_state":"unavailable"' "${WORK}/resp.json" || { echo '!! index outage misreported'; exit 1; }
[[ "$(curljson "${AQ[@]}" "http://127.0.0.1:${PORT}/v1/archive/query?project=proj-A")" == 200 ]] || { echo '!! PG outage blocked Mongo query'; exit 1; }
compose start postgres >/dev/null
for _ in $(seq 1 60); do health | grep -q '"postgres_up":true' && break; sleep 0.5; done
health | grep -q '"postgres_up":true' || { echo '!! PG did not recover'; exit 1; }

if [[ -n "${PREVIOUS_SCHEMA_IMAGE:-}" ]]; then
 echo "==> previous schema-1 image must refuse the new schema-2 database"
 docker image inspect "$PREVIOUS_SCHEMA_IMAGE" >/dev/null 2>&1 || { echo 'BLOCKED: explicit previous image missing'; exit 2; }
 mkdir -p "${WORK}/old-state"
 docker run --rm --pull=never --platform linux/amd64 -v "${WORK}/old-state":/state -v "${WORK}/operator.token":/token:ro "$PREVIOUS_SCHEMA_IMAGE" -state /state -operator-token /token -init >/dev/null
 docker run -d --pull=never --platform linux/amd64 --name "${FACTORY}-old-schema" --network "$NET" -v "${WORK}/old-state":/state -v "${WORK}/operator.token":/token:ro -e STORAGE_POSTGRES_ENABLED=1 -e "STORAGE_POSTGRES_DSN=postgres://factory_test:factory_test_synthetic@postgres:5432/factory_test?sslmode=disable" "$PREVIOUS_SCHEMA_IMAGE" -state /state -operator-token /token -listen 127.0.0.1:0 >/dev/null
 for _ in $(seq 1 40); do [[ "$(docker inspect -f '{{.State.Status}}' "${FACTORY}-old-schema")" == exited ]] && break; sleep 0.25; done
 [[ "$(docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "${FACTORY}-old-schema")" == 'exited 1' ]] || { echo '!! old image accepted newer schema'; exit 1; }
 docker logs "${FACTORY}-old-schema" > "${WORK}/old-schema.log" 2>&1
 grep -q 'database schema is newer' "${WORK}/old-schema.log" || { echo '!! old image exited for another reason'; cat "${WORK}/old-schema.log"; exit 1; }
 docker rm "${FACTORY}-old-schema" >/dev/null
else
 echo 'NOT_TESTED: previous-image schema refusal (set PREVIOUS_SCHEMA_IMAGE)'
fi

echo "==> online workflow cutover keeps the other project writable"
WREV="$(python3 - "${WORK}/state" <<'PY'
import hashlib, pathlib, sys
body=b'[]'
doc=b'# Factory structured workflow v1\n\n<!-- sha256:'+hashlib.sha256(body).hexdigest().encode()+b' -->\n```json\n'+body+b'\n```\n'
for name in ('wf-A','wf-B'):
    (pathlib.Path(sys.argv[1])/(name+'.md')).write_bytes(doc)
print(hashlib.sha256(doc).hexdigest())
PY
)"
for wp in wf-A wf-B; do
 [[ "$(curljson -X POST "${H[@]}" -d "{\"UUID\":\"${wp}\",\"Label\":\"Synthetic workflow\"}" "http://127.0.0.1:${PORT}/v1/projects")" == 201 ]] || { echo '!! workflow mint'; exit 1; }
 [[ "$(curljson -X POST "${H[@]}" -d "{\"project\":\"${wp}\",\"document\":\"/state/${wp}.md\",\"revision\":\"${WREV}\",\"to\":\"postgres\",\"expected_epoch\":1,\"edits_frozen\":true}" "http://127.0.0.1:${PORT}/v1/workflow/cutover")" == 200 ]] || { echo '!! workflow enable'; cat "${WORK}/resp.json"; exit 1; }
done
[[ "$(curljson -X POST "${H[@]}" -d '{"principal_id":"workflow-agent","kind":"agent","projects":["wf-A","wf-B"],"ops":["workflow.read","workflow.write"],"secret":"synthetic-workflow"}' "http://127.0.0.1:${PORT}/v1/grants")" == 201 ]] || { echo '!! workflow grant'; exit 1; }
WEPOCH="$(python3 -c "import json,sys;print(int(json.load(open(sys.argv[1]))['epoch']))" "${WORK}/resp.json")"
WH=(-H 'X-Principal-Id: workflow-agent' -H "X-Grant-Epoch: ${WEPOCH}" -H 'X-Secret: synthetic-workflow' -H 'Content-Type: application/json')
[[ "$(curljson -X PUT "${WH[@]}" -d '{"expected_version":0,"epoch":2,"fields":{"status":"ready"}}' "http://127.0.0.1:${PORT}/v1/workflow/task?project=wf-A&id=task")" == 200 ]] || { echo '!! workflow write A'; exit 1; }
[[ "$(curljson -X POST "${H[@]}" -d "{\"project\":\"wf-A\",\"document\":\"/state/wf-A.md\",\"revision\":\"${WREV}\",\"to\":\"markdown\",\"expected_epoch\":2,\"edits_frozen\":true}" "http://127.0.0.1:${PORT}/v1/workflow/cutover")" == 200 ]] || { echo '!! workflow disable A'; cat "${WORK}/resp.json"; exit 1; }
[[ "$(curljson "${WH[@]}" "http://127.0.0.1:${PORT}/v1/workflow/task?project=wf-A&id=task")" == 403 ]] || { echo '!! A grant not revoked'; exit 1; }
[[ "$(curljson -X PUT "${WH[@]}" -d '{"expected_version":0,"epoch":2,"fields":{"status":"still-writable"}}' "http://127.0.0.1:${PORT}/v1/workflow/task?project=wf-B&id=task")" == 200 ]] || { echo '!! B write interrupted'; exit 1; }
echo "   project A opted out while B continued through the same running process"

echo "==> RESTART the factory process; data must persist"
docker restart "${FACTORY}" >/dev/null
PORT="$(docker port "$FACTORY" 8777/tcp | head -1 | awk -F: '{print $NF}')"
wait_health_mode '"mode":"both"'
code=$(curljson "${AQ[@]}" "http://127.0.0.1:${PORT}/v1/archive/query?project=proj-A&q=hello")
grep -q 'process e2e hello' "${WORK}/resp.json" || { echo "!! data lost across restart"; exit 1; }
echo "   persisted across restart (query[$code] still returns the record)"
[[ "$(curljson "${WH[@]}" "http://127.0.0.1:${PORT}/v1/workflow/task?project=wf-A&id=task")" == 403 ]] || { echo '!! A revoke lost on restart'; exit 1; }
[[ "$(curljson "${WH[@]}" "http://127.0.0.1:${PORT}/v1/workflow/task?project=wf-B&id=task")" == 200 ]] || { echo '!! B workflow lost on restart'; exit 1; }


echo "==> BACKEND-DOWN: stop Mongo; /health must flip mongo_up=false and capture must FAIL CLOSED"
compose stop mongo >/dev/null
for _ in $(seq 1 40); do echo "$(health)" | grep -q '"mongo_up":false' && break; sleep 0.5; done
echo "$(health)" | grep -q '"mongo_up":false' || { echo "!! mongo_up did not flip false"; exit 1; }
# IMPORTANT SERVER-LEVEL BEHAVIOR (honest): the live-capacity meter reads Mongo StorageBytes,
# so with Mongo down the capacity measurement fails and capture is REJECTED at admission
# (fail-closed, 503) BEFORE any WAL write. The server therefore does NOT buffer-then-drain a
# capture while Mongo is down; it refuses it. (The WAL buffer-then-drain path F5/F6 is proven
# at the INGEST unit level in ingest.TestArchiveUnavailableBuffersThenDrains, where admission
# is independent of Mongo - but it is NOT reachable through this API capture path while Mongo
# is down, because the meter depends on Mongo. This is a known limitation, not a silent pass.)
code=$(curljson -X POST "${H[@]}" -d "${CAP//m1/m2}" http://127.0.0.1:${PORT}/v1/capture)
echo "   capture while Mongo down -> HTTP ${code}: $(cat "${WORK}/resp.json")"
[[ "$code" == 503 ]] || { echo "!! expected a fail-closed 503 while Mongo down"; exit 1; }
# Nothing was admitted, so nothing can resurrect: the archive copy of m2 must not appear later.

echo "==> RECOVERY: restart Mongo; /health recovers and capture WORKS AGAIN"
compose start mongo >/dev/null
for _ in $(seq 1 60); do echo "$(health)" | grep -q '"mongo_up":true' && break; sleep 0.5; done
echo "$(health)" | grep -q '"mongo_up":true' || { echo "!! mongo_up did not recover"; exit 1; }
# A fresh capture after recovery must succeed and be queryable; m2 (refused while down) must NOT exist.
[[ "$(curljson -X POST "${H[@]}" -d "${CAP//m1/m3}" http://127.0.0.1:${PORT}/v1/capture)" == 200 ]] || { echo "!! capture did not recover"; cat "${WORK}/resp.json"; exit 1; }
for _ in $(seq 1 20); do
  curljson "${AQ[@]}" "http://127.0.0.1:${PORT}/v1/archive/query?project=proj-A&q=hello" >/dev/null
  n=$(python3 -c "import json;print(len(json.load(open('${WORK}/resp.json')).get('hits',[])))")
  [[ "$n" -ge 2 ]] && break; sleep 0.5
done
echo "   post-recovery hit count: ${n} (expect 2: m1 + m3; m2 was refused while Mongo down, never admitted)"
[[ "${n}" -eq 2 ]] || { echo "!! unexpected hit count after recovery (got ${n})"; cat "${WORK}/resp.json"; exit 1; }
grep -q '"MessageID":"m2"' "${WORK}/resp.json" && { echo "!! m2 must NOT exist (it was refused, never admitted)"; exit 1; }


echo "==> PostgreSQL-only workflow must work without capture or Mongo"
docker rm -f "${FACTORY}" >/dev/null
ENVARGS=(-e STORAGE_POSTGRES_ENABLED=1 -e "STORAGE_POSTGRES_DSN=postgres://factory_test:factory_test_synthetic@postgres:5432/factory_test?sslmode=disable" -e STORAGE_CAPTURE_ENABLED=0)
run_factory
wait_health_mode '"mode":"postgres-only"'
[[ "$(curljson -X PUT "${WH[@]}" -d '{"expected_version":1,"epoch":2,"fields":{"status":"pg-only"}}' "http://127.0.0.1:${PORT}/v1/workflow/task?project=wf-B&id=task")" == 200 ]] || { echo '!! PG-only workflow write failed'; cat "${WORK}/resp.json"; exit 1; }
[[ "$(curljson "${AQ[@]}" "http://127.0.0.1:${PORT}/v1/archive/query?project=proj-A")" == 503 ]] || { echo '!! archive silently failed over to PG'; exit 1; }

echo "==> Mongo-only capture-off must preserve archive reads and erasure"
docker rm -f "${FACTORY}" >/dev/null
ENVARGS=(-e STORAGE_MONGO_ENABLED=1 -e "STORAGE_MONGO_URI=mongodb://factory_test:factory_test_synthetic@mongo:27017/?authSource=admin" -e "STORAGE_MONGO_DB=${DB}" -e STORAGE_MONGO_COLLECTION=archive -e STORAGE_CAPTURE_ENABLED=0)
run_factory
wait_health_mode '"mode":"mongo-only"'
[[ "$(curljson "${AQ[@]}" "http://127.0.0.1:${PORT}/v1/archive/query?project=proj-A&q=hello")" == 200 ]] || { echo '!! capture-off archive read unavailable'; exit 1; }
grep -q 'process e2e hello' "${WORK}/resp.json" || { echo '!! capture-off lost archive'; exit 1; }
[[ "$(curljson -X POST "${H[@]}" -d "${CAP//m1/m4}" "http://127.0.0.1:${PORT}/v1/capture")" == 503 ]] || { echo '!! capture-off accepted intake'; exit 1; }
[[ "$(curljson -X POST "${H[@]}" -d '{"Project":"proj-A"}' "http://127.0.0.1:${PORT}/v1/barriers/project")" == 200 ]] || { echo '!! capture-off barrier failed'; exit 1; }
[[ "$(curljson -X POST "${H[@]}" -d '{"Project":"proj-A"}' "http://127.0.0.1:${PORT}/v1/purge/project")" == 503 ]] || { echo '!! complete purge falsely claimed without known PG index'; exit 1; }
echo "==> restore PG access to erase every managed index with capture still disabled"
docker rm -f "${FACTORY}" >/dev/null
ENVARGS+=(-e STORAGE_POSTGRES_ENABLED=1 -e "STORAGE_POSTGRES_DSN=postgres://factory_test:factory_test_synthetic@postgres:5432/factory_test?sslmode=disable")
run_factory
wait_health_mode '"mode":"both"'
[[ "$(curljson -X POST "${H[@]}" -d '{"Project":"proj-A"}' "http://127.0.0.1:${PORT}/v1/purge/project")" == 200 ]] || { echo '!! complete capture-off purge failed'; cat "${WORK}/resp.json"; exit 1; }
grep -q '"index_purged":true' "${WORK}/resp.json" || { echo '!! index erasure not verified'; exit 1; }
[[ "$(curljson "${AQ[@]}" "http://127.0.0.1:${PORT}/v1/search/query?project=proj-A&q=hello")" == 200 ]] || { echo '!! post-purge search failed'; exit 1; }
python3 -c "import json,sys;assert not json.load(open(sys.argv[1]))['hits']" "${WORK}/resp.json"
[[ "$(curljson "${AQ[@]}" "http://127.0.0.1:${PORT}/v1/archive/query?project=proj-A")" == 200 ]] || { echo '!! capture-off post-purge query failed'; exit 1; }
python3 -c "import json,sys;assert not json.load(open(sys.argv[1]))['hits']" "${WORK}/resp.json"

echo "==> PROCESS-LEVEL E2E OK (real composition root: capture/persist/query + restart persistence + Mongo-down fail-closed + capture recovery)"
