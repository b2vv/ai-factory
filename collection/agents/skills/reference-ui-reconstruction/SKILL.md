---
name: reference-ui-reconstruction
description: Відтворює вебінтерфейс за скріншотом, мокапом, макетом Figma чи іншим візуальним референсом із вимірюваною відповідністю. Використовуй цей скіл, коли користувач надає референс, просить скопіювати чи відтворити наявний інтерфейс, вимагає відповідності макету або повідомляє про вигадані агентом відступи, типографіку, кольори чи компоненти. Фіксуй спостережувані факти до написання коду й перевіряй результат скриншотом у тому самому розмірі вікна.
---

# Reference UI Reconstruction

Use a visual reference as a parity target, not as inspiration. The goal is to reduce invention: every visible decision should be either measured from the reference, inherited from the project, or explicitly marked as unknown.

This skill complements `frontend-design`. `frontend-design` is allowed to make intentional aesthetic decisions; this skill closes those degrees of freedom when a reference exists.

## 1. Establish the reference contract

Record:

- the reference file or URL;
- its pixel dimensions and aspect ratio;
- the intended viewport, device pixel ratio, and responsive breakpoint if known;
- whether the reference is a complete screen, a crop, or a partial state;
- which parts are authoritative and which parts are unavailable or ambiguous.

Do not silently fill cropped, blurred, or hidden areas with invented UI. Choose the least-assumptive interpretation and record uncertainty.

**Done when:** the target viewport and the boundary of what must match are written down.

## 2. Extract facts before implementation

Create a compact reference sheet before writing components. At minimum capture:

- page regions and their bounding boxes;
- main alignment lines, columns, gutters, and container width;
- spacing rhythm and repeated gaps;
- background, surface, border, text, muted, and accent colors;
- typography roles, approximate family, size, weight, line height, and letter spacing;
- component shapes: radius, border width, shadow, icon size, control height;
- visible states: selected, disabled, hover/focus if shown, empty/loading/error if shown;
- content lengths that affect wrapping and density.

Prefer relative measurements and repeated relationships over guesses such as “roughly a card.” Use tokens for repeated values. If a property cannot be observed, label it `unknown` instead of inventing precision.

**Done when:** every major visible region has a measured or explicitly uncertain description, and repeated values have candidate tokens.

## 3. Inspect the project before creating a system

Search the project for:

- existing design tokens and theme definitions;
- typography and font loading;
- layout primitives and component inventory;
- icon library and asset conventions;
- the route or screen being changed;
- screenshot, browser, storybook, or visual-test tooling.

Reuse existing primitives when their rendered result can match the reference. Add a new token or component only when the inventory cannot express the observed design. Project conventions win over generic defaults, but they do not justify changing the reference.

**Done when:** the implementation seam, reusable components, and token source are named before new UI code is written.

## 4. Build the smallest faithful slice

Implement in this order:

1. viewport and page background;
2. primary containers and alignment lines;
3. large surfaces and structural regions;
4. typography and content wrapping;
5. controls, icons, borders, radius, and shadows;
6. responsive collapse and visible states.

Keep content realistic and close in length to the reference because text width changes geometry. Do not add decorative elements, extra cards, invented metrics, or alternate patterns merely to make the screen feel complete.

Extract repeated measurements into tokens, but do not abstract one-off geometry prematurely. A component is ready to share when it is repeated or when it represents a stable interaction/state boundary.

**Done when:** the page can be rendered at the reference viewport and all visible regions have an implementation or a documented limitation.

## 5. Run the visual parity loop

Render the implementation at the exact reference viewport. Compare the result against the reference in this order:

1. global frame, viewport, and page bounds;
2. major regions, columns, and alignment;
3. typography scale, weight, wrapping, and vertical rhythm;
4. surfaces, colors, borders, radius, and shadows;
5. icons, controls, and fine details.

Use an overlay, side-by-side comparison, or image diff when the environment supports it. Fix the largest geometric mismatch first. Do not compensate for a wrong parent layout with local arbitrary offsets.

Repeat until the remaining differences are either below the agreed tolerance or explicitly explained by missing assets, fonts, responsive information, or unavailable interaction state.

**Done when:** at least one generated screenshot has been compared at the target viewport and the remaining mismatches are recorded, not merely assumed away.

## 6. Protect the system from drift

For a multi-screen product, promote stable observations into a reference-backed system:

- semantic tokens with their source and usage;
- layout primitives and breakpoint rules;
- component variants and allowed states;
- typography roles and wrapping constraints;
- asset and icon choices;
- a small set of reference screenshots used as parity fixtures.

Keep a `reference-parity.md` or equivalent note when the work is substantial. It should distinguish observed facts, project constraints, deliberate deviations, and unresolved questions.

**Done when:** another screen can reuse the extracted system without re-guessing the reference decisions.

## Hard guards

- A screenshot is evidence, not permission to redesign.
- Never claim pixel parity without rendering and comparing at the target viewport.
- Never invent hidden or cropped UI without marking it as an assumption.
- Do not replace measured geometry with a generic dashboard or card-grid template.
- Do not use visual polish to hide a structural mismatch.
- If screenshot capture or comparison is unavailable, say so plainly and downgrade the result to an unverified reconstruction.

## Handoff to `design-pass`

After this skill produces the reference sheet and parity constraints, continue with `design-pass` for the project-aware design method and anti-slop gate. In a reference-driven task, the reference sheet closes the aesthetic axes; `frontend-design` may improve implementation quality but must not override measured reference facts without an explicit deviation.
