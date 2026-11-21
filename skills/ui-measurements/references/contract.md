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
ID and expected `location.pathname`. Query strings and full URLs are not collected. The full
pathname decides `route-mismatch`; it is echoed as `actual.route` only while its JSON string is
≤ 2048 UTF-8 bytes, otherwise `actual.route` is `null` with `actual.routeOversized: true`.
`context`, check IDs, selectors and expected text are echoed verbatim: never put secrets or
private identifiers in them or in a route you intend to measure.
`settled` is the runner's declaration, supplemented by runtime font and animation
checks, not proof against future async changes. Wrong route or unsettled runtime
state is NOT_TESTED. `declaredZoom` is optional and explicitly declared: DPR or
visualViewport scale is not proof of browser zoom. Actual width/height are CSS
pixels of the evaluated frame; `frame: child` is not top-level viewport acceptance.

State labels retain their attribution: `context.state` is caller-declared, not independently
observed by the helper. A data state such as `loaded` says nothing about interaction state
(`rest`, hover, focus, active); never automatically map `loaded` to `rest`. To compare against a
rest-state norm, record interaction-state evidence, or explicitly justify state invariance for
a noninteractive target in the existing evidence record. Otherwise that comparison is `NOT_TESTED`.

Each of 1–32 checks needs a unique ID (up to 80 characters), selector (up to 256)
and kind `fit`, `contrast`, `text` or `style` (see below). Context/other source strings are up to 512
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
`style` rows are excluded from the aggregate (see below). An aggregate FAIL takes precedence over NOT_TESTED, but every untested row remains
visible and required gaps still block the existing gate. An all-PASS report proves
only the selected numeric observations. Reuse the existing evidence artifact and
redaction policy; exact fixture text is intentionally included only in text-check
rows. Do not place secrets or private payloads in configuration or reports.

## `style` kind — read selected computed values

A `style` check returns **measured facts** about caller-selected targets. It has no expected
value and never produces `PASS` or `FAIL`; design verdicts belong to the review lenses. It
shares the contract above: same `context` object, 1–32 checks per call, unique `id` ≤ 80
chars, `selector` ≤ 256 chars, invalid configuration throws `Invalid UI measurement config`
before any DOM read, no DOM/style writes, no network, no navigation, no screenshots, no evidence
persistence. It runs in the existing runner or an agent browser's page-evaluation facility
(the "equivalent evaluation facility already available" above).

In an agent-driven browser without a test runner, evaluate the helper source followed by
`measureUI(config)` as one expression in the page's JavaScript evaluation tool, with `config`
written inline; the returned object is the report. Nothing is injected into the page beyond that
evaluation.

### Configuration

```js
{ id: 'tile-padding', kind: 'style', selector: '[data-role="summary-tile"]',
  properties: ['padding-top', 'padding-right', 'font-size', 'line-height'],
  limit: 10 }          // integer 1–50, default 1
```

Context gains one optional field: `colorScheme` (non-empty string ≤ 512 chars, e.g. `'light'`,
`'dark'`). The report echoes it and also reports the actual `prefers-color-scheme` and
`forced-colors` media results, next to the existing `actual.viewport`. A declared scheme that
differs from the media result is not an error (themes may be class-based); both are reported and
callers key by the declared scheme.

- **properties**: 1–16 unique entries per check, longhands from the allowlist; anything else
  (shorthand, unknown name, duplicate, non-string) is invalid configuration, so results compare.
- **limit**: an integer 1–50; a non-integer or out-of-range value is invalid configuration.
- **Allowlist:** `font-size`, `font-weight`, `font-style`, `line-height`, `letter-spacing`,
  `text-transform`, `font-family` (derived, see Output), `color`, `background-color`,
  `opacity`, `padding-{top,right,bottom,left}`, `margin-{top,right,bottom,left}`, `row-gap`,
  `column-gap`, `width`, `height`, `min-width`, `min-height`,
  `border-{top,right,bottom,left}-width`, `border-{top,right,bottom,left}-color`,
  `border-{top-left,top-right,bottom-right,bottom-left}-radius`, `box-shadow` (derived, see
  Output), `display`, `position`.
- **Never read:** `background-image`, `content`, `cursor`, `mask*`, `list-style-image`, custom
  property values, rule selectors, stylesheet URLs, text content, any attribute value other than
  ARIA `role`; from the `style` attribute only property names are reported.
- **Origin is out of scope** for this kind. Where a value comes from (token, class, inline) is
  established by reading the source; otherwise it is `source: unresolved`.

### Matching (same selection code path as the existing kinds)

Each check is processed in this fixed order; the first step that ends the check sets its reason.

