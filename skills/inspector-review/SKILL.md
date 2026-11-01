---
name: inspector-review
description: Independently inspects whether completed, "done"-claimed work actually delivered the required result and fits this project — not just that isolated tests or the author's report pass. Runs a single clean inspector (fresh context, no author history) against the primary task, authoritative requirements and a fixed commit/diff. Narrow by design — it does not replace step-back-review (plan/boundary lens) or code-review (standards). Use when implementation is claimed ready and real integration, delivery (commit→package→installed→used) or a suspected local-PASS gap needs an outside check, or when the owner asks for an independent look at finished work. Triggers: "inspector-review", "did this actually land", "is it really integrated", "independent check of finished work", "local PASS but is the task done".
---

# Inspector review

Answer one question: **is the required result implemented, and does it work as part of this
project — not only in isolated tests or the author's report?**

This is a narrow inspector for *finished* work. It is not a universal reviewer and does not
change code. It complements, and does not absorb:

- **step-back-review** — the plan/downstream and forest-level responsibility-boundary lens, used
  while a change is still being conceived or planned.
- **code-review** — repository standards and correctness of the diff.

Inspector-review starts where those leave off: the work is declared done, and the open doubt is
whether it *actually landed in the project*.


## When step-back-review hands off to inspector-review

Hand off only when a concrete risk below is named — not on every small change:

- The work is implemented and claimed ready, but its real integration still needs checking.
- The change spans several components, or the path from implementation to installation and use.
- There is doubt that a local PASS means the whole task is done: the capability may be unwired,
  manual steps may remain, or only isolated tests were run.
- The owner explicitly asks for an independent look at finished work.

During conception or planning, keep the check inside step-back-review — do not hand off. Do not
auto-run the inspector on every minor change. When a named risk **and** permission to delegate
review both hold, run one clean inspector (see below). Otherwise, briefly propose a run with the
specific reason, and wait. Re-run only after relevant fixes or a direct owner request.

step-back-review should carry only this pointer — a reference, not a mandatory gate.


## Clean run

Run a **separate agent with a new context**, carrying none of the implementation history, author
memory, GREEN summaries, or prior review conclusions.

Pass into the initial request:
- the primary task and the authoritative requirements and owner decisions;
- the project path and the exact commit or a frozen diff;
- the bounds of permitted checks.

Do **not** pass the author's "everything is correct here" list. An agent document or a code
comment is not automatically an owner decision.

The inspector must read the project's current rules and contracts itself — a clean context does
not mean ignoring requirements or protective limits. The author's report may be read **after**
the first independent pass, to reconcile what was claimed against what was found.

Verify the launch mechanism truly withholds the author's history. Name any settings it inherits
automatically if they cannot be removed by a supported means — do not call a run "clean" if it is
not. If an isolated run is unavailable, report the limitation: the author's self-check does not
substitute for an inspector. A fresh context of the **same model** is not an independent
second-provider review — label it honestly as such.


## What the inspector checks

Pick checks by the risk of the change; do not walk a universal mega-checklist.

1. **Fidelity to the original task** — what was done, skipped, added, and any unapproved scope
   change. An agent doc or code comment is not automatically an owner decision.
2. **Integration** — real entry points and call sites, responsibility owners, compatibility with
   neighbouring contracts. Look for unused code, duplication of an existing capability, two
   conflicting implementations, and hidden manual steps.
3. **One main user path** — plus the relevant failure or retry for it, chosen by the change's
   risk.
4. **Delivery changes** — trace commit → package → installed version → actual use. A file present
   in a manifest does not prove installation; discovery does not prove correct application.
5. **Tests** — whether they check the required behaviour, not just constants or implementation
   assumptions, and whether a result is a fresh run rather than a stale cached one.


## Boundaries

- Read-only by default. Only safe, isolated checks are allowed; tests may write to temporary
  fixtures.
- Do not change code, rules, tests, acceptance criteria, hooks, credentials, consent, grants, or
  live data. Do not run a check with side effects without matching permission.
- Do not read or print secrets "for audit completeness".
- Do not re-review the whole repository. Step outside the diff only to check its real
  dependencies and consequences.
- Do not demand new architecture for a hypothetical future. Each recommendation must remove a
  concrete, demonstrated problem.
- Do not fix your own findings within this run, and do not start an endless re-review loop.


## Verdict discipline

A mandatory acceptance criterion that is demonstrably unmet is a defect, not an observation:

- An explicit, applicable acceptance criterion that is **not met**, with **no owner-approved
  exception**, forces **NEEDS CHANGES**. It cannot be a FIT and cannot be downgraded to
  non-blocking.
- A technical explanation — from the author, *or from the inspector itself* (for example "the
  mechanism self-recovers, so the missing control is fine") — does **not** replace the owner's
  decision and does not license lowering such a discrepancy to non-blocking. Only the owner grants
  the exception; until then the criterion stands.
- If it is unclear whether the criterion applies, or whether the cited requirement is
  authoritative, the verdict is **NOT VERIFIED** with one concrete question — not FIT.
- **FIT may not contain any unresolved discrepancy with a mandatory requirement.** Ordinary
  optional improvements, with no mandatory criterion behind them, may remain non-blocking notes.

An exception counts as owner-approved only when a cited owner decision records it — not an agent
document, a code comment, or the inspector's own reasoning.


## Short result

- **Verdict: FIT / NEEDS CHANGES / NOT VERIFIED.**
- **Checked:** the commit/diff, requirements, scenarios, and actual results.
- **Per finding:** the violated requirement or contract, the place in code, the evidence, the
  consequence, and the smallest sufficient fix.
- Assumptions and limitations are stated separately from defects. No categorical BLOCKER without
  evidence.
- A fresh context of the same model is marked honestly — not presented as an independent
  other-provider review.


## Minimal acceptance (self-check)

On isolated examples:

1. Code and unit tests are green, but the capability is not wired to the real use path → the
   inspector finds the gap.
2. The author claims the delivery is finished, but the installed version is old → the inspector
   distinguishes the package from the actual installation.
3. A small change is integrated correctly → the inspector accepts it without inventing defects or
   demanding a system rebuild.
4. An explicit, applicable acceptance criterion is unmet while tests are green and there is a
   technically reasonable justification, but **no owner-approved exception** → the inspector
   returns NEEDS CHANGES; it does not downgrade the gap to non-blocking on its own reasoning.
   Control: the same gap **with a cited owner-approved exception** is not blocked for that reason.

Separately confirm the clean context: the author's report, with its hint, does not enter the
inspector's initial request. Keep the examples and expectations out of its starting context.


## Invocation

One supported way: start a fresh agent session (no shared history) that discovers this skill
through normal skill discovery, and give it only the primary task, the authoritative
requirements, the project path, and the exact commit or frozen diff — then ask it to run
`inspector-review`. For example:

    claude -p "Run inspector-review. Primary task: <requirements>. Project: <path>. \
    Inspect commit <sha> (or the attached diff). Permitted checks: read-only plus isolated \
    tests in a temp dir. Report the short result."

Do not seed that initial prompt with the author's conclusions or GREEN summary; reconcile those
only after the first independent pass.
