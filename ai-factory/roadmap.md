---
title: "Development queue and acceptance criteria"
reviewed: 2026-10-16
---

[Entry point](../docs/legacy/ai-factory-plan-entry.md) · [Status](status.md#capabilities) · [Routes](workflow.md#routing) · [Tasks](roadmap.md#tasks) · [Repo practices](repo-evidence.md#repo-evidence) · [History](history.md#history)

<a id="tasks"></a>

<a id="черга-розвитку-та-критерії-приймання"></a>
# Development queue and acceptance criteria

These are tasks and target criteria, not an instruction to execute them all. Current status lives only in [status.md](status.md#capabilities). First inspect the target repo: do not recreate what is already implemented. Repository commands/ports below are task context; verify their currency before execution.

<a id="3-авторство-й-оцінювання-скілів"></a>
## 3. Skill authoring and evaluation

The current name is [writing-for-agents](../skills/utils/writing-for-agents/SKILL.md); `writing-great-skills` is historical. Use the rubric for structure, progressive disclosure and verifiable completion criteria. The global skill already exists; there is no need to duplicate it in every repo merely for availability.

The 2026-10-14 audit had access to Codex [skill-creator](../../.codex/skills/.system/skill-creator/SKILL.md). This does not prove installation of the same-named Claude plugin. The old cache/installed_plugins and `run-skill-generator` record does not confirm current state; do not use it to decide installation.

E1.8 remains an eval-loop proposal: check triggering, output content and behavior on typical/boundary tasks with an available skill-creator variant. Behavioral evals are also useful for explicit invocations. Plugin installation is not part of this edit; a script's presence does not mean the eval has run.

---

<a id="4-запроєктована-структура-obsidian-для-dg"></a>
## 4. Proposed Obsidian structure for dg

Vault/Shared state and verification limits are in [status.md](status.md#capabilities). The target E0 layout below is preserved, not a repeated inventory.

According to the `~/.agents/obsidian-cheatsheet.md` runbook, the layout follows cargotrans-ui.

**Ports:** 27123 = cassiopeia, 27124 = its HTTPS, 27133 = cargotrans-ui → **27143 was planned for dg**. Current occupancy and server operation were not checked.

Layout of `~/vaults/diagram-hierarchy/`:

```
1 - Notes/{ADR,Domain,Prompts,Reports,Sessions}   # ADR: links/overview only; original in the repo
2 - Contract/  -> symlink to dg/AGENTS.md, dg/CONTEXT.md, dg/CONTRIBUTING.md
3 - Reference/ -> Docs (dg/docs), Work (dg/work), Requirements (docs/REQUIREMENTS.md)
4 - Shared     -> ~/vaults/global   (patterns, prompts, skills, rules — shared throughout)
```

`Domain/` mirrors actual dg boundaries: `core-wasm`, `sdk-render`, `contour`, `row-tree`,
`export`, `interactions`, `demo` — not FSD layers (there are none here).

---

<a id="5-реєстр-задач-і-критерії-приймання"></a>
## 5. Task registry and acceptance criteria

IDs are preserved. Execution and evidence are recorded in status.md; old E4/E5 results were moved to history.md.

Notation: **[me]** — I can do it in-session; **[you]** — hands-on GUI/browser work is needed.
Priority: **P0** unblocks the rest; **P3** is optional.

<a id="e0--obsidian-для-dg--vault-diagram-hierarchy--p0"></a>
### E0 · Obsidian for dg — vault `diagram-hierarchy`  (P0)

| # | Task | Who | DoD |
|---|---|---|---|
| E0.1 | Create `~/vaults/diagram-hierarchy` with `1 - Notes/{ADR,Domain,Prompts,Reports,Sessions}` structure | me | directories exist |
| E0.2 | Symlinks: `4 - Shared` → `~/vaults/global`; `2 - Contract/*` → `AGENTS.md`, `CONTEXT.md`, `CONTRIBUTING.md`; `3 - Reference/*` → `docs`, `work` | me | `ls -l` shows links, not copies |
| E0.3 | `.gitignore` (ignore `2 - Contract`, `3 - Reference`, `4 - Shared`, `.obsidian/plugins/*/data.json`, `.obsidian/workspace*.json`) + `git init` + first commit | me | `git status` is clean |
| E0.4 | Vault `Home.md` + `README.md` (following cargotrans-ui: layout, MCP port, security) | me | both files exist; `[[Home]]` is the entry |
| E0.5 | Templates `_ADR Template` (index/link to repo ADR), `_Report Template`, `_Session Template`, `_domain-note-template` | me | copied from cargotrans-ui, adapted for dg |
| E0.6 | Open the vault in Obsidian → Community plugins → **Local REST API with MCP** → Install/Enable → HTTP server on → **port 27143** → copy the Bearer token | **you** | plugin listens on `127.0.0.1:27143` |
| E0.7 | Settings → Files & Links → Excluded files: `4 - Shared/.obsidian` | **you** | global config is not indexed |
| E0.8 | From the selected dg project root: `claude mcp add -s local --transport http obsidian http://127.0.0.1:27143/mcp/ --header "Authorization: Bearer <token>"` → `claude mcp list` = ✓ Connected | me (after E0.6) | MCP `obsidian` in dg local scope |
| E0.9 | `dg/CLAUDE.local.md` — port cargotrans-ui rules: KB start, **incremental live Session note** (flush early and often), fallback to `work/reports/<topic>/_wip-*.md` when Obsidian is closed | me | file exists, `.gitignore` ignores it |
| E0.10 | Update `~/.agents/obsidian-cheatsheet.md` §3 — table row `diagram-hierarchy / 27143` | me | ports table is current |
| E0.11 | Seed `1 - Notes/Domain/`: `_how-it-works.md`, `_domain-moc.md`, `_gotchas.md`, `_glossary.md` — from `CTO-RESEARCH.md` + `SPEC.md`, with `path:line` | me | 4 files, every claim has a source |

<a id="e1--глобальний-шар-скіли-пайплайна--p0p1"></a>
### E1 · Global layer: pipeline skills  (P0–P1)

Home is `~/.agents/skills/<категорія>/<name>/SKILL.md` or a separate root directory; exact paths are in status.md. The compatibility path placeholder `<категорія>` means category. Shared contains reference cards updated separately, not executable copies.
**Every skill passes the `writing-for-agents` rubric before merge.**

| # | Task | Priority | DoD |
|---|---|---|---|
| E1.1 | `cto-research` — section skeleton (product / codebase and seams / infrastructure / dependencies / risks / one-screen verdict), `path:line` per claim, freshness gate by base commit, HEAD and staged/unstaged/untracked changes; write the header on first assembly | P0 | a dg run reproduces the structure of the existing `CTO-RESEARCH.md` |
| E1.2 | `plan-critique` — fan out into 4 lenses (AI-slop / logical gaps / excess complexity / uncovered edge cases), structured verdict per lens + consolidation; implemented through available independent-delegation mechanisms under agent rules; without them, BLOCKED | P0 | state `4 launched / N returned`; every returned lens gives a finding or explicit “clean”; a missing lens makes the gate red with that lens named |
| E1.3 | `plan-defense` — deterministic checklist of 5 questions (malformed input / service failure / race+repeated click / empty and boundary data / rollback); each closed by **a reference to a plan line**, otherwise the gate is red | P0 | a 5-row table in the plan, each row either references a plan line or says “out of scope because <reason>”; an empty row = red gate |
| E1.4 | `acceptance-spec` — table `scenario / precondition / action / observable result / verification method`; embedded in `plan.md` **before** code | P1 | table generated and linked from tasks.md |
| E1.5 | `ship-report` — 6 fixed thread sections, report as a **delta** from the plan; section 2 is the `acceptance-spec` table with added “actual result” and “verdict” | P1 | all 6 sections present (empty = “not applicable because…”, not deleted); every table row has a verdict; state the “not tested” count |
| E1.6 | `post-deploy-check` — run **key** scenarios against the production/Pages URL, production ⟂ test discrepancies, logs and integrations, append to the same report | P2 | name what is available/unavailable and which build opened; a discrepancy list exists even if empty; result in the existing report, not a new one. ⚠️ implemented as `auto`, not user-invoked: “перевір прод” is the retained natural trigger meaning “check production”, and `ship-report` must reach it |
| E1.7 | Rule `~/.agents/rules/multi-model-roles.md` — role allocation and context independence; check available models/providers in the current session | P1 | An agreed pilot names the author and independent reviewer, actual tools/models and rule-loading channel; launched/returned check counts match or the gate is BLOCKED. Vault visibility alone is not DoD |
| E1.8 | Select an available `skill-creator` and plan an eval loop; installation, if needed, is a separate decision; evaluate E1.1 / E1.2 / E1.5 (test prompts + `description` optimization) | P2 | At ≥5 prompts per skill, invocation relevance and output behavior are checked against expected criteria: typical, boundary, irrelevant request and unavailable tool; for explicit invocation, contract fulfillment. Record version, results and defects; triggering alone is not PASS |
| E1.10 | `repo-bootstrap` — 11-item inventory (manifest, briefing, contract pointers, `CLAUDE.local.md`, artifact home, tasks/debt/archive, gates, tracker, CRG, vault, agenda), two branches (check / initialization), idempotent; **does not invent content** — `⚠️ missing` instead of a plausible standard, `TODO:` instead of deciding for a person | P0 | produces a state table in an unfamiliar repo; a second dg/cargotrans run creates nothing new |
| E1.9 | `cto-agenda` — **what to do next**: candidates from six listed sources (tasks/issues, debt, briefing risks, unchecked boxes, skipped tests and `TODO`, product forks) → **unblocks × reversibility** axes → **one** next move + why not the others. Home is `work/AGENDA.md`, rebuilt, not appended | P0 | all 6 sources examined with candidate counts; each candidate has a source or `⚠️ no source` label; name one move and reject 2–3 alternatives |

<a id="e2--cargotrans-ui--доростити-наявний-конвеєр--p1"></a>
### E2 · cargotrans-ui — extend the existing pipeline  (P1)

The goal is minimal additions to the existing process after checking its state, not rebuilding it.

| # | Task | DoD |
|---|---|---|
| E2.1 | `spec-flow` §3: add **mandatory** “side effects / migration plan / rollback” fields to `plan.md` | a plan without them fails GATE 2 |
| E2.2 | Reconcile local GATE 2 with the agreed process: `plan-critique` + `plan-defense` + constitution; `grilling` belongs to global spec-flow GATE 1 and is not automatically added twice | both new gates are invoked from spec-flow |
| E2.3 | Remove prohibition-based wording from `spec-flow` (**negation** in the writing-for-agents rubric) — rewrite as a positive goal | no “DO NOT enable” without a paired “do this instead” |
| E2.4 | Add a pointer to `~/.agents/rules/subagent-orchestration-ledger.md` (ledger + 4 statuses) in `AGENT.md` — the rule exists now but the contract does not reference it | pointer present, ledger stored at `reports/<topic>/wave-NN/progress.md` |
| E2.5 | Task branches in the main repository, one writer, explicit handoff and stopping on foreign WIP — [branch ownership](workflow.md#task-branches); no automatic worktree/clone | task record contains branch/base/owner, snapshot and agreed runtime slot |
| E2.6 | Connect `ship-report` to `spec-flow` §7 as the final-report format in `reports/<topic>/` | fixed report template |
| E2.7 | Playwright user-flow run with **screenshots in the report artifact** (`.env.playwright.local` exists) | Current desktop/mobile screenshots with viewport dimensions actually inspected; main scenario, states and keyboard exercised; defects fixed and rechecked. Evidence and PASS/FAIL/BLOCKED/N/A in the report; do not count human verification without a result |
| E2.8 | `post-deploy-check` on the cargotrans production URL | checklist exists and has been run once |

<a id="e3--dg--підняти-базу-конвеєра--p1"></a>
### E3 · dg — establish the pipeline foundation  (P1)

The initial record says dg had only CRG wrappers; the repo's current state was not checked. Order matters: review criteria first, orchestrator second.

| # | Task | DoD |
|---|---|---|
| E3.1 | `dg/.claude/skills/review/SKILL.md` — following cargotrans, but criteria **enumerated for dg**: `work/CODING_STANDARDS.md`, `work/SPEC.md` §13, `work/TDD.md`, `AGENTS.md`; machine gates = `npm run test:verify` (typecheck + test + e2e + compare:nodes) + `npm run test:rust` | review does not guess standards; `work/tasks/**`, `work/tech-debt/**` explicitly are **not** criteria |
| E3.2 | `dg/.claude/skills/spec-flow/SKILL.md` — port from cargotrans, threshold redefined for dg (new subsystem in `packages/core` or `packages/sdk`, SDK public API change, worker-contract change), artifacts → `work/reports/<topic>/` | pipeline runs on an actual T-task-level task |
| E3.3 | Bind `cto-research` (E1.1) to existing `work/CTO-RESEARCH.md` as its output artifact + staleness gate (file dated 2026-08-24, base `a5eb0f6`) | skill updates the file rather than writing a second one |
| E3.4 | Check global `writing-for-agents` availability in dg; if needed, add a pointer to the current SKILL.md without duplication | skill available in dg |
| E3.5 | “Pipeline” section in `AGENTS.md`: research → plan → critique → defense → tests-first → implement → review → report → post-deploy, with skill links | one agent entry point |
| E3.6 | `acceptance-spec` for live P0 (`work/tasks/T78-post-t77-critique.md`) as a format pilot | scenario table exists, every row has a verification method |

<a id="e4--незалежне-ai-ревю-на-pr-p2"></a>
### E4 · Independent AI review on PRs (P2)

| # | Task | DoD |
|---|---|---|
| E4.1 | Check the existing dg ai-review workflow and agreed criteria; access is configured separately | Valid YAML and a real test PR; skipped is distinguished from successful review |
| E4.2 | Check separate standards/spec-and-edges jobs and their input contexts | Two independent verdicts with evidence; different runners alone do not prove independence |
| E4.3 | Check the resulting ready-for-human/needs-info label | Exactly one correct label and an explanation on the test PR |
| E4.4 | P3: evaluate an external vendor's usefulness as a third reviewer | Benefit/friction decision recorded; do not install just in case |

### E5 · Post-deploy (P2)

| # | Task | DoD |
|---|---|---|
| E5.1 | Check dg prod-smoke/playwright.prod/test:prod/post-deploy workflow against the actual deployment | Build, scenarios and verdict named; failure observable without manually opening it |
| E5.2 | Check cargo tools/post-deploy/run.sh and yarn post-deploy on an agreed test environment | Guards and relevant flows checked; unavailable environment means BLOCKED; switch/cleanup are not automated by this plan |
| E5.3 | Add the post-deploy result to the existing ship-report | One report per feature, with separate pre/post-deploy evidence |

Exact old commands, parameters, figures and limitations are retained in [E4/E5 history](history.md#ci-history); they are not a current verification.

<a id="6-наступний-порядок-після-актуалізації"></a>
## 6. Next sequence after updating the inventory

1. Before implementing any E0/E2/E3/E4/E5, inspect the specific target repository and compare its state with the criteria; for ADR and local workflow use [repo practices](repo-evidence.md#repo-evidence). Do not recreate what already exists; local skill copies may differ from global.
2. Compare E1.1–E1.6, E1.9–E1.10 with status.md. The next step is a pilot on an agreed real task and evidence, not rewriting skills. UI requires the design-pass cycle from [workflow](workflow.md#ui).
3. Based on inventory, select a specific E2/E3 gap: contracts, acceptance scenarios, independent gates, ledger, report. Preserve local standards and language/package boundaries.
4. Check E4/E5 separately: CI file ≠ successful job; job ≠ independent quality review; historical smoke ≠ healthy current deployment. Do not silently configure access/secrets or write them in reports.
5. E1.8/E4.4: eval and cross-vendor work after checking the basic process and making a separate scope decision.

Controlled DB/log access is determined by the needs of the specific scenario and existing permissions, not merely a “frontend” or “SDK” label. The number of parallel agents/PRs is determined by task independence and available resources; 3–8 or 5–50 is not a standard.

The 2026-10-14 pass changed only the plan. No projects, browser scenarios, CI, deployments or evals ran; configurations, plugins and implementation of plan items were not changed.
