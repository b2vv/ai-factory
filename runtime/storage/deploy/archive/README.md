# Persistent local archive restart policy

This optional Compose overlay is the repository-owned restart policy for an
**already provisioned** local archive with `factory`, `postgres` and `mongo`
services. It is not a bootstrap installer or a complete deployment. The private
base Compose file owns the image, credentials, health checks, mounts, networks,
project identity and loopback port. Never replace that file with a test harness.
The [dev harness](../dev/README.md) and disposable integration tests intentionally
keep their existing restart policy; do not apply this overlay to them.

## Authorized deployment

Set `BASE` to the absolute existing private Compose file and `POLICY` to the
absolute `restart.compose.json` beside this document. Keep the existing Compose
project name (`-p` if the deployment uses it), working directory and environment.
The base must already define working health checks for both databases.

```sh
docker compose -f "$BASE" -f "$POLICY" config --quiet
```

Review the resolved model locally, without publishing secrets: the only intended
changes are `restart: unless-stopped` on those three services and factory's
`depends_on` health conditions. Verify existing image, named volumes, bind mounts,
networks and host `127.0.0.1` port binding are unchanged. Stop if a service is
missing, a database lacks its health check, or identity/storage/exposure changes.
Use both files on every future authorized `up`; alternatively incorporate these
same fields into the private base through its deployment process. A kit update
alone neither changes running containers nor starts Docker.

For a running deployment, after saving the persistent policy, apply it without
recreating containers using the **verified existing names**:

```sh
docker update --restart unless-stopped "$POSTGRES_CONTAINER" "$MONGO_CONTAINER" "$FACTORY_CONTAINER"
```

Do not guess names, run `down -v`, bootstrap new databases, or recreate the stack
just to change restart policy. For a later authorized Compose start/update, use
`docker compose -f "$BASE" -f "$POLICY" up -d` with the same project identity.
That operation can recreate changed services and needs its own reviewed rollout.
Keep a private backup of the previous base and record previous effective policies
for rollback; reverting the files alone does not change running container policy.

## Startup and verification boundaries

- `unless-stopped` restarts exited containers and restores running services after
  Docker Engine restarts. An intentional `docker stop` stays stopped across Engine
  restarts until explicitly started. It does not start Docker Desktop itself.
- Compose starts factory after database health checks pass. Docker Engine's restart
  manager does not evaluate Compose dependencies. Factory startup fails with a
  nonzero exit when a required database is unavailable, allowing restart-policy
  retries. A container merely becoming unhealthy is **not** restarted by this policy.
- Inspect effective restart policies and confirm the same container IDs, image,
  mounts and loopback binding. Check database health and archive `/health`, then an
  authorized scoped read-only search. Do not infer capture completeness from health.
- A config validation or `docker update` is not a reboot/fault-injection test.
  Record those as NOT_TESTED unless separately exercised in an approved window.
  Never restart the whole Docker daemon while other projects depend on it just
  to prove this setting.

Run the offline contract fixtures (no Docker, credentials or live data):

```sh
python3 -B -m unittest discover -s runtime/storage/deploy/archive -p 'test_*.py' -v
```
