---
title: Subagent-orchestration — ledger + status protocol + brief-file handoff
---

<a id="-subagent-orchestration-ledger-4-статуси-brief-файли"></a>

# 🧩 Subagent-orchestration: ledger, 4 statuses, brief files

> A distillation of the **methodological core** of the `subagent-driven-development` skill (obra/superpowers) — **without installing the skill itself** (it duplicates the existing `implement` + orchestration model + `Workflow` tool). Only three reusable patterns missing from ad-hoc orchestration are included here: **durable ledger**, **escalation status protocol**, **brief-file handoff**. Source: `github.com/obra/superpowers/skills/subagent-driven-development`.
>
> A cross-project addition to: memory `feedback_agent_orchestration_model` (tech-lead orchestrator + role-fleet + per-wave summary/handoff), `feedback_wave_reports_convention`, `feedback_delegate_large_tasks`. For Claude Code, it layers onto the native `Workflow` tool (pipeline/parallel) with [a task branch and one writer](../ai-factory/workflow.md#task-branches); `Agent isolation:worktree` is not the default and requires an explicit instruction.

---

<a id="коли-застосовувати"></a>

## When to apply

You are executing a plan with **multiple independent tasks** through subagents in one session (controller + implementer-fleet), and need **reliable recovery after context compaction** + **controlled blocker escalation** instead of “silent retry”.

---

<a id="1-durable-ledger-progress-файл"></a>

## 1. Durable ledger (progress file)

One durable note that survives context compaction and session reset.

- **Location:** `<repo>/.superpowers/sdd/progress.md` (or any git-ignored path in the repo; for this stack, prefer `reports/<topic>/wave-NN/progress.md` to fit the existing wave-reports convention).
- **At startup** — read the ledger: **DO NOT** redispatch tasks marked complete; resume from the first unmarked task.
- **When you dispatch a task** — append a line **immediately**, without waiting for review:
  ```
  Task N: dispatched (model=<тір>)
  ```
  The implementer's tier is needed **before** completion — when choosing the reviewer's tier
  ([[multi-model-roles]] §3: “review by a different tier”). If compaction occurs between DONE and
  review dispatch, the answer is already in the ledger; it is not in the orchestrator's memory.
- **When the task passes review** — append a line:
  ```
  Task N: complete (commits <base7>..<head7>, review clean, model=<тір>, reviewer=<тір>)
  ```
  The `<тір>` placeholder means tier. Both tiers on one line make the rule verifiable after the fact, not only at the time.
- **After restoring a session** — trust **the ledger + `git log`**, not memory/a retelling.

> Connection to the stack: the `Workflow` tool has its own `resumeFromRunId` (a cache of agent() calls) — the ledger is needed for **manual** orchestration (Agent-tool in a loop) or as a human-readable journal over the Workflow journal.

---

<a id="2-статус-протокол-implementerа-4-коди--реакція-controllerа"></a>

## 2. Implementer status protocol (4 codes → controller response)

Each implementer finishes with **one of 4 statuses**; each triggers a specific response — **never ignore escalation or force the same model to retry without changes**.

| Status | Meaning | Controller response |
|---|---|---|
| **DONE** | Work completed | Assemble the review-package → dispatch the task-reviewer |
| **DONE_WITH_CONCERNS** | Completed, but the implementer has concerns | Read the concerns BEFORE proceeding. Correctness/scope concerns — resolve before review; observations (“the file is growing”) — record and proceed to review |
| **NEEDS_CONTEXT** | Required information was not provided | Add the missing context → redispatch |
| **BLOCKED** | Cannot complete | Assess the blocker. Do not ignore it or force the same retry without changes |

---

<a id="3-brief-file-handoff-артефакти-як-файли-не-інлайн-текст"></a>

## 3. Brief-file handoff (artifacts as files, not inline text)

To keep dispatch prompts thin and resilient to compaction, pass **file paths**, not pasted text.

**The dispatch prompt must contain:**
1. one line describing where this task fits in the project;
2. **the brief path**, introduced as “read this first — these are your requirements, with exact values verbatim”;
3. interfaces/decisions from previous tasks that the brief cannot know;
4. your resolution of any ambiguity you noticed in the brief;
5. the report-file path + report contract (what the implementer will write and where).

> For this stack: put brief/report files under `reports/<topic>/wave-NN/` (the existing convention). In the `Workflow` tool, the same is achieved with `schema` returns + files in the session-dir; for Agent-tool, use explicit paths.

---

<a id="антипатерни"></a>

## Antipatterns

- ❌ Keeping progress only in context → compaction = re-running completed tasks. Maintain a ledger.
- ❌ Pasting full requirements inline into dispatch → bloated controller context. Pass the brief path.
- ❌ Forcing a BLOCKED retry by the same agent without changed inputs → the same failure. Change the context or escalate to a human.
- ❌ Confusing this with installing a duplicate skill: this is a **pattern note**; `implement`/`Workflow` remain the primary orchestration tools.
