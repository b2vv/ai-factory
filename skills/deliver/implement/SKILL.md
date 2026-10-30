---
name: implement
description: "Implements work from a specification or a set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Call the Skill tool with "tdd" where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, call the Skill tool with "code-review" to review the work.

Completion follows the rules for THIS task's class as `ai-factory/feature-lifecycle.md` and `ai-factory/review-handoff.md` ALREADY state them — apply those existing requirements VERBATIM; do NOT add a new mandatory Small review or strengthen the Small path. Done is blocked only by unresolved BLOCKERS; non-blocking recommendations do not block done (record them). Do not present self-review as an independent PASS.

Commit per the branch-ownership contract — committing is not the done signal.
