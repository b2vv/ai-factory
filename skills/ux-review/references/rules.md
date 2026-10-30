
# ux-review — ruleset (cited UX rules)

Each rule's format: `[category] NAME — principle → HOW TO CHECK / what constitutes a violation → source(URL)`.
The **HOW TO CHECK field is mandatory**: a rule without an observable check does not enter the report.

Thresholds that DIFFER between sources (name both; do not invent a single one):
- **Touch target:** WCAG 2.2 min 24×24 CSS px (AA, 2.5.8) · WCAG enhanced 44×44 (AAA, 2.5.5) · Apple HIG 44×44 pt · Material 48×48 dp + 8 dp spacing. Apply by context (touch-first action → 44/48; dense desktop table → 24 with spacing).
- **Response time—different measures:** 0.1 s = perceived immediacy · **0.4 s (Doherty)** = target interactivity · 1 s = continuity-of-thought boundary · 10 s = attention boundary (beyond it, percentage progress is mandatory). Do not confuse the 400 ms target with 1 s/10 s thresholds.
- **Zoom—two criteria:** 1.4.4 Resize Text = text up to 200% without loss · 1.4.10 Reflow = no two-dimensional scrolling at 400% (equivalent to 320 CSS px). Check both; do not conflate them.

---

## 1. Nielsen 10 Usability Heuristics
Source for all 10: https://www.nngroup.com/articles/ten-usability-heuristics/

[heuristic] Visibility of system status — the system communicates what is happening promptly → violation: an action without loading/confirmation/state change; no “saved/sent”.
[heuristic] Match system & real world — user language, familiar concepts, natural order → violation: internal jargon, codes or developer terms in the UI.
[heuristic] User control & freedom — an explicit emergency exit: undo/cancel/back → violation: irreversible actions without undo, a modal without dismissal, flow traps.
[heuristic] Consistency & standards — identical words/actions mean the same thing; platform conventions → violation: a button behaves differently on different screens, nonstandard icons/terms.
[heuristic] Error prevention — prevention is better than notification → violation: a destructive action without confirmation/constraints; a free-text field where selection is needed.
[heuristic] Recognition over recall — make options visible rather than requiring memory → violation: users must remember data from a previous screen; hidden requirements.
[heuristic] Flexibility & efficiency — accelerators for experienced users without obstructing beginners → violation: no shortcuts/defaults/repetition of frequent actions.
[heuristic] Aesthetic & minimalist design — no excess competing with what matters → violation: clutter, decoration distracting from the task.
[heuristic] Help users with errors — plain-language errors, specific problem + solution → violation: a cryptic code without explanation or a correction path.
[heuristic] Help & documentation — ideally no help needed; when needed, easy to find, task-focused, concrete steps → violation: help is hard to find/disconnected from context.

## 2. Laws of UX
[law] Jakob's Law — users expect your product to work like familiar others → violation: unconventional patterns where an established convention exists → https://lawsofux.com/jakobs-law/
[law] Fitts's Law — time to reach a target depends on distance and size → violation: small distant click targets; the primary action hidden/shrunk → https://lawsofux.com/fittss-law/
[law] Hick's Law — decision time grows with the number/complexity of choices → violation: long menus/many equal options without grouping/defaults → https://lawsofux.com/hicks-law/
[law] Miller's Law — working memory holds ~7±2 items → violation: long ungrouped lists/fields; break into chunks → https://lawsofux.com/millers-law/
[law] Postel's Law — liberal input, strict output → violation: rejecting valid input because of formatting (spaces in a card/phone number) → https://lawsofux.com/postels-law/
[law] Tesler's Law — irreducible complexity must be borne by someone → violation: unavoidable complexity shifted onto the user instead of the system → https://lawsofux.com/teslers-law/
[law] Peak-End Rule — experience is judged by its peak and ending → violation: a painful peak (error) or ending (payment/confirmation) without care → https://lawsofux.com/peak-end-rule/
[law] Aesthetic-Usability Effect — attractive things are perceived as more usable → violation: untidy visuals reduce trust and tolerance for small problems → https://lawsofux.com/aesthetic-usability-effect/
[law] Doherty Threshold — productivity rises with interaction <400 ms → violation: UI response >400 ms without optimistic update/feedback → https://lawsofux.com/doherty-threshold/
[law] Law of Proximity — nearby objects form a group → violation: a label farther from its own field than another; ungrouped actions → https://lawsofux.com/proximity/
[law] Law of Common Region — a shared boundary/background groups items → violation: related elements without a shared container/card → https://lawsofux.com/common-region/
[law] Serial Position Effect — first and last items are remembered better → violation: key navigation items/actions hidden in the middle → https://lawsofux.com/serial-position-effect/
[law] Zeigarnik Effect — unfinished tasks are remembered better → violation: no progress indicator/checklist for a multistep flow → https://lawsofux.com/zeigarnik-effect/
[law] Von Restorff (Isolation) Effect — a distinct element is remembered → violation: multiple “primary” CTAs compete; the primary action is not visually distinguished → https://lawsofux.com/von-restorff-effect/


