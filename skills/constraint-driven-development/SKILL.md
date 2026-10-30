---
name: constraint-driven-development
description: Preserve an existing project's quality constraints during implementation or review, especially when checks fail or a change appears to weaken tests, thresholds or safeguards.
---

# Constraint-driven development

Read the project's accepted constraints, scripts, task acceptance and applicable instructions first. Reuse their owner and primary task record. This skill is a focused quality-floor check, not another implementation or review pipeline. It does not prescribe a stack, coverage percentage, new CONSTRAINTS.md, hooks, tools or CI.

Before implementation, record the applicable floor and evidence in the existing checkpoint: accepted behavior, relevant checks, permitted exceptions and exact scope. A project with no documented threshold does not inherit an arbitrary threshold from this skill. Ask only when a genuinely unresolved decision affects the authorized work.

On a failing check, investigate the implementation before weakening the check. Inspect changes to thresholds, exclusions, skipped/deleted tests, assertions, suppressions, stubs/empty catches and exception policy. These are **signals**, not proof: an assertion refactor can preserve or improve behavioral coverage. Compare the old failure-detection capability with the replacement and its relevant execution evidence. A confirmed reduction needs the contract owner's explicit, scoped decision; an author's explanation alone is not that decision.

Bind evidence to repository/root, base, HEAD, and the exact scoped dirty/untracked file hashes. Include deletions and the scope inventory, not only tracked diff. After HEAD or relevant bytes change, recheck the affected evidence; stale review is not inherited automatically. Missing input, skipped checks or unavailable independent review are BLOCKED/NOT_TESTED, never clean.

For interruption or a second sprint task, read the current primary record and establish that task's checkpoint before coding. Verify graph freshness if used; a stale graph can be replaced by direct file/caller inspection with that limitation recorded. Keep the existing reviewer route, local commit gate and final-delta review.

Read [floor evidence](references/floor-evidence.md) when assessing a signal or preparing the evidence record, including its **Anti-patterns** section, and the shared [reference anti-patterns](../../ai-factory/reference-anti-patterns.md) (4-field template + cross-cutting rules). The floor moves only by an explicit, reviewed owner decision — never by relaxing a check to obtain PASS. The shared offline validator checks record completeness and snapshot equality; it does not detect all weakening or prove the truth of supplied evidence. Use the project's real tests and independent review for those claims.

Adapted from Addy Osmani's agent-skills at the pinned source recorded in [provenance](references/provenance.md). [MIT license](LICENSE.addyosmani).
