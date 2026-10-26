---
name: frontend-design
description: "Visual interface design so it reads as intentional rather than templated. Use when the user builds or reworks the appearance of a web system, portal, app, site or individual screen; asks that it not look AI-generated; or asks about palette, typography, density or design direction. Ukrainian compatibility trigger aliases: \"щоб не виглядало як AI\"."
license: Complete terms in LICENSE.txt
---

# Frontend Design

Work as the design lead at a small studio known for giving every client a visual identity that could not be mistaken for anyone else's. This client has already rejected proposals that felt templated. Make deliberate, opinionated choices specific to this brief, and take one real aesthetic risk you can justify.

## 1. Name the artifact, then take the branch

Two artifacts need different work. Decide which one this is before anything else, because every later step forks here.

- **Page** — a landing, a marketing site, a one-off. The unit is the page. It is read once, in order, and judged in seconds.
- **System** — a portal, an application, a dashboard, an admin tool, any product with many screens. The unit is the *set*. It is used daily, out of order, and judged by how little it gets in the way on the hundredth visit.

Most briefs that say "site" are pages; most that say "system", "portal", "app", or name an entity to manage are systems. When the brief is genuinely both (a marketing site with an app behind it), split it and design them as two artifacts.

If the brief does not pin down the subject, pin it yourself: name one concrete subject, its audience, and the single job. State your choice. Use anything in memory about this human's preferences, their product, or designs you have made for them before. The subject's own world — its materials, instruments, artifacts, vernacular — is where distinctive choices come from. Build with the brief's real content throughout.

**Done when:** the branch is written down, along with the subject, audience, and the one job.

## 2. Find what is already decided

Skip only for a genuine greenfield. Any existing product has decisions you do not get to make again, and overriding them silently is the most common way this work goes wrong.

Look for, and name what you find:

- **the token source** — where colour, spacing, radius, and type scale are actually defined (a CSS custom-property block, a theme file, a config);
- **the component inventory** — what already exists, so you extend rather than duplicate. Search before you create;
- **the theming mechanism** — how light/dark or brand variants are switched, and which mechanism is *not* used. Getting this wrong produces dead CSS that silently never applies;
- **the parity gate** — a design source (Figma, a spec, a sibling product) the work is measured against;
- **the styling idiom** — how variants are expressed, so new code reads like its neighbours.

Then the rule that follows from it: **most axes are already spent.** Palette, type, radius, spacing are decided; do not open them. Spend the freedom that remains — composition, density, hierarchy, motion, the one structural device — and say plainly which axes you treated as closed.

If an axis genuinely must change, that is a proposal to make explicitly, not a change to slip into a screen.

**Done when:** each item above is named with its location, or recorded as absent.

## 3. Plan before writing code

Reuse the project token system and typography roles found in step 2. Draft only missing decisions; the counts and font pairings below are greenfield suggestions, not requirements to replace existing tokens or add typefaces:

- **Colour** — 4–6 named values. In the system branch, include the semantic roles states need (success, warning, danger, info), not only brand tones.
- **Type** — typefaces for 2+ roles: a characterful display face used with restraint, a complementary body face, and a utility face for captions or data if the content has any.
- **Layout** — a layout concept in one-sentence prose plus ASCII wireframes, used to compare alternatives rather than to illustrate the first idea.
- **Signature** — the one thing this work is remembered by. **This differs by branch:**

  - **Page:** the hero is a thesis. Open with the most characteristic thing in the subject's world, in whatever form fits — a headline, an image, an animation, a live demo, an interactive moment. A big number with a small label, supporting stats, and a gradient accent is the template answer; use it only if it is genuinely the best one.
  - **System: the signature is a system, not a splash.** There is no hero. Character lives in what *repeats* — density and rhythm; the type scale and how tightly it is set; how a control behaves at rest, focus, and error; the vocabulary of empty, loading, partial, and failed; the motif of transitions; the one structural device present on every screen. The test is recognition by repetition: a screenshot of *any* screen should be identifiable as this product. A decorated dashboard bolted onto otherwise default screens fails this test.

**Done when:** every value above is written, and the signature is one nameable thing rather than a mood.

## 4. Check the plan against the defaults

AI-generated design currently clusters around three looks:

1. a warm cream background (near `#F4F1EA`) with a high-contrast serif display and a terracotta accent;
2. a near-black background with a single bright acid-green or vermilion accent;
3. a broadsheet layout with hairline rules, zero border-radius, and dense newspaper columns.

