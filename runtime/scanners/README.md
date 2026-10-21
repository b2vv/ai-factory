# Offline scanner candidate

Implemented locally; **real scanner acceptance NOT RUN; independent review PENDING**.
The shipped manifest deliberately has no image/version/platform/DB provenance pins. Both
validation and execution BLOCK before Docker until those fields have reviewed values.
No fallback tag, registry rule fetching, image pull, product invocation or implicit update.
The JSON-formatted `compose.yaml` is a template, not directly runnable Compose: the runner
fills image pins and canonical mounts after validation. No installer activates it.

## Bounded coverage and inputs

Two original Semgrep rules flag direct `eval(...)` calls in JavaScript/TypeScript and Python.
They are a small baseline, not a comprehensive security ruleset. No external rule content
or `17e31e11` material is included. Authored for private owner-directed toolkit use; this
adds no public license grant. Engine, rule reuse and DB rights are separate reviews.

`manifest.json` rules.files keys are relative to `runtime/scanners/rules/`: the existing
`baseline.json` and nested `semgrep-rules/**/*.yaml`, `.yml` or `.json` are accepted.
Each selected file requires an exact SHA-256; traversal, hidden components, symlinks,
hardlinks and other roots/extensions are rejected. Limits are 2,000 files, 10 MiB per
file and 100 MiB total. Staging creates subdirectories and copies only this allowlist;
unlisted files (including license documents) never become scanner configs. Required
vendor notices remain in the package and release inventory. Compose mounts the staged
root read-only at `/rules` and passes `--config /rules`, retaining baseline-only support.
Adding directory content alone does not activate rules: the vendor step must update
rules.files, scope/provenance/rights and review status together. Real engine support for
the final rules remains a runtime acceptance gate.

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

## Explicit commands, after prerequisites are closed

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

Still required before security acceptance: vetted image/version/platform/DB digest provenance
and terms; real positive/clean/error runs for each engine; real Yarn production and dev-only
vulnerability detection (including transitive dependencies); missing/corrupt/stale DB errors;
actual mount/network/source-secret isolation; read-only cache success; immutable snapshot
update/reuse; and independent review bound to the final diff. Choose dependency fixtures and
expected advisories against the approved DB snapshot, without downloading/installing packages.
No P6/revoke, product rollout, CI activation, stand changes or commit/push are included.
