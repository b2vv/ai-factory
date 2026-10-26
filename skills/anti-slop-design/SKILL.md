---
name: anti-slop-design
description: 'A concrete catalog of frontend design AI tells (typography, color, layout, decoration, copy, motion), three dials and a mechanical pre-flight gate to keep an interface from looking templated. The factual companion to the methodological `frontend-design`. Use when building/refactoring the appearance of a landing page, portal, application or screen; when asked to avoid an AI-generated/templated look; or to check a finished screen for clichés. Compatibility trigger aliases: "щоб не виглядало як AI / не шаблонно / anti-slop", "anti-slop", "не як AI", "taste", "прожар дизайн", "design tells".'
license: Adapted from leonxlnx/taste-skill (MIT); see Provenance.
---


# anti-slop-design — AI-tell catalog + gate

These are **facts and a gate**, not a method. The method—when to branch (page vs system), what is already decided, where the risk lies—is in [`frontend-design`](../ship/frontend-design/SKILL.md). This skill supplies concrete criteria for that method: a list of machine clichés and a mechanical check before “done”.

**Nothing here triggers automatically.** First read the brief, then extract only what fits. A rule without context is slop too.

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

- **Inter is not the default.** First consider `Geist`, `Outfit`, `Cabinet Grotesk`, `Satoshi`, or an appropriate brand font. _Override:_ Inter is fine for neutral/Linear-style or public-sector/a11y.
- **Serif is emphatically not the default.** “Feels creative/premium” is NOT a reason. “Creative brief = serif” is the most common AI tell. _Override:_ only when the brand explicitly names serif, or the aesthetic is genuinely editorial/luxury/heritage AND you can explain why this particular serif. **Banned as defaults:** `Fraunces`, `Instrument_Serif`.
- **Headline emphasis** uses italic/bold in the SAME font, not a random serif word inserted into sans (or vice versa). Mixed emphasis is amateurish.
- **Italic descender clearance:** an italic word with `y g j p q` at `leading-none` clips descenders; use at least `leading-[1.1]` + `pb-1`.


### 2.2 Color

- **At most 1 accent.** Saturation < 80% by default.
- **LILA rule:** “AI Purple / blue glow” is not the default. A neutral base (Zinc/Slate/Stone) + one high-contrast accent (Emerald, Electric Blue, Deep Rose, Burnt Orange). _Override:_ accept a brand's request for purple, but with intent, not a generic gradient.
- **Consistency lock:** use the chosen accent across the ENTIRE page. A warm-gray page does not get a blue CTA in section 7. One palette per project, without switching between warm↔cool grays.
- **Premium-consumer ban** (the second most common tell): for cookware/wellness/artisan/luxury, the LLM default is beige/cream + brass/clay/oxblood + espresso. **Banned as a default reach.** Rotate instead: Cold Luxury (silver/chrome/smoke), Forest (green/bone/amber), Black-and-Tan, Cobalt+Cream, Terracotta+Slate, or pure monochrome + one pop. Do not use the same warm-craft palette twice in a row. _Override:_ the brand explicitly names these colors.


### 2.3 Layout

- **Anti-center:** at `DESIGN_VARIANCE > 4`, avoid a centered hero; use split 50/50, left text/right asset, asymmetric whitespace, scroll-pin. _Override:_ editorial/manifesto/launch, where the message itself is the design.
- **Zigzag cap:** no 3+ consecutive sections with the same image+text split.
- **Eyebrow cap (mechanical):** the number of `uppercase tracking` microlabels above headings ≤ ceil(sections / 3). The hero counts as 1.
- **Section-layout variety:** for 8 sections, at least 4 different layout families.


### 2.4 Materiality and decoration

- **Cards only when elevation conveys real hierarchy.** Otherwise group with `border-t`/`divide-y`/space.
- **Tint shadows to the background color**: no pure-black drop shadows on light backgrounds.
- **One corner-radius system** across the entire screen.
- **Banned decorative slop** (default off; only with a real semantic reason): version footers on marketing (`v1.4.2`, `Build 0048`, `last sync 4s ago`), scroll cues (`Scroll ↓`), section-number eyebrows (`00 / INDEX`, `06 · how it works`), decorative strips at the bottom of the hero (`BRAND. MOTION. SPATIAL.`), fake photo-credit captions (`Field study no. 12 · Ines Caetano`), pills/labels over images, decorative dots, locale/city/weather strips without a global-context reason.


### 2.5 Copy and honest evidence

