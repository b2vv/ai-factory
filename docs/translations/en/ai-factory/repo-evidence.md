---
title: "ADR and workflow: QnA and generic-ui sources"
reviewed: 2026-10-16
---

> **Historical English translation — authored derivative.** Original: [ai-factory/repo-evidence.md](../../../../ai-factory/repo-evidence.md). Original SHA256: `1dc7347146630f15d4b0fff6a3878b21f0787006494be0d26c96a49f3585116c`. Source base: `2c0960885926075502a319a19eafbed901690dde`. The sealed original remains unchanged; the in-repository historical document has a separately recorded local-project reference cleanup. Historical assertions, statuses, examples, and limitations are retained; this translation does not establish current policy, execution evidence, or activation. Original-language compatibility anchors and literal protocol tokens remain where required.

[Entry point](../../../legacy/ai-factory-plan-entry.md) · [Status](../../../../ai-factory/status.md#capabilities) · [Routes](../../../../ai-factory/workflow.md#routing) · [Tasks](../../../../ai-factory/roadmap.md#tasks) · [Repository practices](#repo-evidence) · [History](../../../../ai-factory/history.md#history)

<a id="repo-evidence"></a>

<a id="adr-і-workflow-джерела-qna-та-generic-ui"></a>
# ADR and workflow: QnA and generic-ui sources

<a id="71-джерела-й-межі-висновку"></a>
### 7.1 Sources and limits of the conclusion

The `work/` directories inside two repositories were examined. Source names and line numbers below are historical attributions; unavailable local-project link targets have been removed without claiming current access or revalidation:

- **QnA backend:** `openai-qna` — the actual directory name is `openai-qna`, not `qna-ai`; identified through README.md:1 and AGENTS.md:6.
- **generic-ui:** `generic-ui`.

In both, `CLAUDE.md` refers to `AGENTS.md`. Below, **rules**, **existing examples**, and **proposals** are distinguished. Reading a review/journal confirms that a verification record exists, not that this audit reran the tests. The repositories, their skills, and ADRs were not changed.

<a id="adr-gates"></a>

<a id="72-коли-потрібен-adr-а-коли-достатньо-іншого-запису"></a>
### 7.2 When an ADR is needed and when another record suffices

**Confirmed common rule in these two projects:** a candidate must meet all four criteria — hard to reverse; the decision is not obvious without context; there is a real rejected alternative with a reason; the record changes the reader's/agent's future actions. Sources: QnA PRINCIPLES.md:44, generic-ui constitution.md:89. This describes local contracts, not an already established global requirement for all repositories.

Practical candidates from the sources:

- **Contract between consumers/repositories:** a change requires implementations to be coordinated, while a local refactor appears safe. QnA example: ADR 0026:3 — shared citation replay fold semantics, with independent duplication rejected.
- **Non-obvious invariant with a real alternative:** QnA ADR 0032:3 — preserving Events after rewind, the amend-in-place alternative, and implications for several implementations.
- **Deletion-blocker:** “keep X until consumer Y migrates.” generic-ui explicitly requires naming what is retained, what blocks deletion, and what will permit it: constitution.md:105. This is a candidate only if all four criteria are met.

**An ADR is not automatically required** for every task, TODO, deferred cleanup, obvious edit, or implementation recap. If even one criterion fails, put a short “why” in the owning document/comment or omit the record. Correcting a stale fact in an existing ADR is not a new decision: in QnA this is a separate mandatory freshness check that does not repeat the four criteria (PRINCIPLES.md:116). Changing the decision itself or the reason for rejecting an alternative requires a new decision, not a silent rewrite of the old one.

<a id="73-хто-запускає-етапи-і-як-повязані-артефакти"></a>
### 7.3 Who initiates stages and how artifacts relate

| Question | QnA backend | generic-ui |
|---|---|---|
| Process authority | `PRINCIPLES.md` → `work/README.md` → local work skill | Constitution and specs; `work/README.md` is an optional execution protocol |
| Plan and implementation | Developer owns the plan and orchestrates; a fresh Worker implements and maintains the journal | Reviewer owns plan/review; a separate Worker owns code and journal; Operator transfers work between sessions |
| Critique | Design critic before the plan, based on design; plan critic when the plan specifies behavior; an obvious sequence of edits may not need one | An additional Critic is optional for complex/risky work, after Reviewer approval and before commit; this is a separate code-quality lens |
| ADR candidates | Reviewer compiles the promote list; absence of a future draft before codify is not itself a finding | Reviewer forms the promote-on-commit list; Operator transfers durable knowledge into specs/ADRs/wiki |
| Recording and acceptance | After approval, Developer requests codify; Maintainer reads raw review/journal and accepts, clarifies, or rejects ADRs | Operator is responsible for promotion and commit; do not automatically import QnA's separate Maintainer role here |
| Links | Plan names ticket/base/design; journal and review preserve progress. A permanent ADR has self-contained reasoning, without a dependency on work/design | Plan contains Constraints with links to specs/ADRs; work retains the audit trail; knowledge spanning tasks moves into permanent docs |
| Archive | The work branch is frozen; work artifacts do not enter base when landing | The directory moves to `work/archive/<NNN>-<slug>/` together with additional artifacts |

Table sources: QnA work/README.md:9, work-reviewer.md:32, design/README.md:12, adr-format.md:67; generic-ui work/README.md:3, sections Roles, Lifecycle, Files, and Optional role — Critic.

**Important local difference:** both processes leave commit to the operator; QnA also assigns branch/push/rebase/tag to the operator. This is not a reason to change global permissions, but a rule to read and follow when working in these particular repositories. Archiving, deletion of superseded ADRs, and ephemeral design are also local policies, not automatic actions for other projects.

<a id="repo-skills"></a>

<a id="74-які-скіли-справді-підключені"></a>
### 7.4 Which skills are actually connected

**QnA — existing local file** .claude/skills/work/SKILL.md:1. It follows `work/README.md` rather than replacing it:

`design critic as required by the design document → work plan-critique according to plan content → work run → work review → work codify → work land`.

`plan-critic`, `work-worker`, `work-reviewer`, `design-critic` are versioned prompt files in `.claude/agents/`, not global skill names. Fresh contexts read these exact files; the author does not rewrite their reviewer's prompt. Specific Claude models and spawn mechanisms from the local description cannot be assumed available in Codex. If another agent does not discover the local work skill, read the file explicitly; merely renaming `/work` to `$work` does not prove discovery. Without an independent context, the corresponding gate remains BLOCKED.

**generic-ui — a file protocol without a mandatory skill runner.** `role-reviewer`, `role-worker`, `role-critic`, `mode-careful`, `mode-ralph` are mentioned as optional in work/README.md:11, but their executable SKILL.md files were not confirmed in the inspected local/global locations. Do not declare them executed or installed.

There are, however, prompt skills directly connected through specs/README.md:22:

- validate-spec.md — one spec against live code;
- analyze-specs.md — consistency across multiple specs; before a bundle or after constitution/structure changes; after its fixes, repeat validate for the affected spec;
- pre-qa-review.md — pre-QA review, QA handoff, and analysis of results after QA.

Invoke them with an explicit request to read the file; frontmatter alone does not confirm a slash command. Global `spec-flow`, `plan-critique`, or `design-pass` can be proposed here as supporting lenses, but do not claim they are already automatically integrated into these local processes.

<a id="75-приклади-й-виявлені-розбіжності"></a>
### 7.5 Examples and identified discrepancies

- **QnA, observed example:** work/038-message-feedback/plan.md:3 links ticket, base, and design, and explicitly explains a different branch name as the operator's decision. review.md:119 separates fact corrections in ADR 0002/0013 from the promote list:158 for the new rewind invariant; ADR 0032 exists on disk. This proves an artifact relationship, not landing or a repeated gate run.
- **generic-ui, existing examples:** work/002-keda-scaling/review.md:27 records ADR 0020 alongside spec updates, while lines 43–45 record verification of the four gates and supersede links. work/003-jobs-heartbeat-research/plan.md:84 leaves the decision in a per-job record/comments and creates an ADR only under the four gates. This confirms that a decision journal and an ADR are different things.
- **generic-ui, local adaptation:** work/004-navigate-message-feedback/plan.md:9 uses design as the plan without duplication; line 35 requires amendment of ADR 0002, while lines 43–50 assign browser/live verification and review to a human, without a reviewer agent. Therefore, do not mechanically apply the general work scheme over the contract for a specific task. Handing verification to a human does not prove it has already been performed.
- **QnA, template contradiction:** adr-format.md:45 recommends ADR links to design, while lines 67–72 prohibit such links, and design is deleted on landing. Do not transfer this contradiction into a global template; raise it with the owner as a separate correction. The source was not changed in this audit.
- **An example is not the current rule:** the QnA work/038 review describes verification of HEAD with uncommitted changes (review.md:3), while the current work skill requires committed state before review (SKILL.md:59). The date/reason for this difference was not established; do not treat an old example as permission to bypass the current contract.

Practical routing and the agreed handoff are in [workflow.md](../../../../ai-factory/workflow.md#routing). Examples here do not automatically update current status.
