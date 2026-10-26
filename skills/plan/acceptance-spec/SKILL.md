---
name: acceptance-spec
description: Describes a feature as observable product behavior — scenario, precondition, user action, expected result, verification method — before any code is written. Use when planning a feature and recording how it should work for the user, or on triggers "acceptance", "acceptance criteria", "test scenarios".
---


# acceptance-spec — a feature as observable behavior

A scenario table written **before** code and kept in the plan. Unit tests verify
the internal implementation; this table records what is visible **from outside** — making
“tested” a fact rather than a judgment.

**Observable** is the key word. A row describes what can be observed externally:
on screen, in a response, in a file. Internal state, a private field, a function call do not belong here;
they belong at the unit level.


## 1. Collect scenarios

Take the plan (or spec) and list scenarios in three groups — **all three are mandatory**:

1. **Happy path** — what the feature exists for. Usually 1–3 rows.
2. **Boundaries** — zero elements, one, the maximum, duplicates, deepest nesting, longest text.
3. **Failures** — malformed input, unavailable dependency, repeated action, interrupted process.

Groups 2–3 overlap with `plan-defense` questions. This is not duplication: that checks
**whether the plan considered it**; this checks **exactly what the user experiences**.


## 2. Fill in the table

| # | Scenario | Precondition | User action | Expected observable result | Verification method |
|---|---|---|---|---|---|
| 1 | <short name> | <system state and data before the action> | <what the person does> | <what they see / what changed externally> | e2e `<file>` / unit `<file>` / manual |

Rules for filling it in:

- **The expected result is one observation**, phrased so that two people can agree
  whether it matched. “The list updates correctly” fails; “the list has 0 rows
  and displays the empty-state text” passes.
- **Verification method** names the specific level and, when the file already exists, its path.
  A “manual” row is allowed, but then it **stays in the report permanently** as a manual step.
- One row = one scenario. Split two expectations in one row into two rows.


## 3. Connect it to the work

- Put the table in the plan file (“Acceptance scenarios” section) — **before** splitting into tasks.
- Each implementation task references the row numbers it covers.
- Rows without an existing test become separate test-writing tasks — and under
  `tdd` those tests are written **first**.


## 4. Completion

The skill is complete when **all** of the following hold:

- [ ] All three scenario groups are represented; an absent group says “none, because <reason>”.
- [ ] Every row has an observable result — no “works correctly”.
- [ ] Every row has a verification level; state how many rows remain manual.
- [ ] The table is in the plan file, and every task knows which rows it covers.
