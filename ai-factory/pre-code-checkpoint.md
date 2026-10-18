# Pre-code checkpoint — one record per task, no parallel tracker

Before the first product mutation, the operator/coder checks this block in the existing task/plan/phase record. Batch or sprint approval approves the intended scope; it does not mark every task READY. A brief points to the checkpoint. The coder verifies it against current inputs before implementation. Record owner, route (small/full/resume), root/HEAD and a fingerprint or explicit inventory of relevant dirty/untracked files. READY means these prerequisites are met for this scope; it does not authorize commits, deployments or other effects.

| Required content | Evidence in the existing record |
|---|---|
| Scope and acceptance | Source/acceptance IDs, observable outcome, non-goals; unknown requirements are not inferred from existing code |
| Proportional grilling | Gaps, assumptions, alternatives, questions and answers/decisions with their source; explicitly distinguish owner decisions from author inference. For an obvious small fix, explain briefly why no further question is needed |
| Dependencies and writers | Required predecessor outputs and current readiness; shared files/resources, owner and order/slot when needed. A batch's approval is not evidence that a predecessor is done |
| Scoped impact | Checked entrypoints/callers/contracts and tests, concrete file:line or search/query evidence, coverage limits; root/HEAD and relevant dirty/untracked fingerprint |
| Planning review / defense | Applicability under local risk thresholds, chosen existing-session or subagent route, independent verdict/evidence when required, and unresolved findings. For full/risky plans apply the required independent planning gate and defense or an explicitly agreed equivalent; a post-code review is not a retroactive plan verdict |
| Readiness | READY or BLOCKED, owner, remaining required question/dependency/finding and affected scope. Unresolved required items cannot be READY; independent unaffected tasks need their own checkpoint |

**Tools are conditional; impact evidence is not.** Use a suitable available tool (CRG, ttsc or another authorized source) when it helps. Graphify is optional; never run all graph tools ritually. Before relying on graph results, verify root/revision, scope hashes, coverage and relevant untracked inputs; stale, unknown or null impact is not proof of safety. If unavailable, stale, disproportionate or unauthorized, use direct file/search analysis and state the reason, concrete checked callers/contracts and search limits. An empty caller result needs bounded search evidence, not just “none.” No implicit graph refresh, derived database migration or paid probe.

**Small:** the same content may fit a few sentences in one record. A sound local scope reason can make additional grilling/plan lenses N/A; existing stronger gates remain. Do not add four documents or invent questions to fill a template. **Resume:** cite the existing checkpoint, compare current scope/HEAD/dirty inputs, and revalidate affected questions/dependencies/impact/gates; preserve explicitly unaffected evidence. An unchanged finished handoff does not reopen work. Do not invent historical grilling or backfill PASS into old tasks.

The selected skill retains its contract: [grilling](../skills/plan/grilling/SKILL.md), [plan-critique](../skills/plan/plan-critique/SKILL.md), [plan-defense](../skills/plan/plan-defense/SKILL.md). A claim of `plan-critique` completion requires its four independent lenses; one author self-check is not that PASS. Use the currently authorized independent route; no implicit new reviewer, duplicate session or contact. Exact-file reading is an instruction fallback, not proof of native invocation. If a required independent gate is unavailable, mark that dependent scope BLOCKED. Local contracts can be stronger; this checkpoint does not waive queue grilling, human QA or product gates.

## Optional declaration validator

[precode.py](../runtime/checkpoint/precode.py) checks explicitly supplied JSON and a separately supplied current snapshot. [Example](../examples/checkpoint/record.json) and [snapshot](../examples/checkpoint/snapshot.json) are generic fixtures, not live proof. The human-readable block above is sufficient unless the local task explicitly chooses JSON; do not create a duplicate source of truth merely to use the helper.

```sh
python3 -B runtime/checkpoint/precode.py record /explicit/record.json /explicit/current-snapshot.json
python3 -B runtime/checkpoint/precode.py batch /explicit/batch.json /explicit/current-snapshots.json
python3 -B runtime/checkpoint/precode.py index --root /explicit/repository --index work/tasks/README.md --task-root work/tasks
```

The validator checks declaration consistency: missing impact, unresolved required questions/dependencies, stale snapshot declarations and missing independent evidence block READY. Batch validation returns each task's status. `index` is an opt-in directory-index check for Cargo-style task folders, not a universal phase/queue migration. It checks links/directory coverage, not semantic status truth.

**Enforcement limit:** neither prose nor this helper proves factual evidence, correct applicability, reviewer independence, native discovery or agent compliance. It never reads Git state, runs graphs, starts agents or changes configuration. The operator must collect/verify current evidence and invoke the check if selected. No CI/hook enforcement is installed by this release; fixtures validate the helper's behavior only.
