> **Historical English adaptation — authored derivative.** Historical source: [docs/legacy/starter-readme.md at `2c0960885926`](https://github.com/b2vv/ai-factory/blob/2c0960885926075502a319a19eafbed901690dde/docs/legacy/starter-readme.md). Original SHA256: `6329060b1357c88ca744fb691a44dc28912b85a941b0c1507fbccb7154a8c7b4`. Source base: `2c0960885926075502a319a19eafbed901690dde`. The immutable source at this commit and hash remains the historical reference; the [current in-repository document](starter-readme.md) is an English adaptation. Historical assertions, statuses, examples, and limitations are retained; this document does not establish current policy, execution evidence, or activation. Current labels, placeholders, and section navigation are English; local-project links remain removed.

> Retained documentation from release 626fd68. Historical layout/status statements below are preserved for provenance; current paths and commands are in the root README and migration guide.

# AI Factory — full personal collection and portable tools

## Start here

- **[All 73 original skills →](../../skills)** — the full included collection with subdirectories and supporting files.
- **[Full AI Factory plan →](../../ai-factory/ai-factory-plan.md)** — plan, workflow, roadmap and related rules.
- The [root `skills/` directory](../../skills) contains only **5 portable adapters**, not the entire collection.

The inventory covers 84 internal definitions: 73 are included; 11 synced sets explicitly prohibit copying outside the service under their licenses and appear only in the [manifest with exclusion reasons](../../provenance/source-map.json).

---

Full internal collection correction, version `0.3.1-candidate`. Start with the [full source collection](../collection.md) and [complete AI Factory plan](../../ai-factory/ai-factory-plan.md). Inventory coverage is 84/84 shared definitions: 73 copied and 11 explicitly license-restricted provider dependencies. External symlink targets and project/system/plugin skill collections are excluded by the user’s clarified scope. See the exact boundaries and transformations in [collection manifest](../../provenance/source-map.json).

The following starter remains available as optional portable wrappers; it is not the complete canonical source collection.

# AI Factory portable toolkit — 0.2.0 candidate

Reusable personal workflow core for Codex CLI and Claude Code: proportional lifecycle, planning skills, independent review packages, model-binding declarations, graph freshness guidance, opt-in session handoffs and a working offline staged installer. Preserve each project's stack, contracts and existing task tracker.

Status: author-validated candidate. Independent reviewer identity/acceptance is pending; no independent PASS is claimed. Native CLI discovery, hook activation and behavior on a new PC remain NOT_TESTED. Packaging or publishing this repository is not rollout to any project or global configuration.

Start with [three onboarding routes](../portable/onboarding.md), then [feature lifecycle](../portable/feature-lifecycle.md). [Capabilities](../portable/capabilities.md) distinguishes implemented behavior, optional components and omissions.

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

The final command only plans. Explicit apply/update/rollback commands and their concurrency preconditions are in [installer contract](../portability-design.md). Do not point the installer at a product repository or existing host configuration directory. No git/network commands are issued by the installer.

See [source provenance](../../provenance/starter-source.json), [licensing and notices](../../PROVENANCE.md), [review handoff](../portable/review-handoff.md) and [release manifest](../../release-manifest.json). Personal histories, credentials, graphs, host configs and product source are excluded. Optional third-party skills/binaries are not mirrored.
