# Storage control API — reproducible Docker dev/test launch

This directory provides a reproducible, repository-based Docker launch of the Factory
storage control-registry/API **test harness** for local manual verification.

It is **not** a supported host distribution. Per owner decision D1 the supported delivery is
the digest-pinned OCI image plus the operator-only Docker-free helper; this compose setup
exists only to exercise the loopback control API from the host. Databases are disabled and
no conversation capture is performed.

## Security model

- The server binds **loopback only by default**. Containerized use binds the container's
  `0.0.0.0` (container namespace only) and requires the explicit `-dev-allow-nonloopback`
  flag; the compose file publishes the port to the **host's `127.0.0.1` only**, never to the
  LAN or the internet.
- `-dev-allow-nonloopback` changes nothing about authentication or authorization: an operator
  secret is required for every control mutation, and agent requests are checked against a
  principal-bound, epoch-pinned grant. The flag gates only the bind address check.
- The container drops all capabilities, runs with `no-new-privileges`, a read-only root
  filesystem, a tmpfs `/tmp`, a dedicated bridge network, no host networking, no privileged
  mode, and no access to the Docker socket.
- The operator token is a synthetic secret you create locally; it is bind-mounted read-only
  and is never committed or baked into the image.

## Requirements

- Docker Engine **>= 28.0.0** (earlier versions had a `127.0.0.1` port-publishing issue).
- The image is built from source as a static `linux/amd64` binary; the builder cross-compiles
  from the native build platform, so no emulation is required to produce the binary.

## One-time setup

Create a synthetic `0600` operator token on the host and point the compose file at it:

```sh
printf '{"id":"operator","secret":"REPLACE-WITH-A-RANDOM-SECRET"}' > /path/to/operator.json
chmod 600 /path/to/operator.json
export FACTORY_OPERATOR_TOKEN=/path/to/operator.json
# optional: pick a host port (default 8777), bound to 127.0.0.1 only
export FACTORY_HOST_PORT=8777
```

All commands below are run from the repository root and reference this compose file by path.

## Build the image (from source, before init)

Build the image from the repository sources **first**, so initialization and start run the
exact image you just built rather than relying on an implicit on-demand build:

```sh
docker compose -f runtime/storage/deploy/dev/compose.yaml build
```

## Initialize (explicit, one-time; after build)

Initialization is a separate operator action; normal startup never creates authority. Run it
only **after** the image is built (previous step). This creates a fresh registry in the named
state volume and exits:

```sh
docker compose -f runtime/storage/deploy/dev/compose.yaml run --rm factory \
  -init -state /state
```

Running `init` against an already-initialized or non-pristine state is refused (it is not a
recovery bypass).

## Start / Stop / Restart

```sh
# start (image already built in the Build step above); publishes to 127.0.0.1:${FACTORY_HOST_PORT:-8777}
docker compose -f runtime/storage/deploy/dev/compose.yaml up -d

# confirm the publish is host-loopback-only
docker compose -f runtime/storage/deploy/dev/compose.yaml ps
docker compose -f runtime/storage/deploy/dev/compose.yaml port factory 8777

# logs
docker compose -f runtime/storage/deploy/dev/compose.yaml logs

# stop (keep state) / restart
docker compose -f runtime/storage/deploy/dev/compose.yaml stop
docker compose -f runtime/storage/deploy/dev/compose.yaml restart
```

## Smoke check (from the host)

```sh
BASE=http://127.0.0.1:${FACTORY_HOST_PORT:-8777}
SEC=$(python3 -c "import json;print(json.load(open('$FACTORY_OPERATOR_TOKEN'))['secret'])")

curl -s "$BASE/health"                              # mode=file-only, databases/capture disabled
curl -s -H "X-Operator-Secret: $SEC" -X POST "$BASE/v1/projects" -d '{"UUID":"proj-A","Label":"a"}'
curl -s -X POST "$BASE/v1/projects" -d '{"UUID":"x"}'   # 401 without the operator secret
```

Endpoints: `/health`, `/v1/projects`, `/v1/grants`, `/v1/grants/revoke`, `/v1/consent`,
`/v1/barriers/project`, `/v1/whoami`.

## Tear down

`down -v` **DELETES the durable test state**: it removes the named state volume, destroying
every minted project, grant, consent and deletion barrier. Use it only when you want to
discard the test state. Omit `-v` to stop and remove the containers and network while
**keeping** the state volume.

```sh
# remove containers + network AND DELETE the test state volume
docker compose -f runtime/storage/deploy/dev/compose.yaml down -v

# (alternative) remove containers + network but KEEP the state
docker compose -f runtime/storage/deploy/dev/compose.yaml down
```

## Not implemented here

Real MongoDB/PostgreSQL adapters, WAL ingestion/capture, workflow cutover, TLS/mTLS, the
supported OCI image, and the Docker-free operator helper are out of scope for this dev/test
harness.
