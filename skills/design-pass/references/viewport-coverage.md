
# Viewport coverage — shared UI contract

Read this contract before collecting evidence in design-pass, ux-review or interface-review. For each applicable changed/audited surface (screen, dialog, panel or component in context), check all four classes at **100% browser zoom and normal text size**:

| Class | Default viewport, CSS px |
| --- | --- |
| Phone | 390 × 844 |
| Tablet portrait | 768 × 1024 |
| Tablet landscape | 1024 × 768 |
| Desktop | 1440 × 900 |

These are reproducible defaults, not a list of physical devices. A project may specify other supported sizes: record the source, exact CSS width × height and mapping to each class before checking. A different size does not permit silently skipping a class or orientation. If the project explicitly does not support a class, cite the current contract/owner decision and impact; only then use N/A with a reason. Lack of time, tooling or evidence is not N/A. Do not expand a small change to the entire product.

For each applicable surface × class, retain in the existing plan/report: route/surface, role and state/fixture, revision and relevant dirty scope, actual CSS width × height, browser zoom and text-scaling method, expected/actual result, path/ID of the current screenshot and confirmation that it was actually inspected. Also inspect content below the first screen. A screenshot file without inspection is not evidence. A screenshot proves appearance; record performed actions and scenario results separately.

Retain checks at an intermediate width near a changed breakpoint and for applicable states/interactions: open/active, loading/empty/error/recovery, keyboard/focus, overflow and long text. Check them where the change can have an effect; one default screenshot does not cover these states. After a fix, repeat the affected viewports/states at the final revision.


## Scaling and accessibility — separate checks

- **200% text enlargement:** check readability and absence of lost text/actions; record the actual method. CSS `font-size: 200%` simulates text enlargement; it is not actual browser zoom or full evidence of scaling all text (including px-sized descendants).
- **Reflow:** separately check a narrow 320 CSS px viewport or actual 400% browser zoom with equivalent CSS width, stating initial/final dimensions and applicable exceptions for two-dimensional content. Do not call viewport resizing or CSS font-size actual browser zoom.
- If acceptance specifically requires browser zoom, evidence of real zoom is required; CSS simulation does not cover it. No zoom/text/reflow check replaces the four baseline viewports, and baseline viewports do not replace accessibility checks. Axe/build/unit PASS does not establish visual coverage.

Each row's status: **PASS / FAIL / NOT_TESTED / N/A**. Without current inspected evidence — **NOT_TESTED** with a reason and next step. An unavailable required check also blocks the gate (**BLOCKED**); it cannot count as PASS. A documented limitation is not accepted without an explicit owner decision. Applicable required rows with FAIL or NOT_TESTED rule out an unconditional “done and verified”.
