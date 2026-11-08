---
name: ui-measurements
description: Measure selected UI box fit, supported solid text contrast and explicitly stable fixture values through an existing browser runner. Use conditionally during design-pass or interface review when current project checks leave a relevant measurement gap.
---

# Selected UI measurements

Support the existing [design-pass](../design-pass/SKILL.md) facade and review lenses;
do not become a new design method, global scanner or accessibility certification.
Reuse current Storybook/E2E/a11y observations first. Run this helper only for a
missing relevant measurement, in the already authorized browser/project stack.
No installation, screenshots, video or animated demonstration is required by this
helper. It does not authorize navigation, test data changes or host registration.

1. In the **existing** [browser evidence record](../design-pass/references/browser-state-evidence.md),
   select the route, state/role, fixture, revision/dirty scope and affected targets.
   Use the shared viewport contract; one measured viewport does not close others.
   Where the UI depends on data/input, cover relevant empty/populated and
   disabled/enabled pairs with the facade; one state does not prove the other.
   Use authorized fixtures/interactions; changing live data needs its own permission.
2. Confirm the agreed expectation and a tool that can actually measure it. Use
   [the invocation contract](references/contract.md) only if the project lacks an
   equivalent current check. Wait for the named state with the existing runner;
   never infer settled state from a timeout alone.
3. Evaluate `scripts/measure-ui.cjs` in that browser context. The function reads
   explicitly selected targets and returns expected/actual values, actual frame
   viewport and PASS/FAIL/NOT_TESTED. It performs no DOM writes, network, scan of
   all numbers, screenshot capture or evidence-file persistence.
4. Interpret each result within its measured scope, inspect the relevant screen
   and merge it into the existing UX/visual finding. Fix and rerun the same state
   after edits. Keep a required unsupported check BLOCKED/NOT_TESTED; use N/A only
   with the existing contract's applicability reason. Never update a baseline to
   hide a defect.

## What the numbers establish

- **Box fit:** selected client/scroll dimensions, with declared tolerance. Local
  horizontal scrolling can be intentional for a table; record the reason and
  reference and verify access separately. Deliberate truncation, ancestor clipping,
  overlapping surfaces and glyph ink need scoped inspection; a box PASS proves
  none of these. Use only an x-axis check for page horizontal overflow: ordinary
  vertical page scrolling is not a defect. Two-dimensional exceptions apply only
  to the relevant content, not automatically its surrounding controls.
  **A fit PASS is not a pointer-target-size check:** even a 10-by-10 CSS px
  control can fit its contents. For target size, use separate bounds and interaction
  evidence for the actual active area, not an inner icon or an assumed wrapper.
  A padded wrapper counts only where pointer input actually activates the intended
  action; verify that behavior, including overlapping/intercepting surfaces. Record
  the applicable project/WCAG criterion and any justified exception (for example
  spacing, equivalent control, inline, user-agent control or essential presentation).
  Do not infer a violation from an inner box below 24 CSS px, or a pass from wrapper
  dimensions alone. See [WCAG 2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).
- **Contrast:** only supported opaque, solid sRGB leaf-text paint. Unsupported
  effects or pseudo-text paint, text outside its background box, unresolved fonts, hidden/content-visibility ancestors and active
  animations produce NOT_TESTED. Non-unit opacity on the text or an ancestor
  yields NOT_TESTED for unsupported compositing (zero opacity is unrendered).
  This is independent of disabled semantics: an enabled dimmed target may be
  NOT_TESTED, while supported opaque text in an inactive control may get a numeric
  result. The helper does not inspect disabled/aria-disabled or establish inactivity.
  Verify actual inactive status before applying the relevant contrast exception;
  appearance or opacity alone is insufficient. Check the applicable enabled state
  separately. Reuse a reliable existing tool for other paint.
  Choose the applicable normal/large text and AA/AAA threshold, or explicit project
  minimum, **before** calling; supply its source. The helper compares that declared
  minimum without rounding, but does not decide applicability, inactive-control/
  logotype exceptions or WCAG conformance. [WCAG 1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
  and [1.4.10](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html) explain these boundaries.
- **Fixture values:** exact text only from an explicitly stable named/versioned
  fixture with a source and agreed expected string. A number on a live page is not
  an invariant. Dynamic/unknown fixtures remain NOT_TESTED. This checks one UI
  observation, not backend integrity or all business data.

Typography families, accent counts, radius variants and motion choices remain
contextual design decisions under the facade's priority rules. A subjective
heuristic cannot waive an applicable accessibility/function requirement, and a
numeric helper result cannot replace visual, keyboard or journey verification.
