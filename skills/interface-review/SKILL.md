---
name: interface-review
description: 'Orchestrates a complete interface review in one pass: the visual gate (anti-slop-design), the usability audit (ux-review), the project layer and, when available, a11y conformance and copywriting, merged into deduplicated ranked findings and one gate. The review counterpart of design-pass, which builds. Use for a full review or audit of a screen, flow, prototype or PR rather than a single lens. Triggers: "interface-review", "full interface review", "interface readiness gate", "critique the screen or flow".'
---


# interface-review — complete interface review orchestrator

This is **composition and ordering**, not new rules. Just as `design-pass` combines building (reconstruction → method →
anti-slop gate), `interface-review` combines **review**: visual gate + usability audit (+ project,
+ a11y/copy when available) into one merged, deduplicated, ranked report. Each axis uses its existing
skill — this supplies only sequence and **merge**, so several lenses do not count one defect repeatedly.


## When to use

Full review/audit of a screen, flow, prototype or PR; the final interface “readiness” gate. For one
lens, invoke the corresponding skill directly (`ux-review` for usability, `anti-slop-design` for appearance).
To find and name problems with the owner before a gate, without ranking or gating, use [`ui-audit`](../ui-audit/SKILL.md).
Its confirmed problems, and every entry that fails an applicable accessibility, keyboard or functional requirement whatever
the owner answered, are evidence here and enter the merge, not findings to rediscover. Such a requirement entry leaves the
gate only through a dated limitation the owner explicitly accepted (ui-audit §4). The reuse condition below (same build,
viewport and UI state) still applies.


## Sequence

0. **Scope + evidence (once).** Name the artifact (screen / flow / prototype / diff), **viewports**
   (read and apply the [shared viewport contract](../design-pass/references/viewport-coverage.md): its four baseline classes, plus text enlargement/reflow separately), **role + task**. Capture screenshots / walk through the flow — all lenses
   use the SAME evidence, not memory. For PRs, use diff mode (below).

1. **Project layer (when in a repository).** Load the local design skill / tokens / `CLAUDE.md`/
   `AGENTS.md`. It **overrides** generic rules where they overlap (e.g. deliberate enabled+no-op instead of `disabled`
   is a project decision, not a violation). For contextual design defaults the order is [design-pass §3](../design-pass/SKILL.md#3-priority-and-limits-of-general-rules): **authoritative reference > project > catalog > generic** (in a review the anti-slop catalog takes the method's place in this order; it remains a catalog, not a method). Applicable accessibility/function requirements retain their own authority; neither a project aesthetic nor a reference waives them.

2. **Visual lens — [`anti-slop-design`](../anti-slop-design/SKILL.md).** Machine-generated visual cliches +
   §3 pre-flight as a gate. Owns: template typography, decoration, generic palette, “AI appearance”.

3. **Usability lens — [`ux-review`](../ux-review/SKILL.md).** Full pass over `references/rules.md`
   (heuristics, Laws, WCAG-UX, forms/tables/states/nav/copy/touch/cognitive) with its own gate and deduplication.
   Owns: usability, accessibility-UX, copy, states, responsiveness.

4. **Optional lenses (when the skill exists).** Deeper a11y conformance (full WCAG review beyond UX-SC) and
   specialist copywriting — if the corresponding skill is available; otherwise `ux-review` already covers their UX aspects.

5. **MERGE (the key step).** Consolidate all lenses' findings into ONE list:
   - **Dimension ownership:** appearance/cliches → anti-slop; usability/forms/tables/states/nav/copy/touch →
     ux-review. **General tie-break (both lenses have a specific rule for ONE defect):** the lens with a
     CITED referenceable rule owns it; a purely visual reading without a source is corroboration. Examples:
     contrast/focus → ux-review's cited WCAG rule; **grouping/hierarchy/density** (“sections blend together,
     no grouping”) → ux-review's cited `[law] Common Region`/`[law] Proximity`/`[cog] Chunking` owns it,
     while anti-slop's “looks flat” collapses into corroboration.
   - **One observed defect = one finding** under the most specific lens; do NOT add severities.
   - Rank together (blocker / major / minor), most severe first; a `drift` from ux-review ranks like a violation.
   - **Owner decisions** from the lenses (ux-review semantic-consistency decisions, open role questions)
     are not findings: merge them into one unranked list, grouped by role and cause, each marked
     *gating* or *stylistic* ([semantic-consistency](../ux-review/references/semantic-consistency.md) §5).
   - **Concept fit** outcomes (compatibility and visual fit, kept separate) are merged under the visual
     lens; anti-slop-design owns the visual-fit verdict and design-pass (in audit mode, the proposal)
     carries the compatibility outcome ([concept fit](../anti-slop-design/references/concept-fit.md) §5);
     they are not repeated or re-researched here.


