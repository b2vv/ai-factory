---
title: Model roles — independent context and adequate review capability
---

> **Historical English adaptation — authored derivative.** Historical source: an earlier private revision of this kit. Original SHA256: `908d20088fcc0c49a1316ee43e92d671448f2c9336ef287103b2df3cdc2a371f`. Source base: `2c0960885926075502a319a19eafbed901690dde`. The immutable source at this commit and hash remains the historical reference; the [current in-repository document](multi-model-roles.md) is an English adaptation. The current authored policy below supersedes the historical tier-separation matrix; the original source identity remains preserved, not a current model catalog or runtime proof.

# Model roles

Use the existing task record and local review gates. This is not an automatic model
router, a new tracker or permission to spawn paid/external services. Small work
needs only its applicable roles. See [bindings](../ai-factory/models.md).

## 0. Who reads this and when

The executor coordinating authorized reviewers reads this before dispatch. Record
role, actual host/model when known, selected reviewer, snapshot and required gates
in the existing record. Do not turn role separation into mandatory delegation of
all implementation or extra agents for a small task.

## 1. What is actually available

Use the supported catalog and capabilities of the current host/session, not fixed
historical Claude tier names or another executor's inventory. Model availability,
entitlement, budget and actual invocation are separate facts. Unknown stays unknown;
never infer an unknown author was Opus. Do not probe paid access, rewrite model
settings or bypass permissions to fill missing evidence.

A fresh reviewer must not inherit the author's conversation or private reasoning.
Use the host's supported clean-context mechanism, with a self-contained pinned
brief, accepted contracts and raw evidence. A fork that inherits authoring history
is not independent even if a different model is selected. Do not infer context
isolation from an API method name alone.

## 2. Role allocation

| Role | Selection requirement |
|---|---|
| Planning / architecture | Capability sufficient for the decision risk, dependencies and alternatives. |
| Research | Capability sufficient for source interpretation and uncertainty; read-only unless separately authorized. |
| Implementation | Capability sufficient for the authorized slice and checks. |
| Mechanics | A less costly available executor may handle truly deterministic work. A fixed answer format does not make a verdict mechanical. |
| Plan critique / defense / code review | Independent executor/context with capability sufficient for the artifact's complexity and risk; preserve local minimum model/effort requirements. |

### 2.1 When the preferred reviewer is unavailable

The same model/tier as the author is allowed in a fresh independent context.
Do not downgrade a reviewer merely to obtain a different tier. Preserve the local
reviewer capability floor and required evidence: if no adequate authorized reviewer
is available, the affected gate is BLOCKED with its owner and next step, not a
silent weaker substitution or author self-review. Report a justified alternate
selection and its limits; model price or name alone is not proof of adequacy.

### 2.2 Multiple lenses and cost

Keep the independent lenses required by the selected skill: plan-critique still
requires four separate clean-context lenses. They may use the same sufficiently
capable model. Do not merge them to save cost or send them each other's conclusions.
Cross-model/cross-vendor review is an optional additional perspective when useful,
available and authorized, not a prerequisite for independence or a replacement
for fresh context. Reduce irrelevant input and avoid duplicate runs; do not weaken
required review scope, capability or evidence to fit a budget.

## 3. Independence rule

- The **authoring executor** does not issue its own independent verdict. Distinct
  clean review context is mandatory; distinct model identity is not.
- Record known author/reviewer bindings at dispatch for traceability, not as a
  tier-inequality test. Unknown author tier does not force an assumed tier or an
  unnecessary model switch. The reviewer still needs the exact artifact and rules.
- Required lens count and separate verdicts remain unchanged. An absent, empty or
  failed reviewer is NOT_TESTED/BLOCKED, never a clean verdict. A bounded authorized
  retry may use the same or another adequate model in a clean context; report the
  actual launched/returned counts and unresolved gate.
- For fixes, the assigned independent reviewer may assess the final delta and
  affected criteria against the pinned prior verdict. Prior review findings do not
  make that reviewer the implementation author. If the reviewer actually authored
  the revised artifact/solution, use another independent reviewer for that scope.
  No blanket critic or model rotation is required. Retain raw findings and verify
  final snapshot freshness under [review handoff](../ai-factory/review-handoff.md).
- One available adequate tier can author and independently review in separate
  clean contexts. Do not label that fact alone an independence violation.
- Duplicate dispatch/delivery is handled by the existing ledger and handoff;
  changing the model is not deduplication. Do not redispatch completed work merely
  because a session resumed. Preserve unknown delivery until reconciled.
- An invalid review reopens the affected gate. Rerun with a proper independent,
  capable reviewer and preserve the old evidence/history; it does not automatically
  revert code, authorize git mutations or erase consequences of an earlier action.

## 4. Proportionality and evidence

Runtime checks and independent judgment are complementary. Green tests do not
prove reviewer independence or capability; a second model does not prove correctness.
Record the reviewed snapshot, sources, findings, checks/limits and actual verdict.
No role label or helper validation substitutes for the independent response.

## 5. Boundary cases

| Situation | Required result |
|---|---|
| Author and reviewer use Opus (or any same model) | Allowed only with separate clean context and adequate capability. |
| Different model receives authoring conversation | Not independent; prepare a clean review. |
| Unknown author model | Record unknown; do not assume Opus or rotate tiers. |
| Only a weaker-than-required reviewer is available | BLOCKED, not automatic downgrade. |
| Reviewer assesses author's fix to its finding | Final-delta review permitted; check affected criteria and freshness. |
| Reviewer wrote the replacement implementation | Another independent reviewer required for that scope. |
| Lens returns nothing | Missing verdict remains visible; bounded retry or BLOCKED. |

## Related

- [Model bindings](../ai-factory/models.md)
- [Review handoff](../ai-factory/review-handoff.md)
- [Orchestration ledger](subagent-orchestration-ledger.md)
