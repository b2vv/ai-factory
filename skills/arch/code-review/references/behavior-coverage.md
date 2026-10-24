# Behavior coverage during review and TDD

Read this reference before assessing coverage for code changes or selecting tests
for changed behavior. Apply it to the pinned diff and agreed public seams; it does
not expand the review to all repository code or authorize writes to live source,
production data, shared services, installs, or new sessions.

## Mutate each changed behavioral construct

Enumerate every changed guard, filter clause, serializer and invariant in the
reviewed diff, including supporting conditions rather than only the headline
feature. Include deleted constructs: in the disposable final snapshot, independently
reintroduce the old restriction or behavior as an inverse mutation and check that
tests detect the regression. Record each location, expected observable behavior
and discriminating test.
Use the existing task/review evidence record; no separate framework is required.
For documentation-only changes with no such constructs, record N/A with a reason.

In an authorized disposable copy of the exact reviewed source and tests, establish
a passing unmutated baseline. Remove or meaningfully alter each construct one at
a time, run the relevant tests, and restore baseline bytes before the next mutation.
Keep tests unchanged during that comparison. Do not mutate the live working tree.
Coordinate one mutation runner so independent review axes do not race on fixtures.

Record the source snapshot, individual mutation diff, command, exit status,
actual failing test/assertion and raw output. A killed mutation requires a test
failure attributable to the changed behavior. Syntax/import/collection errors,
missing services, timeouts or other infrastructure failures are invalid/inconclusive
runs, not detection. Never invent failures or use aggregate failure counts as proof.

Zero attributable failures means no demonstrated discriminating coverage for that
mutation. Investigate and classify it as an actual coverage gap or an evidenced
behaviorally equivalent/redundant mutation before prescribing new tests. Require
the worker to close an actual gap with a behavior test at an agreed seam. Check
that the test reaches the path (for concurrency, that scheduling allows the race),
then rerun baseline and mutation after repair. For equivalent/redundant mutations,
record the evidence and have the reviewer accept the disposition; do not label
them killed or silently omit them. Missing tools, permissions or runnable baseline
leave the check BLOCKED/NOT_TESTED, not PASS.

## CI-skipped service tests need plain coverage

For each changed behavior, inspect test skip conditions and the actual applicable
CI job, service provisioning, variables, selection and results. A Mongo/live-service
test that skips in CI cannot be its sole coverage. Unknown CI execution remains
NOT_TESTED; a locally provisioned service is not evidence that CI runs the test.

When the applicable service test skips in CI and is the behavior's only coverage,
require a plain deterministic test, without that skip, exercising the same
production logic through an agreed seam and selected by CI. Independently specified
expected values must expose the behavior; do not duplicate implementation logic in
assertions. Keep the real service test as integration coverage. Evidenced real CI
execution of that test satisfies this particular gap requirement: cite the
job/configuration and execution evidence. Stronger local test requirements still apply.

A plain test proves only its stated logic scope. Mocks, fakes and in-memory adapters
do not prove real database/service integration, query semantics or concurrent
behavior. Do not weaken an existing required real integration check or replace its
claim with a mock result. When the behavior cannot be separated honestly, report
the missing CI integration coverage and blocker rather than claiming a plain test
proves it. Preserve existing seam agreements and stronger repository requirements.

## Reporting

Carry the construct inventory, per-mutation evidence and CI coverage gaps into the
existing review output. Keep Standards and Spec findings separate. Name any remaining
NOT_TESTED/BLOCKED behavior and required integration checks; a green local suite or
package fixture cannot erase them. Preserve existing approval, independent review,
read-only review and evidence requirements.