## 3. WCAG 2.2 (UX-related SC)
[wcag] 2.5.8 Target Size (Min) AA — targets ≥24×24 CSS px or sufficient spacing → violation: a <24px click target without a spacing/inline/UA/essential exception → https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
[wcag] 2.5.5 Target Size (Enhanced) AAA — targets ≥44×44 CSS px → violation (AAA): below 44px for primary actions → https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html
[wcag] 2.4.7 Focus Visible AA — visible focus indicator → violation: outline:none without a replacement; invisible focus → https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html
[wcag] 2.4.11 Focus Not Obscured (Min) AA — focused element at least partially visible → violation: sticky header/banner obscures focus → https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html
[wcag] 3.2.3 Consistent Navigation AA — repeated navigation in the same order → violation: navigation items change order/location across pages → https://www.w3.org/WAI/WCAG22/Understanding/consistent-navigation.html
[wcag] 3.2.4 Consistent Identification AA — components with the same function identified consistently → violation: the same action has different labels/icons → https://www.w3.org/WAI/WCAG22/Understanding/consistent-identification.html
[wcag] 3.2.6 Consistent Help A — help/contact in the same location on all pages → violation: help link “jumps” → https://www.w3.org/WAI/WCAG22/Understanding/consistent-help.html
[wcag] 3.3.1 Error Identification A — erroneous field identified, error described in text → violation: only a red border without text; color-only error → https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html
[wcag] 3.3.3 Error Suggestion AA — suggest a correction if known → violation: “invalid format” without a correct example → https://www.w3.org/WAI/WCAG22/Understanding/error-suggestion.html
[wcag] 3.3.4 Error Prevention (Legal/Financial/Data) AA — reversibility / checking / confirmation → violation: irreversible payment/deletion without confirm/review → https://www.w3.org/WAI/WCAG22/Understanding/error-prevention-legal-financial-data.html
[wcag] 3.3.6 Error Prevention (All) AAA — the same for any submission → violation (AAA): submission without reversibility/checking/confirmation → https://www.w3.org/WAI/WCAG22/Understanding/error-prevention-all.html
[wcag] 1.4.3 Contrast (Min) AA — text 4.5:1; large (≥18pt/14pt bold) 3:1 → violation: gray text below 4.5:1 → https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
[wcag] 1.4.11 Non-text Contrast AA — UI components/states 3:1 against adjacent colors → violation: input border/icon/focus ring below 3:1 → https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html
[wcag] 3.3.7 Redundant Entry A — do not ask for the same information twice within a session → violation: repeated address/email entry without autofill/“same as” → https://www.w3.org/WAI/WCAG22/Understanding/redundant-entry.html
[wcag] 3.3.8 Accessible Authentication (Min) AA — no cognitive test for login → violation: password paste prohibited; puzzle CAPTCHA without an alternative → https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html
[wcag] 2.5.7 Dragging Movements AA — a single-pointer alternative to dragging → violation: reorder/slider only by dragging, without a click alternative → https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html


