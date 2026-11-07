---
name: anti-slop-design
description: 'A concrete catalog of frontend design AI tells (typography, color, layout, decoration, copy, motion), three dials and a mechanical pre-flight gate to keep an interface from looking templated. The factual companion to the methodological `frontend-design`. Use when building/refactoring the appearance of a landing page, portal, application or screen; when asked to avoid an AI-generated/templated look; or to check a finished screen for clichés. Additional trigger phrases: "avoid an AI-generated or templated look / anti-slop", "anti-slop", "avoid an AI-generated look", "taste", "critique the design", "design tells".'
license: Adapted from leonxlnx/taste-skill (MIT); see Provenance.
---


# anti-slop-design — AI-tell catalog + gate

This is a **contextual visual-heuristic catalog and gate**, not a method or an accessibility standard. The method—when to branch (page vs system), what is already decided, where the risk lies—is in [`frontend-design`](../ship/frontend-design/SKILL.md). This skill supplies concrete criteria for that method: a list of common defaults and a context-sensitive check before “done”.

**Nothing here triggers automatically.** First read the brief, then extract only what fits. Apply [design-pass priority](../design-pass/SKILL.md#3-priority-and-limits-of-general-rules) in standalone use too: mandatory project/function/accessibility requirements are distinct from aesthetic preferences. Every aesthetic heuristic below permits a documented project/brief/reference reason; it is not a universal ban. A rule without context is slop too.

---


## 0. Design read — one line BEFORE code

Before touching code, state in one line what you are building:

> **“I read this as: `<page type>` for `<audience>`, in a `<vibe>` voice, leaning toward `<design system / aesthetic>`.”**

The audience chooses the aesthetic, not your taste. If the brief is unambiguous, **do not ask**: announce the read and work. If the read genuinely splits, ask **one** clarifying question, not an interrogation.

**Anti-default discipline.** Do not reflexively reach for AI-purple gradients, a centered hero over a dark mesh, three equal feature cards, global glassmorphism, endless microanimations everywhere, or `Inter + slate-900`. These are LLM defaults. Reach further deliberately, based on the design read.

---


## 1. Three dials

After the read, set three numbers (1–10). Gate every layout/motion/density decision against them.

- **`DESIGN_VARIANCE`** — 1 = perfect symmetry, 10 = artistic chaos
- **`MOTION_INTENSITY`** — 1 = static, 10 = cinematic physics
- **`VISUAL_DENSITY`** — 1 = gallery/air, 10 = cockpit/data

**Baseline `8 / 6 / 4`** applies only until the read overrides it. Inference:

| Signal in the brief                                    | VARIANCE | MOTION | DENSITY |
| ------------------------------------------------------- | -------- | ------ | ------- |
| minimalist / clean / calm / editorial / Linear-style    | 5–6      | 3–4    | 2–3     |
| premium consumer / Apple-y / luxury / brand             | 7–8      | 5–7    | 3–4     |
| playful / Dribbble / Awwwards / experimental / agency   | 9–10     | 8–10   | 3–4     |
| landing / portfolio / marketing (default)               | 7–9      | 6–8    | 3–5     |
| trust-first / public-sector / regulated / a11y-critical | 3–4      | 2–3    | 4–5     |

The dials are variables referenced throughout the rest. Do not invent aliases (`LAYOUT_VARIANCE`, `ANIM_LEVEL`).

---


## 2. AI-tell catalog (bias correction)

Every rule has an **override path**. Avoid by default; override when the brand/brief explicitly requests it.


### 2.1 Typography

- **For an open typography axis**, choose a family that serves the brief. Inter, system fonts and more distinctive families are all valid; keep established fonts and do not install a new one to satisfy this catalog.
- **Serif is a choice, not an automatic premium signal.** Editorial, luxury, heritage or a named reference can justify it. Fraunces and Instrument Serif are examples of common defaults, not universally banned fonts; explain the fit instead of mechanically rotating families.
- **Headline emphasis:** prefer a coherent treatment; mixed families can be intentional when the reference or project typography supports them. Do not change an established hierarchy to satisfy this preference.
- **Italic descender clearance:** inspect actual ink at the chosen font, size and scale. Tight line boxes can clip descenders, but CSS line-height alone does not prove it; neither a fixed line-height nor padding recipe guarantees clearance. A box-fit measurement does not measure glyph ink.


### 2.2 Color

- **Accent restraint:** one accent can be a useful starting point for a simple page. Multiple brand accents, charts and semantic success/warning/error colors can be correct; preserve their roles and measured contrast. Saturation counts are preferences, not accessibility measurements.
- **LILA rule:** “AI Purple / blue glow” is not the default. A neutral base (Zinc/Slate/Stone) + one high-contrast accent (Emerald, Electric Blue, Deep Rose, Burnt Orange). _Override:_ accept a brand's request for purple, but with intent, not a generic gradient.
- **Consistency lock:** use the chosen accent across the ENTIRE page. A warm-gray page does not get a blue CTA in section 7. One palette per project, without switching between warm↔cool grays.
- **Premium-consumer default warning**: for cookware/wellness/artisan/luxury, the LLM default is beige/cream + brass/clay/oxblood + espresso. Question that default on an open axis; other possible directions include: Cold Luxury (silver/chrome/smoke), Forest (green/bone/amber), Black-and-Tan, Cobalt+Cream, Terracotta+Slate, or pure monochrome + one pop. Do not choose or reject a palette solely because it appeared in another project; judge this brief and system. _Override:_ the brand explicitly names these colors.


### 2.3 Layout

- **Anti-center:** at `DESIGN_VARIANCE > 4`, avoid a centered hero; use split 50/50, left text/right asset, asymmetric whitespace, scroll-pin. _Override:_ editorial/manifesto/launch, where the message itself is the design.
- **Zigzag cap:** no 3+ consecutive sections with the same image+text split.
- **Eyebrow restraint:** counting repeated `uppercase tracking` microlabels can expose monotony; a suggested starting point is ≤ ceil(sections / 3), not a universal limit.
- **Section-layout variety:** consider variation where it supports the content; stable repeated structure is often correct in a system. No minimum family count is mandatory.


### 2.4 Materiality and decoration

- **Cards should communicate grouping or hierarchy.** Borders, spacing and flatter surfaces can serve the same purpose; use the established component system.
- **Shadows** should fit the theme and surface hierarchy; tinted shadows and restrained black-alpha shadows can both be appropriate.
- **One coherent corner-radius token system**, which may use several values for different component roles; do not flatten it to one radius.
- **Banned decorative slop** (default off; only with a real semantic reason): version footers on marketing (`v1.4.2`, `Build 0048`, `last sync 4s ago`), scroll cues (`Scroll ↓`), section-number eyebrows (`00 / INDEX`, `06 · how it works`), decorative strips at the bottom of the hero (`BRAND. MOTION. SPATIAL.`), fake photo-credit captions (`Field study no. 12 · Ines Caetano`), pills/labels over images, decorative dots, locale/city/weather strips without a global-context reason.


### 2.5 Copy and honest evidence

- **Plain, concrete language.** Banned clichés: “Elevate”, “Seamless”, “Unleash”, “Next-Gen”, “Game-changer”, “Delve”, “Tapestry”, “In the world of…”. Sentence case in headings, not Title Case. No “Oops!” errors or passive voice.
- **No fabricated evidence.** Do not invent client logos, testimonials, metrics or “Trusted by”. Mark demo content with a user-visible label (`sample`, `example`, `demo`). An HTML comment alone is not visible labeling. Do not support a production claim with another AI-generated page.
- **A realistic mock ≠ fraud:** unique avatars/dates instead of identical ones are fine for avoiding a templated look, but this concerns demo plausibility, not forging real identities.


### 2.6 Motion

- **Motion motivated (when motion is in scope):** before any animation, ask “what does it communicate?”. Valid: hierarchy / storytelling / feedback / state change. Invalid: “looks cool”. GSAP everywhere because it is available is amateurish.
- **Motion claimed = evidence:** a dial does not require adding animation. Describe existing/approved motion honestly; keep static work static when appropriate. Verify any claimed behavior and its reduced-motion path with available interaction evidence; no video or animated demo is required.
- Honor **`prefers-reduced-motion`** for all applicable animations regardless of the dial: remove or simplify nonessential motion while preserving clear feedback.
- **Scroll behavior:** reuse the project stack; prefer efficient native/CSS mechanisms where suitable. A justified scroll listener is not universally forbidden: verify its scheduling, cleanup and actual performance rather than forcing a new animation dependency.
- **Timing:** choose easing for the interaction; springs, linear progress and static feedback have different valid uses. A timing preference is not a readiness blocker.


### 2.7 Output and dependencies

- **No placeholders:** no `// TODO: add actual code`, `...`, “rest stays the same”. A complete working implementation.
- **Dependency verification:** before importing a library, check `package.json`; if absent, use an existing alternative or propose the smallest justified dependency under the project authorization; do not install it implicitly.

---


## 3. Pre-flight gate (before “done”)

Record observed evidence, not an automatic style score. Applicable functional/accessibility requirements and agreed acceptance block readiness when failed or untested; contextual preferences require a reasoned design decision. Use [ui-measurements](../ui-measurements/SKILL.md) only for missing supported measurements in the existing evidence record. Do not count unsupported contrast, glyph clipping or unvisited states as PASS.

- [ ] **Design read** announced (§0)?
- [ ] **Dials** explicit and justified by the brief, not a silent baseline?
- [ ] **Punctuation and typography** follow the project voice and content; no universal zero-em-dash rule?
- [ ] **Theme coherence** follows supported project themes/reference; deliberate section inversion is allowed when justified?
- [ ] **Color/shape coherence**: accents, semantic colors and radius variants follow the established system?
- [ ] **CTA legibility and intent**: applicable contrast threshold/source and measured paint recorded (normal/large text, target level and legitimate exceptions distinguished); wrapping fits the agreed layout; repeated actions serve the journey?
- [ ] **Typography/palette** follows the actual brief and established system, with a reason for open choices rather than a rule to differ from another project?
- [ ] **Decoration and repetition** have a reason in the brief/content; numeric caps are diagnostic preferences, while fabricated proof remains prohibited?
- [ ] **Assets** are appropriate and honestly represented; existing SVG/CSS illustrations are allowed, and generated mockups are not evidence of a real product?
- [ ] **Copy self-audit**: every visible line reread, no broken/hallucinated phrases; no fabricated evidence?
- [ ] **Motion motivated** (each animation justified in one sentence) and **claimed = shown**?
- [ ] **Reduced motion** checked for applicable animations; existing scroll/animation mechanisms are justified, efficient and cleaned up?
- [ ] **Mobile collapse** explicit; height does not clip content or actions when the viewport changes, the keyboard appears or text is enlarged? Use full-height only when the layout needs it, with the current stack's tools.
- [ ] **Applicable** empty/loading/error states verified; no nonexistent async states invented?
- [ ] **Icons** follow project assets/library conventions; do not add a library or replace valid custom SVG for this catalog?
- [ ] **No placeholders / TODO**; dependencies checked?

---


## 4. In a project: project facts override these defaults

This catalog is **generic**. Within a real product, most axes are already decided (see `frontend-design` §2, “find what is already decided”):

- **Tokens, font, palette, radius** are defined in the project theme; do not reopen them. Here, “Inter is not the default” and the “LILA rule” **yield** to the canonical project palette.
- **Theme mechanism** (e.g. `[data-theme]` instead of `dark:`) and **styling idiom** (e.g. `clsx` instead of `tv()`) come from the project, not here. Check only themes supported by the project through its mechanism; this skill does not require adding light/dark or dark-only mode.
- **Stack specifics** (RAC primitives, `text-p13/p14` = size, a ban on raw `<input>`, inventory-first deduplication) belong in the **local project skill**, not here.

This catalog contains contextual visual defaults, not truths or mandatory bans for every frontend. Stack decisions belong in the project; applicable accessibility/function requirements are assessed under the UX lens, not waived by a visual override.

---

**Provenance.** Distilled (not copied) from `leonxlnx/taste-skill` v1 + v2 (MIT), 2026-09-29: three dials, tell catalog (Inter/serif/LILA/premium-palette/decoration), motion-motivated, truth-and-proof, output-completeness, pre-flight. The method is intentionally NOT duplicated: it lives in [`frontend-design`](../ship/frontend-design/SKILL.md); stack facts belong in the project skill. The pair runs through [`design-pass`](../design-pass/SKILL.md).

## Reference anti-patterns

This skill's domain anti-patterns are stated inline above (the AI-tell catalog and three dials). During plan/implement/review also consult the shared [reference anti-patterns](../../ai-factory/reference-anti-patterns.md) for the 4-field template and the cross-cutting rules (accessibility REQUIREMENT-vs-preference split; no invented exceptions).
