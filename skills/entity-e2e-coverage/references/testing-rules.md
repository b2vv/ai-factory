
# Entity testing rules

Checked against local sources on 2026-10-17. This is a narrow reference: read the general rules and only your repository-specific section; reread the applicable original before running anything. The current local contract takes precedence over practices imported from another repository. Commands in sources are not authorization to run them. No external manuals were used.


## General invariants of this skill

- **Observable behavior, not internal state.** Assertions must distinguish correct from incorrect user outcomes; an open page/toast does not prove data correctness. Unit tests check a seam, E2E checks the required user path. Sources: [acceptance-spec §1–2](../../plan/acceptance-spec/SKILL.md), [tdd: What a good test is / Anti-patterns](../../arch/tdd/SKILL.md). Do not start the entire TDD process merely because of this link.
- **Independent expectation.** Preserve QA IDs and field-level expected values from QA/spec/fixture in the baseline; use a literal/known-good example or agreed transform, not a repetition of the implementation algorithm. Source: [tdd: Tautological](../../arch/tdd/SKILL.md). Reconcile all scoped QA IDs with the original source; existing tests are not a complete requirements inventory.
- **Correct surface and state.** Create persistence, created read-only view, edit prefill, update persistence and updated/reloaded view have separate assertions where applicable. This is the user's new targeted contract, recorded in [SKILL.md](../SKILL.md), not a claim that every repository already had this rule. API/DB evidence can supplement persistence but does not prove a UI label/format. An absent inapplicable surface is N/A with a reason; an unavailable required surface is BLOCKED.
- **Synchronize with the required result.** Wait for the specific state/completion of the relevant save and data display, not an arbitrary sleep or an adjacent signal. A bounded retry assertion must fail if the expected state is absent. Do not hide a race by increasing the timeout. Basis: Cargo ADR-0008; its strict requirement to prove a wait with a red test is local, not an automatic obligation for every other repository.
- **Data and independence.** Use a unique fixture identity per run, explicit prerequisites, creation through authorized means and cleanup only of entities created by this test. Do not depend on accidental test order or other people's data. Shared auth/seed setup may be a local contract: do not replace it with new logins “for isolation”. Sources: Cassiopeia ADR-0071 and Cargo FIXTURES below. No authorized environment means BLOCKED mutations; do not switch to production.
- **Risk-based negative scenarios.** For a changed contract, check applicable invalid input, permissions, empty/null, save failure/retry and preservation of unchanged fields. Do not add every possible scenario to every change. Explain missing groups; source: [acceptance-spec §1](../../plan/acceptance-spec/SKILL.md).
- **Do not silently weaken a gate.** Skip/xfail/did-not-run, snapshot updates, assertion replacement, QA row removal or expected changes require visible analysis. Changing product acceptance is the owner's decision, not an adaptation to a bug. Sources: [ship-report §2](../../ship/ship-report/SKILL.md), Cargo FIXTURES “did not run” below. A snapshot is a reviewed expectation, not automatic new truth after a failure.
- **Execution evidence.** An actual run, revision/diff, entity/fixture, environment and specific assertions/artifacts are required. A test plan, successful build or unchecked screenshot does not close a row. Sources: [design-pass §5](../../design-pass/SKILL.md), [ship-report §2, §5](../../ship/ship-report/SKILL.md). The validator checks metadata; the reviewer checks evidence truthfulness.


## Scoped checks and completion

- **Filters only within scope:** separate positive matching and negative nonmatching assertions for every declared entity type × list surface. PASS for trucks does not prove trailers, even with a shared component. Separate controls/URL/API from actual list contents. For AND, Clear, reload, chip removal and no-results, check the exact acceptance outcome; disappearance of one fixture row does not itself prove an empty list. Do not add filters to ordinary CRUD.
- **Keyboard only when acceptance requires it:** send the required key through browser input to the actual focused control and check the expected UI effect. Unit dispatch of submit/callback does not replace Enter. Call automation “simulated browser key”, not physical manual QA. Record the key, input method and effect; claim manual QA only after actual manual observation.
- **Temporary regressions:** do not remove useful acceptance/regression specs until scenarios move into a permanent maintained suite, assertion/entity/state equivalence is reconciled and that suite's targeted run succeeds. Preserve the mapping of old and new scenarios in the current report. This does not authorize deleting others' files, committing or pushing.
- **PASS precision:** reconcile the claim with actually executed assertions, entity types, surfaces/states and final revision/diff. Summary, plan checklist and evidence must agree. Mark incomplete work PARTIAL or BLOCKED with a reason; out of scope is N/A with a source and reason. Old PASS does not carry over to a new UI delta. Do not repeat a completed task solely because of an identical handoff with unchanged inputs; check existing status. The repetition's origin remains unknown until there is evidence of its trigger.