## 4. Forms
[form] One thing per page — one question/decision per page (group only where research supports it) → violation: a long multisection form where focus is lost → https://design-system.service.gov.uk/patterns/question-pages/
[form] Label above field — persistent visible label above the field → violation: label disappears/left label clips the field on mobile → https://baymard.com/blog/mobile-form-usability-label-position
[form] Placeholder ≠ label — do not use a placeholder instead of a label → violation: the hint disappears during input → memory and error-correction failures → https://www.nngroup.com/articles/form-design-placeholders/
[form] Inline validation — validate at the right time (on blur/after completing the field, not every character), with the error beside the field + highlighting → violation: errors only on submit or “on every character” → https://baymard.com/blog/inline-form-validation ; https://www.nngroup.com/articles/errors-forms-design-guidelines/
[form] Error wording — describe what happened + how to fix it; no jargon/“please/sorry/you forgot” → violation: “An error occurred”/“This field is required” without guidance → https://design-system.service.gov.uk/components/error-message/
[form] Error summary — summarize errors at the top with links to fields; the same text in the summary and beside the field → violation: no navigation to the first error in a long form → https://design-system.service.gov.uk/components/error-message/
[form] Preserve input on error — do not clear fields on error → violation: a failed submission erases the form → https://design-system.service.gov.uk/components/error-message/
[form] Input types & autocomplete — correct type/inputmode/autocomplete → violation: email as type=text without autocomplete; no numeric keyboard → https://www.nngroup.com/articles/web-form-design/
[form] Destructive confirmation — destructive/financial/legal actions reversible, checked or confirmed → violation: one-click delete/pay without confirm/undo → https://www.w3.org/WAI/WCAG22/Understanding/error-prevention-legal-financial-data.html
[form] Logical grouping — group related fields (proximity/common region) → violation: chaotic field order; a label closer to another field → https://lawsofux.com/proximity/


## 5. Tables / data lists
[table] Numeric right-align — numbers right-aligned, preferably tabular/monospaced digits → violation: left-aligned numbers make place values hard to compare → https://www.nngroup.com/articles/data-tables/
[table] Freeze headers — freeze the header row and identifier column during scrolling → violation: scrolling loses the meaning of a column/row → https://www.nngroup.com/articles/data-tables/
[table] Row tracking — zebra/light borders/hover to track the row → violation: an uninterrupted surface without visual landmarks → https://www.nngroup.com/articles/data-tables/
[table] Human-readable first column — first column = understandable identifier, not auto-id → violation: UUID/numeric key in the first column → https://www.nngroup.com/articles/data-tables/
[table] Row/batch actions — actions through checkboxes + Select All; avoid hover-only menus → violation: actions visible only on mouse hover → https://www.nngroup.com/articles/data-tables/
[table] Filters/sort visible state — noticeable filters + explicit indication of active filter/sort → violation: unclear that the list is filtered/why it is empty → https://www.nngroup.com/articles/data-tables/
[table] Edit in side panel — edit in a nonmodal side panel, not a modal hiding the table → violation: a modal covers other rows' context → https://www.nngroup.com/articles/data-tables/
[table] Narrow-screen strategy — on narrow screens: horizontal scroll with a sticky column (identifier + actions) or stacked cards, without clipping → violation: the table breaks the layout/is clipped; actions disappear during horizontal scrolling → https://www.nngroup.com/articles/mobile-tables/
[table] Empty/zero state — an empty table explains what will be here and offers an action → violation: emptiness without explanation (loading? error?) → https://www.nngroup.com/articles/empty-state-interface-design/


## 6. Navigation / IA
[nav] Single primary nav — one primary navigation, stable across screens → violation: competing navigation systems or navigation changing order → https://www.w3.org/WAI/WCAG22/Understanding/consistent-navigation.html
[nav] Current-state visibility — visible current location (active state) → violation: no highlight for the current item/step → https://www.nngroup.com/articles/ten-usability-heuristics/
[nav] Breadcrumbs for depth — breadcrumbs in deep hierarchies → violation: a deep section with no path back through levels → https://www.nngroup.com/articles/breadcrumbs/
[nav] Consistent identification — identical actions have identical labels/icons → violation: “Delete” is sometimes a button, sometimes a trash icon, sometimes “Remove” → https://www.w3.org/WAI/WCAG22/Understanding/consistent-identification.html


