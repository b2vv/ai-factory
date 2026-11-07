# Browser evaluation contract

Use the existing project runner. In a CommonJS-capable test, for example:

```js
const path = require('node:path');
const measureUI = require(path.join(kitRoot, 'skills/ui-measurements/scripts/measure-ui.cjs'));
const result = await page.evaluate(measureUI, {
  context: {
    revision: 'revision plus scoped dirty fingerprint', state: 'orders loaded',
    fixture: 'orders-seed-v3', evidence: 'existing-run/state-evidence-id',
    route: '/orders', settled: true, declaredZoom: '100%, verified by runner'
  },
  tolerance: 1,
  checks: [
    { id: 'page-width', kind: 'fit', selector: ':root', axis: 'x' },
    { id: 'label', kind: 'fit', selector: '[data-testid="order-label"]' },
    { id: 'table', kind: 'fit', selector: '[data-testid="table-scroll"]',
      scrollX: { reason: 'columns require a local horizontal scroller', evidence: 'agreed-table-contract' } },
    { id: 'label-contrast', kind: 'contrast', selector: '[data-testid="solid-label"]',
      minimum: 4.5, source: 'agreed WCAG 1.4.3 AA normal-text requirement' },
    { id: 'fixture-total', kind: 'text', selector: '[data-testid="total"]', expected: '42',
      fixture: { id: 'orders-seed-v3', source: 'versioned seed/expected-value reference', stable: true } }
  ]
});
```

This example does not establish that Playwright, a particular route, selector or
fixture exists. Use the equivalent evaluation facility already available; do not
install one for the example. Supply authorized test identities and sanitized data.
The function must run in the selected page/frame realm with DOM, computed styles,
font status and animation-state APIs. It does not drive or settle the page.

Required context strings are revision/dirty fingerprint, state, fixture, evidence
ID and expected `location.pathname`. Query strings and full URLs are not collected.
`settled` is the runner's declaration, supplemented by runtime font and animation
checks, not proof against future async changes. Wrong route or unsettled runtime
state is NOT_TESTED. `declaredZoom` is optional and explicitly declared: DPR or
visualViewport scale is not proof of browser zoom. Actual width/height are CSS
pixels of the evaluated frame; `frame: child` is not top-level viewport acceptance.

Each of 1–32 checks needs a unique ID (up to 80 characters), selector (up to 256)
and kind `fit`, `contrast` or `text`. Context/other source strings are up to 512
characters; expected fixture text is up to 2048 and can be empty. Geometry tolerance
is finite 0–2 CSS px, default 1 for integer CSSOM dimensions; do not use tolerance to
excuse a visible defect. `axis` is x/y/both (default both). An intentional scroll-x
allowance needs a reason/reference, default/both axes and actual auto/scroll CSS; its rationale is retained in expected.scrollX and vertical fit is still checked; it does not establish
keyboard, touch or full-content accessibility. No blanket clipping exception exists.

Contrast needs a finite declared minimum within 1–21 and its agreed source. Only
visible HTML leaf text with directly opaque sRGB foreground/background and no
unsupported paint/compositing is measured. Gradients/images, alpha, effects,
pseudo content/first-letter/first-line paint overrides, fill/stroke, inset shadows, text offsets or overflow, masks, transforms or unavailable APIs are
NOT_TESTED; do not change page styles to make the helper pass. Color calculations
use CSS sRGB values, not sampled antialiased pixels, and thresholds are compared
without rounding. The caller/lens owns large-text classification and exceptions.

Text checks require an expected string. They run only when `fixture.stable` is
true, its ID equals context.fixture, and a source/version reference is present.
Otherwise the configured expectation is retained but the observation is NOT_TESTED.
No inference is made about other text, numbers, timestamps, live totals or ordering.

Invalid/empty/unbounded configuration throws `Invalid UI measurement config`
before DOM reads; record a failed measurement setup, not a UI PASS. Missing,
ambiguous, unrendered or unsupported targets remain NOT_TESTED with a fixed reason.
An aggregate FAIL takes precedence over NOT_TESTED, but every untested row remains
visible and required gaps still block the existing gate. An all-PASS report proves
only the selected numeric observations. Reuse the existing evidence artifact and
redaction policy; exact fixture text is intentionally included only in text-check
rows. Do not place secrets or private payloads in configuration or reports.
