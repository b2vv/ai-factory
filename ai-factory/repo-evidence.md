---
title: "ADR and workflow: lessons from local repository protocols"
reviewed: 2026-10-16
---

> **Generalized derivative.** Historical source: an earlier private revision of this kit. Original SHA256: `1dc7347146630f15d4b0fff6a3878b21f0787006494be0d26c96a49f3585116c`. Source base: `2c0960885926075502a319a19eafbed901690dde`. This public version keeps only the generic lessons; repository names, file/line attributions and project-specific examples were removed. It does not establish current policy, execution evidence, or activation.

[Entry point](../docs/legacy/ai-factory-plan-entry.md) · [Routes](workflow.md#routing) · [Repository practices](#repo-evidence)

<a id="repo-evidence"></a>

# ADR and workflow: lessons from local repository protocols

### 7.1 Sources and limits of the conclusion

The `work/` directories of two reference repositories with their own file-based work protocols were examined. The conclusions below are generic lessons, not a description of any particular repository. Reading a review/journal confirms that a verification record exists, not that the tests were rerun. Below, **rules**, **observed patterns**, and **proposals** are distinguished.

<a id="adr-gates"></a>

### 7.2 When an ADR is needed and when another record suffices

**Four-gate criteria (observed in both reference protocols):** a candidate must meet all four criteria — hard to reverse; the decision is not obvious without context; there is a real rejected alternative with a reason; the record changes the reader's/agent's future actions. This describes local contracts, not an already established global requirement for all repositories.

Practical candidate types:

- **Contract between consumers/repositories:** a change requires implementations to be coordinated, while a local refactor appears safe (for example, shared semantics with independent duplication rejected).
- **Non-obvious invariant with a real alternative:** for example, preserving an event history after a rewind instead of amending in place, with implications for several implementations.
- **Deletion-blocker:** “keep X until consumer Y migrates.” Name what is retained, what blocks deletion, and what will permit it. This is a candidate only if all four criteria are met.

**An ADR is not automatically required** for every task, TODO, deferred cleanup, obvious edit, or implementation recap. If even one criterion fails, put a short “why” in the owning document/comment or omit the record. Correcting a stale fact in an existing ADR is not a new decision; it can be a separate mandatory freshness check that does not repeat the four criteria. Changing the decision itself or the reason for rejecting an alternative requires a new decision, not a silent rewrite of the old one.

### 7.3 Who initiates stages and how artifacts relate

Two observed role layouts illustrate the range; neither is a global template:

| Question | Layout A (developer-led) | Layout B (reviewer-led) |
|---|---|---|
| Process authority | Principles document → `work/README.md` → local work skill | Constitution and specs; `work/README.md` is an optional execution protocol |
| Plan and implementation | Developer owns the plan and orchestrates; a fresh Worker implements and maintains the journal | Reviewer owns plan/review; a separate Worker owns code and journal; Operator transfers work between sessions |
| Critique | Design critic before the plan; plan critic when the plan specifies behavior; an obvious sequence of edits may not need one | An additional Critic is optional for complex/risky work, after Reviewer approval and before commit |
| ADR candidates | Reviewer compiles the promote list | Reviewer forms the promote-on-commit list; Operator transfers durable knowledge into specs/ADRs/wiki |
| Recording and acceptance | After approval, Developer requests codify; a Maintainer reads raw review/journal and accepts, clarifies, or rejects ADRs | Operator is responsible for promotion and commit; do not import a separate Maintainer role from another layout |
| Links | Plan names ticket/base/design; a permanent ADR has self-contained reasoning, without a dependency on work/design | Plan contains Constraints with links to specs/ADRs; knowledge spanning tasks moves into permanent docs |
| Archive | The work branch is frozen; work artifacts do not enter base when landing | The directory moves to `work/archive/<NNN>-<slug>/` together with additional artifacts |

**Important local difference:** a project may leave commit, branch, push, rebase or tag to the operator. This is not a reason to change global permissions, but a rule to read and follow in that repository. Archiving, deletion of superseded ADRs, and ephemeral design are also local policies, not automatic actions for other projects.

<a id="repo-skills"></a>

### 7.4 Which skills are actually connected

- A local work skill may orchestrate the local `work/README.md` rather than replace it (for example: design critique → plan critique → run → review → codify → land). Role prompts kept as versioned files in `.claude/agents/` are not global skill names; fresh contexts read these exact files, and the author does not rewrite the reviewer's prompt.
- Specific models and spawn mechanisms from a local description cannot be assumed available in another agent. If an agent does not discover the local work skill, read the file explicitly; renaming `/work` to `$work` does not prove discovery. Without an independent context, the corresponding gate remains BLOCKED.
- A file protocol may mention optional roles/modes whose executable SKILL.md files do not exist in the inspected locations. Do not declare them executed or installed.
- Prompt files linked from specs (for example, validate one spec against live code, analyze consistency across specs, pre-QA review) are invoked by an explicit request to read the file; frontmatter alone does not confirm a slash command.

Global `spec-flow`, `plan-critique`, or `design-pass` can be proposed as supporting lenses, but do not claim they are already integrated into a local process.

### 7.5 Observed patterns and discrepancies

- A plan can link ticket, base and design, and explain a different branch name as the operator's decision; a review can separate fact corrections in existing ADRs from the promote list for a new invariant. This proves an artifact relationship, not landing or a repeated gate run.
- A decision journal and an ADR are different things: a per-task record can hold a decision, with an ADR created only under the four gates.
- A task contract may assign browser/live verification and review to a human, without a reviewer agent. Do not mechanically apply the general work scheme over that contract; handing verification to a human does not prove it has been performed.
- A local ADR template can contradict itself (for example, recommending links to design while prohibiting them because design is deleted on landing). Do not transfer such a contradiction into a global template; raise it with the owner.
- **An example is not the current rule:** an old review may have verified uncommitted state while the current work skill requires committed state before review. Do not treat an old example as permission to bypass the current contract.

Practical routing and the agreed handoff are in [workflow.md](workflow.md#routing).