## 7. Feedback and states
[state] Loading threshold — <1s nothing; 1–10s spinner/skeleton; >10s progress bar with % and cancellation → violation: a spinner for <1s (flickering) or a blank screen for >10s → https://www.nngroup.com/articles/response-times-3-important-limits/
[state] Perceived latency — response <400ms or optimistic update/immediate feedback → violation: a click without reaction for >400ms → https://lawsofux.com/doherty-threshold/
[state] Empty states instructive — empty state explains what could be here and offers an action → violation: an entirely empty screen → confusion → https://www.nngroup.com/articles/empty-state-interface-design/
[state] Error states actionable — what happened + how to fix it, next to the cause → violation: generic “Something went wrong” without a next step → https://design-system.service.gov.uk/components/error-message/
[state] Success + undo — confirm success; provide undo for destructive actions → violation: silent success; deletion without “Undo” → https://www.nngroup.com/articles/ten-usability-heuristics/
[state] Progress indicator >10s — long operations with percentage progress and a time estimate → violation: an endless spinner for a long operation → https://www.nngroup.com/articles/progress-indicators/


## 8. Content / microcopy
[copy] Action-oriented buttons — button label = action/outcome (verb) → violation: “OK/Submit/Yes” instead of “Save changes/Delete course” → https://www.nngroup.com/articles/ten-usability-heuristics/
[copy] User's language — user vocabulary, no jargon or codes → violation: technical terms/internal names in UI → https://www.nngroup.com/articles/ten-usability-heuristics/
[copy] Consistent terminology — one term per concept throughout the product → violation: “course/program/class” used as synonyms → https://www.w3.org/WAI/WCAG22/Understanding/consistent-identification.html
[copy] Predictability — label/action fulfills its promise → violation: “Save” also publishes; a link leads elsewhere → https://lawsofux.com/jakobs-law/


## 9. Mobile/touch/responsive
[mobile] Touch target — ≥44×44 pt (Apple HIG) / ≥48×48 dp (Material); WCAG min 24px / AAA 44px: name the applicable threshold → violation: a 24px icon button as the primary touch action → https://developer.apple.com/design/human-interface-guidelines/accessibility ; https://m3.material.io/foundations/designing/structure
[mobile] Target spacing — sufficient space between targets (Material ~8dp) → violation: dense small targets → mistaken taps → https://m3.material.io/foundations/designing/structure
[mobile] No 2D scroll (Reflow) — content without horizontal scrolling at 400% (320 CSS px), except exceptions (tables/maps) → violation: a wide block breaks the viewport → https://www.w3.org/WAI/WCAG22/Understanding/reflow.html
[mobile] Resize text 200% — text readable when enlarged to 200% without loss/overlap → violation: clipping/overlapping at 200% text → https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html


## 10. Cognitive load
[cog] Progressive disclosure — show only what is needed now, reveal the rest on demand → violation: all options/fields on one screen at once → https://www.nngroup.com/articles/progressive-disclosure/
[cog] Smart defaults — sensible defaults instead of empty required choices → violation: a mandatory choice without an obvious default → https://lawsofux.com/hicks-law/
[cog] Recognition over recall — recognition instead of recall (visible options, recents, autofill) → violation: users must remember a code/name from another screen → https://www.nngroup.com/articles/ten-usability-heuristics/
[cog] Chunking 5±2 — group into blocks of ~5±2, not long ungrouped lists → violation: a menu/form with 15 equal items without groups → https://lawsofux.com/millers-law/


## 11. Interactive control states
[states] Interaction-state matrix — each interactive control defines and visually distinguishes rest / hover / active(pressed) / focus / disabled / loading → violation: hover=rest; no pressed feedback; disabled indistinguishable from active; loading without indication → https://m3.material.io/foundations/interaction/states/overview
[states] Focus separate from hover — visible keyboard focus state, not just mouse hover → violation: hover exists, focus does not (keyboard is “blind”) → https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html
[states] Disabled explains why — clear WHY a control is unavailable (hint/text); better to hide unavailable actions than show lifeless gray → violation: a gray control without any explanation → https://www.nngroup.com/articles/ten-usability-heuristics/
[states] Loading/pending on the control — an asynchronous action shows pending on the control itself (spinner / temporarily disabled), not a “dead click” → violation: click without reaction, unclear whether it is running → https://www.nngroup.com/articles/progress-indicators/

---


