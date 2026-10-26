---
name: ux-review
description: 'Audits an interface against cited UX best-practice rules: Nielsen heuristics, Laws of UX, UX-related WCAG 2.2 criteria, and patterns for forms / tables / states / navigation / copy / touch targets / cognitive load. Takes a screen, flow or prototype and returns RANKED violations, each with a source and an observable check. About usability, not whether it looks AI-generated (anti-slop-design) or exact mockup reconstruction (design-pass). Use to check/critique UX of a screen, flow, prototype or redesign, define UX acceptance criteria or gate interface readiness. Compatibility trigger aliases: "ux-review", "ux-аудит", "перевір UX", "ux lint", "прожар UX", "usability review", "юзабіліті".'
---


# ux-review — UX audit against cited rules

These are **facts + a gate**, not a construction method. The method (how to make design decisions, page vs system branching,
where risk lies) is in [`frontend-design`](../ship/frontend-design/SKILL.md). How NOT to look templated is in
[`anti-slop-design`](../anti-slop-design/SKILL.md). Accessibility-standard conformance belongs in specialized
accessibility review. This skill checks one thing: **is this convenient and predictable to use**,
against verifiable rules with collected primary sources.

Rules live in [`references/rules.md`](references/rules.md), each in the format
`[category] NAME — principle → HOW TO CHECK (observable check) → source(URL)`. The
**HOW TO CHECK field is mandatory**: a rule without a way to check it on this screen is a hypothesis dressed as
a rule and cannot support a gate. Do not report a rule you cannot check on the artifact.


## When to apply

UX review or audit of a specific screen / flow / prototype / redesign; defining UX acceptance;
a final interface-readiness gate before delivery. Not palette/typography selection (that is
`frontend-design`) or pixel parity with a mockup (that is `design-pass`).


## Procedure

0. **Scope.** Name the artifact (live page / screenshot / prototype / multistep flow), **viewports**
   (read and apply the [shared viewport contract](../design-pass/references/viewport-coverage.md): phone, tablet portrait, tablet landscape, desktop at 100%; text enlargement/reflow separately), and **who/why** (role + user task).
   Without a user task, half the heuristics are meaningless.

1. **Evidence, not memory.** For a live/visual target, capture it (actually inspected screenshots of every applicable surface × baseline viewport under the shared contract);
   for a flow, walk the steps. Each violation must rest on what was *seen* (element, screen, step),
   not a general “usually bad”. The same principle as §3 pre-flight in `anti-slop-design`.

1b. **Edge conditions.** Run applicable rules not only in the happy state but also under stress: very long text/name, empty (0), 1 item, many (overflow), error state, slow network. Many defects (clipping, crowding, broken layout, missing actions) are visible ONLY here.

2. **Rule pass.** Walk `references/rules.md` category by category. For every rule,
   perform its HOW TO CHECK against the artifact → `pass` / `violation` with evidence (exactly what and where).
   Skip rules inapplicable to this screen type (e.g. table rules on a form), and state what
   you skipped.

Before ranking, record the target accessibility level from project requirements; if absent, say so. Failure of an AAA criterion is not automatically a blocker for an AA target. Distinguish a verified defect from an untested criterion.

3. **Rank.** Each violation → **blocker** (blocks the task / data loss / unreachable control /
   failure of an applicable mandatory WCAG criterion, considering target level and exceptions) · **major** (substantial friction, confusion, high cognitive load) ·
   **minor** (polish). A finding without an observable check is not a finding; remove it.
   **Dedup:** one observed defect = one finding under the MOST SPECIFIC rule; cite other matching rules as corroboration within the same finding, and do NOT add their severities. (The ruleset deliberately repeats across categories—recognition-over-recall, consistent-identification, error-prevention, target-size, proximity, latency—so do not count one defect multiple times.)

4. **Report.** Ranked list, most severe first. Each finding:
   - **rule + category** (e.g. `[forms] Placeholder ≠ label`);
   - **violation**: what was observed and where (element/screen/step), with evidence;
   - **source**: primary-source URL for the rule;
   - **fix**: a specific change.
   End with a short summary of `pass` results and explicitly skipped categories.


## Gate mode (readiness pre-flight)

As in `anti-slop-design`, the interface is not “ready” until the blocker+major list is empty **or** each
item is a dated limitation explicitly accepted by the user (magnitude or mechanism, not “we will fix it later”).
Run against a screenshot/live screen, not from memory; if you could not capture it, say so honestly.


## Diff / PR review mode

For UI regression review of a branch or PR, take the changed screens/components (diff), identify affected rules and run them against the base branch (before/after). Look specifically for **regressions** introduced by the change (broken state/contrast/focus/responsiveness/copy), not all existing screen debt. A new finding is a regression in this diff; record debt outside the diff separately rather than mixing it with regressions.


## Priority when layers disagree

**project > skill rules > generic.** Canonical repository tokens, patterns and standards (local
design skill, `CLAUDE.md`/`AGENTS.md`, design system) **override** a generic rule where they cover it
(e.g. a project intentionally keeps a button enabled+no-op rather than `disabled`: this is a
project decision, not a violation). The skill rule applies where the project is silent. Where sources themselves conflict
(e.g. WCAG minimum touch target 24px vs Apple HIG 44px), name both thresholds and the applicable context;
do not pretend there is a single number.


## Honesty

- Do not cite a rule you have not checked on the artifact. Do not invent thresholds or URLs.
- Do not inflate severity: a blocker is a blocker, not a preference.
- Name skipped work (no narrow-viewport capture, flow not walked) as skipped; do not present it as `pass`.

## Done

- scope named (artifact, viewports, role+task);
- evidence from every applicable baseline viewport inspected and recorded under the shared contract; missing evidence is NOT_TESTED, a required gate is BLOCKED;
- applicable `references/rules.md` categories checked, skipped categories named;
- each finding has rule + evidence + source(URL) + fix and is ranked;
- severity assigned; findings without observable checks removed;
- in gate mode: blocker+major empty or each is a dated limitation explicitly accepted by the user.

---

**Companion:** rules are in [`references/rules.md`](references/rules.md). Complements, does not replace:
[`anti-slop-design`](../anti-slop-design/SKILL.md) (machine clichés in appearance), accessibility review
(WCAG conformance), [`design-pass`](../design-pass/SKILL.md) (mockup reconstruction),
[`frontend-design`](../ship/frontend-design/SKILL.md) (visual decision method).
