---
name: design-pass
description: 'Creates or improves UI from project constraints and a design plan through browser verification and fixes. Use for sites, screens and user journeys, including from a screenshot or Figma mockup. Additional trigger phrases: "paired design", "give it a deliberate design", "match the mockup". For an audit without changes, use interface-review.'
---


# design-pass — design, implementation, verification

The result is an interface with clear hierarchy, a complete primary journey and verification evidence. A successful build confirms compilation, not design or UX quality. Scale the process to the change: for one button, check its context and states; for a new screen, the entire journey. Do not expand a small task into a product redesign.


## 1. Start with the current project

Before choosing a style or implementing, read applicable `AGENTS.md` and `CLAUDE.md`. Find the local design skill in `.agents/skills/`, `.claude/skills/`, `skills/` or through links in those instructions; read only what is relevant. Record specific files or their absence for:

- color, typography, spacing and radius tokens;
- existing reusable components and layout primitives;
- theme mechanism and actually supported themes;
- stack, styling approach, fonts, icons and assets;
- target routes, launch commands and available verification tools.

The absence of a local skill **does not mean** design axes are open: check the implementation and adjacent screens. Do not import Tailwind, light/dark, dark-only, palettes or components from another project. Do not add a theme, font or library merely to satisfy a global default.


## 2. Brief, reference and plan

Name the artifact type (`page` / `system`), audience, primary task, change boundaries and primary action. Define a short verifiable journey: start → action → expected outcome; where applicable, error → recovery. If there is enough information, work; clarify only uncertainty that materially changes the outcome.

- **With a reference:** read [reference-ui-reconstruction](../reference-ui-reconstruction/SKILL.md). Record viewport, reference boundaries, geometry, tokens, typography, components and unknowns. Distinguish exact reconstruction from a mood-only reference. Do not restart this orchestrator through a backlink from the skill.
- **Method:** read [frontend-design](../ship/frontend-design/SKILL.md). Use project decisions already found; do not repeat discovery. Make a compact plan for composition, hierarchy, typography, spacing and narrow-screen behavior. Name closed and open axes. One distinctive technique or aesthetic risk is appropriate only within the brief; do not invent a new style for a targeted change or reconstruction.
- **Visual filter:** read [anti-slop-design](../anti-slop-design/SKILL.md), announce the design read and justify applicable dials from the brief. Its catalog checks appropriateness; it is not a reason to replace the project's style.

Read the task record's CURRENT acceptance criteria (feature-lifecycle "one primary task record") as the baseline; do not re-derive a parallel acceptance. PROPOSE UI-observable checks (viewport/state) as additions — proposed, not adopted. UX does not itself change the agreed acceptance/scope; a scope change is agreed by the owner first, then recorded. When there is no task record (small work with no durable record), a short message is sufficient, without extra files.


## 3. Priority and limits of general rules

The explicit user request defines the goal. For visual decisions: **authoritative reference > project > method > generic defaults**. The project defines implementation approach; a reference does not authorize replacing the stack. Name any conflict between the reference and canonical system and record the required deviation; do not silently rewrite global tokens.

In this process, helper-skill rules about specific fonts, accent counts, themes, radii, punctuation, icon libraries, CSS classes or mandatory motion are conditional heuristics. Do not turn them into universal blockers. Explain an appropriate exception; do not change branding, text or semantic state colors for a mechanical checkbox. Apply general UX patterns to the task too, not as orders to always add a sidebar, modal or split a form.

At the same time, a reference's appearance or a project rule does not prove accessibility or functionality. Do not mark an identified problem `pass` merely because of its origin. Do not invent testimonials, clients, metrics or successful checks.


## 4. Implement a complete slice

Start with structure and geometry, then typography, content, components and details. Reuse tokens and primitives. Copy and realistic text lengths are part of design; for writing, apply the `WRITING.md` resource from frontend-design. Label demo data as demo.

Before delivery, read and apply the [shared viewport contract](references/viewport-coverage.md): four baseline classes, separate text enlargement/reflow and evidence. Ensure and verify applicable criteria:

| Axis | Observable outcome |
| --- | --- |
| Hierarchy | The screen's purpose and primary action are clear; secondary actions do not compete; headings, grouping, alignment and spacing rhythm agree. No clipped text, accidental wraps or decoration without a function. |
| Responsiveness | All four baseline viewports from the shared contract preserve meaning, order and access to actions. Navigation, tables, modals and sticky elements behave explicitly; no accidental horizontal overflow. Also check an intermediate width near a changed breakpoint. |
| States | For changed controls: rest, hover where a pointer exists, pressed/selected, visible focus, disabled and pending where applicable. For data/forms: loading, empty/no-results, error with recovery, success. Do not add a nonexistent asynchronous state to static content. |
| Accessibility | Semantic headings and controls, accessible names and labels, meaningful alt, logical keyboard order, visible unobscured focus. For dialogs: entry, dismissal and focus return. Measure contrast rather than judging by impression; state is not conveyed by color alone. |
| Journey | The primary action fulfills its promise and gives feedback; back/cancel works, an error does not erase input. Walk the primary path and relevant error/retry path. Long text, empty and overflowing data do not break the screen. |
| Motion and scale | If animation exists, it explains an action/state, does not obstruct and respects reduced motion. Separately check text enlargement to 200% and reflow at a narrow viewport; do not count one as the other. |