All three are legitimate for some briefs, but they arrive regardless of subject — defaults rather than choices. **Where the brief pins down a direction, follow it exactly; the brief's own words always win, including when they ask for one of these looks.** Where the brief leaves an axis free, do not spend that freedom on a default.

The system branch has its own defaults, equally unearned: a left sidebar with icon-plus-label items, cards with soft shadows on a grey field, a four-stat row above a table, and every state rendered as a centred grey spinner. Same rule applies.

Now review the plan: work through a similar brief in your head and see whether you arrive somewhere similar. Anything that reads as the generic answer for any brief of this kind gets revised, and you say what changed and why.

**Done when:** each axis either differs from the defaults above, or carries a written reason for matching one.

> **Pair (added 2026-09-29):** the concrete, itemised version of these defaults — the AI-tell catalogue (Inter/serif bans, the LILA purple-glow rule, the premium-consumer beige+brass ban, decoration clichés, copy clichés, motion rules) plus a mechanical pre-flight gate — lives in [`anti-slop-design`](../../anti-slop-design/SKILL.md). This skill owns the *method* (branch, find-what's-decided, spend-the-remaining-axes, take one risk); that skill owns the *facts and the gate*. Load it here and run its §3 pre-flight before step 6. In a project, the project's own token/stack facts win over both.

## 5. Build to the plan

Follow the revised plan exactly; derive every colour and type decision from it.

Watch CSS selector specificity. Classes that cancel each other out are easy to generate — especially a type-based selector (`.section`) against an element-based one (`.cta`), and most often on the paddings and margins between sections.

Do this planning and iteration in your thinking. Show the human ideas only once you are confident they will land.

**Done when:** every colour and type value in the code traces to a value in the plan.

## 6. Look at what you made

Critique it as you build, not after. A picture is worth a thousand tokens: take a screenshot if the environment allows one — a browser tool, a component workbench, a dev server.

Check, on the screenshot rather than from memory: it holds at a mobile width; keyboard focus is visible; reduced motion is respected. In the system branch also check the states — empty, loading, error, and the longest realistic content — because those are where systems actually break and where a design that looked finished stops being one.

Run the [`anti-slop-design`](../../anti-slop-design/SKILL.md) §3 pre-flight here as the mechanical last filter (em-dash count, theme/colour/shape locks, eyebrow count, motion-claimed-equals-shown, no fabricated proof, no placeholders). A failed box means not done.

Then apply Chanel's advice: before leaving the house, look in the mirror and take one accessory off. Cut the decoration that does not serve the brief.

**Done when:** a screenshot was taken and critiqued — or you have said plainly that you could not take one, rather than letting the check pass in silence.

## Principles that hold in both branches

**Typography carries the personality.** Pair display and body faces deliberately, not the families you would reach for on any project, and set a clear scale with intentional weights, widths, and spacing. Make the type treatment a memorable part of the design, not a neutral delivery vehicle.

**Structure is information.** Numbering, eyebrows, dividers, and labels should encode something true about the content. Numbered markers (01 / 02 / 03) belong only where the content really is a sequence and the order carries meaning the reader needs.

**Motion is deliberate.** Decide where — and whether — animation serves the subject: a load sequence, a scroll reveal, hover micro-interactions, ambient atmosphere. One orchestrated moment usually lands harder than scattered effects. Extra animation is a common tell that a design was machine-made. In the system branch, motion earns its place mainly by explaining a *change* — what appeared, what moved, what is still loading.

**Match complexity to the vision.** Maximalist directions need elaborate execution; minimal directions need precision in spacing, type, and detail. Elegance is executing the chosen vision well.

**Spend boldness in one place.** Let the signature be the one memorable thing and keep everything around it quiet. Not taking a risk is itself a risk — but two risks compete and both lose.

## Copy is design material

Words exist in a design to make it easier to understand, and therefore easier to use. Bring the same intentionality to copy as to spacing and colour, and treat missing copy as your job rather than a placeholder.

Full guidance — voice, controls, errors, empty states, register — is in [`WRITING.md`](WRITING.md). Read it whenever you are writing interface text, which in the system branch is almost always.

---

**Provenance.** Adapted from `anthropics/skills` → `skills/frontend-design` (upstream `2235be7c60`, 2026-06-09), restructured 2026-08-11 against `writing-great-skills`: the process became steps with completion criteria, the page/system branch was added, and the copy guidance moved to `WRITING.md`. Upstream terms remain in `LICENSE.txt`. Re-syncing means merging by hand — diff against that commit, not against `main`.
