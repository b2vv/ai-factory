---
name: ship-report
description: Writes the final feature report in six fixed sections — done, tested scenarios, non-obvious findings, screenshots, user-flow walkthrough, risks and limitations — as a delta from the plan. Use at feature or task completion, before deployment, when a report rather than a wall of text is needed, or on triggers "ship report", "feature report", "summarize the work".
---


# ship-report — the report people read instead of the diff

The feature's final artifact. Not a retelling of work, but the basis for a deployment decision.

**Delta** is the key word: the report explains how **actual results** differ from what
the plan promised. The plan is already written and sits nearby; restating it in the report creates a second copy
that will diverge. If it matched the plan, say that in one line and move on.


## Home

`plan.md` already lives in the repository's artifacts home (`.claude/standards.md` → `## Artifacts`, the manifest section heading).
Put the report **there too**, beside the plan, and duplicate it as a Report note in Obsidian if the channel is live.

**One report per feature.** Append Post-deploy to this same file (`post-deploy-check`),
not a new one — otherwise the feature's history scatters across files nobody reconnects.


## Six sections

The order is fixed. Fill a section without content with “not applicable because <reason>” —
do not delete it. An empty section is visible; a deleted one looks as though it was never needed.


### 1. What was done

Steps with files and results. Compress what matched the plan into one line referencing
the plan section. Expand only **deviations**: what was done differently and why.


### 2. Tested scenarios

**This is not prose.** Take the plan's `acceptance-spec` table and add two columns:
**actual result** and **verdict** (matched / differed / not checked).

A “not checked” row is allowed and valuable — it shows the boundary of verification. A row where
the expectation was silently rewritten to fit the actual result makes the whole table decorative.

If there is no table in the plan (the feature proceeded without `acceptance-spec`), say so explicitly and list what
you checked, rather than creating a retrospective table tailored to known results.


### 3. Non-obvious findings

What makes the report worth reading closely: discoveries made along the way that nobody expected —
a discrepancy between documentation and code, an unknown dependency, behavior at a boundary.
Every finding has an anchor (`path:line`, commit, test name).

If nothing non-obvious happened, say so. That is a normal result for a small feature
and suspicious for a large one.


### 4. Screenshots

For visible changes — before/after. For invisible ones (SDK, worker, schema) — “not applicable because the change
has no on-screen manifestation”.


### 5. User-flow walkthrough

What the person does, step by step, and sees at each step — exactly the path
a real user will take. One end-to-end walkthrough, not a list of checked functions.

State whether it was performed manually or by an e2e run, and exactly how.


### 6. Risks and limitations

What remains uncovered; where it may break; what was deliberately excluded from scope (with a reason). Debt created
by this feature is named here, not left in someone's head.

Read the review findings from the task record's review-handoff package (where `code-review` wrote them). Name any unresolved findings here. Per `ai-factory/review-handoff.md`, completion is blocked by unresolved BLOCKERS; non-blocking recommendations are recorded, not gating. Do not present the report as a completion verdict while a BLOCKER is unresolved.


## Completion

The skill is complete when **all** of the following hold:

- [ ] All six sections exist; none deleted, empty ones say “not applicable because…”.
- [ ] Every acceptance-table row has an actual result and a verdict; state the number of
      “not checked” rows.
- [ ] Section 1 is a delta: matches compressed into references, only deviations expanded.
- [ ] Every §3 finding has an anchor.
- [ ] The report lives in the artifacts home beside the plan; the Post-deploy section is left empty
      for the future `post-deploy-check`.
- [ ] §6 accounts for the review-handoff findings; any unresolved BLOCKER is named and the report
      does not claim completion over it.
