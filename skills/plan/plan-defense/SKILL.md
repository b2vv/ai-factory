---
name: plan-defense
description: Makes a plan defend itself against five fixed questions — malformed input, dependency failure, race and repeated invocation, empty and boundary data, rollback — with every answer pointing to a line in the plan. Use as the last gate before splitting into tasks or implementation, or on triggers "захист плану", "plan defense", "а що буде якщо" (Ukrainian phrases retained as compatibility aliases).
---


# plan-defense — five questions answered by a line in the plan

The last gate before execution. `plan-critique` looks for **what is wrong in the plan**;
this skill checks **what is missing from it** — against a fixed list.

A defense is accepted only as **a line in the plan**. An answer in chat closes nothing: the next
agent will read the plan, not this conversation. Every closed question therefore ends with a file edit.


## Questions

Run all five, in order. For each, ask whether the plan contains a place that answers it.

1. **Malformed input.** Data has the wrong shape or type, a missing field, or a field
   outside the expected range. Where does the plan say what happens and what the user sees?
2. **Dependency failure.** An external service, worker, WASM module, or network does not respond,
   returns an error, or responds slowly. Where does the plan say how the system degrades?
3. **Race and repeated invocation.** The user clicked twice, two tabs, a request overtook an earlier one,
   the same step ran twice. Where does the plan say why the result remains single?
4. **Empty and boundary data.** Zero elements, one element, the maximum, duplicates, deepest
   nesting. Where does the plan say what is displayed and what does not break?
5. **Rollback.** The change was shipped and caused harm. Where does the plan say how to return — and whether anything
   irreversible (data migration, external effect) cannot be undone by rollback?


## Answer format

One table, five rows, in the plan file:

| # | Question | Closed by line | Verdict |
|---|---|---|---|
| 1 | malformed input | `plan.md §4, step 2` | closed |
| 5 | rollback | — | **gap** |

A gap closes in one of two ways, both requiring a plan edit:

- **add** the missing behavior to the plan;
- **narrow the scope** with an explicit line “case X is out of scope because <reason>” — the question is then closed
  deliberately rather than forgotten.


## Completion

The skill is complete when **all** of the following hold:

- [ ] The five-row table is in the plan file.
- [ ] Every row has either a reference to a plan line or an explicit “out of scope because…”.
- [ ] State the number of remaining gaps. **Zero → gate green**, the plan moves into tasks.
      Any other number → gate red, naming the exact table row keeping it red.
