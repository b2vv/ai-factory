# Reading design values by meaning

A value (spacing, size, weight, radius, height, color) answers a question about a component:
what it is for, how important it is, where it lives, what it must fit. A value list per
selector keeps the answers and loses the questions, so it cannot tell a system from an
accident. This reference describes how to **find** relevant differences, **understand** why a
value is what it is, and **separate** things that only look related from things that are.

It is a reasoning method, not a scanner. It does not authorize normalizing a design and never
overrides an accessibility or functional requirement. Scale it to scope: a targeted change
checks only the roles it touches and their siblings.

---

## 1. Finding: where to look

| Pattern | How | Surfaces |
|---|---|---|
| **Group by purpose** | Collect each distinct treatment (not every repeat), group by what it does for the user, compare side by side (Frost, *Interface Inventory*). | One thing drawn several ways. |
| **Reverse lookup** | For one value, list every use and ask what the uses share. | Values with no role; values shared by unrelated roles. |
| **Near-duplicates** | Groups whose values are close but not equal. | Differences worth explaining; a small gap is a reason to look, not evidence. |
| **Cross-screen / cross-state sweep** | Follow one role through screens, states, breakpoints and themes in scope. | A role re-drawn per screen, or a state that silently changes it. |
| **Source trace** | Read the source: token, component style, page override, inline, library default, layout. | Values set outside the system; a question, not a defect. |
| **Singletons** | Values that occur once in scope. | A unique role, or a stray value. |

A finding starts as a **candidate**, never as a verdict.

### Comparison key

Compare treatments only **within one key: role × viewport × color scheme/theme × state**.
Viewport comes from the reader's actual viewport, color scheme from the declared and reported
media state, state from the declared context. A difference **between** keys is not classified
automatically: check whether the change is expected — a documented breakpoint or theme rule, a
responsive definition in the source, a state definition, the reference. With that evidence it is
a `variant`; a change that breaks the role on one key (for example on phone) is a finding for that
key; without evidence it is `unexplained`. The key uses the declared color scheme when the context
declares one (themes may be class-based, so a declared scheme that differs from the media query is
not an error), otherwise the reported media result; readings without either are not compared
across schemes.

Values are compared as the **exact strings** the browser returns (`9px`, `normal`, `oklch(…)`)
— except the two derived fields the contract defines (first font family, shadow layer count) —
grouped by equality; near-equal groups are surfaced as near-duplicate candidates, never merged.
Fluid source expressions (`clamp()`, `vw`, custom properties) come from the source read or stay
`source: unresolved`.

### Capturing values

- **Reader.** Rendered values come only from the `style` kind of `ui-measurements`; its input and
  output are defined in one place, the [ui-measurements contract](../../ui-measurements/references/contract.md).
- **Required readings.** Before a check, name what it requires: which elements (by selector and
  role) and which properties. The check uses a reading only if the style row is `OBSERVED` **and**
  every required element was returned **and** every required property of it is present in
  `values`/`derived`. Otherwise the check is `NOT_TESTED`, whatever the measurement aggregate or
  `styleStatus` says (the aggregate excludes style rows; `styleStatus` is per row, not per
  element). In particular: a required element that was skipped (any `skipped` bucket), that lies
  beyond the window (`truncated`), or a required value listed in `oversized` is not observed.
  The skipped and oversized counts go under "not covered"; they are never read as "absent".
- **Caller records** with each reading: the key, the observation status, the role and its
  confidence, and whether the result was `truncated`. A truncated result is a sample: it does not
  count toward `system`, instance counts or candidate norms.
- **Where.** In the agent-driven browser that already shows the page; a project test runner that
  already exists may run the same reader read-only for regression; do not add one.
