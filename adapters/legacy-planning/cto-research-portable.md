---
name: cto-research
description: Builds or updates the single pre-implementation briefing — product, codebase and seams, infrastructure, dependencies, risks — with every claim linked to a primary source. Use before planning a significant feature, when starting in an unfamiliar repo, when the existing briefing is stale, or on the triggers "cto research", "брифінг", "розберись у продукті" (the Ukrainian phrases are retained compatibility triggers).
---

Portable adaptation: use the [bundled lifecycle](../../docs/portable/feature-lifecycle.md) and [review routing](../../docs/portable/review-handoff.md). Local contracts and current user authorization govern writes and delegation. Named skills not linked here are optional external extensions, not installed dependencies.

# cto-research — a pre-implementation briefing

One file the agent reads **before** the plan. Not a ticket or an ADR.

The briefing is a **cache** of primary sources, not an independent truth. Every claim carries a
source link; when the descriptive cache and primary source disagree, correct the cache. Code does not override an accepted contract; escalate normative contradictions to the owner.
This is the single rule from which the rest of the skill follows.

## 1. Find the briefing's home

First read applicable `AGENT.md` / `AGENTS.md` / `CLAUDE.md`: if they point to a briefing, use that path. Otherwise search `work/CTO-RESEARCH.md` → `CONTEXT.md` → `docs/CONTEXT.md` and verify it is actually a briefing before updating. Do not rewrite an instruction file as a briefing; an existing explicitly designated briefing section may be updated while preserving the rest. If none exists, within the permitted write scope propose/create `work/CTO-RESEARCH.md`
(or `docs/` in a repo without `work/`) and add a pointer in the repo contract file.

**One briefing per repo.** A second file alongside the first creates two diverging caches.

## 2. Freshness gate (the first step when the file exists)

Read the header: date + base commit. Compare with `git log --oneline <base>..HEAD`. Also inspect `git status --short`, staged/unstaged diffs and relevant untracked files: uncommitted work can change the briefing without new commits. If the base is missing or does not resolve, the gate is unverified — rebuild the briefing. Relevant local changes require updating the affected sections and noting in the header that it includes uncommitted state.

| Observation | Action |
|---|---|
| 0 commits of difference and no relevant local changes | the briefing is fresh → go directly to the plan; the skill is complete |
| commits exist, but neither they nor local changes affect briefing areas | update the header (date, base) and say so |
| commits affect product / boundaries / infrastructure / dependencies | **rebuild** affected sections (steps 3–4) |
| no header (a person wrote the file or this is the first run) | the gate has **nothing to compare**: say so, build the briefing as new and **write a header** — the gate works from it next time |

State how many commits have elapsed and which affected the briefing — that is the evidence that the gate ran.
The header is the sole carrier of this gate, so a run without it is not complete.

## 3. Research five axes

Investigate each axis in its primary source (code, workflow files, lockfiles, `git log`), not a retelling.

1. **Product** — what it is, for whom, delivery format, data scale, where the logic lives.
   Sources: `docs/REQUIREMENTS.md`, README, live tasks.
2. **Codebase and seams** — packages/layers, where boundaries lie (module↔module, main↔worker,
   native↔JS, client↔server), what crosses each boundary. Sources: code, available CRG as optional navigation evidence after a freshness check.
3. **Infrastructure and delivery** — CI workflows, gates, how and where it deploys, which commands are green now.
   Sources: `.github/workflows/`, `package.json` scripts, configs.
4. **Dependencies** — critical libraries, versions, what is blocked on what.
   Sources: lockfiles, `package.json`, `Cargo.toml`.
5. **Risks** — recorded debt/criticism, intentionally unfinished work, the most fragile areas.
   Sources: `tech-debt/`, `tasks/`, anchor comments in code.

## 4. Write the briefing

The section order is fixed:

1. **One-screen verdict** — product in one paragraph, current state, live P0, and
   **architectural fact #1**: what an agent is most likely to misunderstand unless stated
   (the gap between “claimed” and “how it actually works”).
2. Product · 3. Codebase and seams · 4. Infrastructure and delivery · 5. Dependencies · 6. Risks.

Writing rules:

- **Every claim carries a source** — `path:line`, `doc §`, workflow filename or commit hash.
  A claim without a found source retains an `⚠️ unverified` label and wording
  “it appears that…” — so the next reader knows where the cache is thin.
- Use tables instead of paragraphs for “question → answer → source” pairs.
- The header contains the date and base commit (`git rev-parse --short HEAD`) — these drive the freshness gate.

## 5. Completion

The skill is complete when **all** of these hold:

- [ ] All six sections exist, none empty.
- [ ] Every claim has a source or an `⚠️ unverified` label — state how many claims carry the label.
- [ ] The header is updated: today's date + current short hash.
- [ ] “Architectural fact #1” is named.
- [ ] The repo contract file (`AGENT.md` / `AGENTS.md`) contains a pointer to the briefing.

Next is the plan (`spec-flow`, if present in this repo). The briefing does not make decisions by itself.
