---
name: step-back-review
description: Steps back from a task or subtask to judge it against the agreed parent plan and the right responsibility boundaries before recommending a change. Applies two lenses in one skill — parent-plan/downstream awareness and forest-level SOLID (responsibility ownership across modules). Use when reviewing whether a locally correct change still fits the overall plan, duplicates another task's responsibility, contradicts an agreed contract, or forces avoidable downstream rework; or to check that a simple task is not over-engineered for a hypothetical future. Not a separate "tree-solid" skill — SOLID here is the boundary lens of this one skill. Triggers: "step back", "step-back-review", "does this fit the plan", "responsibility boundary", "forest-level SOLID", "right owner".
---

# Step-back review

Review a task or subtask from far enough back to see its place in the agreed plan and whether
its responsibilities sit with the right owner. A change can be locally correct yet still
undermine the parent goal, duplicate another task's responsibility, contradict an agreed
contract, or make an already-planned next step harder. This skill produces a concise judgment
and the smallest sufficient action — it changes no code by itself.

This is **one skill with two lenses**:
- **Lens A — parent-plan and downstream awareness:** does the change fit the agreed goal,
  acceptance criteria, contracts, and the planned next steps?
- **Lens B — forest-level SOLID:** at the module/forest level, does each responsibility sit
  with the right owner, with boundaries and dependencies pointing the right way?

Forest-level SOLID is Lens B **of this skill**, not a separate skill. Do not split it into a
`tree-solid` (or similarly named) skill. It is the analytical lens applied to judge
responsibility boundaries across modules — tree-level, in-module pattern/SOLID analysis is a
different, existing concern (see `pattern-architecture-review`); do not duplicate it here.

This skill adds a review *lens*, not a new mandatory stage. Run it inside the existing
task-class review flow (feature-lifecycle + review-handoff) and write its result into the
review or task record that already exists. Do not create a parallel plan, a duplicate
acceptance list, or a new required document.


## When to use

- Reviewing a task/subtask that touches shared responsibilities, a contract, or a planned
  sequence of work.
- Deciding whether a locally reasonable solution is right in the context of the whole plan.
- Checking that a small task has not grown speculative abstractions for a hypothetical future.

Skip the full stepping-back when the change is self-contained and touches no shared
responsibility, contract, or downstream step — say so and do the ordinary local review.


## Procedure

### 1. Locate the task in the plan
Read the current task and its linked parent task or overall plan, if present. Identify the
agreed goal, acceptance criteria, constraints, relevant ADRs, and the existing implementation.
If no parent plan exists, review against the available task and evidence — do not require
creating a plan just to run this check.

**Done when:** you can state the agreed goal this task serves, or confirm none is recorded.

### 2. Map only the relevant neighbours
Follow only the preceding, parallel, and downstream tasks that bear on the decision. Determine
what this task consumes, what it must produce, and who owns each responsibility. Do not scan
the whole backlog or impose a full architecture review on a small change.

**Done when:** the task's inputs, outputs, and the owners of the touched responsibilities are
identified for the relevant neighbours only.

### 3. Apply both lenses
- **Lens A (plan/downstream):** does the proposed solution duplicate existing or planned work,
  put logic in the wrong owner, contradict an agreed contract, or make an agreed downstream step
  unnecessarily difficult?
- **Lens B (forest-level SOLID):** does each responsibility sit with a single, right owner
  (SRP across modules)? Can the behaviour be extended without editing unrelated owners (OCP)?
  Do substitutable collaborators honour their contract (LSP)? Are interfaces/consumers free of
  dependencies they do not use (ISP)? Do modules depend on agreed abstractions rather than on
  each other's internals, with the dependency pointing the agreed direction (DIP)?

Judge boundaries at the forest (module/owner) level, not line-by-line style.

**Done when:** every concern is a concrete conflict or a confirmation that the approach fits.

### 4. Separate confirmed from tentative; cite evidence
Distinguish confirmed dependencies and approved decisions from tentative roadmap ideas. Cite
the task, plan section, ADR, or code supporting each concern. A dependency on *future* work
does not by itself justify expanding the current task.

**Done when:** each concern cites its source, and speculative items are marked as such.

### 5. Recommend the smallest sufficient action
Choose the least that resolves the real conflict: keep the local solution, reuse or modify
existing code, clarify a boundary or handoff, or propose a change to the affected part of the
plan. Propose material changes to scope, acceptance criteria, ownership, or execution order for
approval — do not apply them silently.

**Done when:** the recommendation is the smallest action that fits the plan and boundaries.


## Guardrails

- Do not implement future tasks early, invent future requirements, or add abstractions merely
  because they might be useful later. Reject premature abstraction and keep the solution small
  when only speculative future needs justify it.
- A dependency on future work does not automatically justify expanding the current task.
- Do not silently change scope, acceptance criteria, task ownership, or agreed execution order.
  Propose material changes for approval.
- Do not scan the entire backlog or force a full architecture review on every small change.
  Follow only the links and dependencies relevant to the decision.
- Reuse existing task records and review outputs. Do not create a parallel plan, a duplicated
  acceptance list, or a new mandatory document.
- If missing information could change the recommendation, state the uncertainty and ask one
  focused question. Otherwise proceed within the known scope.


## Review output

Add a concise section to the **existing** review or task record (not a new document):

- The parent goal and the relevant dependency, where applicable.
- The concrete conflict found, or confirmation that the local approach fits.
- Supporting task / ADR / code references.
- The smallest recommended action and any approval needed.
- The contract or artifact the next task must receive.


## When to hand off to inspector-review

This skill judges a change against the plan and responsibility boundaries. When the work is
already implemented and the open question is whether it *actually landed in the project*, that is
a different job — the `inspector-review` skill. Hand off only when one of these concrete risks is
named:

- The work is implemented and claimed ready, but its real integration still needs checking.
- The change spans several components, or the path from implementation to installation and use.
- There is doubt that a local PASS means the whole task is done: the capability may be unwired,
  manual steps may remain, or only isolated tests were run.
- The owner explicitly asks for an independent look at finished work.

During conception or planning, keep the check here — do not hand off. Do not auto-run the
inspector on every minor change. When a named risk **and** permission to delegate review both
hold, run one clean inspector (fresh context, primary requirements and the exact diff, no
author conclusions). Otherwise, briefly propose a run with the specific reason, and wait. Re-run
only after relevant fixes or a direct owner request. This is a pointer, not a required gate.


## Behavioural expectations (self-check)

1. A locally correct change breaks an explicitly agreed downstream task → detect the conflict
   and propose a minimal correction.
2. Two parallel subtasks duplicate the same responsibility → identify the overlap and propose a
   clear single owner, without implementing unrelated work.
3. A simple subtask has only speculative future requirements → reject premature abstraction and
   keep the solution small.
4. No parent plan exists → work with the available task and evidence without inventing a
   mandatory planning stage.
