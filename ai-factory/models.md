---
title: "Three model roles in the current workflow"
reviewed: 2026-10-16
---

[Entry](../docs/legacy/ai-factory-plan-entry.md) · [Workflow](workflow.md) · [CRG](crg.md)

# Helper / Coder / Escalation-reviewer

This is a manual division of roles in the existing workflow, not an installed router or a new pipeline. Small tasks do not need three agents. The local contract defines acceptance, gates, commit ownership and the need for independent review. Preserve the current stack and user changes.

| Role | Boundaries and result | Escalation |
|---|---|---|
| Helper | Fast, cheaper read-only search, file map, short summary with file:line; no source edits, final verdict or heavy checks | Ambiguous requirements/architecture, conflicting sources or missing evidence → Coder |
| Coder | Implement the agreed scope, acceptance, appropriate deterministic checks; journal of decisions/changes/results | High risk or two failed justified fixes → Escalation |
| Escalation / reviewer | Complex causes, cross-module contracts, auth/access/data/migrations/irreversibility; review in a new independent context | No independent executor or missing access/decision → BLOCKED + specific handoff |

High risk goes directly to Escalation, without requiring a failed cheap pass first. If Escalation authored the solution/code, another reviewer is needed for the verdict; self-review does not become independent through a new role name. A model does not replace compiler/lint/tests, browser interaction or human acceptance.

<a id="bindings-і-рівень-підтвердження"></a>
## Bindings and level of confirmation

Determine bindings anew for the particular host/session, regardless of provider. A role name does not specify a model ID. Old cache snapshots and configured defaults are historical candidates, not a current catalog or entitlement. A Codex app/dot/other executor catalog does not carry over to local Codex CLI or Claude Code.

| Session inventory field | Required evidence / action if absent |
|---|---|
| Host, session, date, role | Name the particular CLI/app and session; do not infer it from the repository name |
| Available catalog and provenance | An already available catalog for this exact host/session with a reference; if absent, obtain a read-only inventory by a supported method or leave UNBOUND |
| Candidate + effort | The candidate must be in this catalog; effort only from confirmed host capabilities, otherwise unresolved |
| Entitlement | Separately unknown / available / unavailable with evidence; catalog presence does not guarantee account access |
| Budget | Separately unknown / approved / denied; account for the current request, do not enable paid access |
| Actual binding | Only an already confirmed actual run/session state; a configured candidate is not runtime proof |

For Helper, Coder, Escalation/reviewer record candidate status (catalog unknown / unselected / missing / listed), entitlement, budget and a specific next step. Missing candidate → choose from the available same-host catalog; unknown entitlement → verify access without a paid probe; unknown budget → owner decision before a costly run. An unconfirmed combination is **UNBOUND**. If the current model is already known, it may be recorded as the actual binding without assuming a cheaper tier; the Helper role alone does not reduce cost.

The [preflight schema](../docs/onboarding-helper.md) checks only the supplied inventory and session identity, not evidence authenticity or entitlement. `VALIDATED_DECLARATION` does not mean an executed model binding. No model API probes, automatic switching, config writes or permission bypass to fill the table. An existing independent reviewer may perform authorized work; if the required tier/reviewer is unavailable, BLOCKED applies to that specific gate, not self-review PASS. There is no need to assign all three roles to a small task.

<a id="ліміти-роботи"></a>
## Work limits

- Helper: one narrow task; up to 5 targeted search/tool steps and roughly 800 tokens of summary. After one refined retry, hand off findings and the blocker. These limits are a starting budget, not a criterion of truth.
- Coder: no more than two fixes of one failing check without new evidence/a hypothesis. Next, provide a short Escalation package; do not repeat the same expensive full gate without a reason.
- Reviewer: one initial pass and one pass over fixes; update the contract after a scope/decision change. Empty/null/timeout ≠ clean: one justified retry, then BLOCKED.
- Context: pass the contract, exact files/lines, diff and results; not the entire chat, repository archive or full graph dump. Handoff guideline ≤1500 tokens plus links; split a large scope before dispatch. Do not shorten evidence merely to fit the limit.
- After two cycles without progress or before compaction, record the journal and a specific next step. Do not guess money/quotas; there is no automatic cost routing.

<a id="crg-і-мінімальний-handoff"></a>
## CRG and minimal handoff

Before graph-assisted work: [CRG freshness/coverage](crg.md). For stale/missing/untracked scope, do not conclude “no callers”, “dead code”, “zero impact”; switch to `rg`, current files, language tools and tests. Model size/cost does not fix stale context.

In the existing plan/journal record: role + actual model/effort/host; goal/acceptance and boundaries; repo/root/branch/HEAD + dirty/untracked scope; authoritative instructions; CRG status and exact queries/limits; changed files; commands/results PASS/FAIL/BLOCKED/N/A; decision/blocker; next executor and one action. The reviewer receives these artifacts without the author's chat history. No new mandatory journal is needed.

<a id="докази-доступності"></a>
## Evidence of availability

Keep a secret-free catalog/session reference and date in the current task record. Config/cache may be considered only as the corresponding source type, without reading credentials or calling an old cache the current catalog. Discovery, entitlement, budget and invocation require separate evidence. This documentation update ran no model API or CLI probes and changed no defaults.
