# Reproducible dev/test image for the Factory storage control-registry/API TEST HARNESS.
#
# This is NOT a supported host distribution: the supported delivery is the digest-pinned
# OCI image plus the operator-only Docker-free helper (owner decision D1). This image exists
# only so the loopback control API can be exercised from the host during manual verification.
#
# The binary is built from the repository sources (no pre-built artifact), stdlib-only, as a
# static CGO-free linux/amd64 executable, then placed on an empty base so the running image
# contains nothing but the binary. The builder runs on the native build platform and
# cross-compiles, so no emulation is needed to produce the amd64 binary.
#
# Default runtime contract is unchanged: the server binds loopback only unless the explicit
# -dev-allow-nonloopback flag is passed. In this image the container binds 0.0.0.0 (container
# namespace only) and the compose file publishes the port to the host's 127.0.0.1 only.
# Authentication/authorization are unchanged: an operator secret and principal-bound agent
# tokens are still required and checked.

FROM --platform=$BUILDPLATFORM golang:1.23 AS build
WORKDIR /src
# Build context is the storage module root (runtime/storage); copy the whole module.
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /factory ./cmd/factory

FROM scratch
COPY --from=build /factory /factory
# No ENTRYPOINT arguments: all flags (including -state, -operator-token, -listen and the
# explicit -dev-allow-nonloopback) are supplied by the compose command, so nothing about the
# loopback-only default is baked into the image.
ENTRYPOINT ["/factory"]
