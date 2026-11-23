# Concept fit — proposals keep the product's character, not only pass contrast

A proposal can use existing tokens and pass contrast and still look like it came from another
product: a new emphasis device, a new density, a decoration the product never uses. This
reference adds a short **concept card** and two checks. It adds no facade and no new document
per task; each part attaches to an existing step (see the last section).

Accessibility is never weakened for the concept. Source priority is the existing
[design-pass](../../design-pass/SKILL.md) §3 contract.

## 1. Concept card

Built by [frontend-design](../../ship/frontend-design/SKILL.md) from evidence already gathered in its plan (§2 decided axes, §3 what
repeats) and the [anti-slop](../SKILL.md) §0 design read. One line each, each with evidence (screens, tokens, role
IDs from the [semantic-consistency](../../ux-review/references/semantic-consistency.md) reference):

- **Design read**
- **Closed axes** — where palette, type, radius, spacing are defined
- **What repeats** — the system-branch signature items listed in frontend-design §3 (by
  reference, not restated)
- **Emphasis vocabulary** — how the product makes something important (weight, size, color,
  position, space)
- **Does not do** — explicit restraints (e.g. accent color only for actions)

- A line without evidence is `absent` or `unknown`; it is never invented to fill the card (a
  product may have no motif or structural device).
- A small local change fills only the lines it touches.
- Agent-inferred lines are `inferred` and go to the owner.
- The product's current look is evidence of the concept but may itself contain drift; it is not
  a norm by itself (norms: semantic-consistency §4).
- Where the card is kept is an open owner decision (design standards or task record); until it
  is decided, the card is written into the task record, or, without one, into the audit report (audit mode)
  or the design-pass final report (design-pass §6).

## 2. Two separate checks

| Check | Establishes | How |
|---|---|---|
| **Concept compatibility** | that the *described* proposal is consistent with the card | the proposal names the card line it relies on; emphasis only through the emphasis vocabulary; nothing from "does not do"; a new device only as an explicit `extends concept` proposal |
| **Visual fit** | that a *concrete variant*, seen in context, looks like the same product | the variant shown next to its real neighbours on the same key (viewport, color scheme, state), then the anti-slop §3 pre-flight applied to what was shown |

Compatibility never substitutes for visual fit.

**Showing a variant** (proportional; a prototype is a decision tool, not a required artifact):
- simple case → the existing local preview or Storybook, if the project already has it;
- ambiguous or complex case → a temporary prototype or variants side by side with the real
  screen;
- a screenshot of the current screen proves the problem, not that a future solution fits.

The product is not changed to show a variant; in audit mode the showing happens outside the
product (existing preview/Storybook or a temporary prototype).

**Temporary vs evidence.** Temporary code, prototypes and stands are removed after the check.
Before removal, a short record goes into the task record — or, without a task record, into the audit
report (semantic-consistency §5) or the design-pass final report (design-pass §6). The record holds the variant shown (what it changed), state,
viewport, color scheme, verdict, decision, and a link to a kept screenshot if one exists.
A verdict without this record cannot be verified and is treated as `NOT_TESTED`.

## 3. Verdicts and their effect

Each check has its **own** outcome; a proposal carries both, e.g. `compatibility: compatible ·
visual fit: NOT_TESTED`.

**Concept compatibility** (the described proposal against the card):

| Outcome | Means | Effect |
|---|---|---|
| `compatible` | names the card lines it relies on; uses an existing emphasis means **under the norm already accepted for this role and context**; nothing from "does not do" | may go to visual fit or, where showing is not warranted, to implementation |
| `extends concept` | needs a new device, a change to a card line, or **changes the accepted norm itself** even with an existing means (e.g. size becomes the main emphasis for this role for the first time) | owner approval of the extension before implementation; then visual fit |
| `conflicts` | uses something from "does not do" or an emphasis outside the vocabulary | not implemented as is; revise, or propose `extends concept` |
| `NOT_TESTED` | no card, or the card lines this proposal touches are `unknown`/`inferred` and unconfirmed | not reported as `compatible`; card lines go to the owner |

If compatibility depends on an unresolved norm or role decision, report `NOT_TESTED` and name
that dependency. A conditional scenario after resolution may be described separately, never
as the current final `compatible` verdict. An unrelated open decision does not block compatibility.

**Visual fit** (a concrete variant actually seen):

| Outcome | Scope | Effect |
|---|---|---|
| `fits` | the shown variant, in the shown states/viewports/color schemes only | may proceed; post-implementation re-check in the product (states, responsive keys) is still required |
| `conflicts` | the shown variant | not implemented as is; revise and show again |
| `NOT_TESTED` | not shown, or no evidence record | never reported as `fits` |

**Proceed rule.** Implementation may start only when compatibility is `compatible` (or an
approved `extends concept`) **and** visual fit is `fits` — or visual fit is `NOT_TESTED` and the
acceptance criteria and risk of the change allow that (a small local change; recorded as
`NOT_TESTED`, never as `fits`). Visual fit `fits` never repairs a compatibility `conflicts`;
`compatible` never stands in for a visual fit that the acceptance criteria require.

Concept-fit verdicts are design-quality results, not acceptance: open mandatory acceptance
criteria or required evidence do not become PASS by being listed as decisions
(semantic-consistency §5, gating decisions).

## 4. Accessibility

A requirement is never weakened for the concept. Contrast PASS alone establishes neither role
preservation nor visual fit. Seek an accessible solution within the concept that preserves the
required role distinctions (for example through existing palette tokens). If none exists, propose
an explicit concept change (compatibility `extends concept`) for the owner; never silently remove
a required role distinction. Accessibility requirements remain mandatory either way.

## 5. Where it attaches

- **frontend-design** — builds the short card from evidence already gathered in its plan.
- **design-pass** — before implementation, runs concept compatibility and, where the change
  warrants it, the visual-fit showing; after implementation, the re-check in its browser pass.
- **anti-slop-design** — owns the visual-fit verdict; its §3 pre-flight is also applied to a shown
  variant before implementation (in addition to its existing use before "done").
- **interface-review** — merges the verdicts into its report under the visual lens, without
  repeating the research.
- **Audit mode** — each proposal carries a compatibility outcome; visual fit is shown where the
  risk warrants it, otherwise `NOT_TESTED`.
