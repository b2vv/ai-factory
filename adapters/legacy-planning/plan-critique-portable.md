---
name: plan-critique
description: Critiques a completed plan through four independent lenses — AI-slop, logical gaps, excess complexity, uncovered edge cases — and consolidates findings into blocking / non-blocking. Use as a gate after writing a plan or specification, before task breakdown, or on the triggers "критика плану", "прожар план", "plan critique" (the Ukrainian phrases are retained compatibility triggers).
---

Portable adaptation: use the [bundled lifecycle](../../docs/portable/feature-lifecycle.md) and [review routing](../../docs/portable/review-handoff.md). Local contracts and current user authorization govern writes and delegation. Named skills not linked here are optional external extensions, not installed dependencies.

# plan-critique — four lenses on a plan

The gate between “the plan is written” and “we execute the plan.” It differs from `grilling`: `grilling`
questions **you**, while this skill reads **the plan** and returns findings.

**Lens** is the central concept: four independent readings of the same text, each blind to
the others. One reading “for everything bad” yields one finding and a sense of completion; four narrow
readings yield four different ones.

## 1. Prepare the material

Input: a plan file (`plan.md`, `spec.md`, task). Plus context without which the lenses are blind:
the repo briefing (`cto-research`), repo standards, existing mechanisms the plan could reuse.

## 2. Run four lenses in parallel

Each lens is a **separate independent reviewer with a clean context through the agreed route**, seeing the plan and context but not
the conclusions of other lenses. (When the user enables orchestration, use the same fan-out through
`Workflow`; the behavior is identical.)

| Lens | What it looks for |
|---|---|
| **AI-slop** | plausible filler: invented abstractions for one call, ceremony without a user, steps restating the obvious, “for the future” without anyone requesting that future |
| **Logical gaps** | steps that do not follow from preceding ones: unstated prerequisites, state nobody sets, wrong order, a gap between “we did X” and “therefore Y works” |
| **Excess complexity** | the same outcome in fewer moves: a new mechanism where one exists (reuse-first), a layer without a second client, configuration for a single case |
| **Edge cases** | empty / boundary / duplicate data, repeated and concurrent invocation, dependency failure, partial application midway through a step |

Each finding returns in a fixed format:

```
[lens] <title>
where:   <plan section or line>
why:     <what specifically breaks or costs extra>
action:  <plan correction — not code>
weight:  blocking | non-blocking
```

**Blocking** = this part of the plan leads to a wrong result or rework.
**Non-blocking** = costs extra, but the result will be correct.

### A lens that did not return

A subagent may fail on infrastructure, be skipped or return `null`. This is **not** “clean” —
it is a lens that did not run, and silence makes it look exactly like a clean result.

1. Count returned verdicts against launched lenses **numerically**: `4 launched / N returned`.
   State the discrepancy before consolidating findings.
2. One justified retry in an authorized independent context; another tier only if available and authorized.
3. Still empty → **the gate is red**, and the summary names exactly which lens is missing.

Roles and availability: [models](../../docs/portable/models.md); route: [review handoff](../../docs/portable/review-handoff.md). Do not launch new subagents without an agreed route; existing separate contexts are acceptable. The author's context is not an independent lens.

## 3. Consolidate

- Collapse duplicates across lenses into one finding, preserving how many lenses saw it
  (a finding seen by two lenses weighs more than two separate ones).
- Sort blocking findings first.
- Turn each blocking finding into a plan correction — and name the changed line.

## 4. Completion

The skill is complete when **all** of these hold:

- [ ] State the `launched / returned` count. Handle a discrepancy under “a lens that did not
      return”: either a retry produced a verdict or the gate is red with the lens named.
- [ ] Each returned lens produced ≥1 finding or an explicit “clean, because <what exactly was checked>”.
- [ ] Every finding has a weight.
- [ ] Every blocking finding is either incorporated in the plan or recorded as consciously accepted, with a reason.
- [ ] State the final count: how many blocking findings remain open (zero → the plan is ready for `plan-defense`).