This is a baseline check of changed UI, not WCAG certification. For specific criteria and sources, use applicable sections of the [ux-review rules](../ux-review/references/rules.md), considering conformance level and exceptions. Also consult the shared [reference anti-patterns](../../ai-factory/reference-anti-patterns.md) (4-field template + the a11y REQUIREMENT-vs-preference split) and, for evidence capture, the **Anti-patterns** section of [browser state evidence](references/browser-state-evidence.md): a screenshot is evidence only for the expectation actually checked in it, and `prefers-reduced-motion` is honored. An a11y REQUIREMENT is not downgraded to PASS by a stylistic preference. Do not claim full conformance from a screenshot or one automated scan.


## 5. Browser → findings → fixes → recheck

Before the pass, make a compact inventory of new/changed UI states in the current plan/report. If scope includes a popover, active trigger or chips, explicit visual coverage is required for each state; a closed/default screenshot does not prove them. Mark inapplicable items N/A with a reason; required but unavailable items BLOCKED.

1. **Determine capabilities.** Use an actually available browser tool, local test runner or project tools. Do not assume a particular MCP, Playwright, browser or image viewer is available. Find the documented launch command; do not install a new verification stack merely for this skill.
2. **Open the result.** Start or use the local application and open the changed route with reproducible data. For redesigns, capture the before state where possible. Check font/asset loading and related runtime errors.
3. **Look and interact.** Capture and actually inspect screenshots of each applicable surface in all four baseline viewports under the shared contract; record exact CSS dimensions, scale and evidence. Also inspect below-the-fold content. Walk the journey, keyboard interactions, states and scaling from §4. A static screenshot does not confirm behavior, and a created but unviewed file does not confirm visual quality.
4. **Compare.** With a reference, use the same viewport and state, side-by-side/overlay/diff as available. Without one, compare against the plan, criteria and project system. Start with large proportions and hierarchy, then typography, spacing and details.
   Separate the actual diff, explanation of its cause and decision to accept the baseline. A low diff percentage does not prove no regression; for a modal, check foreground and background/backdrop. Do not claim no-diff without an actual comparison. Do not blindly update the baseline: preserve the agreed local review mechanism and evidence of differences.
5. **Fix and recheck.** Record the specific defect, location and evidence; fix within scope. Repeat the same journey/viewport and affected neighboring states. Fresh evidence is required after the final edit: a pre-fix screenshot does not prove the fix. Repeat until criteria are met or a specific blocker arises; do not cycle through cosmetic variants without an improvement criterion.

For the final pass, apply [interface-review](../interface-review/SKILL.md): visual and UX lenses are mandatory for changed UI, but depth follows scope. Reuse collected evidence and deduplicate findings. This is a correction stage in design-pass, not just an audit report.

If a tool, launch, data or access is blocked, perform available independent checks and name the exact reason and next step. Report static analysis, build and tests separately from browser checks. Inability to inspect does not undo the implementation, but leaves visual verification blocked.


## 6. Done and handoff

“Done and verified” only when, for the agreed scope:

- project constraints, plan and applicable criteria are recorded;
- implementation passes appropriate project checks;
- the current result has been inspected in a browser at every applicable baseline viewport under the shared contract, with the primary journey and applicable states checked;
- any reference has been compared at the target viewport, with differences described;
- applicable anti-slop pre-flight and UX pass are complete; blocker/major findings are fixed and rechecked. The only exception is a limitation explicitly accepted by the user with a date and impact, with status “done with limitations”. Merely recording a defect does not mean it is accepted.

At the end, briefly report what changed and why; which screens/journeys/viewports were checked; where evidence is; and what remains. Use **PASS / FAIL / NOT_TESTED / N/A** for checks, with grounds (a required untested check blocks the gate: **BLOCKED**). Untested is not PASS; explain inapplicability for N/A. If a key check is blocked, status is “implemented, verification incomplete”, with a specific next step instead of unconditional “done”.

Reconcile the summary and plan checklist with evidence for the final revision/diff: old PASS does not close a new UI delta. If acceptance requires a keyboard action, check the required key through browser input and the expected UI effect; this is a simulated browser key, not physical manual QA or unit dispatch of submit. Do not redo a completed task solely because of an identical handoff with unchanged inputs; do not attribute repetition to automation without evidence.


## Terminal usage

The shared `SKILL.md` does not require agent-specific tools:

- **Codex CLI:** `$design-pass` in the request or selection through `/skills`.
- **Claude Code:** `/design-pass` followed by the task.

For example: “Update the settings screen in the current project. First find tokens and primitives; implement and check the primary journey, responsiveness and states in the browser. Fix findings, show evidence and separately name blocked checks.”

Open helper-skill links as files relative to this directory; do not assume a slash command or special tool is available. If a resource is missing, name it, continue with this skill's available requirements and do not count an unperformed specialized gate.

## Browser evidence refinement

For permission/session/error recovery states and action-correlated DOM, console or network evidence, use [browser state evidence](references/browser-state-evidence.md). Reuse the existing entity coverage and reviewer route; this adds no tool installation or second checklist.
