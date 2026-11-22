# 0.9.0: public baseline, project connections and test bridges

First release under the plain `x.y.z` version scheme. Git tag: `release-0.9.0`.

## Versioning

- `x` (major): an incompatible change for an existing installation — for example the
  format of `installed.json` or the release manifest, `kit.py` commands, or the managed
  project block — that needs manual steps on update.
- `y` (minor): a new capability without breaking existing installations (a component,
  command or skill).
- `z` (patch): fixes, tests and documentation without a behavior change.
- While `x` is `0` the kit is an alpha; an incompatible change then raises only `y`.
  `1.0.0` is set when install and update are declared stable.
- The version is raised for a release, not for every commit. A release is the commit
  that sets the new `version` in `release-manifest.json`, tagged `release-x.y.z`.
- No pre-release or build suffixes; `0.` already marks the alpha.

The installed kit is an exported package without Git history, so it reads its version
from the release manifest; the tag marks the same commit in the repository. Connected
projects are bound to no version: their managed block points to the installed kit's
`installed.json` (`latest`).

## Changes since 0.8.0-alpha.1

- The public repository restarts from a single baseline commit; earlier history is
  not carried over.
- Reconnecting a project keeps its recorded conversation-archive search route.
- The managed project block carries no kit hash or version.
- Provenance and licenses are recorded for the dashboard and web-to-md dependencies
  (`provenance/runtime-dependencies.json`).
- `tools/run_tests.py` runs the storage, dashboard and web-to-md Go suites with an
  explicit, version-checked toolchain (`AI_FACTORY_GO`), and `--suite <name>` runs one.
  Dashboard tests run from a clean checkout with the test-only `nobundle` tag. The
  ui-measurements browser test finds Google Chrome on macOS.
- The storage Go suite passes on macOS (temp-directory symlinks in backup tests, a
  startup-refusal deadline under load, a storage-only hang guard for the fsync-bound
  API package).
- Layout-migration and native-handoff digests are history; tests pin current bytes only
  for licenses, notices and frozen helpers, and the release manifest pins the rest.
- A Git checkout is not a release: export it before `verify_release.py`, which now
  names the failing check.

## Limits

The storage alpha limits recorded in [0.8.0-alpha.1](release-0.8.0-alpha.1.md) still
apply. Native skill discovery and invocation on a given host remain NOT_TESTED until
checked there.
