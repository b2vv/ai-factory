---
name: acceptance-spec
description: Describes a feature as observable product behavior — scenario, precondition, user action, expected result, verification method — before code is written. Use when planning a feature and recording how it should work for the user, or on the triggers "acceptance", "приймальні критерії", "сценарії тестування" (the Ukrainian phrases are retained compatibility triggers).
---

Portable adaptation: use the [bundled lifecycle](../../docs/portable/feature-lifecycle.md) and [review routing](../../docs/portable/review-handoff.md). Local contracts and current user authorization govern writes and delegation. Named skills not linked here are optional external extensions, not installed dependencies.

# acceptance-spec — a feature as observable behavior

A scenario table written **before** code and kept in the plan. Unit tests verify
the internal implementation; this table records what is visible **externally** — and makes
“tested” a fact rather than a judgment.

**Observable** is the key word. A table row describes what can be seen externally:
on screen, in a response, in a file. Internal state, a private field or a function call do not belong here;
they belong at the unit level.

## 1. Collect scenarios

Take the plan (or specification) and list scenarios in three groups — **all three are mandatory**:

1. **Happy path** — the reason the feature exists. Usually 1–3 rows.
2. **Boundaries** — zero items, one, maximum, duplicates, deepest nesting, longest text.
3. **Failures** — malformed input, unavailable dependency, repeated action, interrupted process.

Groups 2–3 overlap with `plan-defense` questions. This is not duplication: that checks
**whether the plan considered it**; this records **exactly how it appears to the user**.

## 2. Fill in the table

| # | Scenario | Precondition | User action | Expected observable result | Verification method |
|---|---|---|---|---|---|
| 1 | <short name> | <system state and data before the action> | <what the person does> | <what they see / what changed externally> | e2e `<file>` / unit `<file>` / manual |

Rules:

- **The expected result is one observation**, phrased so that two people agree
  whether it matches. “The list updates correctly” does not qualify; “the list has 0 rows
  and shows empty-state text” does.
- **Verification method** names the specific level and, when the file already exists, its path.
  A “manual” row is allowed, but then it **remains in the report permanently** as a manual step.
- One row = one scenario. Split two expectations in one row into two rows.

## 3. Link it to the work

- Put the table in the plan file (the “Acceptance scenarios” section) **before** task breakdown.
- Each implementation task references the row numbers it covers.
- Rows without an existing test become separate test-writing tasks — and under the
  local TDD contract (if applicable), those tests are written **first**. This package does not require a separate tdd skill.

## 4. Completion

The skill is complete when **all** of these hold:

- [ ] All three scenario groups are represented; an absent group says “none, because <reason>”.
- [ ] Every row has an observable result — no “works correctly”.
- [ ] Every row has a verification level; state the number of rows that remain manual.
- [ ] The table is in the plan file, and every task knows which rows it covers.
