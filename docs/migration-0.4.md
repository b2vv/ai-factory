# Migration from 0.3.1 / 626fd68 to 0.4

This is a new normal release, not an in-place edit of the previous immutable release. Existing project pins continue to use their old paths and hashes until an independently reviewed project upgrade. No global symlinks or callbacks are retargeted.

| Previous live path | New live path |
|---|---|
| collection/agents/skills/ | skills/ (73 originals, groups/variants retained) |
| collection/agents/ai-factory/*.md | ai-factory/*.md (full plan, not a summary) |
| collection/agents/rules/ | rules/ |
| collection/agents/AGENTS.md | rules/agent-entry.md (inherited host entry, not repo maintainer AGENTS) |
| skills/{four planning names}/SKILL.md | adapters/legacy-planning/{name}-portable.md (explicit policy profiles) |
| skills/graphify-local/SKILL.md and matching original | skills/graphify-local/SKILL.md (one identical source) |
| onboarding/preflight.py and identical original | runtime/onboarding/preflight.py |
| review/review_package.py | runtime/review/review_package.py |
| session-size/session_guard.py | runtime/session-size/session_guard.py |
| collection original review/session code | runtime/legacy/review/ and runtime/legacy/session-size/ |
| collection/manifest.json | provenance/source-map.json |

All source paths in provenance are historical; `destination` and migration `new_path` are live. Source hashes and license notices are retained. The complete 350-entry mapping includes exact duplicate removals, updated test imports, generated integrity metadata and retained docs. Historical Git version 626fd68 preserves the prior release without copying a second editable skill tree.

## Behavioral variants are explicit

Planning originals retain their contracts. Portable acceptance uses conditional local TDD; portable cto research specifies authorization and contract priority; portable critique accepts the agreed independent-session route; defense retains its portable routing preface. They remain separately named adapter documents, not silently merged policy. The exact-duplicate Graphify copy is the only removed skill body.

Portable review disables git hooks/fsmonitor; original legacy review retains its original invocation. Portable session guard requires `--store` with an absolute path; legacy retains its historical default home-store behavior. Neither is automatically executed. Selecting the new layout does not migrate live hooks or any existing store. Use exact module paths, not basename resolution.

## Managed upgrade and rollback

Verify the source release first. Inspect current installed components and choose the complete desired set. The old `collection` name remains accepted and resolves to `core`, `skills`, `graphify`, `legacy-runtime`; the old planning/review/session-guard/graphify choices remain explicit. Component dependencies are resolved transitively and cycles are rejected. Core-only installs intentionally do not claim to install all skills.

Run `tools/kit.py plan` against a dedicated managed destination; moves appear as explicit add/remove records, with matching managed hashes and no unmanaged collision. After reviewing it, use the existing `update --execute --exclusive-window --plan-id ...` contract. A genuinely exclusive writer window remains necessary; the filesystem has no cross-process CAS guarantee. Repeat plan must be NOOP. A local edit must BLOCK update, not be overwritten.

Rollback requires the exact transaction and rollback plan ID. It restores previous bytes/paths/modes/selected components using verified backups; a foreign edit BLOCKS rollback. Unrelated files remain. No reset/clean/global root replacement is permitted. Stale aliases are not automatically installed; `provenance/source-map.json` is a mapping, not executable registration.

## Validation and independent review

Run `tools/run_tests.py --previous-release <explicit immutable old release>` to exercise new install, upgrade, repeat NOOP, rollback, local edits and both runtime variants in temporary fake homes only. Missing the explicit old release is reported as a skipped upgrade test, not proof of upgrade success. Runtime tools and provider services are not installed by tests. No product e2e/reset/seed/browser probes are implied.

The three current project pins remain 626fd68. A future project upgrade needs fresh baseline, new isolated cache, route/hash-only adapter delta, preserved local QA/skills/tasks, and a new immutable package for the existing independent Claude reviewer. Neither author tests nor old reviewer acceptance imply acceptance of this future delta.
