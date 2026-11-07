---
name: entity-e2e-coverage
description: "Plans and checks E2E coverage of entity fields and QA findings without substituting an edit check for a read-only view. Use for entity create/view/edit/update and scoped list-filter scenarios, their tests or coverage audits; not for general visual review."
---

# Entity E2E coverage

The goal is to preserve every required QA expectation and verify it on the correct surface. This is a narrow coverage contract, not a test runner or a guarantee of no bugs.


## Before testing

1. Read [testing-rules](references/testing-rules.md), including its **Anti-patterns** section, and the shared [reference anti-patterns](../../ai-factory/reference-anti-patterns.md) (4-field template + cross-cutting rules). Never rewrite an expected value to fit the actual output, and take expectations from the contract, not the output under test. Then: the general invariants and only the current repository's section; check the original local rules, scope, acceptance and all relevant QA findings. Locate the actual surfaces: read-only page, drawer, preview, list cell, edit form. One URL may have different modes. Do not invent a view page or expand the task to all CRUD.
2. In the existing plan/test artifact, create a matrix: **QA requirement ID + source → entity field → deterministic expected value/format/permitted transform → surface + state → action → assertion → evidence**. Separate the requirements baseline from results; reconcile the IDs with the original QA source, not just existing tests.
3. Take expectations from the spec/QA/an independent fixture. Not from the current UI or mechanically from the API response that this same test must verify. An ambiguous format needs a contract, not an assumption.


## Separate obligations

Each applicable obligation has its own row and assertion:

- **Create persistence:** the actual test entity was created and the required data saved; a success toast or local form state does not prove this. Check a reread after save completes, bypassing the client cache if necessary. API/DB can provide additional persistence evidence.
- **Read-only view after create:** open the actual read surface; check the visible values/formats of required fields, including data from the QA finding. An edit input, API/DB and a screenshot without checking the expectation do not replace this row.
- **Edit prefill:** open edit separately and check initial values, selected options and required unchanged fields. A read-only view does not prove correct prefill.
- **Save update:** change fields to distinct values that remain distinct under contractual normalization; check persistence, not just the entered text.
- **View after update/reload:** after save, separately check required changed and unchanged fields on the read surface and after reload/reopen according to the contract. Old create/view evidence does not cover the new state.

Not every row is needed for every task. An absent/inapplicable surface or an out-of-scope action is **N/A with a source and reason**. If the spec requires a view but access/implementation is missing, use **BLOCKED** (or FAIL for a proven defect), not N/A. A list cell can be a read surface only for fields/states it actually displays and that the contract accepts.

For required fields, distinguish label from ID, date-only from instant/timezone/locale, false from empty, null from an empty string, and a nested reference from its display label. Check a specified permitted transform explicitly; do not normalize arbitrarily and hide a defect. Choose fixture values that make the error visible.


## Conditional scenarios

If acceptance covers filters or a keyboard action, apply the [scoped rules](references/testing-rules.md#scoped-checks-and-completion): matching/nonmatching for every declared entity type × surface, and browser key input with the expected UI effect. Controls/URL/API do not replace list results; submit dispatch does not replace a key. Do not add these requirements to ordinary CRUD outside scope.


## Execution and completion

Use only test data in an authorized environment. Before a mutation, check current authorization and command side effects; clean up only your own fixtures. The skill does not authorize shared-data resets, deployment, installations or new MCPs. In particular, Courses `make check`/`make e2e-local` can delete development volumes: do not run them as an automatic prerequisite.

Row evidence: an actual run ID, tested revision **and diff fingerprint** (including relevant dirty/untracked files), test/assertion locator, artifact/trace or a manual record with the actually observed result. Record fixture/entity identity, environment and the implemented check; a plan or a written but unexecuted test is not PASS. After code changes, rerun affected assertions; do not silently carry over old evidence.

The report preserves every QA ID, field and required surface/state. PASS requires its own executed assertion; FAIL/BLOCKED leave the gate open. Skip/xfail are not PASS. Removing/weakening a row, changing a requirement, updating a snapshot or changing a test requires an explicit diff, reason and review under the local process; changing acceptance requires its owner's decision. Do not rewrite expected to fit actual. A fixed QA finding is closed by rerunning its specific scenario.

Before completion, reconcile the summary, plan checklist and evidence with the final revision/diff and actually checked entities/states/assertions. Incomplete means PARTIAL/BLOCKED; inapplicable means N/A with a reason. Keep useful temporary regression specs until migration, coverage reconciliation and a targeted run of the permanent suite; see [testing-rules](references/testing-rules.md#scoped-checks-and-completion). Do not redo a completed task because of an identical handoff with unchanged inputs; first check status and existing evidence. Do not attribute repetition to automation without evidence.

This matrix is a VIEW of the agreed acceptance criteria (field × surface × state), not a rival definition of them; it refines existing acceptance/report artifacts rather than duplicating them. [acceptance-spec](../plan/acceptance-spec/SKILL.md) defines behavior; this skill checks field × surface × state; [interface-review](../interface-review/SKILL.md) assesses UX/appearance and does not replace data assertions. Execute through the current runner or an authorized browser, without depending on another project's webdev stack.

When machine validation is needed, read the [format and examples](references/matrix.md) and use the [validator](scripts/validate_matrix.py). It checks baseline/report consistency and evidence metadata, **does not prove that the browser executed assertions**, and cannot find requirements omitted from the baseline. An independent reviewer checks sources and actual artifacts.
