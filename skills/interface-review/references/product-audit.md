# Semantic audit of an existing product

Goal: in a live product, discover its components, understand what each means for the user,
find logical inconsistencies, and **propose** changes that make meaning clearer. The audit is
read-only; its output is the interface-review report plus the audit sections in §5.

Read the [semantic-consistency reference](../../ux-review/references/semantic-consistency.md) first (below: *the reference*). Below, **Rule** marks what invalidates the audit if skipped;
**Recommended** marks a default that may be changed with a written reason.

## 0. Scope

- **Rule.** Name the product area, the user roles and their main tasks, and the **source** of
  each task (owner, product docs, analytics, or `inferred` — listed for owner confirmation).
- **Rule.** List the routes/screens in scope and how the list was closed (navigation, router
  config, owner). Unlisted areas are out of scope, not clean.
- **Rule.** State the sampling budget and the keys sampled: templates × key states × the
  baseline viewports of the shared [viewport contract](../../design-pass/references/viewport-coverage.md) × color schemes the product supports.
  Unsampled keys go under "not covered".
- **Recommended.** Sample by template and task (list, detail, form, dashboard, settings,
  empty/error), not by page count; narrow a large product to one task or section first (NN/g,
  *How to Conduct a Heuristic Evaluation*). A product with one template marks cross-screen
  checks N/A with the reason and weights cross-state and cross-breakpoint sweeps instead.
- **Rule.** Use authorized accounts and fixtures; do not create or change live data.
- **Rule.** Before starting, look up earlier decisions and norms as semantic-consistency §5
  "Across tasks" describes; report changes against them.

## 1. Discovery

**Source first.** Read the component library, tokens/theme and shared styles; count usage of
components, classes and tokens by searching the source. Count CSS-in-JS by component, not by
generated class. Label these counts `in source` (they include dead or flagged code). A source read
proves presence or absence in the code read only (semantic-consistency §1, *Source read ≠ rendered
observation*): an unused token or a missing control is reported for the sampled screens and files,
not as a defect of the product. This read
also provides value origin for the reference rule "Values through the system".

**Render second.** On each sampled key, read candidate elements with the `style` kind of [ui-measurements](../../ui-measurements/references/contract.md)
(semantic-consistency §1, *Capturing values*). Select candidates by meaning signals: interactive elements,
distinctively styled text, repeated containers, ARIA roles, library components. Label these
counts `in sample`; never mix them with source counts in ranking. If untraversed regions
(shadow roots, iframes, canvas) hold most of a key's components, that key is NOT_TESTED rather
than a short clean list.

**Group** by exact values within one comparison key (semantic-consistency §1).

**Norms** come from semantic-consistency §4; the product's own dominant treatment of a role is a
candidate norm to confirm, as in data-driven consistency checks over an app's own screens
(Park et al., arXiv 2023). Without a design system or scale, system-bypass and
override checks are N/A (not clean), and the deliverable becomes a proposed role inventory with
candidate roles → values, each marked `new, needs owner`.

## 2. Roles and importance

- **Rule.** Every treatment gets a role in product words with its evidence and role confidence
  (semantic-consistency §2).
- **Rule.** Importance is ranked **per user role and task** (primary → supporting → metadata),
  each with its source; `inferred` importance is listed for the owner.
- **Recommended.** Show the role inventory and inferred items to the owner before ranking
  proposals. If the owner is unavailable, the audit still completes: stylistic decisions stay
  open; checks that depend on a gating decision stay `BLOCKED` / `NOT_TESTED`.

## 3. Checks

Apply the semantic-consistency rules (ux-review `rules.md` §12, criteria in semantic-consistency §6), including the cross-role
rules *Importance follows weight* and *Affordance consistency* and WCAG 1.4.1. Audit mode adds
one analysis:

- **Override causes.** For clustered overrides or detached components, decide which of the
  three causes in semantic-consistency §2 the evidence supports; each leads to a different proposal.

## 4. Proposals

Each proposal names a **target**: normalize to an existing token/component · define a variant ·
introduce a semantic token or role · rebalance hierarchy · separate look-alikes · request a norm
(`record-norm`, semantic-consistency §4) · ask. The owner answers with a decision from semantic-consistency §4.

Each proposal contains:
- role (with role ID), inconsistency and evidence: screens, keys, selectors, values with
  observation status, origin or `source: unresolved` — stored under the existing evidence
  redaction policy;
- counts with their label (`in sample` / `in source`);
- target: existing token/component, or a new one marked as new (no silent new scale step);
- expected effect for the stated user role and task;
- blast radius: one instance vs shared component/token;
- accessibility: a fix is proposed for the whole role so it does not create new drift, but each
  instance is checked in its own states and backgrounds; a requirement outranks any style;
- concept fit ([concept-fit](../../anti-slop-design/references/concept-fit.md) §3), two separate outcomes: concept compatibility
  (`compatible` / `extends concept` / `conflicts` / `NOT_TESTED`) for every proposal, and visual
  fit (`fits` / `conflicts` / `NOT_TESTED`) where the risk of the change warrants showing it
  (outside the product), otherwise visual fit `NOT_TESTED`.

**Order:** major before minor; then larger instance/screen count; then shared-component changes
before local ones; avoid reopening closed design axes (palette, type family, radius system)
without the owner. No changes are applied during the audit; no full redesign for local problems.

## 5. Report

The interface-review report (findings ranked, decisions for the owner as its own section, gate),
plus these audit sections:

1. Scope and **run identity**: build/commit, accounts/fixtures, sampled routes × keys, reader
   kit release and helper file hash, earlier records consulted (or "none readable").
2. Role inventory with role confidence.
3. Proposals (§4), in order.
4. Not covered: unsampled keys, untraversed regions, NOT_TESTED readings, truncated samples,
   skipped elements by reason, `oversized` values, count of `invalid` values.

## Additional sources (beyond the semantic-consistency reference)

- Kate Moran, Kelley Gordon, *How to Conduct a Heuristic Evaluation*, NN/g, 2023-06-25 — https://www.nngroup.com/articles/how-to-conduct-a-heuristic-evaluation/
- Park, Kim, Kim, Seo, *Computational Approaches for App-to-App Retrieval and Design Consistency Check*, arXiv 2023 (norms from the product's own screens) — https://arxiv.org/html/2309.10328
- Figma, *Design system audits* — https://www.figma.com/solutions/design-system-audits/
