# Synthetic sprint batch — not a real approval or retrospective PASS

Use the existing batch/task records. This example names no product project and authorizes no execution.

| Task | Decision surface and dependency | Planning state | Readiness |
|---|---|---|---|
| A: wording correction | Existing behavior/contract unchanged; no shared writer | Small N/A with reason; exact plan and file impact recorded | May be READY only after current evidence is collected |
| B: new failure policy | Required owner question open; shares contract with C | Plan critic not yet able to accept | BLOCKED even if the sprint was approved |
| C: consumer update | Requires B's accepted contract; no independent permission to guess it | Dependency unresolved | BLOCKED |

If B changes the error contract, re-critique B and revalidate C's affected contract/test strategy. A does not inherit that invalidation when its scope and inputs are unchanged. If B only fixes spelling, record the unchanged decision surface, compare the plan delta, and bind retained evidence to the new plan identity without pretending a new independent critique ran. Open blockers never disappear because a header says ACCEPTED.

The accompanying JSON fixtures use synthetic identities to test declaration handling. Their expected statuses are test assertions, not historical evidence. Real runs record command, exit/status, exact HEAD plus scoped dirty/untracked evidence, and artifact references. Unrun checks are NOT_TESTED/BLOCKED with no invented exit code.

## Whole-to-slice example (synthetic, no execution claim)

The existing design record specifies a producer/consumer error contract. Task B
links that approved design revision, delivers the producer contract and excludes
later UI work. Task C consumes B's verified output, not merely its DONE label.
The cold-plan check asks whether a new implementer can identify the exact error
shape, caller behavior and permitted tests from those references. An unanswered
shape question blocks B and dependent C, not independent wording task A.

In each task's existing record, retain the current stage, applicable planning
lenses and raw verdict pointers. If the full plan-critique skill is selected, four
independent lenses must return; one missing response leaves that gate blocked.
Separate implementation-review axes remain separate. Even if producer and consumer
unit checks pass, combined acceptance is NOT_TESTED until an authorized check
exercises their shared error boundary. A result showing incompatible payloads is
FAIL, not a majority PASS. Once the required boundary evidence and verdicts are
verified, close only the agreed slice; later UI work remains excluded.

If the design changes the error shape after B was accepted, revalidate B's affected
evidence and C's plan before continuation. A wording-only edit retains applicable
evidence with explicit rebinding. None of these outcomes creates another task
index, copies the design, or authorizes a new worker or product operation.

### Final-review decision counterexamples

- A slice adds a dependency forbidden by an accepted ADR. Green unit tests do not
  close review: cite that decision and resolve the conflict through local rules.
- A rename leaves an existing ADR naming a deleted API. Record factual freshness
  as a required correction, not a new architecture decision.
- A new cross-consumer protocol meets the local decision threshold. Record its
  rationale/alternative and the local approval or codification owner; if drafts
  belong after review, do not invent a premature missing-draft finding.
- A typo-only slice has no relevant architecture impact. Record both existing-ADR
  applicability and new-material N/A reasons after checking the local sources;
  do not create a ceremonial ADR.
- A required decision source is unavailable. Report BLOCKED with owner, not N/A
  or “ADR checked”; the rest of the independently evidenced review can stand.