- **Plain, concrete language.** Banned clichés: “Elevate”, “Seamless”, “Unleash”, “Next-Gen”, “Game-changer”, “Delve”, “Tapestry”, “In the world of…”. Sentence case in headings, not Title Case. No “Oops!” errors or passive voice.
- **No fabricated evidence.** Do not invent client logos, testimonials, metrics or “Trusted by”. Mark demo content with a user-visible label (`sample`, `example`, `demo`). An HTML comment alone is not visible labeling. Do not support a production claim with another AI-generated page.
- **A realistic mock ≠ fraud:** unique avatars/dates instead of identical ones are fine for avoiding a templated look, but this concerns demo plausibility, not forging real identities.


### 2.6 Motion

- **Motion motivated (mandatory):** before any animation, ask “what does it communicate?”. Valid: hierarchy / storytelling / feedback / state change. Invalid: “looks cool”. GSAP everywhere because it is available is amateurish.
- **Motion claimed = motion shown:** if `MOTION_INTENSITY > 4`, the page must actually move (hero entry, key-section scroll reveal, CTA hover physics). Static output claiming `7` is broken. If working motion is beyond scope, lower the dial to 3 and deliver a clean static result.
- Honor **`prefers-reduced-motion`** for all applicable animations regardless of the dial: remove or simplify nonessential motion while preserving clear feedback.
- **No `window.addEventListener('scroll')`**: only `useScroll()` / ScrollTrigger / IntersectionObserver / CSS scroll-driven. `useEffect` animations require strict cleanup.
- **Spring, not linear** for microinteractions (e.g. `type:"spring", stiffness:100, damping:20`).


### 2.7 Output and dependencies

- **No placeholders:** no `// TODO: add actual code`, `...`, “rest stays the same”. A complete working implementation.
- **Dependency verification:** before importing a library, check `package.json`; if absent, first provide the installation command rather than assuming availability.

---


## 3. Pre-flight gate (before “done”)

Mechanical, not eyeballed. A failed box means not done.

- [ ] **Design read** announced (§0)?
- [ ] **Dials** explicit and justified by the brief, not a silent baseline?
- [ ] **ZERO em-dash (`—`)** anywhere on screen (headings, pills, body, quotes, attribution, alt)?
- [ ] **Theme lock**: one theme across the screen, no section flipping into inversion midway?
- [ ] **Color lock**: one accent used consistently in all sections? **Shape lock**: one radius?
- [ ] **CTA contrast** WCAG AA 4.5:1, label does not wrap to 2 lines on desktop, no two CTAs with the same intent?
- [ ] **Serif / premium palette**: if used, not banned-as-default (or explicitly justified by the brand and different from the previous project)?
- [ ] **Eyebrow count ≤ ceil(sections/3)**; no section-numbering eyebrows, decorative strips, scroll cues, version footers or fake photo credits?
- [ ] **Real images** (gen-tool → seed → explicit placeholder slot), no div-based fake screenshots or hand-rolled decorative SVG?
- [ ] **Copy self-audit**: every visible line reread, no broken/hallucinated phrases; no fabricated evidence?
- [ ] **Motion motivated** (each animation justified in one sentence) and **claimed = shown**?
- [ ] **Reduced motion** checked for all applicable animations; no `scroll` listener; `useEffect` cleanup present?
- [ ] **Mobile collapse** explicit; height does not clip content or actions when the viewport changes, the keyboard appears or text is enlarged? Use full-height only when the layout needs it, with the current stack's tools.
- [ ] **Empty / loading / error** states provided?
- [ ] **Icons** from an allowed library (Phosphor / Tabler / Radix / Lucide), not hand-rolled paths?
- [ ] **No placeholders / TODO**; dependencies checked?

---


## 4. In a project: project facts override these defaults

This catalog is **generic**. Within a real product, most axes are already decided (see `frontend-design` §2, “find what is already decided”):

- **Tokens, font, palette, radius** are defined in the project theme; do not reopen them. Here, “Inter is not the default” and the “LILA rule” **yield** to the canonical project palette.
- **Theme mechanism** (e.g. `[data-theme]` instead of `dark:`) and **styling idiom** (e.g. `clsx` instead of `tv()`) come from the project, not here. Check only themes supported by the project through its mechanism; this skill does not require adding light/dark or dark-only mode.
- **Stack specifics** (RAC primitives, `text-p13/p14` = size, a ban on raw `<input>`, inventory-first deduplication) belong in the **local project skill**, not here.

Rule: this contains what is true for any frontend; everything stack-dependent belongs in a project skill that **extends** this and `frontend-design`.

---

**Provenance.** Distilled (not copied) from `leonxlnx/taste-skill` v1 + v2 (MIT), 2026-09-29: three dials, tell catalog (Inter/serif/LILA/premium-palette/decoration), motion-motivated, truth-and-proof, output-completeness, pre-flight. The method is intentionally NOT duplicated: it lives in [`frontend-design`](../ship/frontend-design/SKILL.md); stack facts belong in the project skill. The pair runs through [`design-pass`](../design-pass/SKILL.md).
