---
name: plan-critique
description: Critiques a completed plan through four independent lenses — AI-slop, logical gaps, unnecessary complexity, uncovered edge cases — and consolidates findings into blocking / non-blocking. Use as a gate after writing a plan or spec, before splitting into tasks, or on triggers "критика плану", "прожар план", "plan critique" (Ukrainian phrases retained as compatibility aliases).
---

<a id="plan-critique--чотири-лінзи-по-плану"></a>

# plan-critique — four lenses on a plan

The gate between “plan written” and “execute the plan”. It differs from `grilling`: `grilling` asks
**you**, while this skill reads **the plan** and returns findings.

**Lens** is the central concept: four independent readings of the same text, each blind to
the rest. One reading “for everything bad” yields one finding and a feeling of completion; four narrow
readings yield four different ones.

<a id="1-підготуй-матеріал"></a>

## 1. Prepare the material

Input: the plan file (`plan.md`, `spec.md`, task). Add the context without which the lenses are blind:
repository briefing (`cto-research`), repository standards, existing mechanisms the plan could reuse.

<a id="2-прожени-чотири-лінзи-паралельно"></a>

## 2. Run four lenses in parallel

Each lens is **a separate subagent with clean context**, seeing the plan and context but not
the other lenses' conclusions. (When the user enabled orchestration, use the same fan-out through
`Workflow`; behavior is identical.)

| Lens | What it looks for |
|---|---|
| **AI-slop** | plausible filler: invented abstractions for one call, ceremony without a user, steps restating the obvious, “for the future” without anyone requesting that future |
| **Logical gaps** | steps that do not follow from earlier ones: unstated prerequisites, state nobody establishes, wrong ordering, a gap between “we did X” and “therefore Y works” |
| **Unnecessary complexity** | the same result with fewer moves: a new mechanism where one exists (reuse-first), a layer without a second client, configuration for a single case |
| **Edge cases** | empty / boundary / duplicate data, repeated and concurrent invocation, dependency failure, partial application midway through a step |

Each finding returns in a fixed format:

```
[lens] <title>
where:   <plan section or line>
why:     <what specifically will break or cost extra>
action:  <change to the plan — not the code>
weight:  blocking | non-blocking
```

**Blocking** = this point in the plan leads to an incorrect result or rework.
**Non-blocking** = costs extra, but the result will be correct.

<a id="лінза-що-не-повернулась"></a>

### A lens that did not return

A subagent may fail due to infrastructure, be skipped, or return `null`. This is **not** “clean” —
it is a lens that did not run, and silence makes it look exactly like a clean result.

1. Count returned verdicts against launched lenses **numerically**: `4 launched / N returned`.
   State the discrepancy before consolidating findings.
2. One retry on another tier, with the same clean context.
3. Empty again → **gate red**, and the summary names the missing lens.

Tier and lens independence: `~/.agents/rules/multi-model-roles.md` §3. A fresh subagent is mandatory:
`fork` inherits the plan author's context and model, so it does not count as a lens.

<a id="3-зведи"></a>

## 3. Consolidate

- Collapse duplicates across lenses into one finding, retaining how many lenses saw it
  (a finding from two lenses carries more weight than two separate ones).
- Sort blocking first.
- Turn each blocking finding into a plan edit — and name the changed line.

<a id="4-завершення"></a>

## 4. Completion

The skill is complete when **all** of the following hold:

- [ ] State the `launched / returned` count. Handle discrepancies using “a lens that did not
      return”: either retry produced a verdict, or the gate is red with the lens named.
- [ ] Every returned lens supplied ≥1 finding or an explicit “clean, because <what exactly was checked>”.
- [ ] Every finding has a weight.
- [ ] Every blocking finding is either incorporated into the plan or recorded as deliberately accepted — with a reason.
- [ ] State the final count of open blocking findings (zero → plan ready for `plan-defense`).

## Clean critic input

Give the selected independent critic the exact artifact, accepted contract, scoped snapshot and raw supporting evidence. Keep the author's proposed verdict, persuasive summary and private reasoning out of the initial packet; preserve relevant factual constraints and raw prior findings. Classify findings as actionable, contract misunderstanding, accepted tradeoff or unsupported, with evidence for each disposition. This refines the existing four-lens/local reviewer route; it does not authorize duplicate reviewers, a different model, paid API fallback or an automatic review loop. Missing authorized execution remains BLOCKED.

Adaptation source: [doubt-driven-development](https://github.com/addyosmani/agent-skills/blob/aeac41d4d005999432bb7312f7ff06383a91d59d/skills/doubt-driven-development/SKILL.md), MIT; [license](LICENSE.addyosmani).
