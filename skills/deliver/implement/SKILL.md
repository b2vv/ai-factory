---
name: implement
description: "Implements work from a specification or a set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Call the Skill tool with "tdd" where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, call the Skill tool with "code-review" to review the work.

Completion criteria come from this task's class in `ai-factory/feature-lifecycle.md` and `ai-factory/review-handoff.md`, applied as written: a Small task takes the Small path, a Full task the Full path. Done waits only on unresolved BLOCKERS; record non-blocking recommendations and close. Report your own review as a self-check, and an independent verdict only when an independent reviewer gave it.

Commit per the branch-ownership contract — committing is not the done signal.