## Cassiopeia

Canonical sources:

- docs/agent/22-testing-strategy.md, §22.0–22.5: unit/Storybook/E2E boundaries, live save semantics, local selector/session patterns. Read the relevant section; do not carry historical numbers into a new report.
- ADR-0071: choose the applicable session pattern; in a shared storageState scenario, do not add your own login that could revoke another session. Dependencies are for genuine data dependencies, not merely a preferred order.
- work/README.md: human QA is separate from code review; qa-test does not equal archive.

Practical implications: after create, wait for the corresponding POST response; obtain the created entity's identity through the local helper/contract. Sequential edit may involve multiple write commands; the first successful response does not prove save completion. This is synchronization only: separate UI view assertions are then required. For a stateful component probe, a no-op onChange does not prove selection persistence (§22.1). Pretest/reset has side effects: check before running.

## Cargo

- ADR-0008: a wait observes the variable that determines readiness; locally, failure without the wait/with a broken condition must be demonstrated. A mock instead of a live rights-read changes what the evidence proves.
- ADR-0014: fast/unit tests do not prove browser behavior; backend generation and test environment must match the run. Its two-environment requirement applies to the local E2E gate; do not call one targeted reproduction a full gate. Live telemetry scenarios have their own dependencies and coordination; do not run them for an arbitrary entity form.
- tests/FIXTURES.md: local/testing fixtures, seed separated from destructive rebuild; visual snapshots depend on writers finishing. `did not run` means unknown, not PASS. Obtain the required role/fixture here; do not copy credential examples into the report.
- work/qa/README.md: tasks → qa after merge → archive after QA; this differs from Cassiopeia.

## Courses

- docs/development/testing.md: ordered gates; Go public seams, Rstest and Playwright with Compose, disposable PostgreSQL for integration. Missing Docker does not become skip-success. Do not run migration-down against the developer DB. Recovery tests restore local services in finally; this is a specialized scoped scenario, not a prerequisite for every entity test.
- Makefile, `e2e-local`, `e2e-reset`, `drain-queue`, `check-generated`, `check`: `make check` and `make e2e-local` include deleting postgres/redis/media volumes of the same compose project, including development data. Drain deletes queue keys and requires an exclusive session. `check-generated` writes generated files. Current authorization with an understanding of these consequences and coordination are required; this skill does not run them automatically.

Do not copy Cassiopeia's shared-session rules or Cargo's two test environments into Courses. A full gate, a targeted regression and a manual check provide different scopes of evidence; name the actual scope.


## Anti-patterns (4-field; shared template + cross-cutting rules in `ai-factory/reference-anti-patterns.md`)

- **Rewriting expected to fit actual.** How-not-to: changing the expected value/snapshot to match what the UI/API
  returned. Consequence: the test certifies the bug. How-to: take expectations from the spec/QA/an independent
  fixture; a defect means FAIL, not an updated expectation. Exceptions: none — changing a requirement needs the
  acceptance owner's decision. Verify: did the expected value come from the contract, or from the output under
  test?
- **Edit check standing in for the read-only view.** How-not-to: proving a field from the edit input instead of
  the read surface. Consequence: a view-rendering defect goes unseen. How-to: open the actual read surface and
  check visible values; prefill is a separate row. Exceptions: a list cell counts only for fields/states it
  actually displays. Verify: is the evidence from the read surface named in the row, or from a different mode?
- **Stale evidence carried over.** How-not-to: reusing a prior run's PASS after code changed. Consequence: the new
  revision has no real coverage. How-to: rerun affected assertions; record run id + revision + diff fingerprint.
  Exceptions: unchanged inputs may reuse evidence if the fingerprint matches. Verify: does the row's fingerprint
  equal the current diff? If not, it is NOT_TESTED at HEAD.
