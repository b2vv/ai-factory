# Offline scanner candidate

The legacy host-Python entrypoint and Docker-only `scan.sh` have independently accepted scoped
synthetic runtime evidence. Docker-only is the selected operational route; its accepted scan,
updater and synthetic NOOP evidence is for the tested macOS host with linux/amd64 containers.
This does not establish full product security, native Linux host portability or image-wide rights clearance.
The Compose template is rendered only after validation; no installer activates this package.

## Bounded coverage and inputs

Two original Semgrep rules flag direct `eval(...)` calls in JavaScript/TypeScript and Python.
They are a small baseline, not a comprehensive security ruleset. No external rule content
or `17e31e11` material is included. Authored for private owner-directed toolkit use; this
adds no public license grant. Engine, rule reuse and DB rights are separate reviews.

`manifest.json` rules.files keys are relative to `runtime/scanners/rules/`: the existing
`baseline.yaml` and nested `semgrep-rules/**/*.yaml` or `.yml` are accepted; `.json` filenames are rejected.
Each selected file requires an exact SHA-256; traversal, hidden components, symlinks,
hardlinks and other roots/extensions are rejected. Limits are 2,000 files, 10 MiB per
file and 100 MiB total. Staging creates subdirectories and copies only this allowlist;
unlisted files (including license documents) never become scanner configs. Required
vendor notices remain in the package and release inventory. Compose mounts the staged
root read-only at `/rules` and passes `--config /rules`, retaining baseline-only support.
Adding directory content alone does not activate rules: the vendor step must update
rules.files, scope/provenance/rights and review status together. Real engine support for
the final rules remains a runtime acceptance gate.

Canonical vendor intent is preserved as **PROPOSED, not selected or accepted**: the earlier
owner-supplied short reference `17e31e11` and destination `rules/semgrep-rules/` remain recorded
in `provenance/security-sources.json`. Upstream identity, full revision, selected file closure
and applicable notices still require independent verification; the earlier stated terms are
not an image-wide or ruleset-wide clearance. No external rule is activated by this integration.

Compatibility: `baseline.json` is renamed to `baseline.yaml` with byte-identical contents
(SHA-256 `1050ea7f9dbf17ef37b1b120b698516f6913b791693a53dac949dc1d924abf91`).
Consumers must explicitly update filename allowlists; no silent Cargo or product migration.

No external ruleset is selected or vendored by this change. Future rule additions
require a separately reviewed source revision, file closure and applicable notices.

Start with `config.example.json`: explicit root, per-file SHA-256 allowlist, fresh reports
path, Factory DB store and immutable snapshot ID. This candidate supports JS/TS/Python
source plus paired `package.json` / `yarn.lock`. It requires nonempty direct devDependencies
for its Yarn baseline. npm/pnpm, alias/workspace edge cases, other languages, image/config/
secret scanning and automatic project discovery are outside this initial coverage.

The caller reviews selected bytes as sanitized (`sanitized_inputs_reviewed: true`). A
filename/key-pattern rejection is defense in depth, not universal secret removal. Unknown
embedded secrets cannot be safely inferred by this wrapper; do not attest unreviewed files.
Only selected regular, single-link files are copied to an isolated temporary source view.
Hidden paths, traversal, symlinks (including parents), hardlinks and hash mismatches fail
closed. Source, rules, DB and reports cannot overlap. Product configs never become scanner
commands or arbitrary Docker options; there are no installation or lifecycle scripts.
Cargo or another product provides only its own config/root/lockfiles/reports and an AI
Factory pin. Product-to-product inputs, caches, volumes or rule imports are forbidden.

## Retained host-Python reference (not the selected operational route)

Use the Docker-only `scan.sh` commands below for current operation. The Python commands in this
section and the DB section document retained implementation interfaces and historical fixtures;
they are not instructions to install or run Python on the host for the selected integration.

Use canonical absolute paths (on macOS, resolve `/tmp` to `/private/tmp`).

```sh
python3 -B runtime/scanners/scanner.py validate --config /absolute/config.json
# Separate, explicit scan authorization and reviewed local socket access are required:
python3 -B runtime/scanners/scanner.py scan --config /absolute/config.json --execute --socket /absolute/docker.sock
```

`validate` is read-only and never connects to Docker. `scan` only inspects locally present
pinned images, then creates containers with pull never/no build. Before start, it inspects
actual resolved bind sources, read-only flags, image ID/pin, network, process, environment,
privileges and extra mounts. Network is none, root filesystem read-only, capabilities dropped,
no socket/secrets mounts; only reports and bounded scratch are writable. Source/rules are
staged copies; DB is the actual immutable snapshot mounted read-only at `/cache`.
Trivy uses memory analysis cache, skip DB/Java updates, offline mode, disabled telemetry,
explicit library-vulnerability scanning and `--include-dev-deps --list-all-pkgs`.
Semgrep uses only local rules, metrics/version checks off and no suppression comments.

