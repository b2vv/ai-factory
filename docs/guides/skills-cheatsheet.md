> **Historical English adaptation — authored derivative.** Historical source: [docs/guides/skills-cheatsheet.md at `2c0960885926`](https://github.com/b2vv/ai-factory/blob/2c0960885926075502a319a19eafbed901690dde/docs/guides/skills-cheatsheet.md). Original SHA256: `4aa1bcca3b8c263499afadeb266ba06eda066e2cd0492643973ab8b6dece0bdd`. Source base: `2c0960885926075502a319a19eafbed901690dde`. The immutable source at this commit and hash remains the historical reference; the [current in-repository document](skills-cheatsheet.md) is an English adaptation. Historical assertions, statuses, examples, and limitations are retained; this document does not establish current policy, execution evidence, or activation. Current labels, placeholders, and section navigation are English; local-project links remain removed.

# 🧠 Skills cheatsheet (`~/.agents/skills`)

Shared store — `~/.agents/skills`; Claude Code and Cursor are connected through symlinks. The corresponding SKILL.md is the current source of behavior; this file and Obsidian Shared are reference guides.

## How to invoke skills
Codex CLI: `$name` (name) or `/skills`. Claude Code: `/name` (name). The `/command` label below describes the Claude `disable-model-invocation` metadata, not the policy of every agent. English triggers are optional.

Audit inventory, 2026-10-14: 60 custom/installed SKILL.md files outside synced, plus 22 in synced. The examples below are not a complete catalog of available tools. Check the mentioned MCPs, plugins, and harness commands in the current session; mark unavailable checks BLOCKED.

## UI: recommended entry point
`$design-pass` in Codex or `/design-pass` in Claude: current project rules → tokens/components/scenarios → reference if needed → plan → implementation → browser → fixes → recheck. Check hierarchy, responsiveness, states, accessibility, and main scenarios; a build is not visual verification. Report PASS / FAIL / BLOCKED / N/A with evidence. Additional lenses: anti-slop-design, ux-review, interface-review.

> Old examples mentioning gamma, RAC, clsx, src/index.css, dark-only, ADR, and specific commands describe an individual project, not global rules. Before copying them, substitute your repository's current rules, paths, libraries, and commands. Ready-to-use general prompts: `~/vaults/global/prompts/`. A release requires a corresponding instruction; a green check alone does not authorize publishing.

---

## 📑 Contents

- [How to invoke skills](#how-to-invoke-skills)
- **Skills in `~/.agents/skills` (54)**
  1. [Planning and alignment](#1-planning-and-alignment-grilling--routing) — `ask-matt` · `grill-me` · `grill-with-docs` · `grilling` · `to-questionnaire` · **`cto-research`** · **`cto-agenda`** · **`plan-critique`** · **`plan-defense`** · **`acceptance-spec`**
  2. [Requirements → tasks → implementation](#2-requirements--tasks--implementation) — `to-spec` · `to-tickets` · `triage` · `implement` · `implement-spec` · `wayfinder` · **`spec-flow`**
  3. [Architecture, design, and code quality](#3-architecture-design-and-code-quality) — `codebase-design` · `domain-modeling` · `improve-codebase-architecture` · `tdd` · `diagnosing-bugs` · `code-review` · `receiving-code-review`
  4. [Git, merging, and safeguards](#4-git-merging-and-safeguards) — `resolving-merge-conflicts` · `git-guardrails-claude-code` · `setup-pre-commit` · `pr`
  5. [CRG — code graph navigation](#5-crg--code-graph-navigation-from-code-review-graph-mcp) — `crg-explore-codebase` · `crg-debug-issue` · `crg-refactor-safely` · `crg-review-changes`
  6. [Prototyping, learning, handoff](#6-prototyping-learning-and-context-handoff) — `prototype` · `frontend-design` · `research` · `teach` · `handoff` · `retro` · **`ship-report`** · **`post-deploy-check`**
  7. [Utilities, migrations, meta-skills](#7-utilities-migrations-and-meta-skills) — `migrate-to-shoehorn` · `scaffold-exercises` · `writing-for-agents` · `wizard` · `wait-what` · `setup-matt-pocock-skills` · `caveman` · **`repo-bootstrap`**
- [🏭 AI-factory pipeline (9 custom skills)](#-ai-factory-pipeline-custom-skills-not-pocock)
- [🎀 Ponytail — lazy senior mode (6 skills)](#-ponytail--lazy-senior-mode-6-skills-not-pocock) — **`ponytail`** · **`ponytail-review`** · **`ponytail-audit`** · **`ponytail-debt`** · **`ponytail-gain`** · **`ponytail-help`**
- [🔗 Skill combinations](#-skill-combinations-for-better-results)
  - [Planning → delivery](#planning--delivery) · [Design / architecture](#design--architecture) · [Bugs / quality](#bugs--quality) · [Intake / process](#intake--process) · [Migration / parity](#migration--parity-legacy--new)
  - [➕ Skill + MCP](#-skill--mcp-combinations-for-better-results)
- [🔌 MCP servers on the machine](#-mcp-servers-on-the-machine)
  - [Shared MCPs](#shared-mcps-both-claude-and-cursor) · [Claude only](#claude-only) · [Cursor only](#cursor-only)
- [🧩 Plugin / built-in skills](#-plugin--built-in-skills-outside-agentsskills)
  - [Plugin skills (figma, figma-friend)](#plugin-skills-from-claudeplugins-managed-by-the-marketplace) · [Built-in harness skills](#built-in-harness-skills-ship-with-claude-code-not-on-disk)
- [🎬 End-to-end scenarios (prompts)](#-end-to-end-scenarios-prompts)
- [🔬 A self-checking review pass (how to get one every time)](#-a-self-checking-review-pass-how-to-get-one-every-time)
- [🛠️ How a skill works (under the hood)](#-how-a-skill-works-under-the-hood)
- [⚙️ Maintenance](#-maintenance)

---

## 1. Planning and alignment (grilling / routing)

### `ask-matt` · command

Command-category placeholder: `/command`.

- **How:** `/ask-matt` when you do not know which skill to use.
- **Where:** at the start of a task when several processes are possible.
- **Why:** a router across all manual skills — suggests the right flow instead of guessing.
- **Prompts:**
  - “/ask-matt — I have a raw QA bug report about the org-hierarchy diagram; which skill should I start with?”
  - “/ask-matt — I need to migrate a legacy form to RHF: grilling, to-spec, or straight to implement?”
  - “/ask-matt — lots of incoming client issues; how should I process them?”

### `grill-me` · command

Command-category placeholder: `/command`.

- **How:** `/grill-me` with your plan/design.
- **Where:** before coding — when the plan seems ready but has hidden gaps.
- **Why:** a relentless interview that follows every decision branch through to shared understanding.
- **Prompts:**
  - “/grill-me — person-form migration plan to RHF; expose hidden gaps in edit-session/commit.”
  - “/grill-me — selection-state design for org-hierarchy (the URL adapter drops arrays).”
  - “/grill-me — theme-flip approach through GoJS ThemeManager; where will it break?”

### `grill-with-docs` · command

Command-category placeholder: `/command`.

- **How:** `/grill-with-docs`.
- **Where:** the same grilling, but when decisions must be **recorded** in documentation.
- **Why:** writes ADR + glossary in parallel and checks the plan against the project's domain language (`GLOSSARY.md`).
- **Prompts:**
  - “/grill-with-docs — decision about notched-border fields; write ADR + glossary alongside it.”
  - “/grill-with-docs — model org vs group as one BE entity; record it in GLOSSARY.md.”
  - “/grill-with-docs — sequential-commit without batching for edit-session; justify it in an ADR.”

### `grilling` · `auto`
- **How:** say “grill my plan” / “stress-test this”.
- **Where:** a reusable interview loop called by other skills.
- **Why:** the core grilling mechanism without additional effects (documentation).
- **Prompts:**
  - “Grill this idea: extract locations into shared/ui/location-fields. Stress-test every branch.”
  - “Stress-test this: navigation badge counters through isolated useWatch.”

---

### `to-questionnaire` · command

Command-category placeholder: `/command`.

- **How:** `/to-questionnaire` when a decision depends on someone outside the conversation.
- **Where:** questions for a customer, lead, or colleague on another team.
- **Why:** turns a decision you cannot answer yourself into a Markdown questionnaire for one person: fill it in asynchronously or work through it together in a meeting. The inverse of `grill-me`: interview someone else rather than yourself.
- **Prompts:**
  - “/to-questionnaire — for the designer: what should we do with the empty table state on mobile?”
  - “/to-questionnaire — questions for the backend about the pagination contract, to send in Slack.”

## 2. Requirements → tasks → implementation

### `to-spec` · command

Command-category placeholder: `/command`.

- **How:** `/to-spec` after discussion.
- **Where:** when everything has already been discussed in chat and a PRD is needed.
- **Why:** synthesizes a PRD from the conversation (without an interview) and publishes it to the tracker.
- **Prompts:**
  - “/to-spec — build a PRD from our discussion about the diagram's theme-flip and put it in the tracker.”
  - “/to-spec — we discussed person media-upload (DropZone + MediaService); synthesize a PRD.”

### `to-tickets` · command

Command-category placeholder: `/command`.

- **How:** `/to-tickets` with a plan/PRD.
- **Where:** when a plan needs to be split into independent tasks.
- **Why:** vertical tracer-bullet slices — each issue can be picked up independently.
- **Prompts:**
  - “/to-tickets — split the badge-counter PRD into tracer-bullet issues.”
  - “/to-tickets — break down the Formik→RHF form migration plan into independent slices.”

### `triage` · command

Command-category placeholder: `/command`.

- **How:** `/triage`.
- **Where:** incoming bugs/features/external PRs that need sorting.
- **Why:** takes an issue through a role state machine and writes agent-ready briefs.
- **Prompts:**
  - “/triage — sort these 12 incoming QA bugs, assign roles, write briefs.”
  - “/triage — external PR + 3 feature requests; take them through the role state machine.”

### `implement` · command

Command-category placeholder: `/command`.

- **How:** `/implement` with a PRD or set of issues.
- **Where:** when requirements are ready and it is time to code.
- **Why:** structured implementation of a piece of work against a specification.
- **Prompts:**
  - “/implement — issue #142 (navigation badge counters) according to the specification.”
  - “/implement — theme-flip PRD; implement the first vertical slice.”

### `wayfinder` · command

Command-category placeholder: `/command`.

- **How:** `/wayfinder` for work that does not fit in one agent session.
- **Where:** a large, vague idea (‘fog’) — the route to the goal is not yet visible; standard `to-spec`/`to-tickets` is premature.
- **Why:** builds a shared map of investigation tickets in the tracker and closes them one at a time until the path to the goal becomes clear.
- **Prompts:**
  - “/wayfinder — migrating the form library across the entire codebase; this is more than one session. Map it into investigation tickets and proceed one at a time.”
  - “/wayfinder — org-restructure is vague at the start; build a map and follow it to a clear plan.”

---

### `implement-spec` · command

Command-category placeholder: `/command`.

- **How:** `/implement-spec` after `to-spec` + `to-tickets`.
- **Where:** the specification is already broken into tickets with blocking relationships.
- **Why:** implements the entire specification in one run. Reads tickets as a task graph, launches executor subagents in their own worktrees along the ready frontier, brings everything into one integration branch, and completes `code-review`. A parallel alternative to `implement`, which handles one ticket at a time.
- **Prompts:**
  - “/implement-spec — the org-type-morph spec and its tickets in `work/`; implement everything on an integration branch.”

## 3. Architecture, design, and code quality

### `codebase-design` · `auto`
- **How:** “design the module interface”, “make the code more testable”.
- **Where:** designing/improving a module interface, choosing a seam.
- **Why:** a shared vocabulary of deep modules — fewer small, leaky abstractions.
- **Prompts:**
  - “Design a deep, testable interface for the org-hierarchy module. Where should the seam go?”
  - “Make the selection-state controller more testable — which seam should move into a hook?”
  - “How can we deepen DropZone/MediaService to reduce leaky abstractions?”

### `domain-modeling` · `auto`
- **How:** “let's record domain terminology”, “write an ADR”.
- **Where:** when ubiquitous language or a written architectural decision is needed.
- **Why:** builds and refines the domain model, maintains `GLOSSARY.md` + ADR.
- **Prompts:**
  - “Let's record ubiquitous language for org vs group (one BE entity) and write an ADR.”
  - “Write an ADR about person-position write-keys (name, not positionName, positionId…).”

### `improve-codebase-architecture` · command

Command-category placeholder: `/command`.

- **How:** `/improve-codebase-architecture`.
- **Where:** when you want to find what to deepen/simplify in the codebase.
- **Why:** scans code, produces a visual HTML opportunities report; then you grill the selected option.
- **Prompts:**
  - “/improve-codebase-architecture — scan the codebase and give me an HTML opportunities report.”
  - “/improve-codebase-architecture — where in modules/ is duplication greatest and depth missing?”

### `tdd` · `auto`
- **How:** “let's do test-first”, “red-green-refactor”, “integration tests”.
- **Where:** a new feature or bug fix through tests.
- **Why:** a disciplined red→green→refactor cycle.
- **Prompts:**
  - “Let's build the badge counter test-first: red-green-refactor.”
  - “Selection-state integration tests: nodeClick opens the sidebar, selectionChanged clears it.”
  - “Fix the focus() bug (reveal-only during multiselect), starting with a failing test.”

### `diagnosing-bugs` · `auto`
- **How:** “diagnose”, “debug this”, “something crashes/is slow”.
- **Where:** difficult bugs and performance regressions.
- **Why:** reproduce → minimize → hypothesis → instrument → fix → regression-test loop.
- **Prompts:**
  - “Diagnose: the diagram resets to root after theme-flip. Reproduce and minimize.”
  - “Debug this: selectedOrgIds gets lost on shift-click.”
  - “Something is slow with a large org-hierarchy tree — find the cause.”

### `code-review` · `auto` ⚠️ *(name collision — see note below)*
- **How:** “review since X”, “review this branch/PR/WIP changes”.
- **Where:** reviewing a diff from a fixed point (commit/branch/tag/merge-base) along two axes.
- **Why:** runs two subagents in parallel — **Standards** (does the code follow the repo's documented standards?) and **Specification** (does the code match the issue/PRD/spec it came from?) — and displays their reports side by side.
- **⚠️ Do not confuse it with the other two ‘code-review’ tools:** the built-in harness skill `/code-review` (bugs/simplification, low→ultra — see [Built-in harness skills](#built-in-harness-skills-ship-with-claude-code-not-on-disk)) and `crg-review-changes` (graph review through `code-review-graph`). All three respond to “review changes”, but along different axes. If invoking `/code-review` and expecting the Pocock version (Standards+Spec), say so explicitly in the prompt.
- **Prompts:**
  - “Review since main — check the branch against repo Standards and the Specification in issue #142.”
  - “Review this PR along two axes: whether it meets coding standards and fulfills the original PRD.”

### `receiving-code-review` · `auto` ⚠️ *(not Pocock — from `obra/superpowers`)*
- **How:** “I received a review; how should I respond?”, “respond to review feedback” — or automatically when review feedback arrives.
- **Where:** AFTER any review (`/code-review`, the `code-review` skill, `crg-review-changes`, an external PR reviewer) — **before** applying fixes.
- **Why:** technical discipline for *receiving* feedback — verify-before-implement, **no performative agreement** (“You're absolutely right!”/“Thanks!”), push back with technical reasoning, clarify ambiguity **BEFORE** partial implementation, fix **one item at a time** with a test; treat external reviewers skeptically + YAGNI-grep (is the thing they want ‘done properly’ even used?).
- **⚠️ Provenance:** the only skill in the store **not** from `mattpocock/skills`, but from `obra/superpowers`; Pocock-sync does **NOT** touch it (see [⚙️ Maintenance](#-maintenance)). It is a review **consumer**, not a producer — do not confuse it with the three ‘code-review’ tools that *perform* reviews.
- **Prompts:**
  - “A review arrived for branch gamma — respond using receiving-code-review: verify each point against the code, clarify ambiguity, avoid performative thanks, fix one item at a time.”
  - “An external PR reviewer asks to ‘do it properly’ — YAGNI-grep, push back with technical reasoning, do not implement blindly.”

---

## 4. Git, merging, and safeguards

### `resolving-merge-conflicts` · `auto` ⚠️ *(removed upstream on 2026-09-24; retained here as custom)*
- **How:** during an active merge/rebase with conflicts.
- **Where:** there is an unresolved git conflict.
- **Why:** guides conflict resolution step by step.
- **Prompts:**
  - “I have a conflict rebasing gamma onto main. Guide me through resolving it step by step.”
  - “Conflict in yarn.lock + two moved org-hierarchy files; resolve it.”

### `git-guardrails-claude-code` · `auto`
- **How:** “add git protection”, “block push/reset”.
- **Where:** when you want to prevent destructive git commands.
- **Why:** installs Claude Code hooks that block `push`, `reset --hard`, `clean`, `branch -D`, etc. **before** execution.
- **Prompts:**
  - “Install git protection: block push, reset --hard, clean, branch -D before execution.”
  - “Add hooks to prevent accidentally pushing directly to main.”

### `setup-pre-commit` · `auto`
- **How:** “add pre-commit hooks”, “set up Husky/lint-staged”.
- **Where:** a new repo without commit-time checks.
- **Why:** Husky + lint-staged (Prettier) + typecheck + tests on commit.
- **Prompts:**
  - “Set up Husky + lint-staged (Prettier) + typecheck + tests on commit.”
  - “Add pre-commit that runs tsc -p tsconfig.app.json and vitest on staged files.”

---

### `pr` · `auto`
- **How:** activates when you write a PR description; manually — `/pr`.
- **Where:** the branch is ready and needs a PR body.
- **Why:** Summary (diagram, diff sketch, or tree) → Evidence (before/after: screenshot, output, test) → Merge Danger (one-way or two-way door, blast radius). Brief, no preamble, using domain language from `GLOSSARY.md`. Adapted from `show-me` (Humanlayer).
- **Prompts:**
  - “Write a PR description for GUI-611 on `navigate-v3`.”

## 5. CRG — code graph navigation *(from code-review-graph MCP)*

### `crg-explore-codebase` · `auto`
- **How / Where / Why:** understand an unfamiliar codebase's structure through a knowledge graph.
- **Prompts:**
  - “Explain the structure of modules/org-hierarchy through the knowledge graph.”
  - “Where does selection-state reach across the codebase? Build and show the graph.”

### `crg-debug-issue` · `auto`
- **How / Where / Why:** systematic debugging through code graph navigation.
- **Prompts:**
  - “Systematically debug why focus() re-selects, using graph navigation.”
  - “Find every place that writes selectedOrgIds through the graph.”

### `crg-refactor-safely` · `auto`
- **How / Where / Why:** planning and safe refactoring through dependency analysis (impact radius).
- **Prompts:**
  - “I want to extract selection-state into a hook — show the impact radius before refactoring.”
  - “Safely move country-roots-panel into modules/org-hierarchy: what are the dependencies?”

### `crg-review-changes` · `auto`
- **How / Where / Why:** structured code review through detect-changes + impact analysis.
- **Prompts:**
  - “Review changes on branch gamma with impact analysis.”
  - “Detect-changes for the latest commit + what is silently affected outside the diff.”

---

## 6. Prototyping, learning, and context handoff

### `prototype` · command

Command-category placeholder: `/command`.

- **How:** `/prototype`.
- **Where:** explore a design before committing — state logic OR several UI options.
- **Why:** a throwaway prototype: a runnable terminal app for business logic, or switchable UI variations on one route.
- **Prompts:**
  - “/prototype — 3 layout options for country-roots-panel on one route.”
  - “/prototype — explore selection-state logic as a runnable terminal app.”

### `frontend-design` · `auto` ⚠️ *(not Pocock — a fork of `anthropics/skills`)*
- **How:** triggers on “build a screen/portal/site”, “make it not look like AI”, questions about palette/typography/density. Manually — `/frontend-design`.
- **Where:** the visual side of UI — a new screen or an existing screen's appearance redesign.
- **Why:** 6 steps with verifiable criteria, rather than advice. The key is the **branch at step 1**:
  - **Page** (landing page, site) — the unit is a page, signature = hero thesis;
  - **System** (portal, app, dashboard) — the unit is a *set of screens*, no hero, **signature = what repeats** (density, type scale, field behavior, state language, transition motif). Test: a screenshot of **any** screen must be recognizable as this product.
- **Step 2 prevents the main harm:** in an existing product, most axes are **already spent** — the skill tells you to find the token source, component inventory, theme mechanism, parity gate, and styling idiom, rather than reopen the palette decision.
- **Step 4 — calibration:** three ‘default AI looks’ with specific hex values + three system-specific defaults (an ‘icon+label’ sidebar, shadowed cards on gray, a row of 4 stats above a table, a gray spinner for every state).
- **Step 6 — gate:** without a screenshot, the design is not ready; if you cannot capture one, say so rather than stay silent.
- **Copywriting** — a separate `WRITING.md` file (progressive disclosure), read when writing interface text.
- **Prompts:**
  - “Build screen <X> — this is a portal, not a landing page; the signature belongs in primitives, not a hero.”
  - “Redesign <screen>. First, step 2: name which axes the design system has already spent.”
  - “Design direction for <product>, and check the plan against the three AI defaults.”
- ⚠️ **Fork.** Upstream — `anthropics/skills@2235be7c60`; resync only manually, by diff against that commit. The license is alongside it in `LICENSE.txt`.

### `research` · `auto` ⚠️ *(do not confuse with `deep-research`; see note below)*
- **How:** “research X”, “collect facts from docs/API”, “delegate reading to a background agent”.
- **Where:** a question worth checking against reliable primary sources (docs, APIs, code); the result is a file in the repo.
- **Why:** starts a background agent that reads while you keep working; records findings in a Markdown file in the repository.
- **⚠️ Do not confuse** with built-in `deep-research` (fan-out web research across external sources with adversarial checking and citations — see [Built-in harness skills](#built-in-harness-skills-ship-with-claude-code-not-on-disk)). `research` is more targeted and background-oriented (docs/API/code within the task); `deep-research` is a broader report from the external web.
- **Prompts:**
  - “Research — determine whether tanstack query v5 supports subscribing to several query keys at once; record it in a file.”
  - “Delegate to a background agent: gather facts from RAC docs about ComboBox keyboard navigation while I continue another task.”

### `teach` · command

Command-category placeholder: `/command`.

- **How:** `/teach`.
- **Where:** learn a concept/skill directly in the workspace.
- **Why:** multi-session learning with materials and progress tracking.
- **Prompts:**
  - “/teach — teach GoJS ThemeManager right in the workspace, tracking progress.”
  - “/teach — RHF + Zod resolver patterns using person-form as an example.”

### `handoff` · command

Command-category placeholder: `/command`.

- **How:** `/handoff` at the end of a session.
- **Where:** context must be handed to another agent / a new session.
- **Why:** compresses the conversation into a compact handoff document.
- **Prompts:**
  - “/handoff — end of session; compress context for the next agent.”
  - “/handoff — pass the current state of theme-flip work to a new session.”

---

### `retro` · command

Command-category placeholder: `/command`.

- **How:** `/retro` at the end of a coding session (in that same session).
- **Where:** a just-completed task or fixed bug.
- **Why:** examines the session and suggests changes to the agent's environment rather than code: navigation pointers, automated checks, code standards, steering files, tool savings, access to information. Converts mechanical standard violations into deterministic checks (lint, pre-commit, CI), leaving `CODING_STANDARDS.md` for genuine judgment calls.
- **Prompts:**
  - “/retro — what in the repo made it hard to quickly find where Navigate history focus lives?”
  - “/retro after fixing the bug: what would have prevented it?”

## 7. Utilities, migrations, and meta-skills

### `migrate-to-shoehorn` · `auto`
- **How:** “shoehorn”, “remove `as` in tests”.
- **Where:** test files containing `as` assertions.
- **Why:** migration to `@total-typescript/shoehorn` (partial test data without `as`).
- **Prompts:**
  - “Remove `as` assertions in mapper tests; migrate to shoehorn.”
  - “Partial test data for person schemas without `as` — move it to shoehorn.”

### `scaffold-exercises` · `auto`
- **How:** “scaffold exercises”, “new course section”.
- **Where:** creating an exercise structure (sections/problems/solutions/explainers).
- **Why:** generates stubs that pass lint immediately.
- **Prompts:**
  - “Scaffold a new course section: sections/problems/solutions/explainers, passing lint immediately.”
  - “Create exercise scaffolds for ‘RHF + Zod’.”

### `writing-for-agents` · `auto`
- **How:** activates when creating or editing a skill or modifying `AGENTS.md` / `CLAUDE.md`; manually — `/writing-for-agents`.
- **Where:** any document an agent will read: a skill, `AGENTS.md`, `CLAUDE.md`.
- **Why:** a reference for principles and vocabulary that make such documents predictable. Successor to `writing-great-skills` (upstream renamed and restructured it on 2026-07-23).
- **Prompts:**
  - “/writing-for-agents — edit my new skill to make it predictable.”
  - “How should I write description triggers so automatic activation works?”
  - “Reread this `AGENTS.md` through an agent's eyes: what is unnecessary or ambiguous?”

### `wizard` · `auto`
- **How:** activates when the agent encounters a step only a person can perform; manually — `/wizard`.
- **Where:** infrastructure provisioning, CI credentials or secrets, an unfamiliar third-party control panel, a one-time migration or switchover.
- **Why:** instead of numbered chat instructions, generates an interactive bash script: opens the relevant URLs, tells you what to click, collects values, and writes them to `.env` or GitHub Actions secrets. Not invoked for steps the agent can perform itself.
- **Prompts:**
  - “We need to create an OAuth application in Google Cloud and put keys in `.env` — make a wizard.”
  - “/wizard — guide me through setting up CI secrets for deployment.”

### `wait-what` · command

Command-category placeholder: `/command`.

- **How:** `/wait-what` immediately after an agent message you did not understand.
- **Where:** any conversation where an answer is too long or unclear.
- **Why:** the agent restates its last message: some context, ASD-STE100 Simplified Technical English, and domain language from `GLOSSARY.md`.
- **Prompts:**
  - “/wait-what”

### `setup-matt-pocock-skills` · command

Command-category placeholder: `/command`.

- **How:** `/setup-matt-pocock-skills` **once** per repo.
- **Where:** before first using engineering skills (`to-tickets`, `triage`, `tdd`, `diagnosing-bugs`, `improve-codebase-architecture`…).
- **Why:** configures the issue tracker, triage-label vocabulary, and domain documentation layout.
- **Prompts:**
  - “/setup-matt-pocock-skills — configure the issue tracker, triage labels, and domain docs in this repo (once).”

### `caveman` · `auto`
- **How:** “caveman mode”, “be brief”, `/caveman`.
- **Where:** maximum brevity and low token cost.
- **Why:** ultra-concise mode (~−75% tokens) without losing technical accuracy.
- **Prompts:**
  - “Caveman mode. Briefly: how do I invoke make:entity?”
  - “Be brief: org vs group in two sentences.”

---

# 🏭 AI-factory pipeline *(custom skills, not Pocock)*

> Nine skills that turn ‘AI as copilot’ into ‘AI as a team’: understanding → selection → plan →
> two gates → tests before code → execution → report. Written against the `writing-great-skills` rubric (now `writing-for-agents`),
> plan and reconciliation — `~/.agents/ai-factory-plan.md`.
>
> **Chain:** `repo-bootstrap` → `cto-research` → `cto-agenda` → `spec-flow`
> (inside: `acceptance-spec`, GATE 2 = `plan-critique` + `plan-defense`, then `tdd` → `code-review`)
> → `ship-report` → deployment → `post-deploy-check`.

**Two foundations without which the chain falls apart:**

- `~/.agents/rules/repo-standards-manifest.md` — **process in the skill, yardstick in the repo**
  (`<repo>/.claude/standards.md`). Global skills stop guessing standards through it,
  making a copy of the skill in every repo unnecessary. §0 binds the yardstick to the **language**
  (Pocock applies only to TS; in a polyrepo this is not a formality).
- `~/.agents/rules/multi-model-roles.md` — who delivers a verdict on someone else's artifact.
  Author ≠ critic, implementer ≠ reviewer; a `fork` does **not** count as a lens (it inherits the model and context).

### `repo-bootstrap` · `auto`
- **How:** “initialize the repo”, “what is missing in the repo”, “set up the project”.
- **Where:** a new or unfamiliar repo; checking whether an existing one is ready.
- **Why:** a 10-row inventory (`present` / `absent` / `present but drifted`) and creation of missing items.
  **Does not invent content:** absent from the repo — `⚠️ missing`, a human decision — `TODO:`. This is how dg
  was found to have no lint at all and no yardstick for its Rust portion.
- **Prompts:**
  - “repo-bootstrap — check what this repo lacks for the pipeline; do not write anything.”
  - “Initialize the repo: create the manifest and CLAUDE.local.md; list the rest.”

### `cto-research` · `auto`
- **How:** “briefing”, “understand the product”, “cto research”.
- **Where:** before planning a significant feature; when starting in an unfamiliar repo.
- **Why:** one briefing per repo as a **cache** of primary sources — each claim has `path:line`; on
  disagreement, corrects the source. A **freshness gate** against `HEAD`: rebuilds only affected sections.
- **Prompts:**
  - “cto-research — prepare a briefing before planning export.”
  - “Is the briefing stale? Run the freshness gate and update affected sections.”

### `cto-agenda` · `auto`
- **How:** “what next”, “what should we work on”, “make a backlog”.
- **Where:** P0 is closed and the queue is empty; a direction must be chosen.
- **Why:** candidates from **six listed sources**, axes **unblocking × reversibility**, and **one**
  next move + why not the others. A product fork goes to the person rather than being disguised as a task.
- **Prompts:**
  - “cto-agenda — P0 is closed; what should we take next and why this specifically?”
  - “Prepare the agenda and separately list the decisions that are mine.”

### `spec-flow` · `auto`
- **How:** “feature through SDD”, “specify the feature”, “spec-flow”.
- **Where:** a new subsystem/slice, a public API change, a cross-cutting change. Threshold comes from the manifest.
- **Why:** a **thin** orchestrator: spec → GATE 1 → plan → GATE 2 → tasks → implement → verify → wrap,
  with each role performed by its specialist skill. Only the sequence and gates are its own.
- **Prompts:**
  - “spec-flow for a new entity — guide it from specification to report.”
  - “Was the threshold met? If not, say so and make a lightweight inline plan.”

### `plan-critique` · `auto`
- **How:** “roast the plan”, “plan critique”.
- **Where:** GATE 2, after writing the plan, before splitting into tasks.
- **Why:** four lenses **blind to each other** — AI-slop / logical gaps / excess complexity /
  edge cases. Reads the **plan** (unlike `grilling`, which questions **you**).
  A lens that did not return means a red gate, not ‘clean’.
- **Prompts:**
  - “plan-critique on plan.md — four lenses, summarize blocking findings separately.”
  - “How many lenses were launched and how many returned?”

### `plan-defense` · `auto`
- **How:** “plan defense”, “what happens if”.
- **Where:** GATE 2, the last step before tasks.
- **Why:** five fixed questions (bad input · dependency failure · race and repeated invocation ·
  boundary data · rollback), each answered by a **line in the plan**, not a chat response.
- **Prompts:**
  - “plan-defense — run the five questions and put the table in the plan.”
  - “How many gaps remain? Zero means we move to tasks.”

### `acceptance-spec` · `auto`
- **How:** “acceptance criteria”, “test scenarios”, “acceptance”.
- **Where:** inside the plan, **before** code.
- **Why:** the feature as **observable behavior**: scenario · precondition · action · expected
  result · verification method. Three mandatory groups: happy path / boundaries / failures.
  ‘The list updates correctly’ fails; ‘0 rows and empty-state text’ passes.
- **Prompts:**
  - “acceptance-spec for this feature — table in plan.md, then tasks by row.”
  - “How many rows remain manual?”

### `ship-report` · `auto`
- **How:** “feature report”, “summarize the work”, “ship report”.
- **Where:** feature completion, before deployment.
- **Why:** six fixed sections (completed / tested scenarios / non-obvious details / screenshots /
  user-flow walkthrough / risks) as a **delta** to the plan — matches collapse into links; only
  deviations are expanded. Section 2 is the `acceptance-spec` acceptance table with ‘actual
  result’ and ‘verdict’ added, not prose. An empty section says ‘not applicable because…’; it is not deleted.
- **Prompts:**
  - “ship-report for this feature — delta to plan.md, a table with verdicts.”
  - “How many acceptance-table rows remain ‘not verified’?”

### `post-deploy-check` · `auto`
- **How:** “check production”, “deployed — check it”, “post-deploy”.
- **Where:** after rollout; for dg — after `pages.yml`, for frontend — at the production URL.
- **Why:** reruns **key** scenarios on real data and appends to **the same** report.
  Value lies in **differences** between production ⟂ test; a match adds nothing. Unavailable things (logs, read-only DB)
  are labeled unavailable — silent omissions turn the report into a signature on unchecked work.
  Separately identifies **which build** actually opened: caches and CDNs serve old builds more often than it seems.
- **Prompts:**
  - “post-deploy-check for the Pages demo — which rows did you rerun and what differed?”
  - “Which logs and integrations are actually available here?”

### Anti-patterns ❌
- ❌ calling gates ‘when I remember’ — GATE 2 must be called from `spec-flow`; otherwise the skills exist but do not act.
- ❌ a verdict on your own artifact (the planner critiques their own plan) — violates `multi-model-roles` §3.
- ❌ a `review`/`spec-flow` copy in every repo — repo specifics belong in `.claude/standards.md`, not the skill.
- ❌ a Pocock finding on `.rs`/`.py` — invalid by construction; bind the yardstick to the language.
- ❌ a second report for the same feature after deployment — post-deploy appends to the existing one; otherwise the feature's history falls apart into files no one reconnects.

---

# 🎀 Ponytail — lazy senior mode *(6 skills, not Pocock)*

> Six skills from [`DietrichGebert/ponytail`](https://github.com/DietrichGebert/ponytail) (MIT).
> One mode and five one-off cards around it. One idea: **the best code is code never
> written**, so before building anything, the agent climbs a ladder and stops at the first
> rung that holds:
>
> `1. is this needed at all (YAGNI)` → `2. already in the codebase` → `3. stdlib` →
> `4. native platform capability` → `5. installed dependency` → `6. one line` →
> `7. only then — the minimum working code`.
>
> **The ladder works *after* understanding the task, not instead of it** — this is the skill's main boundary:
> a lazy solution, not lazy reading. Never cuts validation at the trust boundary, error handling,
> security, or basic accessibility.
>
> **Chain:** `ponytail` (during work) → `ponytail-review` (on the diff) → `ponytail-audit`
> (across the whole repo) → `ponytail-debt` (a register of consciously deferred work). `ponytail-help` and
> `ponytail-gain` are reference and impact cards; they do not do the work.
>
> ⚠️ **Our installation is folder-to-folder, not a plugin.** Upstream installs as a marketplace plugin with
> two Node hooks; we took only six `SKILL.md` files. Consequently: **no automatic activation at
> session start**, and `PONYTAIL_DEFAULT_MODE` / `~/.config/ponytail/config.json` do not work —
> the mode is explicitly enabled (`/ponytail`, `/ponytail ultra`). This is the only body edit in the skill
> (a note in `ponytail-help`, section `## Update`); the rest is English verbatim.

### `ponytail` · `auto` *(mode, lasts until session end)*
- **How:** `/ponytail` (`lite` | `full` — default | `ultra`); or “be lazy”, “yagni”, “do not overcomplicate”. Disable — “stop ponytail” / “normal mode”.
- **Where:** any coding task where the agent might build too much: a new utility, a new component, ‘add a cache’, ‘make an abstraction for the future’, library selection.
- **Why:** the ladder as a **reflex**, not research — stops at the first rung that holds. Plus two things absent from ‘just be brief’: a bug fix targets the **root** (one guard in a shared function is a smaller diff than a guard in every caller), and a deliberate simplification with a ceiling leaves a comment `ponytail: <ceiling>, <upgrade path>` — this is what `ponytail-debt` later collects.
- **Prompts:**
  - “/ponytail — need a date field in the person form. Do not pull in a dependency if the platform can do it.”
  - “/ponytail ultra — ‘add a cache for these API responses’. First challenge the requirement itself.”
  - “ponytail full — fix the empty-selection bug in org-hierarchy: root, not symptom; one guard must cover every caller.”

### `ponytail-review` · `auto`
- **How:** `/ponytail-review`, “review for over-engineering”, “what can be deleted here”.
- **Where:** on a diff / branch / PR — **alongside** normal review, not instead.
- **Why:** one axis instead of ‘generally good, but…’: `delete:` · `stdlib:` · `native:` · `yagni:` · `shrink:`, one line per finding in the format `L12-38: stdlib: 27-line validator. "@" in a string, 1 line.`, and a `net: -N lines possible` summary. Applies nothing. Bugs, security, and performance are **deliberately out of scope** — `code-review` (§3) handles those; one smoke/`assert` check is the ponytail minimum and is never proposed for deletion.
- **Prompts:**
  - “/ponytail-review on the t98 branch diff — only excess complexity, net at the end.”
  - “Is this over-engineering? Run ponytail-review on `packages/sdk/src/export`.”
  - “ponytail-review on this PR; do not apply findings — give me a list to choose from.”

### `ponytail-audit` · `auto`
- **How:** `/ponytail-audit`, “audit for over-engineering”, “what can be removed from this repo”.
- **Where:** a one-off pass over the **entire tree**, before a diff exists: before a large refactor, entering an unfamiliar repo, or when the backlog is empty and you need to find the biggest cuts.
- **Why:** the same as `ponytail-review`, but ranked **largest cut first**, with `net: -N lines, -M deps possible`. Looks for specifics: dependencies duplicating the platform, single-implementation interfaces, single-product factories, wrappers that only delegate, dead flags and configs.
- **Prompts:**
  - “/ponytail-audit across `packages/sdk` — rank it, largest cut first.”
  - “Bloat audit: which dependencies do what the platform already supports?”
  - “ponytail-audit across cassiopeia-admin-ui — top 10 and `net`; touch nothing.”

### `ponytail-debt` · `auto`
- **How:** `/ponytail-debt`, “what did we leave for later”, “list the shortcuts”.
- **Where:** after several sessions in `ponytail` mode; before sprint planning or release.
- **Why:** `grep` over `ponytail:` markers turns scattered comments into a **register** — one row per marker, grouped by file: `<file>:<line>, what was simplified. ceiling: <ceiling>. upgrade: <trigger to revisit>.`. Markers **without a trigger** are labeled `no-trigger` — those quietly decay into ‘later = never’. This is the **only** real number for the repo (unlike `ponytail-gain`). On request, writes the register to a file (`PONYTAIL-DEBT.md`).
- **Prompts:**
  - “/ponytail-debt — collect all `ponytail:` markers; show `no-trigger` separately.”
  - “What did we consciously simplify in the export pipeline, and what triggers a return to it?”
  - “ponytail-debt and put the register in `work/tech-debt/ponytail-debt.md`.”

### `ponytail-gain` · `auto` *(one-off card)*
- **How:** `/ponytail-gain`, “what does ponytail give us”, “show the effect”.
- **Where:** to show yourself or the team why the mode matters.
- **Why:** an ASCII scoreboard: ‘less code / cheaper / faster’. Does not change the mode and **deliberately does not calculate savings for a specific repo**: nobody wrote the unbuilt version, so there is no baseline to subtract from — the card itself directs you to `/ponytail-debt` and `/ponytail-audit` for real numbers.
- **⚠️ The card's numbers are outdated.** The scoreboard prints medians from the **old single-shot** benchmark (−80–94% code, −47–77% cost). Upstream's README itself acknowledges this measurement as partly an artifact of the conversational baseline ([#126](https://github.com/DietrichGebert/ponytail/issues/126)) and provides corrected **agentic** numbers against a fair baseline: **−54% code, −22% tokens, −20% cost, −27% time, 100% safety** (12 feature tickets in a real FastAPI+React repo, Haiku 4.5, n=4). Cite the latter, not the former.
- **Prompts:**
  - “/ponytail-gain — show the scoreboard.”
  - “What does ponytail give us, and where do those numbers come from? Say which are outdated.”

### `ponytail-help` · `auto` *(one-off card)*
- **How:** `/ponytail-help`, “ponytail help”, “what commands are there”.
- **Where:** you forgot which of the six to use, or what each intensity level does.
- **Why:** one table of levels (`lite` names a lazier alternative and you choose · `full` — ladder in force · `ultra` — challenges the requirement itself) and one table of six skills. Changes nothing.
- **Prompts:**
  - “/ponytail-help — how does ultra differ from full?”
  - “ponytail help — which of the six should I use if I already have a diff?”

### Combinations with the rest of the store
- `ponytail-audit` → **`cto-agenda`** (§🏭): the audit supplies ‘what to delete’ candidates; the agenda ranks them alongside features on *unblocking × reversibility* — otherwise ‘minus 400 lines’ never competes with a new feature for attention.
- `tdd` (§3) → `ponytail-review` → **`code-review`** (§3): green tests → trim excess → only then a verdict on standards and spec. Order matters: `ponytail-review` proposes deletion; deleting without green tests is not laziness, it is a second bug.
- `ponytail` ↔ **`caveman`** (§7): orthogonal and intended as a pair — `ponytail` controls **what you build**, `caveman` controls **how you speak**. Together they produce the shortest diff and response.
- `ponytail` + **`plan-critique`** (§🏭, ‘excess complexity’ lens): the lens reads the **plan**; `ponytail-review` reads the **diff**. Thus the former catches an unnecessary abstraction before it is written; the latter after. They do not duplicate each other.
- `ponytail-debt` → **`ship-report`** (§🏭): register rows related to the feature go into ‘risks and limitations’ — otherwise only the person who made the simplification knows its ceiling.

### Anti-patterns ❌
- ❌ enabling `ponytail` for a **non-code** task (report, documentation, translation) — the skill itself forbids it, but a ‘be lazy’ prose prompt produces truncated text, not concise code.
- ❌ using `ponytail-review` **instead of** correctness review — bugs and security are outside its scope by construction; it is a second axis, not a `code-review` replacement.
- ❌ applying `ponytail-audit` findings in bulk without tests — the skill deliberately **applies nothing**; mass deletion of ‘dead flexibility’ without green tests is a classic way to break something with one live caller.
- ❌ citing `−80–94%` from `/ponytail-gain` as current numbers — that is the old single-shot measurement; current numbers are `−54% / −20% / −27%` (see above).
- ❌ expecting the mode to enable itself at session start — we have no plugin hooks; `/ponytail` must be called.

---

# 🔗 Skill combinations (for better results)

> **skill→skill** combination format (below): **Chain → when → why**, followed by **Step by step (with handoffs)** — what each stage gives the next, **Boost/Prerequisite** (which MCP or setup enhances it), **Anti-patterns** ❌, and **Prompts**. `→` sequential; `↔` mutually reinforcing. 🏁 — end-to-end example recipes (feature delivery / refactoring). The [➕ Skill + MCP](#-skill--mcp-combinations-for-better-results) block is lighter (Chain/when/why/prompts).

## Planning → delivery

### `grilling` — interview-loop core *(called from inside other skills)*
- **Chain:** no next step of its own — a reusable engine that `grill-me`, `grill-with-docs`, and `improve-codebase-architecture` (step 3) call internally.
- **When:** you want an interview loop without side effects (no PRD/ADR writing) — for example, inside another skill or manually for a quick pass.
- **Why:** one implementation of the grilling mechanism (one question at a time, with a recommended answer, until shared understanding) — other skills do not duplicate this logic, only add an effect (writing docs) or not.
- **`grill-me` / `grill-with-docs` / `grilling` distinction:** `grill-me` = `/command` (command) over `grilling`, no docs. `grill-with-docs` = `/command` over `grilling` + `domain-modeling`, with ADR/glossary. `grilling` = core; call it directly with a trigger phrase when neither effect is needed.
- **Combination points:** `grilling` ↔ `domain-modeling` (refine terms without a separate ADR) · `grilling` ← `improve-codebase-architecture` (step 3, finish pressure-testing the chosen refactor plan) · `grilling` ← `prototype` (pressure-test the chosen UI/logic option based on what you saw).
- **Anti-patterns:**
  - ❌ grilling every small step separately instead of one pass to shared understanding — client-side ‘interviewing for its own sake’.
  - ❌ confusing it with `grill-me`/`grill-with-docs` in a prompt for another agent — if you need an effect (docs), name it explicitly.
- **Prompts:**
  - “Grill this idea: extract locations into shared/ui/location-fields. Ask one question at a time, with a recommended answer for each.”
  - “Stress-test this: theme-flip through GoJS ThemeManager. Where does it break?”
  - “(inside improve-codebase-architecture) — now grill the chosen TOP-1 refactor plan: where the abstraction leaks, edge cases, how to migrate incrementally.”

### `grill-me` → `to-spec` → `to-tickets` → `implement` 🏁 *(flagship feature-delivery recipe)*
- **Chain:** grill a raw idea → synthesize a PRD → split into issues → implement.
- **When:** the feature is ‘in your head’ and must become code without losing decisions.
- **Why:** each step preserves the previous context; `implement` starts with clear agent-ready tasks rather than fog.

- **Prerequisite:** `/setup-matt-pocock-skills` (once per repo) — otherwise `to-spec`/`to-tickets` have nowhere to write.
- **Step by step (with handoff artifacts):**
  1. **`/grill-me`** — interview on the raw idea → close open questions. → **Handoff:** decision list + scope boundaries.
  2. **`/to-spec`** — synthesize the conversation (no repeat interview). → **Handoff:** PRD in the tracker.
  3. **`/to-tickets`** — PRD → vertical tracer-bullet slices. → **Handoff:** independent issues with criteria.
  4. **`/implement`** — each issue → code against the specification. → **Handoff:** PR/changes.
- **Boost:** `context7` at step 4 if implementation depends on a library API; `tdd` inside `implement` for critical logic.
- **Anti-patterns:**
  - ❌ jumping into `/implement` without grill-me → implementing fog.
  - ❌ `/to-tickets` without a PRD → issues without context or acceptance criteria.
- **Prompts:**
  - “I have a raw badge-counter idea. Run the full cycle: `/grill-me` → `/to-spec` → `/to-tickets` → `/implement`.”
  - “Take theme-flip from idea to code through grill-me → to-spec → to-tickets → implement.”

### `wayfinder` → `to-tickets` (per investigation ticket) *(when a feature is too large for one session)*
- **Chain:** a huge vague idea → `wayfinder` builds an investigation-ticket map in the tracker → each ticket closes in its own session until the path to the goal becomes clear → then standard `to-spec`/`to-tickets`/`implement` on clarified work.
- **When:** an idea is too large for one `/grill-me`/`to-spec` pass — ‘fog’: the structure of the work itself remains unknown, not just implementation details.
- **Why:** `to-spec`/`to-tickets` assume the plan is clear; `wayfinder` is the preceding step when clarity is missing.
- **Prerequisite:** `/setup-matt-pocock-skills` (issue tracker for the map).
- **Step by step (with handoff artifacts):**
  1. **`/wayfinder`** — vague idea → shared investigation-ticket map in the tracker. → **Handoff:** map + first ticket in progress.
  2. **Resolve tickets one by one** — each closed ticket clarifies the map (adds/closes neighboring tickets). → **Handoff:** updated map.
  3. **Once the route is clear** — move to standard `/to-spec` → `/to-tickets` → `/implement` on the now-defined work.
- **Anti-patterns:**
  - ❌ immediately trying to `/to-spec` a huge vague idea → a guess-based PRD and acceptance criteria built on sand.
  - ❌ resolving all investigation tickets in parallel instead of one by one → the map loses its ‘clarify along the way’ purpose.
- **Prompts:**
  - “/wayfinder — moving the form library across the whole codebase; more than one session. Build an investigation-ticket map and proceed one at a time.”
  - “Org-restructure is vague initially: /wayfinder first, /to-spec once the route is clear.”

### `grill-with-docs` ↔ `domain-modeling`
- **Chain:** grilling records decisions in ADR/glossary; `domain-modeling` refines domain language and maintains `GLOSSARY.md`.
- **When:** a new subsystem or complex domain where consistent terminology is critical.
- **Why:** subsequent skills (`improve-codebase-architecture`, `diagnosing-bugs`, `tdd`) read `GLOSSARY.md` — consistent language improves their results.

- **Step by step (a mutual cycle, not linear):**
  1. **`/grill-with-docs`** — grill the decision → write ADR + draft new terms. → **Handoff:** ADR + candidate terms.
  2. **`domain-modeling`** — refines terms into ubiquitous language, integrates them into `GLOSSARY.md`, catches collisions with existing terms. → **Handoff:** updated `GLOSSARY.md`.
  3. **↩ back to `/grill-with-docs`** if modeling revealed new ambiguity — the domain rarely stabilizes on the first pass.
- **Boost:** `context7` — verify that a library supports an assumption before putting it in an ADR (fact, not guess).
- **Anti-patterns:**
  - ❌ an ADR without an agreed glossary → terms drift across code and DTOs.
  - ❌ one pass instead of a cycle → residual ambiguity leaks into implementation.
- **Prompts:**
  - “New org-type-morph subsystem: grill with docs while refining domain language + GLOSSARY.md.”
  - “Verify the organizationType contract through context7, then record ADR + glossary.”

### `research` → `grill-with-docs` ↔ `domain-modeling` *(when a decision depends on unfamiliar API/docs)*
- **Chain:** the `research` background agent checks facts in docs/API/code and leaves a file → grill the decision on verified facts rather than guesses → record ADR + refine terminology.
- **When:** an ADR decision depends on ‘can library/API X do this’, and you want to keep working while someone checks.
- **Why:** unlike on-the-fly `context7`, `research` is background and written: its result remains in a repo file, available for later checks or another agent.
- **Do not confuse:** this is a **different** skill from built-in `deep-research` (fan-out external web search with citations, for unfamiliar technologies/best practices from outside) — `research` here is more targeted, covering docs/API/code within this repo/task.
- **Step by step (with handoff artifacts):**
  1. **`research`** — background agent reads docs/API/code for the question. → **Handoff:** Markdown file with verified facts.
  2. **`/grill-with-docs`** — grill the decision using step 1's file → ADR + draft terms. → **Handoff:** ADR + candidate terms.
  3. **`domain-modeling`** — refines terms and integrates them into `GLOSSARY.md`.
- **Anti-patterns:**
  - ❌ grilling a decision about library/API capabilities from guesses when `research`/`context7` could provide a fact in a minute.
- **Prompts:**
  - “Research — find out in the background whether tanstack query v5 supports subscriptions to several query keys at once; record it in a file.”
  - “Based on the research file about RAC ComboBox — /grill-with-docs, record the decision in an ADR and update GLOSSARY.md.”

## Design / architecture

### `improve-codebase-architecture` → `codebase-design` → `grill-me` 🏁 *(flagship refactoring recipe)*
- **Chain:** a scan yields an HTML opportunities report → the deep-module vocabulary shapes a solution → grill the chosen option into a plan.
- **When:** ‘I want to improve the architecture but do not know where to start’.
- **Why:** from broad scan to a focused, grilling-verified solution — without random refactors.

- **Step by step (with handoff artifacts):**
  1. **`/improve-codebase-architecture`** — codebase scan → **HTML report of ranked opportunities** for deepening/simplification.
     *Boost:* first `code-review-graph` (`get_architecture_overview` + `get_hub_nodes` + `find_large_functions`) — the scan uses real structural metrics rather than selective reading.
     → **Handoff:** choose **ONE** opportunity from the report's top entries (not the whole list).
  2. **`codebase-design`** — for this one opportunity, design a **deep module / seam**: what to hide, where the seam goes, what narrow interface to expose.
     *Boost:* `context7` if the solution depends on a library API (RAC/TanStack/zod).
     → **Handoff:** draft interface + module boundaries + initial migration path.
  3. **`/grill-me`** — grill the draft: abstraction leaks, boundaries/edge cases, incremental migration, what breaks.
     → **Handoff:** verified, agent-ready refactor plan.

- **Pipeline continuation:** plan → `/to-spec` → `/to-tickets` → `/implement`. For broad, risky changes, insert `crg-refactor-safely` (impact radius) before code and close out with `tdd` (regression tests).
  Full chain: `improve-codebase-architecture → codebase-design → grill-me → to-spec → to-tickets → (crg-refactor-safely →) implement → tdd`.

- **Anti-patterns (destroy the potential):**
  - ❌ refactoring the **entire** report at once → overload; take **1 opportunity/pass** and repeat the cycle.
  - ❌ skipping step 3 → exactly the ‘random refactor’ this chain prevents.
  - ❌ coding without step 2's handoff artifact → grill-me has nothing to pressure-test.

- **Prompts:**
  - “Improve org-hierarchy architecture: first `code-review-graph` architecture-overview + hub-nodes → `/improve-codebase-architecture` HTML report → I pick top 1 → `codebase-design` designs the seam → `/grill-me` finishes the plan.”
  - “The selection-state controller has grown: scan it, choose one opportunity, design a deep hook, grill the migration.”
  - “After grilling — turn the plan into `/to-spec` and split it into issues.”

### `prototype` → `grill-me` → `to-spec`
- **Chain:** a throwaway prototype explores the design → grilling closes gaps → PRD records it.
- **When:** uncertain state model/UX before committing.
- **Why:** decisions based on something **running**, rather than imagination.

- **Step by step (with handoff artifacts):**
  1. **`/prototype`** — runnable prototype: state logic (terminal app) OR UI variations on one route. → **Handoff:** running artifact + observations of what works/does not.
  2. **`/grill-me`** — grill based on observations: boundaries, states, what breaks. → **Handoff:** verified decisions.
  3. **`/to-spec`** — record in a PRD. → **Handoff:** PRD in the tracker.
- **Boost:** `playwright` — click/capture the prototype; `Figma Desktop` — pull tokens for UI variations.
- **Pipeline continuation:** PRD → `/to-tickets` → `/implement`.
- **Anti-patterns:**
  - ❌ grilling an imagined design without a prototype → the ‘looks good on paper’ effect.
  - ❌ PRD before grilling → recording something half-baked.
- **Prompts:**
  - “Uncertain about the selection-state model: prototype → grill gaps → PRD.”
  - “3 country-roots-panel UI options: prototype on one route → playwright screenshots → grilling → PRD.”

## Bugs / quality

### `diagnosing-bugs` → `tdd`
- **Chain:** diagnosis reproduces and minimizes the bug → `tdd` turns the repro into a failing test → fix → green.
- **When:** a difficult bug or regression.
- **Why:** the regression test locks the bug out permanently; the fix follows a test rather than a guess.

- **Step by step (with handoff artifacts):**
  1. **`diagnose`** — reproduce → minimize → hypothesis → instrument → find the root. → **Handoff:** minimal repro + root cause.
  2. **`tdd`** — repro → failing test (red) → fix (green) → refactor. → **Handoff:** fix + regression test.
- **Boost:** `playwright`/`chrome-devtools` for runtime bugs (reproduce in the browser, capture DOM/network/performance); `crg-debug-issue` (`code-review-graph`) to find all related places in the graph.
- **Anti-patterns:**
  - ❌ fixing without a minimal repro → treating a symptom, not the cause.
  - ❌ a fix without a regression test → the bug returns next release.
- **Prompts:**
  - “Difficult theme-flip bug: `diagnose` → lock in the regression through `tdd`.”
  - “selectedOrgIds gets lost on shift-click: reproduce in the browser (playwright), find the root, lock it down with a tdd test.”

### `tdd` → `code-review` (skill) *(before merge/PR — Standards + Spec)*
- **Chain:** `tdd` locks down behavior with a green suite → the `code-review` skill checks the completed branch against both axes simultaneously, in parallel.
- **When:** the branch is ready, before opening a PR or merging — you want to check repo standards and the original task in one pass.
- **Why:** two parallel subagents are cheaper and faster than two sequential reviews; side-by-side reports immediately expose a mismatch when standards are met but the spec is not (or vice versa).
- **⚠️ Do not confuse:** this `code-review` is the skill in `~/.agents/skills` (Pocock), **different** from built-in `/code-review` (bugs/simplification) or `crg-review-changes` (graph review). To request this one, specify ‘Standards+Spec’ in the prompt.
- **Anti-patterns:**
  - ❌ relying only on this review and skipping built-in `/code-review` — they check different things (standards/spec vs bugs/simplification), and are not interchangeable.
- **Prompts:**
  - “The badge-counter branch is ready. code-review — check repo Standards and the Specification from issue #142 in parallel.”
  - “Before the PR: review since main on both axes — standards and compliance with the original PRD.”

### `code-review` / `/code-review` / `crg-review-changes` → `receiving-code-review` *(after review — responding to feedback)*
- **Chain:** any review skill produces findings → `receiving-code-review` sets the **response discipline**: verify each point against the code, clarify ambiguity, push back with technical reasoning, fix one item at a time with a test.
- **When:** you receive a review report (your `/code-review`, Pocock `code-review`, graph-based `crg-review-changes`) or feedback from an **external** PR reviewer.
- **Why:** review skills find problems but do **not** dictate *how to respond* — without this, it is easy to slide into performative agreement or blind implementation of bad advice.
- **Anti-patterns:**
  - ❌ “You're absolutely right!” + immediately implementing the entire list → partial implementation of ambiguous requests, blind fixes that break code.
  - ❌ silently accepting an external reviewer without YAGNI-grep / checking whether they understand the whole codebase context.
- **Prompts:**
  - “/code-review returned 8 points — next, receiving-code-review: verify each against code, clarify unclear ones, no performative thanks, fix one at a time with a test.”

### `crg-explore-codebase` → `crg-debug-issue` / `crg-refactor-safely` / `crg-review-changes`
- **Chain:** `explore` builds/refreshes the graph → debug, refactor, or review on the ready graph.
- **When:** a large or unfamiliar codebase.
- **Why:** one graph build = token-efficient context for all three subsequent skills.

- **Prerequisite:** `code-review-graph` MCP is running and bound to the repo (here — `cassiopeia-admin-ui`).
- **Step by step (with handoff artifacts):**
  1. **`crg-explore-codebase`** — `build_or_update_graph` + `get_architecture_overview` → orient yourself in the structure. → **Handoff:** fresh graph + module/hub map.
  2. **Branch on the same graph** (no rebuild):
     - **`crg-debug-issue`** — graph navigation to the bug's root;
     - **`crg-refactor-safely`** — impact radius before a change;
     - **`crg-review-changes`** — `detect_changes` + impact for review.
- **Anti-patterns:**
  - ❌ debugging/refactoring without a fresh graph → stale impact, missed connections.
  - ❌ rebuilding the graph every time → `explore` once, then reuse (incremental updates).
- **Prompts:**
  - “Unfamiliar positions module: first `crg-explore-codebase`, then debug/refactor/review on the same graph.”
  - “Refresh the graph and give an org-hierarchy architecture-overview, then selection-state's impact radius.”

### `crg-refactor-safely` → `tdd`  *(or `resolving-merge-conflicts` → `tdd`)*
- **Chain:** impact analysis / conflict resolution → tests confirm nothing broke.
- **When:** risky changes affecting many places.
- **Why:** dependencies are visible in advance; tests catch regressions.

- **Step by step (with handoff artifacts):**
  1. **`crg-refactor-safely`** (or **`resolving-merge-conflicts`**) — impact radius / conflict resolution → identify every affected point. → **Handoff:** affected-place list.
  2. **`tdd`** — tests for affected points (red for what breaks) → green after the change. → **Handoff:** green suite locking down behavior.
- **Anti-patterns:**
  - ❌ refactoring without an impact radius → missed affected places.
  - ❌ relying only on the graph without tests → impact shows connections, not guaranteed behavior.
- **Prompts:**
  - “Extract selection-state into a hook: impact analysis → tests confirm nothing broke.”
  - “After rebasing gamma: resolve conflicts → run tdd on affected mappers.”

### `tdd` → `migrate-to-shoehorn`
- **Chain:** write tests → replace `as` assertions with shoehorn.
- **When:** test data uses partial fixtures through `as`.
- **Why:** type-safe partial data without manual casting.

- **Step by step (with handoff artifacts):**
  1. **`tdd`** — write/have green tests (possibly using `as` for partial fixtures). → **Handoff:** green suite (with `as`).
  2. **`migrate-to-shoehorn`** — `as` → shoehorn helpers (type-safe partials). → **Handoff:** the same tests, without `as`, without losing types.
- **Anti-patterns:**
  - ❌ migrating to shoehorn before tests are green → mixing two changes makes breakage hard to locate.
- **Prompts:**
  - “Write person-mapper tests test-first → then replace `as` with shoehorn.”

### Cleanup 🧹 *(duplicates / broken logic / styles / motion)*
- **Chain:** `code-review-graph` (`semantic_search_nodes`/`get_community`/`find_large_functions`) → `/code-review` (+`/simplify`) → fixes following component rules → `tdd` + `/run`.
- **When:** after a port/refactor or periodically — remove duplicated components, broken interactive logic, off-rule styles.
- **Why:** no separate ‘cleanup’ skill; this is a composition. The project has firm **behavior/style rules** — a violation = a bug, even if ‘it works’.

- **Step by step (with handoff artifacts):**
  1. **`code-review-graph`** — find component **duplicates** (`semantic_search_nodes` across `shared/ui` + `get_community`/`list_communities`) and oversized nodes (`find_large_functions`). → **Handoff:** merge/extraction candidates.
  2. **`/code-review`** (+`diagnosing-bugs`/`crg-debug-issue` for runtime problems) — **broken logic**: non-modal popover dismiss, focus-rules, RAC patterns, dead/clobbered code. → **Handoff:** fix list.
  3. **Check styles + animations against rules** — canonical tokens (`src/index.css`), **clsx (NOT tv())**, no `dark:` variants, no raw `<input>`, notched-border fields; **motion/animations** (durations, easing, hover/press/focus states, `prefers-reduced-motion`) per `ux-states-and-motion`; `design-language` / `ui-interactivity-rules` / ADR-0021/0022/0026. → **Handoff:** off-rule locations (styles + motion).
  4. **`/simplify`** applies reuse/simplification → **`tdd`** (behavior) + **`/run`**/`Figma Desktop` (visuals). → **Handoff:** clean, rule-compliant code.
- **Guardrails (rules/criteria, not skills):** `ui-interactivity-rules.md` · `ui-component-inventory.md` · `design-language.md` · `ux-states-and-motion.md` · ADR-0021 (interactivity charter) · ADR-0022 (RAC primitives) · ADR-0026 (field notched border) · ‘clsx not tv()’ · canonical color tokens · no `dark:` variant · no raw `<input>`. Quick machine pass — `yarn lint` (boundaries + raw-input rule).
- **Anti-patterns:**
  - ❌ creating a component without searching for duplicates (`semantic_search`/inventory) → another orphan primitive.
  - ❌ ‘works’ ≠ ‘follows rules’: hover-dismiss in a non-modal popover, focus-accent on a label, off-token colors, `dark:` classes (dead under `[data-theme]`).
  - ❌ cleaning styles ‘by eye’ rather than `src/index.css` tokens → design-system drift.
  - ❌ ad-hoc animations (arbitrary durations/easing, ignoring `prefers-reduced-motion`) instead of motion tokens from `ux-states-and-motion` → inconsistent visual interactions.
- **Prompts:**
  - “Find component duplicates in shared/ui through code-review-graph, merge them, run /code-review + /simplify, check styles against ui-interactivity-rules and canonical tokens, close with tdd + /run.”
  - “Clean up org-hierarchy: broken interactive logic + off-token styles + `dark:` remnants → fixes per ADR-0021/0026.”

## Intake / process

### `setup-matt-pocock-skills` → *(all engineering skills)*
- **Chain:** configure tracker/labels/docs once → then `to-tickets`, `triage`, `to-spec`, `implement` work out of the box.
- **When:** first use of engineering skills in a new repo.
- **Why:** without setup they do not know where to write issues or which labels to apply.

- **Step by step (with handoff artifacts):**
  1. **`/setup-matt-pocock-skills`** (once per repo) — issue tracker + triage-label vocabulary + domain documentation layout (`GLOSSARY.md`). → **Handoff:** configured environment.
  2. **Then any engineering skill** — `to-spec` / `to-tickets` / `triage` / `implement` / `tdd` / `diagnosing-bugs` / `improve-codebase-architecture` work without extra setup.
- **Anti-patterns:**
  - ❌ invoking `to-tickets`/`triage` before setup → nowhere to write, no labels → the skill stalls.
- **Prompts:**
  - “New repo: `setup-matt-pocock-skills` once → then to-tickets/triage/implement out of the box.”

### `triage` → `to-tickets` / `implement`
- **Chain:** `triage` sorts intake and writes briefs → ready issues are picked up.
- **When:** a stream of bugs/features/external PRs.
- **Why:** only clearly specified, AFK-ready tasks reach `implement`.

- **Prerequisite:** `/setup-matt-pocock-skills` (triage-label vocabulary).
- **Step by step (with handoff artifacts):**
  1. **`/triage`** — intake through the role state machine → classification + agent-ready briefs. → **Handoff:** sorted tasks with briefs.
  2. **Branch:** **`/to-tickets`** (formalize in the tracker if PRD-level treatment is needed) OR **`/implement`** (if the brief is self-contained).
- **Anti-patterns:**
  - ❌ throwing raw bugs into `/implement` without triage → implementation without criteria or priority.
- **Prompts:**
  - “QA bug stream: `triage` sorts and writes briefs → `implement` takes ready ones.”
  - “12 incoming issues: `triage` with roles → larger ones to `to-tickets`, small ones straight to `implement`.”

### Meta-wrappers
- **`ask-matt`** — unsure which combination to start with → `/ask-matt` suggests an entry point.
- **`handoff`** — the end of any chain: compresses context for the next agent/session.

## Migration / parity (legacy → new)

### legacy → new parity 🏁 *(audit → gap → port → verify)*
- **Chain:** `crg-explore-codebase`+`code-review-graph` → `grill-with-docs` (+`domain-modeling`) → `codebase-design` → `implement` (+`context7`) → `tdd` + `/verify`/`/run`.
- **When:** moving old functionality (cass-clone) to new cassiopeia-admin-ui components — verify nothing was lost and port missing parts according to design rules.
- **Why:** no separate ‘migrate’ skill; the task is **audit → gap → port → verify**, rather than ‘create’/‘improve’. Composition provides parity without a 1:1 transplant or false ‘missing’ reports.

- **Prerequisite:** both repos in the graph (`list_repos_tool`); otherwise `semantic_search` in each separately + manual comparison. Check freeze scope (CREATE/EDIT forms — another session).
- **Step by step (with handoff artifacts):**
  1. **`crg-explore-codebase` + `cross_repo_search`/`semantic_search_nodes`** — match old functionality to its new counterpart by similarity. → **Handoff:** correspondence map + missing/divergent items.
  2. **`/grill-with-docs`** (+`domain-modeling`) — grill the list: real gap vs **intentional delta**. → **Handoff:** verified gap-list in `reports/migration-audit/`.
  3. **`codebase-design`** — fit each gap into new `shared/ui` + modular-MVC, per `design-language` / `ui-component-inventory` / `ux-states-and-motion`. → **Handoff:** port design (**NOT 1:1**).
  4. **`/implement`** — move to **your own `shared/ui` components (built on RAC)**, NOT RAC directly. First search for an existing component in `shared/ui` (`semantic_search`/inventory — **do not breed duplicates**); genuinely absent → create a new primitive on RAC and **record it in `ui-component-inventory`** (for later reuse). `context7` — only to verify the RAC API for this new component. → **Handoff:** changes + (if needed) a new `shared/ui` component.
  5. **`tdd` + `/verify`/`/run`** (+`playwright`/`Figma Desktop`) — behavioral + visual parity with legacy/mockup. → **Handoff:** confirmed parity.
- **Guardrails (this project):**
  - “Migration = rewrite, not port” — rework bad logic, discard dead code, redesign.
  - “Account for tab redistribution” — before flagging ‘field disappeared’, grep the **entire** module + `build-*-vm.ts` (new person-full = 9 tabs, not 1:1).
- **Anti-patterns:**
  - ❌ 1:1 port without `codebase-design` → pulling legacy flaws into the new architecture.
  - ❌ skipping step 2 → false ‘missing’ reports (delta ≠ bug) and report noise.
  - ❌ ‘parity’ without visual verification (`/run`/Figma) → mockup divergence goes unnoticed.
  - ❌ bringing duplicates / broken logic / off-rule styles or animations → immediately run [Cleanup](#cleanup--duplicates--broken-logic--styles--motion) (dedup + behavior + styles + motion).
- **Prompts:**
  - “legacy→new parity for org-hierarchy: cross-repo match cass-clone↔cassiopeia-admin-ui, grill the gap-list, port missing parts to shared/ui per design-language, verify tdd + /run.”
  - “Check whether person-full lost fields against legacy: grep the entire module + build-*-vm; missing items go in reports/migration-audit.”

## ➕ Skill + MCP (combinations for better results)

> Lighter format (no Step by step/Anti-patterns): **Chain → when → why → Prompts**. An MCP gives a skill an external source of truth (fresh docs, a live browser, a code graph, a mockup) absent from model memory.

### Coding with current documentation

#### `tdd` / `implement` + `context7` *(MCP_DOCKER)*
- **Chain:** before coding, `resolve-library-id` → `get-library-docs` → write the test/implementation against the real API.
- **When:** using a library whose signatures the model might hallucinate (new RAC, TanStack, zod v4 versions).
- **Why:** tests and code use the true API rather than stale memory — less ‘green on a lying mock’.
- **Prompts:**
  - “Get fresh RAC Popover docs through context7, then write the form test-first.”
  - “context7: current zod v4 superRefine API → implement org-form validation.”

#### `grill-with-docs` / `domain-modeling` + `context7` *(MCP_DOCKER)*
- **Chain:** while grilling/modeling, check library-capability assumptions against its docs.
- **When:** a decision depends on ‘can library X do this’ — before putting it in ADR/GLOSSARY.md.
- **Why:** the ADR records a verified fact, not a guess; subsequent skills read an accurate GLOSSARY.md.
- **Prompts:**
  - “While grilling the decision, check through context7 whether TanStack Router supports typed navigate with an array, then put it in an ADR.”

### Visual / browser development loop

#### `prototype` (UI) + `playwright` *(MCP_DOCKER)*
- **Chain:** prototype running → `browser_navigate` → `browser_click` / `browser_snapshot` / `browser_take_screenshot`.
- **When:** cycling through UI variations or states and needing to inspect/click each quickly.
- **Why:** decisions based on a running, captured UI rather than imagination; broken states are immediately visible.
- **Prompts:**
  - “Run the country-roots-panel prototype and capture each of its 3 variants.”
  - “Click selection states in the prototype through playwright and show DOM geometry.”

#### `diagnosing-bugs` + `playwright` / `chrome-devtools` *(MCP_DOCKER / plugin)*
- **Chain:** reproduce the bug in the browser (`browser_navigate` + actions) → capture DOM/network/console → form a hypothesis → fix → regression-check the same scenario.
- **When:** the bug appears only at runtime (UI state, network requests, performance).
- **Why:** `chrome-devtools` offers deeper access (DOM/network/performance) than playwright snapshots — a more precise hypothesis.
- **Prompts:**
  - “Reproduce the theme-flip bug in the browser, capture DOM/network/console, give a hypothesis.”
  - “chrome-devtools: performance profile of rendering a large org-hierarchy tree.”

#### `crg-review-changes` + `code-review-graph` ↔ `playwright` *(MCP)*
- **Chain:** `detect_changes` + impact analysis show what is affected → playwright visually verifies affected screens.
- **When:** reviewing changes that might silently break UI outside the diff.
- **Why:** the graph indicates where to look; the browser confirms it is not broken there.
- **Prompts:**
  - “Detect-changes on gamma → playwright visually checks affected screens.”

### Design → code

#### `prototype` / design tasks + `Figma Desktop` *(MCP)*
- **Chain:** `get_variable_defs` / `get_design_context` / `get_screenshot` from the open mockup → transfer tokens and context into prototype/code.
- **When:** exact mockup fidelity is needed (token values, spacing, colors).
- **Why:** pull **real** values from Dev Mode rather than eyeballing approximations.
- **Prompts:**
  - “Extract country-roots-panel tokens and spacing from the open mockup (Dev Mode) and apply them.”
  - “get_variable_defs for status colors from the mockup → compare with src/index.css tokens.”

#### `figma-friend:clone-ui` + `figma` (remote) + `playwright` *(Claude-only MCP)*
- **Chain:** playwright captures a live page → `figma` (Plugin API) recreates it as a Figma file.
- **When:** an existing web screen must be moved into Figma for redesign.
- **Why:** remote `figma` writes cloud files (unlike read-only `Figma Desktop`).
- **Prompts:**
  - “Clone the live org-hierarchy page into a new Figma file (clone-ui + figma + playwright).”

### Navigation / architecture of a large codebase

#### `crg-explore-codebase` / `crg-refactor-safely` + `code-review-graph` *(MCP)*
- **Chain:** `build_or_update_graph` → `get_architecture_overview` / `semantic_search_nodes` / `get_impact_radius`.
- **When:** an unfamiliar or large codebase; risky changes with a broad impact radius.
- **Why:** persistent graph = token-efficient context and impact analysis instead of blind file reading. The `crg-*` skills are the frontend to this MCP.
- **Prompts:**
  - “Build the graph and give an architecture-overview for modules/.”
  - “get_impact_radius for extracting selection-state into a hook before refactoring.”

#### `improve-codebase-architecture` + `code-review-graph` *(MCP)*
- **Chain:** the graph provides `get_architecture_overview` / `get_hub_nodes` / `find_large_functions` → the scan produces an HTML opportunities report → grill the chosen option.
- **When:** ‘I want to improve the architecture but do not know where to start’.
- **Why:** the scan uses structural graph metrics rather than selective reading.
- **Prompts:**
  - “Graph: hub-nodes + large functions → HTML opportunities report → grill the selected option.”

> ⚠️ **MCP state in this project** (see project-memory): `MCP_DOCKER` periodically goes down (browser/figma-screenshot loop is unreliable) — then run figma parity from **PROJECT SOURCE** (`figma/src` + `design/reference`), not through MCP.

---

# 🔌 MCP servers on the machine

> MCP = external toolsets that the agent loads on top of skills.
> Claude and Cursor are configured separately (`~/.claude.json` + plugins / `~/.cursor/mcp.json`), so their sets may differ.

## Shared MCPs (both Claude and Cursor)

### `MCP_DOCKER` — Docker MCP Gateway
- **How:** one gateway, `docker mcp gateway run`, exposes tools from multiple servers; management — `docker mcp server ls / enable / disable`.
- **Where:** when fresh library docs or browser automation is needed.
- **Why:** an aggregator — several MCPs behind one connector, isolated in Docker. Currently **2** enabled:
  - **`context7`** — current library documentation. Tools: `resolve-library-id`, `get-library-docs`. *(when you need a library's true API rather than model memory)*
    - **Prompts:** “context7: resolve-library-id for react-aria-components → get-library-docs about Popover.” · “Get current TanStack Router docs on typed navigate.”
  - **`playwright`** — browser automation. Tools: `browser_navigate`, `browser_click`, `browser_snapshot`, `browser_evaluate`, `browser_take_screenshot`… *(visual development loop, UI e2e checks)*
    - **Prompts:** “playwright: navigate to host.docker.internal Storybook → screenshot story.” · “Click a diagram node and capture a state snapshot.”

### `Figma Desktop` *(local, `127.0.0.1:3845/mcp`)*
- **How:** `get_design_context`, `get_screenshot`, `get_variable_defs`, `get_metadata`.
- **Where:** working with a locally open Figma file (Dev Mode).
- **Why:** pulls design context, tokens, and screenshots directly from desktop Figma — no cloud.
- **Prompts:**
  - “get_variable_defs from the open country-roots-panel mockup → compare with index.css tokens.”
  - “get_screenshot of the selected frame for pixel comparison with the migration.”

### `code-review-graph` *(local binary, bound to `cassiopeia-admin-ui`)*
- **How:** `build_or_update_graph`, `semantic_search_nodes`, `get_impact_radius`, `get_review_context`, `get_architecture_overview`… + `crg-*` skills.
- **Where:** navigation, review, and refactoring of a large codebase.
- **Why:** persistent code graph (tree-sitter) → token-efficient context and impact analysis instead of blind file reading.
- **Prompts:**
  - “build_or_update_graph → get_architecture_overview for modules/org-hierarchy.”
  - “get_impact_radius for a selection-state refactor.”

## Claude only

### `figma` *(plugin `figma`, remote `mcp.figma.com/mcp`)*
- **How:** official remote Figma MCP; backed by `figma:*` skills (full list in [🧩 Plugin skills](#-plugin--built-in-skills-outside-agentsskills)).
- **Where:** create/edit in Figma through Plugin API, generate screens/diagrams/libraries.
- **Why:** full access to cloud Figma files (unlike local `Figma Desktop`, which only reads the open file).
- **Prompts:**
  - “figma-generate-design: build an org-hierarchy screen in a cloud file from our code.”
  - “figma-code-connect: map the Figma button to our shared/ui Button.”

### `chrome-devtools` *(plugin `figma-friend`; also project `cargo/des`)*
- **How:** `chrome-devtools-mcp` — page inspection/debugging through Chrome DevTools Protocol.
- **Where:** debugging a live web page — DOM, network, performance.
- **Why:** deeper DevTools access than playwright snapshots.
- **Prompts:**
  - “Inspect network on the live person-form page during submission.”
  - “Profile org-hierarchy diagram rendering performance.”

## Cursor only

> None unique — all three Cursor servers (`MCP_DOCKER`, `Figma Desktop`, `code-review-graph`) are shared with Claude.

---

# 🧩 Plugin / built-in skills (outside `~/.agents/skills`)

> A **different source** from §1–§7: these skills are not in the physical store and update separately. Listed here to make the cheatsheet complete.

## Plugin skills *(from `~/.claude/plugins`, managed by the marketplace)*

### `figma-friend` plugin *(v0.0.1, marketplace `figma-friend`)*
> Frontend to MCP `figma-friend` / `chrome-devtools`. Invoked as `figma-friend:<skill>` (skill).

- **`clone-ui`** · `auto` — clone a live web page into Figma (“clone this page to Figma”, “recreate this UI”).
  - **Prompt:** “Clone the org-hierarchy page into Figma (`figma-friend:clone-ui`).”
- **`figma-designer`** · `auto` — interactive help with Figma design tasks.
  - **Prompt:** “Help refine the card layout in Figma through `figma-friend:figma-designer`.”

### `figma` plugin *(official, v2.2.60)*
> Frontend to remote MCP `figma` (Plugin API for cloud files). Invoked as `figma:<skill>` (skill). `figma-use` / `figma-create-new-file` / `figma-generate-diagram` are **mandatory preludes** before the corresponding tool call (`use_figma` / `create_new_file` / `generate_diagram`).

- **`figma-use`** · `auto` — any write/unique read action through JS in file context (create/edit/delete nodes, variables, components, auto-layout, bind variables). **Prelude to `use_figma`.**
- **`figma-create-new-file`** · `auto` — a new empty file (design/FigJam/Slides). **Prelude to `create_new_file`.**
- **`figma-generate-design`** · `auto` — transfer a page/view/modal/drawer/panel from code to Figma (builds section by section using DS tokens).
  - **Prompt:** “Build the person-form screen in Figma from our code (`figma:figma-generate-design`).”
- **`figma-generate-diagram`** · `auto` — diagrams in FigJam (flowchart, architecture, sequence, ERD, state, gantt, timeline; Mermaid). **Prelude to `generate_diagram`.**
  - **Prompt:** “Draw an auth-handshake sequence diagram in FigJam.”
- **`figma-generate-library`** · `auto` — build/update a Figma design system from the codebase (variables/tokens, components, theming, foundations).
  - **Prompt:** “Generate a Figma library from our shared/ui tokens and components (`figma:figma-generate-library`).”
- **`figma-code-connect`** · `auto` — Code Connect: mapping Figma components to code snippets (`.figma.ts`/`.js`).
  - **Prompt:** “Map the Figma button to our `shared/ui` Button through Code Connect.”
- **`figma-swiftui`** · `auto` — SwiftUI ↔ Figma (iOS). *Not relevant to this project (web).*
- **`figma-use-figjam`** / **`figma-use-slides`** · `auto` — `figma-use` helpers for FigJam / Slides context.

## Built-in harness skills *(ship with Claude Code; not on disk)*

> Invoked as `/<skill>` (skill); updated with the CLI. Most useful for this project:

- **`/code-review`** — review the current diff for bugs/simplification (low→ultra). `/code-review ultra` — cloud multi-agent. *(also has deprecated alias `/ultrareview`)*
  - **Prompts:** “/code-review — scan the gamma diff for bugs.” · “/code-review ultra — deep review of the entire selection-state branch.”
- **`/verify`** — verify that a change actually works by running the application and observing behavior.
  - **Prompt:** “/verify — confirm that theme-flip does not reset the diagram to root.”
- **`/run`** — run/open the project's application, capture a screenshot, confirm the change in the real UI.
  - **Prompt:** “/run — open org-hierarchy and show a country-roots-panel screenshot.”
- **`/security-review`** — security audit of pending branch changes.
  - **Prompt:** “/security-review — check branch changes in auth-session DI.”
- **`/simplify`** — only reuse/simplification/efficiency (no bug hunt) + apply fixes.
  - **Prompt:** “/simplify — tidy the selection-state controller without changing behavior.”
- **`deep-research`** · `auto` — fan-out web search → fetch sources → adversarial checking → cited report.
  - **Prompt:** “Do deep-research: GoJS ThemeManager re-skin best practices without rebuild, with citations.”
- **`/fewer-permission-prompts`** — generate an allowlist in `.claude/settings.json` for fewer permission prompts.
  - **Prompt:** “/fewer-permission-prompts — add the read-only yarn/git operations I frequently approve to the allowlist.”
- **`/loop`**, **`/schedule`** — recurring runs / cron agents. **`/init`**, **`/review`**, **`update-config`**, **`keybindings-help`**, **`claude-api`** — utility commands.
  - **Prompts:** “/loop 5m /code-review — review the diff every 5 minutes.” · “/schedule — run branch security-review every morning at 9:00.”

> ⚠️ Distinction (4 easily confused things): `/review` (built-in, for GitHub PRs) ≠ `crg-review-changes` (local diff graph review through `code-review-graph`) ≠ built-in `/code-review` (working-diff review for bugs/simplification, low→ultra) ≠ `code-review` skill from `~/.agents/skills` (Pocock version — parallel Standards+Spec, §3). The last two use the same invocation name — specify which version you need in the prompt. Likewise `deep-research` (built-in, external web) ≠ `research` (§6, background agent for docs/code in the repo).

---

# 🎬 End-to-end scenarios (prompts)

> Ready-to-paste prompts that run the **entire chain** of skill + MCP + harness for a typical task. Each has its stack underneath.

### 1. New feature from zero to PR
> Stack: `grill-me → to-spec → to-tickets → implement` (+`context7`,`tdd`) → `/code-review` → `/verify`
- “I have an idea for navigation badge counters. Grill it (`/grill-me`), create `/to-spec`, split with `/to-tickets`, then `/implement` the first slice — use **our own `shared/ui` (built on RAC)**; no component → create a primitive on RAC + add to `ui-component-inventory` (check RAC API through context7), put critical logic under tdd. Finish with `/code-review` and `/verify`.”

### 2. Architectural refactor (flagship 🏁)
> Stack: `code-review-graph` → `improve-codebase-architecture → codebase-design → grill-me` → `crg-refactor-safely` → `implement → tdd` → `/code-review`
- “The selection-state controller has grown. Build the graph (`code-review-graph` architecture-overview + hub-nodes), `/improve-codebase-architecture` give an HTML report; I choose top 1 → `codebase-design` design a deep hook → `/grill-me` finishes the plan → `crg-refactor-safely` shows impact radius → implement with tdd → `/code-review` at the end.”

### 3. Difficult runtime bug
> Stack: `diagnosing-bugs` (+`playwright`/`chrome-devtools`) → `crg-debug-issue` → `tdd` → `/verify`
- “The diagram resets to root after theme-flip. `diagnose`: reproduce in the browser (playwright), capture DOM/console; if needed, find related places through the graph (`crg-debug-issue`); minimize to the root, lock the regression with `tdd`, confirm with `/verify`.”

### 4. UI from mockup to working screen
> Stack: `Figma Desktop` → `prototype` (+`playwright`) → `grill-me` → `implement` → `/run`
- “Extract country-roots-panel tokens and spacing from the open mockup (`Figma Desktop` get_variable_defs), `/prototype` 2–3 variants, capture playwright screenshots, grill (`/grill-me`), implement the choice (`/implement`), show it in the real application with `/run`.”

### 5. Processing incoming work
> Stack: `triage → to-tickets` / `implement` (prerequisite: `/setup-matt-pocock-skills`)
- “12 incoming QA issues: `/triage` with roles and briefs → largest to `/to-tickets`, small self-contained ones straight to `/implement`.”

### 6. Researching unfamiliar technology → decision in an ADR
> Stack: `deep-research` → `grill-with-docs` ↔ `domain-modeling` (+`context7`)
- “Do `deep-research` on GoJS ThemeManager re-skin without rebuild (with citations), then `/grill-with-docs` record the decision in an ADR and refine terminology (`domain-modeling`), checking the API through context7.”

### 7. Moving legacy functionality to new components
> Stack: `crg-explore-codebase`+`code-review-graph` → `grill-with-docs` → `codebase-design` → `implement` (+`context7`) → `tdd` + `/run`
- “Move module X functionality from old cass-clone to new cassiopeia-admin-ui components: cross-repo similarity matching (`code-review-graph`), grill the gap-list (`/grill-with-docs`) into `reports/migration-audit`, design each gap on `shared/ui` per design-language (`codebase-design`), implement using **our own `shared/ui` (built on RAC)** — no component: create a primitive on RAC and add it to `ui-component-inventory` (check RAC API through context7), verify parity with `tdd` + `/run` against legacy/mockup. Not 1:1: rework bad logic, do not flag intentional deltas as missing.”

### 8. Cleanup: duplicates / broken logic / styles / animations
> Stack: `code-review-graph` (semantic_search / get_community / find_large_functions) → `/code-review` (+`diagnosing-bugs`) → rule-based fixes → `/simplify` → `tdd` + `/run`
- “Clean shared/ui + module X: find component **duplicates** through `code-review-graph` (semantic_search + get_community), use `/code-review` to uncover **broken logic** (non-modal popover dismiss, focus-rules, RAC patterns) and **off-rule styles/animations** (canonical tokens `src/index.css`, clsx not tv(), no `dark:`, no raw `<input>`, motion per `ux-states-and-motion` + `prefers-reduced-motion`); fix per `ui-interactivity-rules`/ADR-0021/0022/0026, apply `/simplify`, close with `tdd` + `/run`. Before creating a component — search for an existing one (do not breed duplicates).”

### 9. Merge: correct conflict resolution + fixing a broken algorithm
> Stack: `resolving-merge-conflicts` (+`code-review-graph` `get_impact_radius`) → `diagnosing-bugs` (+`playwright`/`chrome-devtools`) → `tdd` → `/run`/`/verify` → `/code-review`
- “Merging branch Y into gamma. Resolve conflicts (`resolving-merge-conflicts`) — do NOT blindly accept ours/theirs: check both sides' impact through `code-review-graph` (`get_impact_radius`/`get_review_context`) and preserve semantically correct logic. The portal broke after merge — `diagnose`: reproduce in the browser (playwright/chrome-devtools), find the root in merged changes, lock the regression with `tdd`, run the new code `/run`//verify against the real portal, finally `/code-review` the conflict resolution itself. If merge touched shared/ui — check component rules (see [Cleanup](#cleanup--duplicates--broken-logic--styles--motion)).”

### 10. Pull: correct conflict resolution + fixing a broken algorithm
> Stack: `resolving-merge-conflicts` (+`code-review-graph` `get_impact_radius`/`detect_changes`) → `diagnosing-bugs` (+`playwright`/`chrome-devtools`) → `tdd` → `/run`/`/verify` → `/code-review`
- “Doing `git pull` (rebase) of gamma from origin — other people's changes arrived. Resolve integration conflicts (`resolving-merge-conflicts`) — do NOT suppress them blindly: check **incoming** commits' impact through `code-review-graph` (`detect_changes` + `get_impact_radius`), preserve both sides' semantically correct logic. If the portal broke after pull — `diagnose`: locate **which incoming commit** broke the algorithm (reproduce in the browser with playwright/chrome-devtools, use `git bisect` if needed), lock the regression with `tdd`, run new code `/run`//verify against the real portal, `/code-review` the resolution. Boundaries and guardrails are as in scenario #9; shared/ui affected → [Cleanup](#cleanup--duplicates--broken-logic--styles--motion).”

### 11. Release readiness: security-review before release
> Stack: `/security-review` + `/code-review` (+`crg-review-changes` impact) → `tdd` + `tsc -p tsconfig.app.json` + `yarn lint` → `/verify`/`/run`
- “Before releasing branch gamma: `/security-review` pending changes (auth-session DI, tokens, secrets; BE — read-only, do not touch new endpoints/contracts), `/code-review` for bugs + `crg-review-changes` impact of what is affected outside the diff. Run `tdd`, the real typecheck `tsc -p tsconfig.app.json` (NOT `yarn tsc`), `yarn lint` (look for **new** violations — existing noise ~2300). Confirm critical flows with `/verify`//run against the real portal. Red — fix and repeat; all green → release. Then `/handoff`.”

### 12. Ending a session
> Stack: `handoff`
- “`/handoff` — compress the current theme-flip work state into a handoff document for the next session.”

---

# 🔬 A self-checking review pass (how to get one every time)

> Not a skill, but a **pass protocol** — invariants that turn a review from a retelling of someone else's journal into verification. Layered over any review tool: built-in `/code-review`, the `code-review` skill (§3), `crg-review-changes` (§5), or a role-based review file (`work/<NNN>/review.md` in genericui).
> The source case: `genericui` GUI-606, `work/006-pdf-export-width` — 4 passes; in pass 4, the previous round's three must-fix items were closed through **mutations**, while three new findings were found **in the record, not the code**.

## Vocabulary (needed to read this section)

**Gate** — simply a list of commands to run before saying ‘done’. Not a process or abstraction: concrete terminal lines. ‘Gate green’ = all behaved as expected. The gate depends on what the change affected (client / PHP / Helm chart), so it is always a *relevant subset*, not ‘all repo tests’. In genericui its composition is in `work/README.md` → ‘The gate’.

> Example for a change touching both client and PHP (genericui):
> `npx tsc --noEmit` (types, ~40 s) · `npx oxlint src/` (lint, ~2 s) · `yarn test-ci` (client units, ~21 s) · `./vendor/bin/pint --test` (PHP formatting) · `phpstan analyse --memory-limit=1G <changed files>` (changed files) · `./vendor/bin/phpunit --testsuite unit`.

**Baseline** — what failed **before** your change. In a live repo a gate is almost never ‘zero failures’: in genericui `pint` complains about gitignored `tests/config/local.php`, and `phpunit --testsuite unit` yields 7 errors + 2 failures from vendor code. ‘Green’ means **‘exactly the same things fail as before’**, not ‘nothing fails’.

**Attributed baseline** — the same baseline, but **named individually**. The distinction is crucial:
- ❌ ‘phpunit fails, but it already failed’ — faith. Your eighth failure is invisible: 7 became 8, both called ‘already failed’.
- ✅ ‘exactly these two fail (purge-resumability), and exactly these seven (`ArticleActions*`, one vendor deprecation)’ — fact. The eighth is immediately visible.
- The same for static analysis: not ‘25 errors as usual’, but ‘22 in `User.php` + 3 in `edit_welcome_popup.php`’, with separate verification that the file version **before** the change produces the same 22.

**Mutation** — checking whether a test catches anything at all. A test can exist and be decorative. Manually: (1) deliberately break the code (`756` → `680`); (2) run tests; (3) see **exactly what** failed (3 tests — good, nothing — an empty test); (4) `git checkout -- <file>` and confirm `git status --short` is empty. No tool required.

**What the gate does NOT say.** It says ‘nothing broke among things we can check automatically’ — not ‘the feature works for a person’. That is why LIVE-VERIFIED in `work/README.md` is a separate state. In GUI-606 the gate was green for all five rounds, but live testing found a modal printing the same sentence twice: each sentence is individually correct, so the test cannot catch this in principle.

## 6 invariants

1. **A fresh session that did not write this code.** An author reviews their intention, not the result. The reviewer writes no production code, does no `git add`/commit — otherwise they become a worker and lose their angle.
2. **Gate remeasured, not quoted.** Do not take numbers from the journal: run it yourself (`tsc` · lint · tests · `pint` · `phpstan` · `phpunit` — whatever the project has) and report **measured** numbers. Crucially: the baseline is **attributed** — not ‘already failed’, but by file (`User.php` 22, `edit_welcome_popup.php` 3) and test name (2 purge + 7 ArticleActions). An unattributed baseline conceals new breakage.
3. **Every ‘closed’ confirmed by mutation.** Not ‘the test exists’, but ‘break it — and that exact test fails’. Case examples: guard constant 756→680 ⇒ 3 failures; remove copy collapse ⇒ 1; expand it ⇒ 3; disable unmount resolution ⇒ 1; remove `@import` from LESS ⇒ 1. This distinguishes code review from reviewing the code's **protection**.
4. **Tree restored and proven.** After every mutation, `git checkout -- <file>` + empty `git status --short`. Otherwise mutations are a risk rather than a tool.
5. **Independent derivation.** Calculate boundaries, thresholds, percentages from constants yourself. A code comment is not evidence: in the case, the same false comment (‘the guard arrives at width ≤680’) **confirmed** the bug twice instead of exposing it.
6. **Check the record, not only the code.** Commit messages (one in the case described a nonexistent test), document SHAs (dead after rebase — exist only in reflog), `**State:**` in plans, links to ADRs/specs. Code can be right while the description lies.

## Finding buckets

`must-fix` / `should-improve` / `nits` / **`accepted`** — and `accepted` is mandatory: it demonstrates coverage (‘checked, no objections’) and discourages invented remarks. Approve a clean change. Disposition from a fixed vocabulary (`approved` / `changes-requested`), state on a line at the top of the file.

## Prompt (copy/paste)

```
You are Reviewer. Fresh session; no production code, no commits, no git add.
Scope: <commit range or branch>. Read <plan/journal/previous review>,
repo rules (CLAUDE.md / CLAUDE.local.md), and test policy.

Run the gate yourself and report MEASURED numbers with an attributed baseline
(by file and test name, not ‘it already failed’).

Confirm every ‘closed’ from the previous round by mutation:
break -> exactly which tests fail -> git checkout -- -> evidence of a clean tree.

Findings in must-fix / should-improve / nits / accepted buckets.
Also check the record: commit messages, document SHAs, plan state, ADR links.
End with disposition and what to promote into specs/ADRs.
```

## Worker definition of done (to make the pass cheap)

Half the cost of review comes from what the worker did not leave behind. Require in the journal:
- a **mutation table**: defect → how many and which tests fail (then the reviewer *verifies* rather than discovers);
- gate numbers, not ‘green’;
- deviations from the plan **with reasons**;
- an explicit list of open questions.

## Baselines — in a file, not in your head

Record known failures (lint on a gitignored file, N static errors, a flaky suite) in the repo — `specs/stack/gate-baselines.md` or a test-policy section. Then a gate line is a **comparison with a record**, not a judgment, and each pass does not derive the baseline anew (and differently).

## Cost and what to cut

A full pass ≈ 25–30 tool calls, ~15 minutes: mostly gate and mutations. When time is short, cut in this order: mutations for nits → independent arithmetic derivation → record checks. **Do not cut** the remeasured gate or must-fix mutations — without them the pass becomes a journal retelling.

## Connections

- Pass tool: built-in `/code-review` (working-diff, low→ultra) · `code-review` skill (§3, parallel Standards+Spec) · `crg-review-changes` (§5, graph review + impact outside the diff).
- After the pass, when feedback reaches **you**: `receiving-code-review` (§3) — verify before implementing, not ‘You're absolutely right’.
- Lock mutations and regressions through `tdd` (§3); if findings become bug hunting — `diagnosing-bugs` (§3).
- The role-based variant (Reviewer / Worker / Critic with `plan.md` / `journal.md` / `review.md` files) is described in genericui's `work/README.md`; the protocol itself is file-only, requiring no skill.

---

# 🛠️ How a skill works (under the hood)

> Source: official Anthropic **Agent Skills** docs (through context7). Explains the mechanism behind `/command`/`auto` (command/auto) labels and the ‘triggers in English’ rule.

- **Folder structure:** `SKILL.md` (main instructions) + optional reference files (`REFERENCE.md`, `FORMS.md`…) + `scripts/`.
- **Frontmatter (YAML) — 2 required fields:**
  ```yaml
  ---
  name: skill-name
  description: What it does + WHEN to use it. “Use when the user mentions X / asks to Y…”
  ---
  ```
  Claude Code metadata `disable-model-invocation: true` → makes the skill `/command`-only (command-only) in Claude (the `/command` label in §1–§7).
- **Progressive disclosure (3 loading levels)** — why it is token-efficient and why **description decides everything**:
  1. **session start** — ONLY each skill's `name` + `description` enter context (a few lines);
  2. **trigger** — when `description` matches the task, the `SKILL.md` body loads;
  3. **as needed** — reference files/scripts are read only when the skill points to them.
  → The description may be Ukrainian; it must say **both what and WHEN** (otherwise the skill will not activate).
- **MCP tools inside a skill — fully qualified** `Server:tool` (e.g. `code-review-graph:get_impact_radius`, `figma:use_figma`) — to avoid ambiguous calls.
- **Related (another source):** Anthropic-managed skills also exist through the Claude **API** (`container.skills` + beta header `skills-2025-10-02`, e.g. `pdf`/`docx`/`xlsx`/`pptx`) — separate from local `~/.agents/skills` and **not** used here.

> 💡 Editing your skill? Invoke **`/writing-for-agents`** — it applies these principles (description as discovery surface, progressive disclosure, predictability).

---

# ⚙️ Maintenance

- **All skills are physical folders** in `~/.agents/skills` (nothing depends on projects; delete a repo and skills remain).
- **Update Pocock skills:** clone/update `mattpocock/skills` (`skills/engineering|productivity|misc/*`, excluding `deprecated/`) → copy updated folders here (do NOT write through symlinks; translate every `description:` to Ukrainian after copying).
- **Upstream state on 2026-07-08:** `to-prd`→**renamed** to `to-spec`, `to-issues`→**renamed** to `to-tickets` (old names removed here). Added: `code-review`, `research`, `wayfinder`. `caveman` and `zoom-out` **removed upstream** — `caveman` retained here as custom (update manually), `zoom-out` not installed. Upstream also contains `in-progress/*` and `personal/*` (Matt's drafts/personal material) — intentionally not installed; listed in upstream `.claude-plugin`/README if needed.
- **Sync 2026-10-06 (upstream `6fd9479`; previous base — `d574778`, 2026-07-08).** Updated 24 skills, added 6: `implement-spec`, `pr`, `retro`, `wizard`, `to-questionnaire`, `wait-what`. `writing-great-skills` → **renamed** to `writing-for-agents` (old name removed). Upstream **removed** `resolving-merge-conflicts` without replacement — retained here as custom (update manually; Pocock-sync no longer sees it). Upstream **renamed** domain-doc convention `CONTEXT.md`/`CONTEXT-MAP.md` to `GLOSSARY.md`/`GLOSSARY-MAP.md` — in repos with a `CONTEXT.md` glossary, rename the file. ⚠️ `cto-research` and `repo-bootstrap` use `CONTEXT.md` in a **different** sense (project briefing, not glossary) — intentionally not renamed. Every folder now has `agents/openai.yaml` (Codex metadata) — copied along with the folder. **Historical local edit (no longer the only one):** `ask-matt`, ‘Codebase health’ section — line about `/pattern-architecture-review`; reapply on resync. To find the base next time: find the upstream commit whose `SKILL.md` bodies (excluding the `description:` line) match local ones.
- **Non-Pocock skill in the store — `receiving-code-review`** (from `obra/superpowers`, installed 2026-07-09). A **different** upstream — `github.com/obra/superpowers/skills/receiving-code-review`; Pocock-sync (clone of `mattpocock/skills`) **does not see it and must not delete it**. Update manually from superpowers (English verbatim body, Ukrainian `description:`, like the rest). Other superpowers skills were deliberately **not** taken: they duplicate Pocock+harness (`test-driven-development`→`tdd`, `systematic-debugging`→`diagnosing-bugs`, `verification-before-completion`→`/verify`, `writing-plans`→`to-spec`/`to-tickets`, `executing-plans`→`implement`, `brainstorming`→`grilling`, `writing-skills`→`writing-great-skills`) or built-ins (`using-git-worktrees`→harness worktree, `dispatching-parallel-agents`→`Workflow` tool). **`anthropics/skills` `frontend-design` — ADOPTED 2026-08-11, decision revisited.** Previously rejected specifically for conflicting with migration rules (pixel-match figma-source + canonical tokens vs ‘invent a signature design’) — a valid reason: upstream targets **landing pages** and **greenfield**. The fork addresses both: step 1 separates *Page* and *System* (a system has no hero; its signature is what repeats), while step 2 first requires finding the token source, inventory, theme mechanism, and parity gate, and recognizing most axes are **already spent**. Upstream — `2235be7c60` (2026-06-09); Pocock-sync **does not see it and must not delete it**; resync only manually by diff against that commit. License — `frontend-design/LICENSE.txt`, copywriting — `WRITING.md`. For a particular repo with a strict design system, prefer a separate **internal** skill rather than modifying this one.
- **Non-Pocock set — `ponytail*`** (6 skills from `github.com/DietrichGebert/ponytail`, MIT, installed 2026-09-03 from commit `2ed6c52c9d`). **Different** upstream; Pocock-sync **does not see them and must not delete them**. Took only `skills/*/SKILL.md` — folder to folder, like the rest; **did not install the plugin** (upstream offers `/plugin marketplace add DietrichGebert/ponytail`, which also brings two Node lifecycle hooks). Consequence and tradeoff: no hooks → **no activation at session start**, and `PONYTAIL_DEFAULT_MODE` / `~/.config/ponytail/config.json` do not resolve; invoke the mode explicitly (`/ponytail`). Thus the **initial body edit**: a ‘Local note’ block in `ponytail-help`, section `## Update`, because otherwise the card recommends the nonworking `/plugin marketplace update`. After the local audit on 2026-10-14, ponytail-help and ponytail-debt were also changed; preserve the diff on resync. Original bodies are English, `description:` Ukrainian (as everywhere). Update manually by diff against `2ed6c52c9d`; reapply the `ponytail-help` edit on resync. **`.skill-lock.json` intentionally untouched:** this is state for CLI `npx skills` (containing only `archify`, which is not even in the store), and the tool computes `skillFolderHash` itself — a manual entry would contain an invented hash.
- **Orchestration pattern (note, not a skill):** ledger + 4-status protocol (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED) + brief-file handoff from `subagent-driven-development` (superpowers) extracted into `~/.agents/rules/subagent-orchestration-ledger.md` — **without** installing a duplicate skill (duplicates `implement` + `Workflow` tool).
- **`crg-*`** — from `code-review-graph` MCP; updated with the server.
- **Plugin skills** (`figma`, `figma-friend`) — NOT in `~/.agents/skills`; live in `~/.claude/plugins/cache`, updated through `/plugin` (marketplace). State — `~/.claude/plugins/installed_plugins.json`.
- **Built-in harness skills** (`/code-review`, `/verify`, `deep-research`…) — ship with Claude Code, update with the CLI; no manual action needed.
- After skill changes — **restart the session** in Claude Code / **Reload Window** in Cursor, then `/skills`.

## Preserving local fixes (2026-10-14)
Update upstream through a diff; keep a backup. Local edits concern design-pass, frontend-design, anti-slop-design, ux-review, interface-review, ponytail-help/debt, code-review, cto-research, implement-spec, spec-flow, wayfinder, prototype/UI.md, setup-pre-commit, resolving-merge-conflicts, issue-tracker-local.md, the git-guardrails hook, and wizard/template.sh. Do not overwrite them with blind copying. The bundled hook does not update installed copies; synced was left unchanged.
