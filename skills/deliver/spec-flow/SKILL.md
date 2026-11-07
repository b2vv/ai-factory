---
name: spec-flow
description: Takes a substantial feature through the SDD cycle — spec → gate → plan → gate → tasks → implement → verify — with durable repository artifacts; delegates gates, tests and review to specialist skills. Use for a new subsystem, new slice, public API change or cross-cutting change, or on triggers "spec-flow", "feature using SDD", "write a feature specification".
---


# spec-flow — a thin SDD orchestrator

The spec-kit method **without** the official tool. Does not rewrite existing skills — **orchestrates** them.

**Thin** is the key word: it delegates every role for which a skill exists; it owns only
sequence and gates. Performing a role inline here instead of delegating creates
duplication that will diverge from the original.

Source of truth: code + **repository manifest** (`.claude/standards.md`,
format: `~/.agents/rules/repo-standards-manifest.md`). The manifest supplies everything repository-specific:
threshold, placement, branches, artifacts home, constitution.


## 0. Read the manifest

First: `.claude/standards.md`. If absent, say so and assemble it (format in the rule above);
until it exists, the threshold and constitution below have no values, and this must be stated.

The **threshold** comes from the manifest (`## Pipeline threshold`, manifest section heading) — it is structural, not discretionary.
Below the threshold the cycle does not activate: use a lightweight inline plan; pipeline friction would not pay off.

## 1. Setup

1. Branch and PR target follow the manifest's `## Branches and PRs` (manifest section heading).
2. Artifacts home follows `## Artifacts` (manifest section heading): `spec.md`, `plan.md`, `tasks.md` go here.
3. **Live note** — plan immediately, decisions incrementally (flush early and often). The persistence channel
   and its fallback are described in the repository's `CLAUDE.local.md`; if unavailable, maintain the live note
   in the artifacts home as `_wip-<topic>.md` and warn the user.


## 2. specify → `spec.md` (WHAT / WHY)

Sections: **Problem** · **User scenarios** · **Acceptance criteria** · **Out of scope** ·
**Open questions**. Intent only — stack, files and architecture arrive at step 4.

Account for the linked research findings (`cto-research` briefing, if present in the task record), relevant ADRs (respect their status), and existing-code reuse opportunities when writing the spec. The planning gate reading the research later does NOT replace this: the spec author reads it too.


## 3. GATE 1 — shared understanding

Delegate `grilling` on `spec.md`. Move to the plan after user confirmation.
Record decisions in the live note, not just in chat.


## 4. plan → `plan.md` (HOW)

- **Placement** follows the manifest's `## Placement` (manifest section heading).
- **Reuse-first**: check the repository's reuse index (if present) and code graph. List what
  we **reuse**, what is **new**, and **why** existing options did not fit.
- **Side effects · migration plan · rollback** — three mandatory subsections. A plan without them
  does not pass GATE 2.
- Apply the manifest's **constitution** (`## Constitution`, manifest section heading).
- Acceptance scenarios: delegate `acceptance-spec`; the table goes in `plan.md` **before** tasks.
- `plan.md` **absorbs** the future report's plan section.


## 5. GATE 2 — critique and defense

Three checks, all mandatory (two delegated and one inline):

| What | Who | Red gate if |
|---|---|---|
| Plan critique | `plan-critique` | open blocking findings remain, or a lens did not return |
| Plan defense | `plan-defense` | the five-question table has an unclosed row |
| Constitution | inline, per manifest | any violation |

The plan verdict comes from **someone other than its author** — a fresh subagent with clean context
(`~/.agents/rules/multi-model-roles.md` §3). A red gate blocks progression to tasks.

## 6. tasks → `tasks.md` + `work/`

Each task: **atomic**, with explicit files, **verifiable** (a “done” criterion exists),
in dependency order, referencing the acceptance-table rows it covers.
Mark independent ones `[P]`.

**Tasks live in `work/`, not chat.** This repository's layout — directory names and where items move —
comes from the manifest's `## Artifacts` (manifest section heading). Do two things regardless of names:

- A task that **starts** changes state explicitly: either moves to an “in progress” directory or gets a status
  in its file if no separate directory exists. Otherwise “started” and “not started” are indistinguishable.
- A task that **closes** moves to the archive **as a pointer** (what was done, which PR/commit,
  where the result is) — not a copy or deletion. Deleting a task removes the decision trail.

If there are more than a few tasks or they run in parallel, maintain a durable ledger
(`~/.agents/rules/subagent-orchestration-ledger.md`).


## 7. implement → delegate `tdd`

Task by task, red-green-refactor. Update checkboxes in `tasks.md`. Decisions → live note;
each subagent writes its own separate working file under `~/.agents/AGENTS.md`; the coordinator consolidates results and links into the live note. Parallel subagents do not write to a shared file.


## 8. verify → delegate `code-review`

On the branch diff. The global skill takes its criteria from the manifest. Fix findings one at a time, each
with a test (`receiving-code-review`).


## 9. wrap → delegate `ship-report`

The report is a **delta**: what actually happened and how it differs from `plan.md`. Do not write a second plan
in the report; the plan already exists.

---


## Delegation — do NOT rewrite

| Role | Skill |
|---|---|
| Shared-understanding gate | `grilling` |
| Plan critique | `plan-critique` |
| Plan defense | `plan-defense` |
| Acceptance scenarios | `acceptance-spec` |
| Implement | `tdd` |
| Verify | `code-review` → `receiving-code-review` |
| Report | `ship-report` |

Skill unavailable → for a role that does not require independence, perform available work inline and **record in the live note** that delegation failed. For an independent gate, inline self-checking cannot replace review: engage an available independent reviewer under the role rules or mark the gate BLOCKED and do not proceed.
Silent substitution makes the cycle irreproducible: the next run will not know one gate differed.


## Completion

- [ ] Check the threshold against the manifest and state whether it triggered.
- [ ] `spec.md`, `plan.md`, `tasks.md` are in the artifacts home.
- [ ] Both gates passed through delegation; state each verdict and its reviewer.
- [ ] Each task covers named acceptance-table rows.
- [ ] A report exists and is a delta from the plan.