## Measurement and rule priority

Apply [design-pass §3](../design-pass/SKILL.md#3-priority-and-limits-of-general-rules) for rule priority and the [ux-review measurement rules](../ux-review/SKILL.md#measurement-and-rule-priority) for `ui-measurements`; both lenses share them, so they are stated once there.

## Report and gate

One ranked list. Each finding: lens+rule · what was observed and where (evidence) · source(URL) · fix.
Then a separate section **Decisions for the owner** (unranked, grouped by role and cause; gating vs stylistic).
Gate (as in the lenses): the interface is not “ready” until blocker+major is empty **or** each is a dated limitation explicitly
accepted by the user (magnitude/mechanism). An open **gating** decision blocks PASS (the affected check stays
BLOCKED / NOT_TESTED); open **stylistic** decisions do not. Moving an open acceptance criterion or required
evidence into the decisions section does not make it pass. Run on a screenshot/live screen, not from memory.

**Minimum evidence for keyboard, contrast and interaction claims.** These three checks are PASS or FAIL only with the evidence below; details are in the [ux-review measurement rules](../ux-review/SKILL.md#measurement-and-rule-priority) and [ui-measurements](../ui-measurements/SKILL.md). Purely visual findings need no live interaction when a matching screenshot shows them.
- Keyboard: actual key presses with focus observed at each stop; DOM or source order is not keyboard evidence.
- Contrast: the `measureUI` `contrast` result; a ratio calculated by hand is not evidence.
- Interaction: a safe action (changes no live or shared data) and the result observed after it.
- For these three checks, missing evidence is `NOT_TESTED`: never PASS, and it never satisfies an acceptance criterion.

[`ui-audit`](../ui-audit/SKILL.md) evidence is reused only when it matches the same build, viewport and UI state.

Approval of an `extends concept` proposal gates that proposal's implementation, not unrelated
audit checks. A required main-task control proven missing within the relevant scope is a
`violation`; a source-only not-found observation stays limited to the files read. An unverified
required journey stays `NOT_TESTED` and gating, not stylistic. Inferred tasks retain the
[semantic-consistency](../ux-review/references/semantic-consistency.md) §6 limits.

## Audit mode (opt-in)

Only when the task is an audit of an existing product (find logical inconsistencies across its components
and propose changes that make meaning clearer), follow [product audit](references/product-audit.md). It is
read-only, uses the same lenses, report and gate, and adds scope, discovery, role inventory and proposals.


## Diff / PR mode

Take changed screens/components, run the lenses against the base branch (before/after), and report this diff's
**regressions**, not the screen's entire debt. Existing debt outside the diff goes separately.

## Done

- scope + actually inspected evidence for all applicable baseline viewports collected once under the shared contract; missing evidence — NOT_TESTED, required gate — BLOCKED;
- project layer loaded (in a repository) and respected in precedence;
- at least two lenses run (anti-slop + ux-review); optional ones when the skill exists;
- findings MERGED and deduplicated (one defect = one finding, severity not doubled), ranked;
- each finding has lens+rule + evidence + source + fix;
- in gate mode: blocker+major empty, or each is a dated limitation explicitly accepted by the user.

---

**Lenses:** [`anti-slop-design`](../anti-slop-design/SKILL.md) (appearance) · [`ux-review`](../ux-review/SKILL.md)
(usability). **Building counterpart:** [`design-pass`](../design-pass/SKILL.md). Project layer: the repository's local
skill, if present (it overrides generic).

## Reference anti-patterns

This skill's domain anti-patterns are stated inline above (its merged visual + usability gate). During plan/implement/review also consult the shared [reference anti-patterns](../../ai-factory/reference-anti-patterns.md) for the 4-field template and the cross-cutting rules (accessibility REQUIREMENT-vs-preference split; no invented exceptions).