## Most authoritative sources (for citation)
- NN/g 10 Usability Heuristics — https://www.nngroup.com/articles/ten-usability-heuristics/
- NN/g Response-Time Limits — https://www.nngroup.com/articles/response-times-3-important-limits/
- NN/g Placeholders Are Harmful — https://www.nngroup.com/articles/form-design-placeholders/
- NN/g Data Tables / Mobile Tables — https://www.nngroup.com/articles/data-tables/ , https://www.nngroup.com/articles/mobile-tables/
- NN/g Empty States / Progressive Disclosure — https://www.nngroup.com/articles/empty-state-interface-design/ , https://www.nngroup.com/articles/progressive-disclosure/
- NN/g Breadcrumbs — https://www.nngroup.com/articles/breadcrumbs/
- Laws of UX — https://lawsofux.com/
- WCAG 2.2 (W3C Rec) + Understanding pages — https://www.w3.org/TR/WCAG22/
- GOV.UK Design System — https://design-system.service.gov.uk/
- Baymard Institute (form research) — https://baymard.com/blog/mobile-form-usability-label-position
- Apple HIG — https://developer.apple.com/design/human-interface-guidelines/ · Material 3 — https://m3.material.io/


All URLs were confirmed by fetch as of 2026-10-14 (the dead `nngroup.com/articles/hicks-law/` was replaced with lawsofux + NN/g progressive-disclosure).


## Anti-patterns (4-field; shared template + cross-cutting rules in `ai-factory/reference-anti-patterns.md`)

Each rule below is How-not-to / How-to / Exceptions / Verify. Accessibility items are tagged **REQUIREMENT**
(a WCAG success criterion in scope for the project's target level — A/AA, plus any AAA criterion the project
targets or has agreed — no taste/brand/density exception) or **preference** (a stylistic choice that is not a
success criterion), per the central doc's cross-cutting rule 1. An AAA criterion out of scope at an AA target is
scoped-out, not a "preference"; name the applicable threshold rather than dismissing it.

- **Navigation / IA (§6).** How-not-to: nav items that change order or location across pages (3.2.3). How-to:
  keep repeated navigation in a consistent order and place. Exceptions [REQUIREMENT]: none at taste level.
  Verify: diff the nav across pages — reordering is a violation, not a redesign choice.
- **Forms + validation (§4, WCAG 3.3.x).** How-not-to: a color-only error with no text (3.3.1); losing entered
  values on error. How-to: identify the erroneous field in text beside it; keep the form editable with values
  intact. Exceptions [REQUIREMENT]: none for the text identification. Verify: with color removed, is the error
  still conveyed? If not, violation.
- **Loading / empty / error states (§7).** How-not-to: only a happy-state design; a blank screen on 0 items or a
  dead end on failure. How-to: design empty (explain + next action), loading (progress), and error (cause +
  recovery) states. Exceptions: a transient sub-second load may skip a spinner. Verify: force 0 items / a failed
  request — is there a usable state, or a dead end?
- **Dangerous actions.** How-not-to: an irreversible action (delete, overwrite) with no confirm or undo. How-to:
  confirm with consequence named, or provide undo. Exceptions: trivially reversible actions need neither. Verify:
  can the user recover after one wrong click? If not, it needs a guard.
- **Responsiveness (§9).** How-not-to: fixed-width layout that clips or hides actions at phone/tablet widths.
  How-to: verify each baseline viewport (viewport-coverage contract) and text-reflow separately. Exceptions:
  a documented desktop-only tool. Verify: at each baseline viewport, is every primary action reachable?
- **Animation.** How-not-to: motion that ignores `prefers-reduced-motion`; motion as the only state cue. How-to:
  honor reduced-motion; pair motion with a non-motion cue. (Honoring `prefers-reduced-motion` maps to WCAG 2.3.3,
  AAA — a REQUIREMENT when AAA is targeted or agreed, best practice otherwise; never make motion the only state
  cue.) Exceptions: expressive motion where reduced-motion is respected. Verify: with reduced-motion on,
  is the UI still fully usable and are states still conveyed?
- **Information density (§10).** How-not-to: overloading one view so the primary task is lost. How-to: progressive
  disclosure; prioritize the primary task. Exceptions: an expert dense view chosen by the role. Verify: can the
  stated role+task be completed without hunting? Density is a defect only when it blocks the task.
- **Accessibility baseline (§3).** How-not-to: `outline:none` with no replacement (2.4.7); unnamed controls
  (name/role/value). How-to: visible focus; programmatic name/role/value. Exceptions [REQUIREMENT]: none at taste
  level. Verify: keyboard-only, can you see focus and operate every control?