Current CLI references consulted: [Trivy filesystem](https://trivy.dev/docs/latest/references/configuration/cli/trivy_filesystem/)
and [Semgrep scan](https://docs.semgrep.dev/cli-reference). These describe flag intent, not
compatibility of an as-yet unselected image. Exact version flag support, image entrypoints,
read-only HOME/cache behavior and real isolation must be exercised with the reviewed pins.
No preexisting Docker socket denial is changed by adding this implementation.

Results: CLEAN=0, FINDINGS=1, ERROR=2, BLOCKED=3. VALIDATED=0 means declarations passed only.
All reported findings reject this baseline gate. Trivy schema 2 result objects require string
Target/Type and an explicit package inventory with nonempty string Name/Version. Optional
Vulnerabilities may be omitted/null or a list of objects with nonempty string
VulnerabilityID/PkgName/InstalledVersion; other types are ERROR, including falsey objects
and strings. Missing/null package inventory is ERROR because this baseline requests it. Process errors, malformed output or missing
expected source/lockfile coverage never become CLEAN. Trivy's inventory must contain every
direct dev dependency; this is a missing-coverage guard, not proof of transitive completeness.
Reports retain structured scanner outputs, actual inspect data, rendered Compose, input
hashes, manifest hash, DB provenance and per-engine exits. Outputs may contain selected
source excerpts: keep reports private. CLEAN is scoped to the declared rules/DB/inputs.
An interrupted run or cleanup failure is not a completed scan; retain the named project
and resolve its state separately. The runner only cleans its unique Compose project.

## Separate DB phase, outside Git

`update_db.py` has no source/config argument and mounts only a temporary writable DB cache.
It never starts the scanner runner. Reviewed engine and DB OCI digest pins, license/provenance
closure, explicit network authorization and local socket access are prerequisites.
No implicit image pull or registry fallback is used. Network bridge is limited by having
no product mount; registry redirects/actual egress remain a runtime validation gate, not
an asserted host allowlist firewall. No credentials are forwarded.

```sh
python3 -B runtime/scanners/update_db.py init-store --store /absolute/factory-db --execute
python3 -B runtime/scanners/update_db.py update --store /absolute/factory-db --socket /absolute/docker.sock --execute --network-authorized
```

Initialization requires a new dedicated directory outside Git. Updates serialize with an
exclusive lock, use a new cache, validate downloads, seal them and atomically publish a
content-addressed snapshot without replacing an existing snapshot. The entire downloaded
closure is checked before metadata writes or chmod: exactly db/trivy.db and db/metadata.json,
no extra entries, symlinks, hardlinks or special files. snapshot.json is created exclusively
with no-follow semantics. Private download cleanup unlinks file entries and changes only
opened directory permissions, never downloaded file inode permissions. No automatic GC or
mutable `latest` pointer. Failed pre-publication output is temporary; an already published
snapshot is retained. `owner.json` identifies Factory storage; it is an ownership convention,
not cryptographic attestation. Product-owned DB stores must not be relabeled or imported.

Snapshot validation checks exact files, regular/no-link paths, read-only permission bits,
SHA-256, engine/DB source binding, metadata Version (schema 2), UpdatedAt and NextUpdate.
The default maximum age is 24 hours, additionally bounded by NextUpdate, with future dates
rejected. It does not treat hashing as authenticity, validate advisory correctness, or open
the binary DB. Engine compatibility and the actual read-only cache must be tested at runtime.
The owner must prevent concurrent mutation of sealed snapshots; pre/post hashes and inspected
mounts do not provide an OS-level guarantee against a hostile same-user process/path race.

## Acceptance boundary

```sh
python3 -B -m unittest discover -s tests/scanners -v
```

Unit/static/mock tests use temporary fake stores and synthetic reports/advisory IDs. They
exercise positive/clean/error policy, source isolation, pins, schema/freshness/corruption,
actual-inspect rejection and dev inventory guards. They do not invoke Docker or any engine.
Static paired source fixtures live in `examples/security/fixtures`; never execute them.
Synthetic Yarn lock entries in tests prove wrapper behavior only, not Trivy parsing/detection.

Acceptance criteria include scoped image/version/platform/DB provenance and terms decisions,
real positive/clean/error runs, Yarn production/dev/transitive coverage, invalid DB rejection,
actual mount/network isolation, read-only cache, immutable snapshot update/reuse and independent
review bound to final bytes. These were exercised for the accepted scanner milestone; fixture
success is not whole-product security acceptance. Revalidate affected evidence when pins, rules,
runtime code or inputs change. No P6/revoke, product rollout, CI activation or stand change follows
automatically from this release.

## Scoped Semgrep CE fixture evidence

The official Semgrep 1.181.0 linux/amd64 candidate passed authored offline positive, clean, malformed-config and missing-config fixtures, plus version/help. See [runtime evidence](ce-runtime-evidence.json) for immutable evidence hashes and limits. This is CE-only invocation (`--oss-only`), not a CE-only image composition claim. Local directory rules use `.yaml`/`.yml`; the original two-rule baseline is renamed `baseline.yaml` without changing bytes. Existing consumers listing `.json` rules require a reviewed rename and hash-allowlist update; no automatic migration.

Six image-specific environment values are explicit service values checked by the existing verifier. Context/encoding values are preserved exactly; three instrumentation settings are explicitly empty. Empty values do not establish instrumentation inactivity; network-none remains separate enforced isolation. Global SAFE_IMAGE_ENV is unchanged.

The manifest contains exact scoped private-use image and DB pins. Refer to runtime-acceptance.json
for historical host-runner evidence; it does not accept the Docker-only migration. Three Semgrep
notice samples do not establish image-wide source/rights closure. Product rollout remains separate.

## Scoped runtime and local Compose prerequisite

Exact linux/amd64 image pins and private-use decisions are in manifest.json and runtime-acceptance.json. These are not a universal license/provenance clearance, full rule coverage, product scan or release. The immutable DB source is time-bound: an expired snapshot blocks; an update requires a newly reviewed immutable source, never a floating fallback. Factory DB stays outside Git; do not reuse another product's store. Updater scratch1GiB shares2GiB RAM; scan scratch stays256MiB. Both use2CPU/2GiB without extra swap/128PIDs.

If Docker CLI cannot discover Compose with the isolated config, supply optional `compose_plugin` in the local scan config: `{ "path": "/absolute/trusted/local/docker-compose", "sha256": "exact SHA256 of that installed executable" }`. Owner selects trusted existing software; no installation or download is performed. Validate checks canonical regular executable and hash (max64MiB). Execution copies those verified bytes into its temporary Docker config, verifies them again, and removes them with the temporary task directory. No account Docker config or credentials are copied; no host/global settings change. Plugin runs on the host platform, while scanner containers remain linux/amd64. Omit when normal isolated CLI discovery works. An updated binary needs a new explicit hash.

No process timeout guarantees daemon cleanup after host crash/SIGKILL; reconcile exact task container/project before retry. Runtime acceptance used bounded external capture/deadlines; production command timeout remains per-command. Apply equivalent aggregate supervision for controlled unattended runs.

## Docker-only operational entrypoint

Host requirements: POSIX shell, Docker CLI, installed Compose executable and basic utilities
id, dirname, mkdir, cp, cmp, sort, sed, awk, df, du, od, tr, sleep, kill, wait and cat.
No host Python, native scanner, installation or global Docker configuration edit is needed.
The helper and engines run linux/amd64. Supply canonical paths and an explicit hash of the trusted
installed Compose binary; helper verifies that hash before scan orchestration. The installed plugin
is invoked directly with DOCKER_HOST and an empty task Docker config, not an invented plugin flag.

```sh
sh runtime/scanners/scan.sh scan /absolute/config.json /absolute/new-run /absolute/docker.sock /absolute/docker-compose COMPOSE_SHA256
sh runtime/scanners/scan.sh update-db /absolute/factory-store /absolute/new-update /absolute/docker.sock /absolute/docker-compose COMPOSE_SHA256
```

The run directory must be absent; config reports must equal that directory plus /reports.
Use a nonroot host UID/GID; no automatic chown. Only explicit source files are mounted, each RO,
then copied and hashed into isolated staging. Host shell rejects symlink ancestors; same-user hostile
TOCTOU remains outside this best-effort check. No container receives Docker socket or host credentials.
Every helper is created and inspected before start with literal image-specific env/security checks.
The updater lease is atomic mkdir plus owner token; interrupted/uncertain update retains cache and
lease for exact-resource reconciliation. Never remove a lease based only on age.

600 seconds covers the operation, followed by one15-second cleanup budget. INT/TERM/HUP stops new
work and reconciles exact intended names. SIGKILL/host crash cannot be handled; do not reuse a run
until its names are reconciled. Outputs are capped per control command; source reports and disk
accounting remain soft thresholds.2GiB per image and task export,2GiB per incoming DB cache,
10GiB free reserve; no25GiB budget. Existing sealed DB and incoming1.64GiB copy coexist temporarily:
this can require about3.28GiB total store storage. A runtime update with this coexistence requires
reviewed explicit storage accounting; it is not a2GiB aggregate store claim.

A successful scan has result-pending-cleanup.json with engine evidence, result.json with final
cleanup-aware status, entrypoint.exit and per-command separate stdout/stderr. Interrupted runs may
only have entrypoint.exit/cleanup-state and partial receipts; these never constitute CLEAN.
Source stages/reports are retained as private task artifacts, not recursively removed by cleanup.
Only exact containers are removed. Native Linux host behavior remains NOT_TESTED.
Actual stdlib/permission/Compose behavior on the
tested macOS host was independently accepted; new host discovery and product activation remain separate.
