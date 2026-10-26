---
name: plan-defense
description: Makes a plan defend itself against five fixed questions — malformed input, dependency failure, races and repeated invocation, empty and boundary data, rollback — where every answer must point to a plan line. Use as the last gate before task breakdown or implementation, or on the triggers "захист плану", "plan defense", "а що буде якщо" (the Ukrainian phrases are retained compatibility triggers).
---

Portable adaptation: use the [bundled lifecycle](../../docs/portable/feature-lifecycle.md) and [review routing](../../docs/portable/review-handoff.md). Local contracts and current user authorization govern writes and delegation. Named skills not linked here are optional external extensions, not installed dependencies.

# plan-defense — five questions the plan answers with a line

The last gate before execution. `plan-critique` looks for **what is wrong with the plan**;
this skill checks **what the plan is missing** — and the list of missing concerns is fixed.

A defense is accepted only through **a plan line**. A chat answer closes nothing: the next
agent will read the plan, not this conversation. Every closed question therefore ends with a file edit.

## Questions

Run all five, in order. For each: does the plan contain a place that answers it?

1. **Malformed input.** Data arrives with the wrong shape, wrong type, missing field, or a field
   outside its expected range. Where does the plan say what happens and what the user sees?
2. **Dependency failure.** An external service, worker, WASM module or network did not respond, returned
   an error or responded slowly. Where does the plan say how the system degrades?
3. **Race and repeated invocation.** The user clicked twice, two tabs, a request overtook its predecessor,
   the same step executed twice. Where does the plan say why the result remains singular?
4. **Empty and boundary data.** Zero items, one item, maximum, duplicates, deepest
   nesting. Where does the plan say what is shown and what does not break?
5. **Rollback.** The change was rolled out and caused harm. Where does the plan say how to return — and whether
   anything is irreversible (data migration, external effect) and will not be undone by rollback?

## Answer format

One table, five rows, in the plan file:

| # | Question | Closed by line | Verdict |
|---|---|---|---|
| 1 | malformed input | `plan.md §4, step 2` | closed |
| 5 | rollback | — | **gap** |

A gap is closed in one of two ways, both edits to the plan:

- **add** the missing behavior to the plan;
- **narrow scope** with an explicit line “case X is out of scope because <reason>” — the question is then closed
  consciously rather than forgotten.

## Completion

The skill is complete when **all** of these hold:

- [ ] The five-row table is in the plan file.
- [ ] Every row carries either a reference to a plan line or an explicit “out of scope because…”.
- [ ] State the number of remaining gaps. **Zero → the gate is green**, the plan moves to tasks.
      Any other number → the gate is red, and state exactly which table row holds it there.
