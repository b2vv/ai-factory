---
title: "Feature lifecycle — route through existing skills"
reviewed: 2026-10-16
---

# From request to feature readiness

[Entry](../docs/legacy/ai-factory-plan-entry.md) · [Workflow](workflow.md) · [Roles and limits](models.md) · [CRG](crg.md)

This is navigation through the current process, not a new skill or orchestrator. First the user's request and applicable local instructions, then the selected SKILL.md. Preserve the current stack, architecture and plan/journal location. One artifact has one owner; do not create a second task tracker. If spec-flow is selected, it delegates its own stages: do not run the steps below a second time.

Portable onboarding and manifest: [onboarding.md](onboarding.md). Separate normative acceptance/contracts/ADRs from actual code/scripts under the [source rule](workflow.md#source-of-truth): code does not justify a contract violation.

A task branch and one writer in the main repository follow the [branch ownership contract](workflow.md#task-branches); runtime isolation is separate from Git isolation.

## Before code: explicit task readiness

Use the [pre-code checkpoint](pre-code-checkpoint.md) in the existing task/plan: scope/acceptance, proportional grilling and decisions, dependencies, scoped fresh impact or explicit file fallback, required independent planning gate, and READY/BLOCKED. Batch approval is not blanket READY. Small stays short; resume revalidates only the affected scope. Existing stronger local contracts remain. This is a protocol requirement, not automatic agent/CI enforcement.

Security adoption remains **PROPOSED**: [risk-triggered gates](../docs/guides/ai-assisted-onboarding.md#security-proposed) are added to current acceptance only for applicable features and agreed scope. Before execution — provenance/permissions; before acceptance — actual artifact/runtime proof on the final snapshot, scanner detection/clean/error fixtures and independent verdict. A copied-handler harness, exit 0 or merge does not replace required runtime evidence. This link installs no scanners, hooks/MCP or new tracker.

At startup, after a stage and after compaction/resume, restore the [specific pending next action](review-handoff.md#pending-next-action) in the current record: review_mode=existing_session or independent_subagent, writer/reviewer and contact route, prepared/sent/ACK/verdict, blocker/next check. Keep the assigned additional session; if absent, select independent_subagent without launching it merely by making that selection. Selected runtime unavailable → BLOCKED, not silent fallback. Execute only the applicable authorized action; a file is not delivery, and there is no DONE without the required final verdict. Do not repeat unchanged accepted stages.

Proposed security adoption route: [security adapter](../adapters/security/review.md) — security-impact → abuse invariants → actual code/config review → negative tests → final evidence/verdict in the existing task. It adds no discovered skill, reviewer, scanner or automatic execution. Required checks and final verdict must close before DONE; delivery states follow [review handoff](review-handoff.md#delivery-state).

## Startup: who performs critique, review and checks

After clear/new startup/resume: bound pending → brief task/checkpoint + “Continue?”, await the current response without task/review/send; unbound → silence. Consent applies only to the current session/task; permissions stay unchanged. Compaction of an already approved active task preserves continuity without another question; waiting for confirmation does not activate Stop-driven continuation.

Before work, record in the current primary record and show the user: goal → **new subagent / existing separate session / UNDETERMINED**, owner, exact session/agent reference if known, rationale for the current choice, who hands off the package, coordination of shared-resource checks. An explicit request takes precedence. If the mode selected under the contract lacks necessary information/permission, clarify only that before spawn/send; independent safe inventory/planning is allowed. Do not duplicate the reviewer or contact another session without authorization. An existing session ≠ completed review. Mark author checks separately.

Package and verdict follow [review handoff](review-handoff.md): task/session IDs, root/base/HEAD, scoped dirty/untracked hashes and diff, pinned acceptance/contracts, raw evidence/commands/exits, constraints. The reviewer is read-only and independently checks sources; tests with shared side effects require coordination. Findings: file:line + impact + verification. PASS is snapshot-bound; after changes, use proportional final-delta review. Missing response/evidence → NOT_TESTED/BLOCKED. Small retains one primary record, without a second tracker.

## Route selection

- **Small:** clear local scope → short acceptance → necessary context → one completed slice → appropriate checks → local independent review → brief report/next state. For small, one primary task record holds scope/acceptance, plan, append-only progress and outcome; separate independent review and raw evidence only as required by gates. Do not duplicate this in four documents. The plan may be in the existing task or message if the repository permits; do not automatically migrate existing tasks. No mandatory new directory, ADR, grilling or fan-out.
- **Full:** uncertain behavior, cross-module change, data/migration, authorization, external contract or complex UI → research → spec/acceptance/plan → required ADR and independent planning gate → implementation → checks → independent review → fixes → report/QA. Local process first; spec-flow only if selected and compatible with it.
- **Partly configured project:** [repo-bootstrap](../skills/utils/repo-bootstrap/SKILL.md), Codex `$repo-bootstrap`, Claude `/repo-bootstrap`, check-only. Result: gaps and a minimal proposal. Bootstrap commands being present does not authorize installation or configuration rewriting.

Roles: [Helper, Coder, Escalation/reviewer](models.md). Helper gathers evidence read-only; Coder owns authorized changes and artifacts; the reviewer works in an independent fresh context. Model candidates do not mean verified runtime access; Claude binding remains **UNBOUND** until separately checked. The human owner makes product decisions and designated local QA/landing decisions.

## How to invoke

Pairs below are **Codex CLI / Claude Code**. First check discovery and the exact linked SKILL.md; Codex also has `/skills`. A symlink or file on disk does not prove discovery. If local and global names collide, explicitly state the path and read the needed file; this is an instruction fallback, not proof of a successful slash command. Do not invent MCP/Agent APIs; the actual schema and authorized mechanisms determine execution.

Run the selected skill with its own gates, not just its name in the journal. `cto-research` may write a briefing, `spec-flow` may create workflow artifacts, `ship-report` may duplicate a report to available Obsidian; these are not Helper read-only actions or automatic authorization for external writing. If only local action is needed, use the current local contract and honestly call it a local report, not full execution of another skill.

## Stages

### 1. Scope and acceptance

- **Input / when:** request and current task; always, with depth based on risk.
- **Skills:** for substantial uncertainty, [grilling](../skills/plan/grilling/SKILL.md) — `$grilling` / `/grilling`; for a behavioral feature, [acceptance-spec](../skills/plan/acceptance-spec/SKILL.md) — `$acceptance-spec` / `/acceptance-spec`. Short local criteria suffice for an obvious edit.
- **Owner:** Coder formulates; the user resolves unknown product questions.
- **Result:** boundaries and non-goals; observable happy/boundary/failure scenarios, verification method; reason a group does not apply. Do not invent requirements from implementation.
- **Gate → next:** behavior is sufficiently defined; if grilling is selected, its confirmation of shared understanding is required before action. Next 2; an unknown that changes the result means BLOCKED for the dependent part.

### 2. Research and context freshness

- **Input / when:** scope, root/branch/base/HEAD, dirty and untracked files; check currency each time, with deep research only for unknowns.
- **Skills:** [cto-research](../skills/plan/cto-research/SKILL.md) — `$cto-research` / `/cto-research`; [crg-explore-codebase](../skills/crg/crg-explore-codebase/SKILL.md) — `$crg-explore-codebase` / `/crg-explore-codebase` when the graph helps. For a bug, replace broad investigation with [crg-debug-issue](../skills/crg/crg-debug-issue/SKILL.md) — `$crg-debug-issue` / `/crg-debug-issue`.
- **Owner:** Helper gathers files/evidence; Coder writes the needed briefing in its existing location.
- **Result:** affected boundaries, implementation, ADRs, reuse, risks and unknowns with links.
- **Gate → next:** under the [CRG contract](crg.md), verify hashes/coverage, not only HEAD/time; untracked files are not guaranteed to be indexed. For a stale/missing graph, use file search and explicit evidence limits; zero impact, especially for Go, does not prove no impact. Refresh needs separate write authorization and writer coordination; this route does not start it automatically. Next 3 or small slice 6.

### 3. Spec and plan

- **Input / when:** acceptance and evidence; full route or a local requirement. Small uses a compact plan in the current artifact.
- **Skills:** [spec-flow](../skills/deliver/spec-flow/SKILL.md) — `$spec-flow` / `/spec-flow`, only as the selected orchestrator. It delegates acceptance-spec, [plan-critique](../skills/plan/plan-critique/SKILL.md) — `$plan-critique` / `/plan-critique`, [plan-defense](../skills/plan/plan-defense/SKILL.md) — `$plan-defense` / `/plan-defense`. Add individual lenses to the local process as needed.
- **Owner:** Coder/local plan owner; independent reviewer gives the gate verdict.
- **Result:** what/why, tasks with files, dependencies and acceptance IDs, checks, side effects, migration/rollback or justified N/A.
- **Gate → next:** local planning requirements; for spec-flow, GATE 1 and GATE 2 (critique + defense + constitution) are mandatory. plan-critique means all four independent lenses; one self-check is not its PASS. plan-defense covers invalid input, dependency failure, race/repeat, boundaries and rollback with evidence in the plan. Missing reviewer/mandatory manifest → BLOCKED for that process, not hidden bootstrap. Next 4/5/6 as applicable.

### 4. Conditional ADR

- **Input / when:** architectural decision, new dependency/boundary/convention, change to an accepted decision; under the local threshold, not for every feature.
- **Skills:** no separate ADR skill is needed; use the local template and rules. If no threshold exists, propose the [four-gate criteria](repo-evidence.md#adr-gates), do not silently impose them.
- **Owner:** author and decision reviewer/operator designated by the repository.
- **Result:** ADR in the repository with alternatives, consequences and status; plan/task links to it. Separate factual correction from decision supersession.
- **Gate → next:** required decision accepted under local rules; otherwise dependent implementation is BLOCKED. With no trigger, N/A with a short reason. Next 5 or 6.

### 5. UI/design

- **Input / when:** changed screen/control/scenario, reference and local system. UI copy is also assessed: length/localization, wrapping, overflow, zoom, accessible name, open/active states. Text-only does not automatically mean design N/A; proof scope is proportional to impact. Without relevant UI impact — N/A with a reason.
- **Skills:** local design skill first; if needed [design-pass](../skills/design-pass/SKILL.md) — `$design-pass` / `/design-pass`. For audit, [interface-review](../skills/interface-review/SKILL.md) — `$interface-review` / `/interface-review`; this is a mandatory final pass in selected design-pass.
- **Owner:** Coder; reviewer assesses gathered factual evidence.
- **Result:** composition/state plan, component reuse, desktop/mobile criteria, keyboard/focus, error/recovery, zoom/reflow and reduced motion where applicable.
- **Gate → next:** local constraints defined before code; implementation and browser proof complete through 6–7. Do not import a generic stack/theme/font. Without actual render/interaction the UI gate is BLOCKED; a build does not close it.

### 6. Implementation

- **Input / when:** agreed scope/plan, necessary decisions, acceptance; for authorized implementation.
- **Skills:** [tdd](../skills/arch/tdd/SKILL.md) — `$tdd` / `/tdd`, when TDD is selected or required by the process. For risky refactoring, [crg-refactor-safely](../skills/crg/crg-refactor-safely/SKILL.md) — `$crg-refactor-safely` / `/crg-refactor-safely`, only within authorized scope; the name grants no write-MCP permission.
- **Owner:** Coder, with agreed write boundaries between executors.
- **Result:** one completed vertical slice, behavioral tests and updated journal.
- **Gate → next:** global tdd requires seams agreed with the user before writing tests; do not ask again about what is already agreed. Its cycle is one red → minimal green at a time; refactoring belongs to review, not a mass batch of imagined tests up front. A local skill with the same name may have another contract — record the exact path. Next 7.

### 7. Checks and browser QA

- **Input / when:** current diff and acceptance; select the set using the [applicability matrix](onboarding.md#checks) and explicit local gates. Reducing a mandatory gate needs its owner's decision; small alone is not a waiver. RED→GREEN proves defect reproduction/fix; mutation separately introduces a controlled change and checks detection by tests, with its own evidence. Sandbox failure means BLOCKED or an explicitly authorized execution mechanism, not a universal command to run outside the sandbox.
- **Skills:** there is no separate universal test skill; use actual package scripts/Makefile/CI and local rules. UI — complete design-pass/interface-review if selected. For entity E2E/QA field findings use [entity-e2e-coverage](../skills/entity-e2e-coverage/SKILL.md) — `$entity-e2e-coverage` / `/entity-e2e-coverage`: baseline QA ID × field × surface/state before tests; separate persistence/view/edit/update assertions, without substituting edit for required view. Rules and local sources are in [testing-rules](../skills/entity-e2e-coverage/references/testing-rules.md). This supplements current acceptance/report, not a new pipeline. For scoped filters — matching/nonmatching for each claimed entity type × surface; for keyboard acceptance — simulated browser key with a UI effect, not submit dispatch. In design-pass, separately cover changed open/active/chips states. Preserve useful temporary regressions until equivalent transfer and a targeted permanent-suite run under testing-rules.
- **Owner:** Coder runs authorized commands; a separate human QA role where the repository requires it.
- **Result:** command/scenario, SHA+dirty scope, exit/verdict, evidence; for UI, actually inspected frames with viewport and performed interactions, repeated after fixes.
- **Gate → next:** all mandatory applicable checks PASS. FAIL → 6; unavailable execution/unauthorized side effect → BLOCKED with the exact required step. Do not substitute a green overall status for skipped CI/E2E. Next 8.

### 8. Independent review

- **Input / when:** pinned diff/base/HEAD, relevant untracked files, contract and evidence; before readiness under the local gate, mandatory for a risky feature.
- **Skills:** local review first. If global [code-review](../skills/arch/code-review/SKILL.md) — `$code-review` / `/code-review` — is selected, two independent axes: Standards and Spec. [crg-review-changes](../skills/crg/crg-review-changes/SKILL.md) — `$crg-review-changes` / `/crg-review-changes` may provide impact context, not an independent verdict by itself.
- **Applicability:** for changes to abstractions, responsibilities, dependencies or duplication (including test helpers), explicitly assess [pattern-architecture-review](../skills/pattern-architecture-review/SKILL.md) — `$pattern-architecture-review` / `/pattern-architecture-review`. In the current plan/report record a short `applied` with an evidence link or `N/A` with a reason; ordinary docs/typo edits without such a change do not need this pass. Local review is not a full equivalent of specialized lenses. Preserve local precedence; combine the required assessment with independent review of the same pinned diff or add only missing lenses as a separate supplement, without repeating already confirmed checks/cycles.
- **Owner:** independent reviewer in a fresh context; the author provides sources, not self-review as a replacement.
- **Result:** raw findings with file:line, evidence, confidence and blocking status; separate verdict for the required axes.
- **Gate → next:** no open blocking findings; missing/empty reviewer → BLOCKED, not clean review. Do not invent a spec; mark absence skipped/BLOCKED depending on the contract. Next 9 if findings, otherwise 10.

### 9. Fixes and repeated gate

- **Input / when:** findings; only when present.
- **Skills:** [receiving-code-review](../skills/arch/receiving-code-review/SKILL.md) — `$receiving-code-review` / `/receiving-code-review`.
- **Owner:** Coder verifies and fixes; reviewer checks closure.
- **Result:** each finding → fix+verification or evidenced disagreement/accepted owner decision; no unconditional execution of advice.
- **Gate → next:** first clarify unclear related findings under the skill contract. Repeat affected 7–8 on the new diff. Under the [limits](models.md): no more than two fruitless fixes of one check without new evidence; reviewer initial + one fixes pass; null — one retry. Then escalation/BLOCKED, not automatic PASS. Scope change returns to 1–3 through the contract owner. Closed → 10.

### 10. Documentation, handoff and readiness for landing

- **Input / when:** verified diff or honest blocker; session completion/pause.
- **Skills:** local report; when scope fits, [ship-report](../skills/ship/ship-report/SKILL.md) — `$ship-report` / `/ship-report`. Additional [handoff](../skills/ship/handoff/SKILL.md) — `$handoff` / `/handoff` only on explicit request: it creates a temporary file outside the repo, not a replacement for the durable journal; Claude has `disable-model-invocation: true`.
- **Owner:** Coder maintains the report; local owner/operator/QA accepts the next state.
- **Result:** what changed, acceptance verdicts, actual checks, open risks/blockers, decisions/ADRs, root/branch/SHA/dirty, next action and owner under the [handoff contract](workflow.md#handoff). Do not invent an acceptance table afterward as though it had been agreed beforehand.
- **Gate → next:** name ready for review/QA/landing precisely. This is not permission to commit, push, merge or deploy. Pending human QA is not done; moving/archiving only under local procedure. After landing/post-deploy, checks run only under a separate applicable request.

## Adaptation to three repositories

| Repository | What to preserve | Special gates |
|---|---|---|
| Cassiopeia | work/README, local UI/ADRs and existing tasks | `qa-test` before merge; a separate human tester, then merge/deploy and archive. Review and UI fit do not replace QA. Do not use an old conflicting direct-archive instruction to bypass the new gate; show the owner a conflict affecting the task. |
| Cargo | `work/rules/task-workflow.md`: plan owner, worker journal, read-only reviewer, operator | Local review (`.claude/skills/review/SKILL.md`), `$review` / `/review` only if that exact skill is discovered; otherwise the exact file. One pass without fan-out by default. QA convention (`work/qa/README.md`): tasks → qa after merge → archive after QA. The old route without QA does not close this gate. |
| Courses | work/tasks.md, current phase plans/reports and independent review briefs | Preserve the Go modular monolith and TanStack Start/Rsbuild/React Aria. spec-flow only opt-in, without a second task system. Pending user QA does not become done. Heavy commands follow the conditions below. |

**Courses:** Makefile `make check` (line 165) and `make e2e-local` (106) include `e2e-reset`: stopping compose and deleting postgres/redis/media volumes, including dev data of the same compose project (107–128). `drain-queue` (151–156) deletes media/asr queue keys and requires an exclusive heavy-gate session. `check-generated` (159–164) generates files first. This is not a read-only smoke test. Before running, current explicit authorization with understanding of data loss, a verified compose project and absence of competing writers are required; without these the required gate is BLOCKED. Do not bypass a mandatory gate with a smaller command or call that command the full check. In Cassiopeia also inspect pretest:E2E side effects before running; in Cargo skipped E2E does not confirm browser QA.

## Resuming from the middle

0. An identical handoff with unchanged inputs does not reopen a completed task: verify status and return the existing result. Do not attribute repetition to automation without evidence.
1. Read the existing task/plan/journal, latest handoff and raw review. Find the owner and exact latest gate; do not restart the entire route.
2. Check checkout/root/branch/base/HEAD, staged/unstaged/untracked files and changes since the evidence. Leave foreign changes untouched; agree write boundaries.
3. Mark invalidated gates. Contract changed → 1–3; fix only → 6–9; handoff only → 10. Stale graph → fallback 2, without unauthorized rebuild.
4. Record one next action, responsible role and completion criterion. Preserve applicable previous evidence; after code changes rerun affected checks.

**PASS** means an applicable gate actually performed with evidence. **FAIL** means performed, criterion violated. **BLOCKED** means a required gate cannot be performed because of a specific dependency/access/decision. **N/A** means the criterion does not apply, with a clear reason; missing browser, reviewer or permission for a destructive test is not N/A. Other independent authorized steps may continue, but the dependent landing gate remains open.

This document does not establish that the feature, skills, runtime models or gates have already been verified. Current capability status is maintained in [status.md](status.md#capabilities); a real pilot requires a specific task.

## Targeted constraint lens

Use [selective constraints and evaluation](constraint-adoption.md) for suspected quality-floor weakening, task-boundary/resume evidence and final snapshot drift. Reuse the existing primary record and reviewer; live behavior remains NOT_RUN until explicitly authorized trials.
