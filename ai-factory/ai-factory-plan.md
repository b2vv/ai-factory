---
title: "AI factory — entry point and development plan"
date: 2026-08-25
reviewed: 2026-10-16
status: roadmap — not an automatic start of work
scope: global ~/.agents; cargotrans-ui and dg; QnA backend (openai-qna) and generic-ui practices
---

# AI factory: where to start

The goal is to take an agreed task from understanding and planning to a verified result while preserving decisions and context. This is navigation and a development plan: current repository instructions and the user's request determine the work. A link to this file alone does not authorize executing the entire queue, changing configuration or deploying the system.

<a id="start"></a>

To connect another repository, start with [onboarding.md](onboarding.md): read-only preflight, a local manifest, an additive adapter and routing verification. This is the single onboarding instruction; the other files below are references.

Before work, identify the [critique/review executor and handoff package](review-handoff.md): a new subagent or an existing separate session, owner/reference; if uncertain, ask before spawning/sending.

## Before code: explicit task readiness

Use the [pre-code checkpoint](pre-code-checkpoint.md) in the existing task/plan: scope/acceptance, proportional grilling and decisions, dependencies, scoped fresh impact or explicit file fallback, required independent planning gate, and READY/BLOCKED. Batch approval is not blanket READY. Small stays short; resume revalidates only the affected scope. Existing stronger local contracts remain. This is a protocol requirement, not automatic agent/CI enforcement.

A task branch and one writer in the main repository follow the [branch ownership contract](workflow.md#task-branches); runtime isolation is separate from Git isolation.

## Choose a route

| Situation | What to do |
|---|---|
| The project already has a workflow | Read local instructions/work protocol; use them without repeating bootstrap |
| The project is partly configured | repo-bootstrap in check mode only → show gaps and minimal changes → agree before writing |
| Small obvious change | Local rules, bounded scope and appropriate checks; the full pipeline only when needed |
| Significant or risky change | Local process; if absent, agree a route with a plan, acceptance, independent review and evidence |

The detailed [skill and ADR map](workflow.md#skill-map) names triggers, owners and outputs. Codex CLI: `$name` or `/skills`; Claude Code: `/name`. Before invoking, verify the exact file and tool availability; the same name does not guarantee the same skill.

## Navigation

| File | When to read |
|---|---|
| [status.md](status.md#capabilities) | What exists, what is integrated and what was actually verified; the single current status |
| [workflow.md](workflow.md#routing) | Process selection, ADR/skill routes, sources of truth, handoff, UI and checks |
| [feature-lifecycle.md](feature-lifecycle.md) | Practical small/full lifecycle: skills, owners, gates, resume and adaptation to three repositories |
| [models.md](models.md) | Helper / Coder / Escalation-reviewer: bindings, escalation, context budget and manual fallback |
| [crg.md](crg.md) | CRG: schema, freshness, coverage, local recovery and verification limits |
| [roadmap.md](roadmap.md#tasks) | E0–E5 tasks, acceptance criteria and next sequence; not a command list for immediate execution |
| [repo-evidence.md](repo-evidence.md#repo-evidence) | QnA/generic-ui sources and differences, examples, contradictions, local rules |
| [history.md](history.md#history) | Origin of the idea and old measurements; not current status |

## Handoff and completion

Pass the goal, scope, sources, revision/dirty state, decisions, checks, blockers and next step in the **existing** plan/journal — [short contract](workflow.md#handoff). A project ADR lives in the repository; Obsidian contains a link/overview, not a second original.

Every applicable check has PASS / FAIL / BLOCKED / N/A and evidence. A build does not prove UI quality; rendered inspection and interaction are required under the [UI criteria](workflow.md#ui). A skill's presence does not prove its use.

The next step is to choose one project, inspect its process read-only and propose minimal gaps; a real pilot starts under a separate request. This refactoring changed documentation only: skills, repositories, Shared and configurations were unchanged; no pilot/eval/CI/deploy was run.

Canonical directory: `~/.agents/ai-factory/`. The old `~/.agents/ai-factory-plan.md` is only a symlink to this file. Absolute navigation links here support opening through either path; subfiles link to each other relatively.

## Session size and explicit handoff

[Session-size helper](../docs/legacy/session-size.md): 4 MB preparation, 5 MB soft threshold, an atomic checkpoint and explicit ID for a new session. This is not a hard cap or automatic model launch.