- **Settled state** follows the existing [browser-state evidence](../../design-pass/references/browser-state-evidence.md) rules; otherwise NOT_TESTED.
- **Source read ≠ rendered observation.** Reading source (including a fixture's code) proves what
  exists or is absent **in the code read**: definitions, usages, inline overrides. It does not stand
  in for observing the rendered state; a check that needs the rendered result stays NOT_TESTED, and
  a finding resting on source alone says `source only`. A claim of absence or non-use (a token no
  sampled screen uses, a control not found) is scoped to the screens and files actually read and is
  reported as such, not as a product defect.
- **Origin** (token vs literal) comes from reading the source. Rules that need it are NOT_TESTED
  without a source read; origin is never inferred from rendered values.
- **Untraversed regions** (shadow roots, iframes, canvas) reported by the reader are not covered.
  `missing-target` with untraversed regions present means "not covered", not "absent".
- **No render stream** (no browser, no evaluation, no access): only source and `approx`; the gap
  is NOT_TESTED / BLOCKED under the shared [viewport contract](../../design-pass/references/viewport-coverage.md).

**Observation status** (per value):

| Status | Meaning |
|---|---|
| `observed` | read by the style reader, or a source line |
| `approx` | from a screenshot or zoom, with scale/DPR/zoom and precision (±px). Can raise a candidate within its precision; cannot confirm a smaller difference. For an image-only reference, a match means "within the stated precision". |
| `unknown` | not observable (cropped, hidden, unavailable state) — same meaning as in [reference-ui-reconstruction](../../reference-ui-reconstruction/SKILL.md) |
| `invalid` | neither observed nor labeled; dropped from evidence, counted under "not covered" |

## 2. Understanding: why might this value be what it is

List plausible reasons and the evidence that would distinguish them:

- **Role and importance** — similar size reads as similar importance (NN/g, *Similarity*).
- **Task context and density** — focused tasks compact, reading/first-run roomier (Carbon).
- **Container constraints** — row height, neighbor alignment, width, touch-target minimum.
- **Derived values** — height landing on a scale step, line-height or border adding space,
  optical compensation for icons, circles, caps or numerals.
- **Content** — numbers, long or translated labels, empty values.
- **Inheritance** — a library or platform default nobody chose.
- **Accessibility** — a contrast or target-size fix applied in some states or backgrounds.
- **History** — copied and tweaked on one screen.
- **Override of a shared component** — one of three causes: defect in the component, missing
  capability, or unexpected combination of parts (Figma, *Design Systems 104*).

Signals that a difference deserves a question (none is proof): no reason fits; the gap is small
and unexplained by context; the value is set outside the system; one instance differs among many;
two variants occur inside one task or region.

**Evidence for a reason.** A reason counts only with evidence: a source line, a context fact, a
documented decision or an owner statement. Without evidence the item stays `unexplained`. If no
reason can be found, say so; do not invent one.

**Role confidence.** Every role carries one of: `confirmed` (design-system definition or owner),
`supported` (at least two independent kinds of evidence: component identity, ARIA/semantics,
behavior, text, task position), `inferred` (anything less). Inferred roles are listed for the
owner and limit the verdict (§4, §6). When the owner corrects or splits a role, verdicts and
decisions issued against the old role are invalidated and reported as changed in the next run.

**Role ID.** A role is recorded under a stable ID: the design-system component name when one
exists, otherwise the owner-confirmed role name, otherwise a provisional ID marked
`provisional`. The ID's provenance and the role's confidence are separate fields: a provisional
ID can name a `supported` role (two independent kinds of evidence, no owner yet); only
insufficient evidence makes the role `inferred`. A provisional ID is replaced by the
component or owner name once one exists, recorded as a mapping. Example: a tile with no
library component and no owner name, whose ARIA `group` role and its position in the overview task
both mark it as a summary → ID `provisional:summary-tile`, confidence `supported`. A
rename or split is recorded as a mapping old → new IDs. Every recorded verdict or decision also
stores the selector(s) and key it was observed on.

## 3. Separating: things that get confused

| Do not confuse | Decide by |
|---|---|
| **Looks alike ↔ means the same** | Purpose for the user, not appearance or class name. One form can carry several meanings by context, so form and meaning are separate fields (Sunkara et al., COLING 2022). Neither name nor token group proves role (W3C DTCG). |
| **DOM structure ↔ perceived grouping** | Judge grouping on the rendered screen; the element tree only locates elements (Xie et al., ESEC/FSE 2022). |
| **Rule break ↔ meaningful difference** | A formal inconsistency can carry meaning (plainer items marking an auxiliary tier). If the difference lines up with a role difference, it is a signal, not a defect; a detector only flags, the owner decides (Yang et al., ICSE 2021). |
| **Intent ↔ slip in a reference** | An approved reference is a norm for intent, not for its own internal conflicts; each conflict is recorded with an owner decision. |
| **Design decision ↔ implementation artifact** | Whether the rendered result differs; rounding, box model and borders can make different numbers for one decision. |
| **Component ↔ instance override** | Whether the difference lives in the shared definition or one usage. |
| **Local fix ↔ system change** | Whether the correction touches one instance or the shared token/component; a system change needs the owner. |

Variant vs drift vs unexplained, and observation vs estimate, are decided by §4 and §1.

## 4. Norms and verdicts

**Agreed norm** — possible sources (unordered; this list sets no priority):
- the project's design-system definition;
- a documented project rule (standards, token lint);
- an approved reference, minus its recorded internal conflicts;
- a de-facto norm the owner adopted into the design standards (§5).

When sources conflict, resolve by the existing facade contract ([design-pass](../../design-pass/SKILL.md) §3: the explicit
request; mandatory accessibility and functional requirements; then authoritative reference >
project > method > generic defaults) and record the conflict. This reference does not change
that priority.

Within that priority, compare scope, provenance and explicit supersession, not just file
location or recency: neither a task record nor the latest timestamp automatically wins.
A verified accepted decision applicable to the same role/context is not canceled solely
because its copied standards entry is missing; report that synchronization gap separately.
For genuinely conflicting norms left unresolved by the priority contract, report both sources
and scopes, keep the dependent verdict `NOT_TESTED`, and ask the owner to resolve them; do not
silently choose a norm.

A dominant value among instances is a **candidate norm** only. External guidelines inform
proposals but are not a product norm. If most or all instances depart from a design-system
definition, report one **norm conflict: system vs product**, not per-instance drift.

**Verdicts:**

| Verdict | When |
|---|---|
| **system** | same role, same treatment within each key, ≥2 non-truncated instances; candidate semantic token |
| **unique role** | one instance; no token candidacy; compared with sibling roles of similar importance |
| **variant** | same role, different key or context, evidenced reason |
| **violation** | a proven failure of an applicable requirement (accessibility, functional, acceptance criterion, or a cross-role rule as defined in §6) — owned by that requirement's rule |
| **drift** | same role, context checked, departs from an agreed norm; role `confirmed` or `supported` |
| **unexplained** | a difference without enough evidence for `violation` or `drift`; goes to the owner |
| **ambiguous role** | role cannot be established; ask the owner |

**Precedence — exactly one deviation verdict per role and cause**, in this order:
1. proven failure of an applicable requirement → `violation`;
2. otherwise, departure from an agreed norm, context checked, role `confirmed`/`supported` →
   `drift`;
3. otherwise → `unexplained`.

`system`, `unique role`, `variant` and `ambiguous role` describe roles without a deviation.
`violation` and `drift` are findings; `unexplained` is never also a finding. In the ux-review
rule pass, the outcome "violation" is reported as `violation` or `drift` by this precedence.
Different roles with different values are not a finding.

**Owner decisions** on single items: `keep-as-variant` · `normalize` · `separate` · `ask`.
A **norm request** (`record-norm`) is different: it asks the owner to adopt a new product rule
into the design standards.

A scale (type, spacing, radius) is described as **roles → values** from these verdicts, not as
a sorted list of numbers.

## 5. Outputs and where they live

- **Findings** — `violation` and `drift`, with severity (§6).
- **Decisions for the owner** — `unexplained`, `ambiguous role`, inferred roles, candidate
  norms, norm conflicts; a separate, unranked section, **grouped by role and cause** with their
  instances (one decision may cover all keys of a role). Two kinds:
  - *stylistic* (which treatment to keep, whether to normalize) — do not block readiness;
  - *gating* (an acceptance criterion, a required state, an allowed deviation from an approved
    reference, whether an accessibility exception applies) — the affected check stays `BLOCKED` /
    `NOT_TESTED` until decided; never `PASS`.
  No open decision becomes `drift` without confirmation.
- **Recording decisions** — an accepted single-item decision (and an accessibility-driven
  variant with reason `a11y`) is written into the current task record at normal closeout, keyed
  by role ID, cause and key, with the selector(s) it was observed on; no extra command. An audit without a task record writes them into
  its report and the owner chooses where it is kept.
- **Across tasks** — a decision lives only in its task record. A later run finds earlier
  decisions through the project's existing task index or by searching earlier task records for
  the same role ID; it does not assume them. ui-audit records its consistency decisions with the
  same keys (role ID, cause, key, selector), so a run finds decisions from either. A decision that must hold for all future work goes
  through `record-norm` into the design standards. A recorded decision whose role or selector no
  longer exists is reported as stale and never applied silently. If there is no task index or
  earlier records cannot be read, say so: earlier decisions are not covered and every item is
  treated as a new candidate.

## 6. Rules for review

The rules themselves are in [rules.md](rules.md) §12 (seven `[consistency]` rules and
`[wcag] 1.4.1`), in its native form `principle → violation: <observable check> → URL`. This
section holds what they share: violation criteria, severity and dedup.

**Violation criteria by rule type:**
- *Consistency* rules — a departure from an agreed norm with role `confirmed`/`supported` is
  `drift`; otherwise a decision for the owner.
- *Cross-role* rules (distinguishable roles, importance ↔ weight, affordance) — `violation` only
  when **both** roles are `confirmed` or `supported` **and** a task with a stated source shows
  that users must tell them apart, rank them or recognise them as interactive here, and the
  rendered treatment does not allow it. With an inferred role or task → `unexplained`.
- *Accessibility* criteria — ux-review severity directly; never through this gate.

Every hit is classified as `violation`, `drift` or a decision per §4, and cross-role rules per
the cross-role criteria above.

**Severity** (ux-review ranking applies): consistency findings (`drift`, cross-role `violation`)
are minor by default, major when the inconsistency changes what users understand (a status reads
as a different kind of thing, an interactive element looks inert); never `blocker` on consistency
alone. A major one counts in the ux-review readiness gate like any other major finding. **Dedup:** for these
rules the unit is role × cause, applied through ux-review's existing Dedup step.

## Sources (fetched 2026-11-18)

- Rachel Krause, *Maintain Consistency and Adhere to Standards*, NN/g, 2021-01-10 — https://www.nngroup.com/articles/consistency-and-standards/
- Aurora Harley, *Similarity Principle in Visual Design*, NN/g, 2020-09-06 — https://www.nngroup.com/articles/gestalt-similarity/
- Kelley Gordon, *Visual Hierarchy in UX: Definition*, NN/g, 2021-01-17 — https://www.nngroup.com/articles/visual-hierarchy-ux-definition/
- Brad Frost, *Interface Inventory*, 2013-07-10 — https://bradfrost.com/blog/post/interface-inventory/
- IBM Carbon, *Typography: style strategies* — https://carbondesignsystem.com/elements/typography/style-strategies/
- Material Design 3, *Applying type* — https://m3.material.io/styles/typography/applying-type
- Bo Yang et al., *Don't Do That! Hunting Down Visual Design Smells in Complex UIs Against Design Guidelines*, ICSE 2021 — https://xin-xia.github.io/publication/icse213.pdf
- Sunkara et al., *Towards Better Semantic Understanding of Mobile Interfaces*, COLING 2022 — https://ar5iv.labs.arxiv.org/html/2210.02663
- Xie et al., *Psychologically-Inspired, Unsupervised Inference of Perceptual Groups of GUI Widgets*, ESEC/FSE 2022 — https://ar5iv.labs.arxiv.org/html/2206.10352
- Figma, *Design Systems 104: Making metrics matter*, 2025-02-11 — https://www.figma.com/blog/design-systems-104-making-metrics-matter/
- W3C Design Tokens Community Group, *Design Tokens Format Module 2025.10* (CG report) — https://www.designtokens.org/tr/drafts/format/
- WCAG 2.2, *Understanding 1.4.1 Use of Color* — https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html

The reasons in §2 and the separations in §3 are this kit's method, supported but not dictated
by these sources.
