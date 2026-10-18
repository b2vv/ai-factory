# AI Factory — full personal collection and portable tools

Full internal collection correction, version `0.3.1-candidate`. Start with the [full source collection](collection/README.md) and [complete AI Factory plan](collection/agents/ai-factory/ai-factory-plan.md). Inventory coverage is 84/84 shared definitions: 73 copied and 11 explicitly license-restricted provider dependencies. External symlink targets and project/system/plugin skill collections are excluded by the user’s clarified scope. See the exact boundaries and transformations in [collection manifest](collection/manifest.json).

The following starter remains available as optional portable wrappers; it is not the complete canonical source collection.

# AI Factory portable toolkit — 0.2.0 candidate

Reusable personal workflow core for Codex CLI and Claude Code: proportional lifecycle, planning skills, independent review packages, model-binding declarations, graph freshness guidance, opt-in session handoffs and a working offline staged installer. Preserve each project's stack, contracts and existing task tracker.

Status: author-validated candidate. Independent reviewer identity/acceptance is pending; no independent PASS is claimed. Native CLI discovery, hook activation and behavior on a new PC remain NOT_TESTED. Packaging or publishing this repository is not rollout to any project or global configuration.

Start with [three onboarding routes](docs/onboarding.md), then [feature lifecycle](docs/feature-lifecycle.md). [Capabilities](docs/capabilities.md) distinguishes implemented behavior, optional components and omissions.

| Component | Included |
|---|---|
| core (always) | Workflow/lifecycle/ADR/UI/ship guidance, model roles, CRG freshness, read-only onboarding and offline installer |
| planning (opt-in) | cto-research, acceptance-spec, plan-critique, plan-defense with bundled dependency closure |
| review (opt-in) | Scoped immutable evidence capture, freshness/response assessment and final-delta helper |
| session-guard (opt-in) | Explicit-store checkpoint/resume, byte thresholds and optional unregistered hook adapter |
| graphify (opt-in) | Local-only graphify-local skill, documented precision/incremental limitations; no binary |

## Verify and stage offline

Use an already available Python 3.9+ on POSIX/macOS. No tools are downloaded. Before running code, verify trusted provenance and inspect the published file allowlist/checksums; hashes are not signatures.

```sh
python3 -B tools/verify_release.py --root "$PWD"
python3 -B tools/run_tests.py
python3 -B tools/kit.py --package "$PWD" --root '/absolute/dedicated/toolkit' --component planning --component review
```

The final command only plans. Explicit apply/update/rollback commands and their concurrency preconditions are in [installer contract](docs/portability-design.md). Do not point the installer at a product repository or existing host configuration directory. No git/network commands are issued by the installer.

See [source provenance](source-provenance.json), [licensing and notices](PROVENANCE.md), [review handoff](docs/review-handoff.md) and [release manifest](release-manifest.json). Personal histories, credentials, graphs, host configs and product source are excluded. Optional third-party skills/binaries are not mirrored.
