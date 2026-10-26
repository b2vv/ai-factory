> Optional retained portable profile; the full canonical plan is in `ai-factory/`. This profile does not replace original skill contracts or authorize automatic activation.


[Entry](../legacy/starter-readme.md) · [Workflow](workflow.md) · [CRG](crg.md)

# Helper / Coder / Escalation-reviewer

This is manual role allocation within the existing workflow, not an installed router or new pipeline. Small tasks do not need three agents. The local contract determines acceptance, gates, commit ownership and the need for independent review. Preserve the current stack and user changes.

| Role | Boundaries and result | Escalation |
|---|---|---|
| Helper | Fast, cheaper read-only search, file map, short summary with file:line; no source edits, final verdict or heavy checks | Ambiguous requirements/architecture, conflicting sources or missing evidence → Coder |
| Coder | Implement agreed scope, acceptance, appropriate deterministic checks; decision/change/result journal | High risk or two unsuccessful justified fixes → Escalation |
| Escalation / reviewer | Complex causes, cross-module contracts, auth/access/data/migrations/irreversibility; review in a new independent context | No independent executor or missing access/decision → BLOCKED + specific handoff |

Send high risk directly to Escalation, without requiring a failed cheap pass first. If Escalation authored the solution/code, the verdict needs another reviewer; self-review does not become independent through a new role name. A model does not replace compiler/lint/tests, browser interaction or human acceptance.

<a id="bindings-і-рівень-підтвердження"></a>
## Bindings and confirmation level

Determine bindings anew for the specific host/session, regardless of provider. A role name does not specify a model ID. Old cache snapshots and configured defaults are historical candidates, not the current catalog or entitlement. The Codex app/dot/other executor catalog does not transfer to local Codex CLI or Claude Code.

| Session inventory field | Required evidence / action when absent |
|---|---|
| Host, session, date, role | Name the specific CLI/app and session; do not infer them from the repo name |
| Available catalog and provenance | An already-available catalog for this specific host/session with a reference; otherwise obtain read-only inventory by a supported mechanism or leave UNBOUND |
| Candidate + effort | The candidate must be in this catalog; effort only from confirmed host capabilities, otherwise unresolved |
| Entitlement | Separately unknown / available / unavailable with evidence; catalog presence does not guarantee account access |
| Budget | Separately unknown / approved / denied; account for the current instruction, do not enable paid access |
| Actual binding | Only already-confirmed actual execution/session state; a configured candidate is not runtime proof |

For Helper, Coder, Escalation/reviewer, record candidate status (catalog unknown / unselected / missing / listed), entitlement, budget and a specific next step. Missing candidate → choose from the available same-host catalog; unknown entitlement → check access without a paid probe; unknown budget → owner decision before a costly run. An unconfirmed combination is **UNBOUND**. If the current model is already known, it may be recorded as the actual binding without assuming a cheaper tier; the Helper role alone does not reduce cost.

The [preflight schema](../onboarding-helper.md) validates only submitted inventory and session identity, not evidence authenticity or entitlement. `VALIDATED_DECLARATION` does not mean a model binding executed. No model API probes, automatic switching, config writes or permissions bypass to fill in the table. An existing independent reviewer may perform authorized work; if a required tier/reviewer is unavailable, that specific gate is BLOCKED, not self-review PASS. There is no need to assign all three roles to a small task.

<a id="ліміти-роботи"></a>
## Work limits

- Helper: one narrow task; up to 5 targeted search/tool steps and approximately 800 summary tokens. After one refined retry, hand over findings and the blocker. These limits are a starting budget, not a truth criterion.
- Coder: no more than two fixes of the same failed check without new evidence/hypothesis. Then hand over a short Escalation package; do not repeat the same expensive full gate without a reason.
- Reviewer: one initial pass and one pass over fixes; update the contract after scope/decision changes. Empty/null/timeout ≠ clean: one justified retry, then BLOCKED.
- Context: pass the contract, exact files/lines, diff and results, not the whole chat, repo archive or full graph dump. Handoff guideline ≤1500 tokens plus links; split a large scope before dispatch. Do not shorten evidence merely to fit the limit.
- After two cycles without progress or before compaction, record the journal and specific next step. Do not guess money/quotas; there is no automatic cost routing.

<a id="crg-і-мінімальний-handoff"></a>
## CRG and minimum handoff

Before graph-assisted work: [CRG freshness/coverage](crg.md). For stale/missing/untracked scope, do not conclude “no callers,” “dead code,” or “zero impact”; switch to `rg`, current files, language tools and tests. Model size/cost does not fix stale context.

In the existing plan/journal, record: role + actual model/effort/host; goal/acceptance and boundaries; repo/root/branch/HEAD + dirty/untracked scope; authoritative instructions; CRG status and exact queries/limits; changed files; commands/results PASS/FAIL/BLOCKED/N/A; decision/blocker; next executor and one action. The reviewer receives these artifacts without the author's chat history. No new mandatory journal is needed.

<a id="докази-доступності"></a>
## Availability evidence

Keep a secret-free catalog/session reference and date in the current task record. Config/cache may be considered only as the corresponding source type, without reading credentials or calling an old cache the current catalog. Discovery, entitlement, budget and invocation have separate evidence. This documentation update performed no model API or CLI probes and changed no defaults.
