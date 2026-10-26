---
title: "Work routes, context handoff and checks"
reviewed: 2026-10-16
---

[Entry point](../docs/legacy/ai-factory-plan-entry.md) · [Status](status.md#capabilities) · [Routes](workflow.md#routing) · [Tasks](roadmap.md#tasks) · [Repository practices](repo-evidence.md#repo-evidence) · [History](history.md#history)

<a id="task-branches"></a>

## Task branch in the main repository

The normal task route is a separate task branch in the main repository. A worktree, separate clone or detached checkout is not created automatically; another route requires an explicit user instruction. This rule takes precedence over historical examples and the selected skill's defaults for Git isolation; local acceptance, architecture and required gates remain in place.

In the current task/plan, record the main repository root, task branch and base, current HEAD/index/dirty scope, one active writer and the ownership handoff procedure. Only one writer works in a shared working directory at a time; independent read-only research is allowed against a stable snapshot. Before changing branches, check ownership and tree state. Do not switch branches when dirty/staged/untracked WIP belongs to someone else or its ownership is unknown. Do not use stash/reset/clean/commit to clear the tree without separate permission. On conflict, stop dependent actions and agree on the order and boundaries of work; do not silently move to a worktree or clone. Do not interrupt another session's processes.

Runtime/test isolation is a separate contract: agreed ports, service/project identity, data volumes and a heavy-gate slot. It does not imply a Git worktree or permit a destructive reset/seed of shared data. Handoff transfers current branch ownership and snapshot; after a writer/branch change, verify only affected evidence. This rule does not itself initiate a branch, commit, push, deploy or tools.

<a id="routing"></a>

# Work routes, context handoff and checks

This is an agreed process selection scheme, not a new executable skill. Current repository instructions and the user's request determine actions. A project that is already configured does not need another bootstrap.

Practical [feature lifecycle navigation](feature-lifecycle.md) connects stages to existing skills, roles and gates; it does not add a second orchestrator and preserves local workflows.

## Before code: explicit task readiness

Use the [pre-code checkpoint](pre-code-checkpoint.md) in the existing task/plan: scope/acceptance, proportional grilling and decisions, dependencies, scoped fresh impact or explicit file fallback, required independent planning gate, and READY/BLOCKED. Batch approval is not blanket READY. Small stays short; resume revalidates only the affected scope. Existing stronger local contracts remain. This is a protocol requirement, not automatic agent/CI enforcement.

## Startup: who performs critique, review and checks

Before work, record in the current primary record and show the user: purpose → **new subagent / existing separate session / UNDETERMINED**, owner, exact session/agent reference if known, rationale for the current choice, who delivers the package, and coordination of shared-resource checks. An explicit instruction takes precedence. If the choice is not specified and cannot be unambiguously inferred from the current request, ask before spawning/sending; independent safe inventory/planning is allowed. Do not create a duplicate reviewer or contact another session without authorization. An existing session ≠ a completed review. Label authorial checks separately.

The package and verdict follow [review handoff](review-handoff.md): task/session IDs, root/base/HEAD, scoped dirty/untracked hashes and diff, pinned acceptance/contracts, raw evidence/commands/exits, constraints. The reviewer is read-only and verifies sources independently; tests with shared side effects require coordination. Findings: file:line + impact + verification. PASS is bound to a snapshot; after changes, perform a proportional final-delta review. Missing response/evidence → NOT_TESTED/BLOCKED. Small keeps one primary record, without a second tracker.

## Entering a project

| Situation | First step | Continuation |
|---|---|---|
| An existing workflow is in place | Read AGENTS.md/CLAUDE.md, the local work/README, task contract and relevant skills | Use them; add global lenses only for a specific gap, without a second pipeline |
| Repository setup is partial or unknown | repo-bootstrap in check mode; adapt the inventory to the actual stack and local contracts | A table of “present / partial / absent / N/A / not verified”, evidence and a minimal proposed diff; configuration changes after agreement |
| A small, obvious change | Bounded scope, applicable local rules and checks | Do not require a new work-folder, ADR or full fan-out without a local requirement/risk |
| A substantial, risky or cross-module change | The local process; if absent, propose an agreed sequence: research → plan/acceptance → critique/defense → implementation → review → report | Agree on scope, owners and criteria before execution; post-deploy only when applicable and requested |

<a id="skill-map"></a>

## Skill and ADR map

Before invocation, check discovery and availability. If local and global skills share a name, identify the exact selected path; do not rely on accidental collision resolution.

### Selecting an interview and architecture check

First read the relevant current sources; questions to the owner resolve unknown decisions,
rather than replace available technical research. Record the selected exact path, rationale, sources,
expected artifact and gate in the existing task record. Reading a file is not native invocation.

| Situation | Route | Output and gate |
|---|---|---|
| Unknown or stale facts | Bounded reading of docs/code | Source references and remaining questions; reading alone is not domain modeling |
| An interview without a domain model change | [grilling](../skills/plan/grilling/SKILL.md); [grill-me](../skills/plan/grill-me/SKILL.md) only when the wrapper is explicitly selected | One interview, decisions/frontier and confirmation of shared understanding before dependent actions |
| New terms or a domain model change | Explicitly selected [grill-with-docs](../skills/plan/grill-with-docs/SKILL.md): grilling + [domain-modeling](../skills/arch/domain-modeling/SKILL.md) | An actual glossary update for resolved terms; ADR under the selected contract, without repeated grilling |
| Structural architectural impact | [pattern-architecture-review](../skills/pattern-architecture-review/SKILL.md) when applicable | Boundaries, alternatives and findings with evidence; not a requirement to introduce a pattern |
| An obvious small change | The current small checkpoint | Justified N/A for unnecessary interview/architecture review; stronger local gates remain |
| Resume | The existing checkpoint and evidence | Recheck only changed inputs/decisions; unchanged verdicts remain valid within their scope |

`grill-me` and `grill-with-docs` prohibit implicit invocation; the table does not change their
SKILL/agent contracts or permit automatic execution. File presence does not prove discovery.
If reporting readiness/compliance counts, the denominator includes all applicable criteria, including
FAIL and NOT_RUN; the numerator includes only evidenced PASS. N/A has a separate explanation. A blocker overrides
any percentage; stale evidence is not PASS. There is no numerical cutoff: the percentage is only
informational and does not replace acceptance or independent review.

### Qualitative readiness: mandatory criteria and evidence

Owner-approved AF-13 policy (2026-10-22): an unresolved mandatory criterion blocks
the dependent step or completion of the relevant scope regardless of percentage. Do not add
an arbitrary threshold such as 80% or extend a blocker to independent tasks without a dependency.

In the current checkpoint, record for each criterion: ID, requirements or architecture,
mandatory/applicability with rationale, expected condition, evidence path/hash/date/scope,
PASS/FAIL/NOT_RUN/N/A and an explicit blocker. Criteria come from applicable contracts and
acceptance; do not invent them to produce a favorable result. Facts and owner decisions are separate;
architecture obligations are assessed only where applicable. N/A does not waive a mandatory
requirement without justified non-applicability under its contract. A stale or unrelated hash
means NOT_RUN for the current bytes, not PASS. An absent measurement is NOT_RUN, not 0%.

Informational ratio: evidenced PASS / all explicitly listed applicable criteria, including
FAIL and NOT_RUN. Report N/A separately with an explanation. With a zero denominator, show N/A, not 100%.
Even all PASS does not replace required independent review or another local gate.

| Synthetic example | Counts | Decision |
|---|---|---|
| Two current PASS, one mandatory NOT_RUN; UI criterion N/A for docs-only | 2/3 (66.7%); N/A: 1 with rationale | BLOCKED dependent step due to missing evidence |
| Nine PASS, one mandatory FAIL | 9/10 (90%) | BLOCKED; a high ratio does not close a finding |
| A former PASS has a stale hash; the second criterion is PASS | 1/2 (50%); stale → NOT_RUN | Check the changed scope; do not repeat unaffected work |
| Criteria are not yet defined or measured | NOT_RUN, ratio not calculated | First establish applicability/evidence |

This is a docs/checkpoint convention, not a dashboard, automatic metric gate or proof
of actual project readiness. The examples are synthetic, not product measurements.

| Trigger | Where to turn | Owner / expected result |
|---|---|---|
| Unknown setup state | [repo-bootstrap](../skills/utils/repo-bootstrap/SKILL.md), check only | The agent provides an inventory; the user approves necessary changes |
| Product understanding is needed / the briefing is stale | [cto-research](../skills/plan/cto-research/SKILL.md) | Update the existing briefing, not contractual instructions; base + dirty state + sources |
| The next work needs to be selected | [cto-agenda](../skills/plan/cto-agenda/SKILL.md) | A reasoned candidate; product decisions remain with the user |
| Substantial implementation without an appropriate local process | [spec-flow](../skills/deliver/spec-flow/SKILL.md); acceptance-spec, plan-critique, plan-defense at its stages | Agreed plan and criteria; GATE 2: critique + defense + constitution; independent verdict |
| Language review/testing questions in the current task | [Selective language references](../skills/arch/code-review/references/languages/index.md): TS, PHP, Python, Rust, Go; frameworks only for the actual stack | The existing TDD/review core stays unchanged; selected paths, applicability and versions go in the existing task record. For TS, the new reference explicitly states the historical boundary of the old Pocock rule; native activation NOT_TESTED |
| UI | [design-pass](../skills/design-pass/SKILL.md) and [UI criteria](#ui) | Actual rendering, interaction, fixes, rechecking |
| A new lasting decision / change to an old one | Local ADR rules; if absent, propose [four-gate criteria](repo-evidence.md#adr-gates) | The author prepares the rationale under the local workflow; the designated reviewer/operator accepts it |
| A fact in an existing ADR is stale | The local currency/supersession rule | Separate a fact from a decision change, verify code and links; do not mechanically create an ADR |
| Task completion | Local review/report; [ship-report](../skills/ship/ship-report/SKILL.md) if needed | Scenarios, verdict, evidence and limitations in the existing artifact |
| A requested post-deploy check | [post-deploy-check](../skills/ship/post-deploy-check/SKILL.md) | Build identity, key scenarios, additions to the same report |
| QnA / generic-ui | [Local routes and differences](repo-evidence.md#repo-skills) | Do not replace them with global spec-flow; a human reviewer may be the selected local executor |

<a id="source-of-truth"></a>

## Sources of truth

Separate normative and descriptive material. Acceptance and accepted contracts/ADRs define required behavior; code/scripts show the actual implementation and available commands. Code can disprove a stale descriptive note, but does not legitimize a bug or cancel acceptance. Record a conflict with both sources and its impact; the contract owner decides within the request's scope. A request to fix a bug according to an unambiguous accepted contract already permits restoring that rule; code deviation alone does not require new approval. A new decision is needed for conflicting/unclear rules or a proposed contract change; until then, the dependent part is BLOCKED and independent authorized work continues. The user's scope and current runtime permissions bound every route.

A project's architectural decision is stored in its repository, in the directory specified by its rules. Obsidian contains links and an overview, not a second editable ADR original. This is the organizational rule for this plan; show existing conflicts/duplicates to the owner first, without silently migrating them. Work/task/spec links to ADRs; a permanent ADR does not depend on an artifact that will be deleted. QnA additionally prohibits links to procedural work/design records — see the sources.

Repository instructions and the selected SKILL.md define current requirements; Shared and cheat sheets are references. Capability state is maintained only in [status.md](status.md#capabilities). The task queue is in [roadmap.md](roadmap.md#tasks), previous measurements in [history.md](history.md#history). A discrepancy between code and an accepted ADR requires analysis of the cause, not an automatic victory for either side.

<a id="handoff"></a>

## Minimal context handoff

Use the project's existing plan/journal/ledger. No new mandatory file is needed. Before handoff or session completion, add:

| Field | Sufficient content |
|---|---|
| Goal and scope | What must change, file/behavior boundaries, what is outside the task |
| Authoritative sources | Exact paths to instructions, plan, ADRs and selected skills; record owners |
| Tree state | Repository/checkout/branch, commit SHA, staged/unstaged/untracked state in scope; what has been done and by whom |
| Decisions | What was accepted and by whom, rejected alternatives and rationale; open questions separately |
| Checks | Command/scenario, revision or dirty state, result and evidence path; what was not run |
| Blockers | Specific reason, impact, required access/decision; no secrets |
| Next step | One specific action, executor and completion criterion |

The recipient first reads these artifacts and checks tree currency, rather than repeating all reconnaissance. A new reviewer receives the contract and evidence without the author's chat history; raw findings remain accessible. Parallel executors have separate journals and write boundaries. After a failure, read the journal first; no response is not success. When scope/decisions change, update the contract through its owner; when code changes after PASS, repeat affected checks.

### Three roles and CRG

For the current manual route, use [Helper / Coder / Escalation-reviewer](models.md): one role per necessary step, an explicit binding, bounded retries and independent review context. This is not an automatic router or permission for new paid access; local gates remain in effect.

CRG provides context candidates, not a verdict. Before trusting the graph, check [root/branch/revision, hashes and coverage](crg.md), including untracked files; after unsuccessful bounded recovery, work through files and deterministic checks. Build/test/browser QA is not replaced by a graph score or a model's opinion.

### Invocation and tool availability

- Codex CLI: `$назва` or selection via `/skills`; Claude Code: `/назва`. For example, `$design-pass` / `/design-pass`.
- `disable-model-invocation` is Claude metadata; do not transfer its semantics to another agent without verification. Harness commands, `Agent`, `Workflow`, MCP and specific models are not guaranteed.
- Before independent review, identify available tools and delegation rules. If there is no independent executor, mark the gate BLOCKED; the author's self-check does not replace it.
- Count checks launched and results received. A failure or empty response is not “clean”.

<a id="ui"></a>

## UI: readiness criteria

[design-pass](../skills/design-pass/SKILL.md): project rules and local design skill → tokens/components/themes/scenarios → reference if needed → plan → implementation → browser → fixes → rechecking. A particular project's stack, palette, fonts and constraints do not become global.

Check hierarchy, responsiveness, applicable states, keyboard/focus/contrast, reduced motion, zoom, and the main flow with error recovery. Supporting lenses: [frontend-design](../skills/ship/frontend-design/SKILL.md), [anti-slop-design](../skills/anti-slop-design/SKILL.md), [ux-review](../skills/ux-review/SKILL.md), [interface-review](../skills/interface-review/SKILL.md).

Report build, static analysis and tests separately from inspecting rendering and interaction. For each check: PASS / FAIL / BLOCKED / N/A, method and evidence; N/A needs a reason. A screenshot that was created but not inspected does not prove visual quality. Rechecking is required after a fix. An unfulfilled key gate means “implemented, verification incomplete”, not unconditional “done”.

## Integrating ADR checks into subsequent tasks

This is the agreed documentation direction; integration into a specific repository remains a separate task after its audit. No new global skill has been created.

1. Before bootstrap/implementation, find the current workflow, plan/review/commit owner, ADR directory, supersession rule and archive. For a partially configured repository, first show gaps and agree on minimal additions. Do not overlay two competing protocols.
2. During research/plan, record decision candidates: constraints, consumers, alternatives, rationale for the choice and verification. Do not mechanically create an ADR for every ticket. Take the ADR threshold from local rules; if absent, propose [four-gate criteria](repo-evidence.md#adr-gates) for approval.
3. Before implementation, verify that design/plan has the required local approval or an explicitly recorded override, and that completion criteria are testable. The worker receives a self-contained contract; the journal preserves questions and deviations. The local process determines who approves deviations.
4. During implementation, update facts in affected docs/ADRs alongside code. Classify a new decision, a factual correction and deferred work separately. After merge, check incoming ADRs for contradictions and number collisions; the local rule determines re-review scope.
5. The independent reviewer checks code, gates and documentation integrity, and lists decisions for promotion. The owner designated by the local process performs ADR codification and acceptance. Keep links in the correct direction: work/spec/task may link to an ADR; a permanent ADR must not depend on an artifact that will be deleted.
6. Before completion, check that every candidate has a disposition; rejected alternatives and consequences are clear; decisions are not duplicated; numbers and links are correct; contradictions with code are resolved; gate evidence names the command and revision/tree state; blocked items are not counted as PASS. UI still requires browser-check evidence under the [UI criteria](#ui); if the local contract assigns this to a human, the agent prepares a handoff and honestly leaves the result unverified until evidence arrives. Archive/landing follows only the specific project's rules and request.

Add these checks to E1.4/E1.5 and the E2/E3 assessment as **integration candidates after a repository audit**. The existing work protocol takes precedence over the desire to recreate a global pipeline. Implementing these additions, resolving local contradictions and testing a new workflow are separate subsequent tasks, not the result of this documentation pass.

## Session-size handoff (2026-10-17)

The [shared helper](../docs/legacy/session-size.md) counts bytes through stat of the exact transcript_path without reading the transcript. At 4 000 000 / 5 000 000 bytes, it writes a draft; the agent completes the pending operation and records sanitized goal/done/pending/evidence/constraints through checkpoint. Only a COMPLETE checkpoint can be handed off by explicit ID. The new session reads it after checking root/branch/HEAD/dirty metadata. Handoff is context, not permission. Do not replay side effects or resume the old large transcript. There is no automatic CLI launch; starting a new session belongs to the user. If transcript/state access is prohibited, report BLOCKED/UNKNOWN without bypassing permissions.

## Targeted constraint lens

Use [selective constraints and evaluation](constraint-adoption.md) for suspected quality-floor weakening, task-boundary/resume evidence and final snapshot drift. Reuse the existing primary record and reviewer; live behavior remains NOT_RUN until explicitly authorized trials.
