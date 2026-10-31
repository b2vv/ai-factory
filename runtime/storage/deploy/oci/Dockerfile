# Digest-pinned OCI image for the Factory storage server (M7 / PLAN v4 §9.1).
#
# Unlike deploy/dev/Dockerfile (a convenience image pinned only by tag), this is the packaging
# artifact: the BUILDER base is pinned by registry DIGEST so the build is reproducible and does
# not drift with the floating tag, and the RUNTIME base is `scratch` (empty - nothing to pin;
# the image contains only the statically linked binary). go.mod/go.sum are locked and the build
# runs with the module cache only (no network fetch of new modules at build time).
#
# Offline acquisition: build once, `docker save` to a tar, transfer, `docker load` - no implicit
# registry pull of the application image. See deploy/oci/build-and-verify.sh.
#
# The builder digest below is recorded in deploy/oci/manifest.json and must be kept in sync
# with it. linux/amd64 only (other architectures NOT_TESTED, per §9.1).

FROM --platform=$BUILDPLATFORM golang@sha256:60deed95d3888cc5e4d9ff8a10c54e5edc008c6ae3fba6187be6fb592e19e8c0 AS build
WORKDIR /src
COPY . .
# GOFLAGS=-mod=readonly: fail the build if go.mod/go.sum are not already consistent (no silent
# dependency drift during packaging).
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOFLAGS=-mod=readonly \
    go build -trimpath -ldflags="-s -w" -o /factory ./cmd/factory

FROM scratch
COPY --from=build /factory /factory
# No baked flags: the loopback-only default and auth contract are unchanged; all flags
# (-state, -operator-token, -listen, and the explicit -dev-allow-nonloopback) are supplied at
# run time by the operator or the compose command.
ENTRYPOINT ["/factory"]