1. **Runtime reason.** The existing call-level reasons (`viewport-unavailable`,
   `route-mismatch`, `state-not-settled`, `fonts-not-settled`) end every check, as today.
2. **Budget.** If an earlier `style` check in the call already ended with `budget`, this check
   is `NOT_TESTED: budget` (see Budgets).
3. **Selector.** `document.querySelectorAll(selector)`; a throw → `invalid-selector`.
4. **Raw match count.** `matched` = the number of raw matches, *before* any render or skip test
   (hidden, zero-size and SVG elements are counted, exactly like the existing kinds' `nodes.length`).
   - `matched` = 0 → `missing-target`.
   - `limit` = 1 and `matched` > 1 → `ambiguous-target` — the existing kinds' rule
     `nodes.length !== 1`, unchanged. A hidden duplicate therefore makes a `limit`-1 check
     ambiguous; to read the visible one, use a more specific selector or `limit` > 1.
5. **Window.** The first `min(matched, limit)` raw matches in document order are examined.
   Skipped elements **consume the window**: the reader never looks past position `limit` to
   find more readable elements. `truncated` = `matched` > `limit`.
6. **Per element** in the window: the existing `renderReason` decides; a non-null reason skips
   the element and increments its bucket in `skipped`: `non-html-target`, `unrendered-target`,
   `animation-state-unavailable`, `active-animation`. Otherwise the element is read.
   `returned` = the number of read elements; `returned` + sum of `skipped` = `min(matched, limit)`.
7. **Check status.** `returned` ≥ 1 → `OBSERVED`. `returned` = 0 → `NOT_TESTED`, reason = the
   first non-zero bucket in the order `non-html-target`, `unrendered-target`,
   `animation-state-unavailable`, `active-animation` (the order `renderReason` tests them).
   `skipped` always carries all counts.

An `OBSERVED` row with non-zero `skipped` or `truncated: true` describes only the returned
elements; callers must not count it as the full set (the calling review lens decides what a partial reading may support).

### Output per check

```js
{ id, kind: 'style', selector, status: 'OBSERVED' | 'NOT_TESTED', reason,   // reason absent when OBSERVED
  matched: 3, returned: 3, truncated: false,
  skipped: { 'non-html-target': 0, 'unrendered-target': 0,
             'animation-state-unavailable': 0, 'active-animation': 0 },
  elements: [{ index: 0,                       // position among raw matches (0-based)
               tag: 'div', ariaRole: 'group' | null,
               box: { width: 112, height: 64 },                          // CSS px, integers
               values: { 'padding-top': '9px', 'line-height': 'normal' }, // exact strings as returned
               derived: { 'font-family-first': 'Inter', 'box-shadow-layers': 0 },
               // font-family / box-shadow, when listed in properties, appear in derived instead of values
               inlineProperties: ['padding-top', 'padding-left'],         // inline longhand names only, as the element's CSSOM style lists them
               oversized: [] }],                                         // see Field size limits
  untraversed: { openShadowHosts: 1, iframes: 0, canvases: 0, constructedSheets: 0 } }
```

**Reasons** reuse the existing helper strings; only `budget` is new:

| Reason | When |
|---|---|
| `viewport-unavailable`, `route-mismatch`, `state-not-settled`, `fonts-not-settled` | call-level, as for the other kinds (step 1) |
| `budget` | this check, or an earlier style check in the call, would exceed a budget (step 2, Budgets) |
| `report-budget` | a non-style row that would push the whole report over its byte bound (Budgets; defensive) |
| `oversized-value` | a fit/contrast row whose echoed computed string exceeds 64 UTF-8 bytes (Budgets) |
| `invalid-selector` | the selector does not parse (step 3) |
| `missing-target` | no raw match (step 4). If `untraversed` counts are non-zero, the target may be inside them; callers treat it as not covered, not as absent |
| `ambiguous-target` | `limit` 1 and more than one raw match (step 4) |
| `non-html-target`, `unrendered-target`, `animation-state-unavailable`, `active-animation` | no element in the window could be read; the first non-zero bucket (step 7) |

Unsupported properties or options are invalid configuration, not a runtime status.

### Field size limits (UTF-8 bytes)

Sizes are **UTF-8 bytes of the string value**, measured with `new TextEncoder().encode(s).length`,
not characters:

| Field | Cap | Over the cap |
|---|---|---|
| `tag` | 64 B | `tag: null`, `'tag'` listed in `oversized` |
| `ariaRole` | 64 B | `ariaRole: null`, `'ariaRole'` listed in `oversized` |
| each value in `values` | 256 B | the property is omitted from `values`, its name listed in `oversized` |
| `derived.font-family-first` | 128 B | omitted from `derived`, `'font-family-first'` listed in `oversized` |
| each name in `inlineProperties` | 64 B | the name is dropped, `'inlineProperties'` listed in `oversized` |
| `inlineProperties` count | 32 | first 32 in declaration order, `inlinePropertiesTruncated: true` |
| `reason`, keys of `skipped`, `untraversed`, `oversized` entries | fixed strings / integers | — |

Nothing is truncated or guessed. Field caps only keep one element small; the binding bounds are
the serialized style array and the whole serialized report, below.

### Budgets (deterministic)

- **Elements:** at most 50 returned elements per check (`limit` ≤ 50) and 400 per call.
- **Bytes:** the serialized style output of a call — `JSON.stringify` of the array of all style
  result rows, measured in UTF-8 bytes with `TextEncoder` — is at most **1,048,576 bytes**.

A **budget row** has exactly the fields `{ id, kind: 'style', selector, status: 'NOT_TESTED',
reason: 'budget' }`, so its serialized size is known from the configuration before any DOM read.

Before the first check, the reader computes for every style check *i* the reserve `R(i)` = the sum,
over the style checks after *i*, of `1 + bytes(JSON.stringify(budgetRow))` (one comma plus the
row). It then builds each style row completely, in call order, and admits it only if

- the element total including this row is ≤ 400, **and**
- `bytes(serialized array so far, with this row, including brackets and commas) + R(i)` ≤ 1,048,576.

Otherwise that row is replaced by its budget row, and every later style row is a budget row as
well; earlier rows are unaffected. Budget rows always fit, because their room was reserved, so the
final serialized style array is ≤ 1,048,576 bytes by construction (JSON escaping included, since
sizes are measured on `JSON.stringify` output). Exactly 400 elements are allowed; the byte total
equals 1,048,576 only when no later style rows remain (otherwise their reserve is part of the
bound). Non-style rows are not counted in this style budget. There is no wall-clock budget.

**Whole report.** `JSON.stringify(report)` is at most **2,097,152 UTF-8 bytes** (escaping and
non-ASCII included). Every row is bounded by construction: configuration strings have the caps
above, the echoed pathname is capped, style values have their byte caps, and computed strings that
fit/contrast rows echo (`overflowX`, `overflowY`, `fontSize`, `fontWeight`) are kept only up to 64
UTF-8 bytes — a longer one makes that row `NOT_TESTED: oversized-value`. With all caps at their
maximum and worst-case escaping, non-style rows stay near 1 MiB and the style array is ≤ 1 MiB, so
the report stays under the bound. The reader also measures the report with every style row as its
budget row and the longest status strings, replaces non-style rows from the last backwards by
`{ id, kind, selector, status: 'NOT_TESTED', reason: 'report-budget' }` if that ever exceeded the
bound, and admits each style row only if the whole report stays within it; under the current caps
these two fallbacks are defensive and not reached (tests exercise them with a reduced bound).
Every cap is checked by length first (UTF-8 bytes ≥ UTF-16 length), so an oversized string is
rejected before it is encoded or serialized. A required observation that did not fit is
`NOT_TESTED`, never `PASS`. These numbers are initial defaults, changeable only by
a contract change.

### Aggregate

`style` rows are excluded from the aggregate. The aggregate is computed over the other kinds as
today. The report adds a separate summary `styleStatus`: `OBSERVED` if every style row is
`OBSERVED`, `NOT_TESTED` if any style row is `NOT_TESTED`, absent if the call has no style rows.
A caller that needs a style reading must check `styleStatus` or the row itself; an aggregate
`PASS` never implies that a style reading exists. A call containing only `style` checks reports
aggregate `OBSERVED` when at least one row is `OBSERVED`, otherwise `NOT_TESTED` — never `PASS`.
`NOT_TESTED` style rows never change the aggregate of other kinds. `styleStatus: OBSERVED` still
does not mean every required element was read: the caller checks that each required element was
returned and each required property is present.

### Boundaries

- **Traversal:** only the evaluated document; shadow roots, iframes and canvas are not entered,
  only counted in `untraversed`. Closed shadow roots cannot be counted; this is a named limitation.
- **Unknown or custom elements** are read like any other element; their tag is reported.
- **Privacy:** style rows contain tags, ARIA roles, integer boxes, allowlisted computed values,
  the two derived fields and inline property names only, plus the caller's own `id` and
  `selector`; the report also echoes `context` and the capped pathname. Evidence storage follows
  the redaction policy above.
- **Version:** results are attributed by kit release and helper file hash (the helper reports no
  version of its own).
- **Settled state** is the runner's declaration plus the existing font/animation checks; the
  reader does not wait or drive the page.
- **Meaning:** an `OBSERVED` row proves only the listed computed values on the returned elements
  in the declared context. It is not a design PASS, not a role, not a reason.
