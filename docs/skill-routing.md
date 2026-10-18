# Conditional skill routing and dependency closure

Core lifecycle and review operate from bundled documents; no skill runner, graph or model API is required. The optional `planning` component contains four personal planning skills. Each depends only on bundled core docs and the target project's accepted instructions. All Markdown references in these skills are shipped. Mentions of other skill names are optional comparisons/extensions, not executable imports.

| Trigger | Bundled exact file | Output / boundary |
|---|---|---|
| Unknown or stale implementation context | [cto-research](../skills/cto-research/SKILL.md) | Existing briefing with primary evidence; writing only in authorized scope |
| Behavioral feature acceptance | [acceptance-spec](../skills/acceptance-spec/SKILL.md) | Observable happy/boundary/failure scenarios in existing plan |
| Selected independent plan critique | [plan-critique](../skills/plan-critique/SKILL.md) | Four independent lenses under approved reviewer route |
| Plan failure/recovery completeness | [plan-defense](../skills/plan-defense/SKILL.md) | Five questions answered by plan lines or justified N/A |
| Explicit local graph question | [graphify-local](../skills/graphify-local/SKILL.md) | Optional local Graphify evidence; fresh output and source validation |

Packaging a skill is not registration or invocation. In a distribution all files exist; a staged install with omitted components may intentionally lack optional linked skill files. Check selected components in installed state before using them. For Codex/Claude use the host's supported discovery only after a separate check, or read the exact installed SKILL.md and its references as a file fallback. Do not create global aliases automatically.

## Full source collection

The optional `collection` component now preserves the complete eligible internal source tree: spec-flow, grilling, TDD, code-review, receiving-code-review, ship-report, UI/design, entity, CRG and their in-bundle supporting resources. See [collection layout and boundaries](../collection/README.md) and [source manifest](../collection/manifest.json) for exact source variants and runtime/external dependencies. The five portable adapters above remain distinct from inherited originals; do not silently substitute one for the other.

All 84 physical shared definitions are accounted for: 73 included and 11 explicitly restricted provider definitions represented without copied contents. External symlink targets, project/host/system/plugin skill collections and `b2b*` skills are excluded under the user's clarified scope. Missing runtime services or project contracts must be supplied separately; file preservation does not prove native invocation or authorize installation.
