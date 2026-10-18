# Synthetic sprint batch — not a real approval or retrospective PASS

Use the existing batch/task records. This example names no product project and authorizes no execution.

| Task | Decision surface and dependency | Planning state | Readiness |
|---|---|---|---|
| A: wording correction | Existing behavior/contract unchanged; no shared writer | Small N/A with reason; exact plan and file impact recorded | May be READY only after current evidence is collected |
| B: new failure policy | Required owner question open; shares contract with C | Plan critic not yet able to accept | BLOCKED even if the sprint was approved |
| C: consumer update | Requires B's accepted contract; no independent permission to guess it | Dependency unresolved | BLOCKED |

If B changes the error contract, re-critique B and revalidate C's affected contract/test strategy. A does not inherit that invalidation when its scope and inputs are unchanged. If B only fixes spelling, record the unchanged decision surface, compare the plan delta, and bind retained evidence to the new plan identity without pretending a new independent critique ran. Open blockers never disappear because a header says ACCEPTED.

The accompanying JSON fixtures use synthetic identities to test declaration handling. Their expected statuses are test assertions, not historical evidence. Real runs record command, exit/status, exact HEAD plus scoped dirty/untracked evidence, and artifact references. Unrun checks are NOT_TESTED/BLOCKED with no invented exit code.
