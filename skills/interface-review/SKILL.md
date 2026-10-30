---
name: interface-review
description: 'Orchestrates a complete interface review — combines the VISUAL gate (anti-slop-design: machine-generated visual cliches) and USABILITY audit (ux-review: Nielsen heuristics, Laws of UX, WCAG 2.2 UX criteria, forms/tables/states/nav/copy/touch/cognitive), plus the project layer and, when available, a11y conformance and copywriting. Merged, deduplicated, ranked findings + one gate. The review counterpart of design-pass (which is for building). Use for a FULL review/audit of a screen, flow, prototype or PR in one pass rather than one lens. Triggers: "interface-review", "complete interface review", "full interface review", "critique the screen or flow", "UI audit".'
---


# interface-review — complete interface review orchestrator

This is **composition and ordering**, not new rules. Just as `design-pass` combines building (reconstruction → method →
anti-slop gate), `interface-review` combines **review**: visual gate + usability audit (+ project,
+ a11y/copy when available) into one merged, deduplicated, ranked report. Each axis uses its existing
skill — this supplies only sequence and **merge**, so several lenses do not count one defect repeatedly.


## When to use

Full review/audit of a screen, flow, prototype or PR; the final interface “readiness” gate. For one
lens, invoke the corresponding skill directly (`ux-review` for usability, `anti-slop-design` for appearance).


## Sequence

0. **Scope + evidence (once).** Name the artifact (screen / flow / prototype / diff), **viewports**
   (read and apply the [shared viewport contract](../design-pass/references/viewport-coverage.md): phone, tablet portrait, tablet landscape, desktop at 100%; text enlargement/reflow separately), **role + task**. Capture screenshots / walk through the flow — all lenses
   use the SAME evidence, not memory. For PRs, use diff mode (below).

1. **Project layer (when in a repository).** Load the local design skill / tokens / `CLAUDE.md`/
   `AGENTS.md`. It **overrides** generic rules where they overlap (e.g. deliberate enabled+no-op instead of `disabled`
   is a project decision, not a violation). Same precedence as every lens: **project > rules > generic**.

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
   - Rank together (blocker / major / minor), most severe first.


## Report and gate

One ranked list. Each finding: lens+rule · what was observed and where (evidence) · source(URL) · fix.
Gate (as in the lenses): the interface is not “ready” until blocker+major is empty **or** each is a dated limitation explicitly
accepted by the user (magnitude/mechanism). Run on a screenshot/live screen, not from memory.


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
