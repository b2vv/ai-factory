# Reference anti-patterns — the shared template and cross-cutting rules

First-party authored cross-skill reference. One place for the parts that would otherwise be copied into every
skill's `references/`. Domain-specific anti-patterns stay in each skill's own `references/` file; only the shared
template and the genuinely cross-cutting rules live here. Skills ROUTE here for the shared parts during plan /
implement / review, and to their own `references/` for the domain parts.

This doc is first-party authored (see PROVENANCE.md); it is not an upstream mirror and invents no exceptions.

## The 4-field template

Every anti-pattern rule — here or in a skill's `references/` — is written in these four fields. A rule missing a
field is incomplete.

- **How-not-to:** the concrete anti-pattern, the user-facing consequence, and a short example. Name what breaks
  for a real person, not just "bad practice".
- **How-to:** the safe alternative, with a short example.
- **Exceptions:** when a deviation is justified — its conditions and its risks. Where there is NO legitimate
  exception, write "Exceptions: none" explicitly. Do NOT invent an exception to excuse a violation.
- **Verify:** the observable discriminator that tells an allowed exception from a mistake — what you look at to
  decide, not an opinion.

## Cross-cutting rule 1 — accessibility REQUIREMENTS are separate from preferences

Accessibility splits into two kinds, and they are governed differently:

- **REQUIREMENTS** — the WCAG success criteria that are in scope for this project: the A/AA criteria (text
  alternatives, name/role/value, keyboard operability, focus visible, error identification in text, sufficient
  contrast, Target Size (Minimum) 2.5.8), PLUS any AAA criterion the project targets or has separately agreed
  (e.g. Target Size (Enhanced) 2.5.5, 44×44). An in-scope criterion carries **no exception at the level of taste,
  brand or density**. The only deviations are the carve-outs the specific SC itself defines (e.g. 2.5.8's own
  spacing / inline / UA / essential carve-outs). An in-scope REQUIREMENT is never downgraded to PASS by appeal
  to "it looks better" or "the design is dense".
- **PREFERENCES** — genuine stylistic/visual choices that are NOT WCAG success criteria at all (motion flourish,
  exact spacing aesthetics, decorative polish). These may carry real exceptions, documented per the template.
  An AAA criterion is NOT a "preference": it is a conformance criterion. It is simply not mandated *by that
  criterion* when the project's target is only AA — but when the project targets AAA or has agreed the item, it
  is a REQUIREMENT and cannot be waved away as taste.

**How-not-to:** (a) marking an **undersized** target (e.g. 20×20 CSS px) PASS "because dense / on-brand" when no
2.5.8 carve-out actually applies; (b) dismissing an agreed or AAA-target 44×44 obligation as "just a preference";
(c) a color-only error. Consequence: a person who relies on touch accuracy or non-color cues cannot complete the
task, or an agreed conformance obligation is silently dropped.
**How-to:** for 2.5.8 (AA) a target **≥24×24 CSS px passes on size alone**; a smaller target passes only if it
meets the SC's spacing carve-out (a 24px-diameter circle centred on the target does not intersect another
target's circle) or the inline/UA/essential carve-outs. For 2.5.5 (AAA, 44×44), meet it when the project targets
AAA or has agreed it. Put a text error beside any color cue.
**Exceptions:** only the carve-outs a specific SC defines, applied to the target's actual geometry. An AAA item
being out of scope at an AA target is *scoping*, not a taste exception — and does not license calling it a
"preference".
**Verify:** first fix the project's target conformance level and any agreed items; then check the target's real
geometry against the SC's own carve-outs. A taste/brand/density argument against an in-scope criterion is a
mistake; a correctly-applied SC carve-out (e.g. a verified spacing offset on an undersized target) is a real
exception; a target already ≥24×24 needs no exception at all.

## Cross-cutting rule 2 — no invented exceptions

**How-not-to:** inventing an "exception" on the spot to justify shipping a violation (an undocumented special
case, a one-off "this time it's fine"). Consequence: the rule erodes; the next reviewer can't tell an allowed
case from a mistake.
**How-to:** an exception is legitimate only if it is written down in advance (here or in the domain reference)
with its conditions, risks and a Verify discriminator. If it isn't written, it isn't an exception — fix the
violation or get the exception added through the normal change process first.
**Exceptions:** none. (This rule is about exceptions; it has none itself.)
**Verify:** can you point to the exact pre-existing Exceptions line that covers this case, with its conditions
met? If not, it is a violation.

## Routing

Each reference-backed skill, during plan / implement / review, consults:
1. this doc, for the template and the two cross-cutting rules; and
2. its own `references/` file(s), for the domain-specific anti-patterns.

A domain reference states its subject-specific rules in the 4-field template and marks every accessibility item
as REQUIREMENT or preference per cross-cutting rule 1. A reference section that no skill routes to is not done.
