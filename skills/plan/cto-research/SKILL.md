---
name: cto-research
description: Builds or updates the single pre-implementation briefing — product, codebase and seams, infrastructure, dependencies, risks — with every claim linked to a primary source. Use before planning a substantial feature, when starting in an unfamiliar repository, when the current briefing is stale, or on triggers "cto research", "брифінг", "розберись у продукті" (Ukrainian phrases retained as compatibility aliases).
---

<a id="cto-research--брифінг-перед-імплементацією"></a>

# cto-research — the pre-implementation briefing

One file the agent reads **before** the plan. Neither a ticket nor an ADR.

The briefing is a **cache** of primary sources, not independent truth. Every claim carries a source
reference; when cache and source disagree, the source governs and the cache is rewritten to match.
This is the single rule from which the rest of the skill follows.

<a id="1-знайди-дім-брифінгу"></a>

## 1. Find the briefing's home

First read applicable `AGENT.md` / `AGENTS.md` / `CLAUDE.md`: if they point to a briefing, use that path. Otherwise look for `work/CTO-RESEARCH.md` → `CONTEXT.md` → `docs/CONTEXT.md` and verify that it really is a briefing before updating. Do not rewrite an instructions file as a briefing; an existing explicitly designated briefing section can be updated while preserving the rest. If none exists, create `work/CTO-RESEARCH.md`
(or `docs/` in a repository without `work/`) and add a pointer in the repository contract file.

**One briefing per repository.** A second file beside the first creates two diverging caches.

<a id="2-гейт-свіжості-перший-крок-коли-файл-уже-є"></a>

## 2. Freshness gate (the first step when the file exists)

Read the header: date + base commit. Compare with `git log --oneline <base>..HEAD`. Also check `git status --short`, staged/unstaged diffs and relevant untracked files: uncommitted work can change the briefing without new commits. If the base is absent or cannot resolve, the gate is unverified — rebuild the briefing. Relevant local changes require updating affected sections and noting in the header that it includes uncommitted state.

| Observation | Action |
|---|---|
| 0 commits difference and no relevant local changes | briefing is fresh → go directly to the plan; skill complete |
| commits exist, but neither they nor local changes touch briefing areas | update the header (date, base) and say so |
| commits touch product / boundaries / infrastructure / dependencies | **rebuild** affected sections (steps 3–4) |
| no header (written by a person or this is the first run) | gate has **nothing to compare**: say so, build the briefing as new and **write the header** — it enables the gate next time |

State how many commits have passed and what in them affected the briefing — that is the evidence that the gate ran.
The header is the gate's only carrier, so a run without it cannot finish.

<a id="3-збери-по-пяти-осях"></a>

## 3. Research five axes

Research each axis in primary sources (code, workflow files, lockfiles, `git log`), not summaries.

1. **Product** — what it is, who it serves, delivery format, data scale, where logic lives.
   Sources: `docs/REQUIREMENTS.md`, README, live tasks.
2. **Codebase and seams** — packages/layers, where boundaries lie (module↔module, main↔worker,
   native↔JS, client↔server), what crosses each boundary. Sources: code, CRG `architecture_map`.
3. **Infrastructure and delivery** — CI workflows, gates, how and where deployment happens, which commands are green now.
   Sources: `.github/workflows/`, `package.json` scripts, configurations.
4. **Dependencies** — critical libraries, versions, what is blocked on what.
   Sources: lockfiles, `package.json`, `Cargo.toml`.
5. **Risks** — recorded debt/criticism, deliberate incompleteness, most fragile areas.
   Sources: `tech-debt/`, `tasks/`, anchor comments in code.

<a id="4-напиши-брифінг"></a>

## 4. Write the briefing

Section order is fixed:

1. **One-screen verdict** — the product in one paragraph, current state, live P0, and
   **architectural fact #1**: what the agent is most likely to misunderstand unless told
   (the gap between “declared” and “how it actually works”).
2. Product · 3. Codebase and seams · 4. Infrastructure and delivery · 5. Dependencies · 6. Risks.

Writing rules:

- **Every claim carries a source** — `path:line`, `doc §`, workflow filename or commit hash.
  A claim with no located source retains a `⚠️ unverified` label and the wording
  “it appears that…” — so the next reader knows where the cache is thin.
- Use tables instead of paragraphs for “question → answer → source” relationships.
- The header contains date and base commit (`git rev-parse --short HEAD`) — they drive the freshness gate.

<a id="5-завершення"></a>

## 5. Completion

The skill is complete when **all** of the following hold:

- [ ] All six sections exist, none empty.
- [ ] Every claim has a source or a `⚠️ unverified` label — count the labeled claims.
- [ ] The header is updated: today's date + current short hash.
- [ ] “Architectural fact #1” is named.
- [ ] The repository contract file (`AGENT.md` / `AGENTS.md`) contains a pointer to the briefing.

Next comes the plan (`spec-flow`, if present in this repository). The briefing itself makes no decisions.
