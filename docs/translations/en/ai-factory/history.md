---
title: "History of the concept and previous measurements"
reviewed: 2026-10-16
---

> **Historical English translation — authored derivative.** Original: [ai-factory/history.md](../../../../ai-factory/history.md). Original SHA256: `d7520cdbe02175d651383dbe6c1e2ab756fa584357e096b5b42b279a0b752cdf`. Source base: `2c0960885926075502a319a19eafbed901690dde`. The original is unchanged. Historical assertions, statuses, examples, and limitations are retained; this translation does not establish current policy, execution evidence, or activation. Original-language compatibility anchors and literal protocol tokens remain where required.

[Entry point](../../../legacy/ai-factory-plan-entry.md) · [Status](../../../../ai-factory/status.md#capabilities) · [Routes](../../../../ai-factory/workflow.md#routing) · [Tasks](../../../../ai-factory/roadmap.md#tasks) · [Repository practices](../../../../ai-factory/repo-evidence.md#repo-evidence) · [History](#history)

<a id="history"></a>

<a id="історія-задуму-та-попередніх-вимірів"></a>
# History of the concept and previous measurements

These are historical records, not current commands or statuses. Current capabilities are described only in the [status registry](../../../../ai-factory/status.md#capabilities). Old “missing” claims, ✅ marks, and numbers below do not carry over to the current state without fresh verification.

<a id="1-історичний-розбір-треду-2026-08-25"></a>
## 1. Historical analysis of the thread (2026-08-25)

Below, “Present/Missing” describe the original motivation. The current global state is in the status.md registry; repo-specific claims need fresh verification.

The thread has 12 stages. Each below: **essence → what covers it here → what is missing**.

<a id="11-deep-cto-research-перед-кодом"></a>
### 1.1 Deep CTO research before code
Essence: the agent understands the product, codebase, patterns, infrastructure, dependencies, and risks;
nobody implements before understanding.

- **Present:** `dg/work/CTO-RESEARCH.md` — an exact example of what the thread describes in words
  (a one-screen verdict, every claim leads to a primary source, “if they diverge, correct the source”).
  In cargotrans-ui, `AGENT.md` (38 KB) + `CONTEXT.md` serve this role.
- **Missing:** the **process** that produces and updates this file. Currently it was written manually once
  (2026-08-24) and will silently go stale. A `cto-research` skill is needed: a fixed section skeleton,
  a `path:line` requirement for every claim, and a **staleness gate** (file older than N commits → reread).
  A staleness precedent already exists: `~/vaults/cargotrans-ui/tools/kb-staleness.mjs`.

<a id="12-план-як-детальний-документ-75-часу"></a>
### 1.2 The plan as a detailed document (75% of the time)
Essence: not a task list, but what/where we change, which services, side effects, migration, and how we test.

- **Present:** `spec-flow` in cargotrans-ui does exactly this (spec→gate→plan→gate→tasks→implement→verify,
  artifacts in `reports/<topic>/`).
- **Missing:** (a) dg has none at all; (b) the plan section has no mandatory
  **side effects / migration / rollback** fields — half of what the thread calls a “painstakingly perfected plan.”

<a id="13-план-критикує-сам-себе-ai-slop-дірки-зайва-складність-edge-cases"></a>
### 1.3 The plan critiques itself (AI-slop, gaps, excess complexity, edge cases)
- **Present:** `grilling` (global skill) + GATE 1/GATE 2 in spec-flow.
- **Missing:** critique currently has **one voice and one lens**. The thread describes *separate agents for separate
  defects*. A `plan-critique` is needed — fan-out into 4 independent lenses (AI-slop / logical gaps /
  excess complexity / uncovered edge cases), each returning a structured verdict,
  followed by synthesis. This is exactly what available delegation tools can implement; `Workflow` is not a guaranteed dependency.

<a id="14-різні-моделі-для-різних-ролей"></a>
### 1.4 Different models for different roles
The idea is to separate author, researcher, and independent reviewer. Specific model names, APIs, and available providers depend on the agent and current session; do not treat the old tier matrix as a verified configuration. A cross-vendor process is optional E4.4, with a file brief and verifiable result, if tools are available and use is authorized. Different models alone do not prove context independence.

<a id="15-плани-захищають-перед-імплементацією"></a>
### 1.5 Plans are defended before implementation
Essence: scrutinize the details — what if the user does this? what if the data is malformed? what if the service fails? how do we roll back?

- **Present:** `grilling` is close, but it is a dialogue with the user, not a checklist.
- **Missing:** `plan-defense` — a **deterministic** checklist of 5 mandatory questions
  (malformed input / failed external service / race and repeated click / empty and boundary data / rollback),
  where every question must be closed with a **link to a plan line**, otherwise the gate is red.
  This is cheaper and more repeatable than manual grilling.

<a id="16-ai-cto-ріже-роботу-на-команди-та-спринти"></a>
### 1.6 AI CTO splits work into teams and sprints
- **Present:** `~/.agents/rules/subagent-orchestration-ledger.md` — durable ledger, a 4-status
  protocol (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED), brief-file handoff.
  This is exactly the thread's “responsibility areas + dependencies + readiness criteria.”
- **Missing:** the rule lives in `~/.agents/rules/`, but **no repository contract refers to it**
  (neither cargotrans's `AGENT.md` nor dg's `AGENTS.md`). In practice, it therefore has no effect.

<a id="17-тести-плануються-до-коду-детерміністично-на-рівні-продукту"></a>
### 1.7 Tests are planned before code, deterministically, at product level
Essence: not just units testing internal implementation — what the user sees, does, what should happen, and what counts as correct.

- **Present:** `dg/work/TDD.md` (red-green-refactor, success+failure), global `tdd` skill,
  playwright in both repositories.
- **Missing:** an **acceptance spec format as a plan artifact**: a table
  `scenario | precondition | user action | expected observable result | how verified (e2e/unit/manually)`.
  Without it, “tested” remains a judgment rather than a fact.

<a id="18-тестове-середовище-як-prod-агент-проходить-фічу-як-юзер-контрольований-доступ-до-логівсервісівread-only-бд-дії-трекаються"></a>
### 1.8 A prod-like test environment; the agent walks through the feature as a user; controlled access to logs/services/read-only databases; actions are tracked
- **Present:** playwright configurations in both repositories; dg has a demo-app and `compare:nodes` (visual comparison).
  Browser-tool availability must be established in the current session.
- **Missing:** (a) for cargotrans-ui — a recorded user-flow run with **screenshots in an artifact**;
  (b) read-only database / log access is not established as controlled access anywhere.
  Honestly: the read-only database item for a frontend repository (cargotrans-ui) and an embed-SDK (dg) is
  **not applicable**; it concerns a backend service. I am not adding it to the tasks.

<a id="19-execution-550-паралельних-pr"></a>
### 1.9 Execution: 5–50 parallel PRs
- **Present:** native `Agent isolation:"worktree"`, `Workflow` with `pipeline`/`parallel`,
  `.claude/worktrees/` as a starting point.
- **Missing:** rules to keep parallelism from undermining itself: who maintains the ledger, how file
  boundaries are divided between branches, and what to do on conflict. Also an **honest limit**: 5–50 PRs for one feature
  make sense only when the feature splits into genuinely independent slices; for an FSD repository,
  3–8 is realistic, not 50. The thread's numbers are marketing; the mechanism is not.

<a id="110-незалежні-ai-ревюєри-на-github-ревюєр-не-знає-як-писався-код"></a>
### 1.10 Independent AI reviewers on GitHub; the reviewer does not know how the code was written
- **Present:** local `review` (cargotrans-ui) — strong because it enumerates standards rather than guessing.
- **Missing:** (a) dg has no equivalent at all; (b) no **PR reviewer in CI** reads task+plan+diff
  from scratch. The thread's key property — **reviewer blindness to creation history** —
  needs a fresh context without authorship history; this may be a separate process or an appropriately isolated subagent. Running on GitHub alone does not guarantee this.
  For dg this is feasible: `b2vv/dg` is on GitHub, and `gh` is already used (`docs/agents/issue-tracker.md`).

<a id="111-звіт-замість-полотна-що-зроблено-які-сценарії-протестовані-що-неочевидного-знайшли-скріни-проходка-по-flow-ризики"></a>
### 1.11 A report instead of a wall of text: what was done, scenarios tested, non-obvious findings, screenshots, flow walkthrough, risks
- **Present:** the `reports/<topic>/` convention (cargotrans-ui, ~30 directories) + Report/Session templates in Obsidian
  + the live-note rule in `CLAUDE.local.md` (incremental flush — after an actual context loss).
- **Missing:** `ship-report` — a skill with the thread's **fixed 6 sections**, where “screenshots” and “user-flow
  walkthrough” are not optional. Currently the report structure differs slightly each time.

<a id="112-post-deploy-ключові-тести-на-prod-логи-інтеграції-фінальний-апдейт"></a>
### 1.12 Post-deploy: key tests on prod, logs, integrations, final update
- **Original gap, later partially closed according to E5's record.** For dg, the idea is to run smoke on
  the GitHub Pages demo after `pages.yml`. For cargotrans-ui — smoke on the production URL after deployment.

---

<a id="2-reality-check-по-треду-принципи-не-метрики"></a>
## 2. Reality-check of the thread (principles, not metrics)

To avoid building the plan on advertising:

- “hundreds of thousands of agents,” “500+ commits per day” are a showcase, not the mechanism. What transfers here is
  **pipeline discipline**: research → plan → plan critique → plan defense → tests before code →
  parallel execution → independent review → structured report → post-deploy.
- “75% of time on planning” is an unverified quantitative claim: the existence of briefing and gates does not measure time spent. Keep planning discipline without a percentage requirement.
- “rejected PRs 100+ times” is achievable only when the reviewer has an **enumerated** yardstick (as in
  cargotrans-ui's `review` skill); otherwise it is noise rather than quality.

---
<a id="51-історичний-запис-виміру-2026-08-25"></a>
## 5.1 Historical measurement record (2026-08-25)

Preserved as the origin of decisions. “Missing” statuses and implementation criticisms below are not a current audit: global has already changed; see status.md. The cited numbers and results were not reproduced on 2026-10-14.

Not a plan recap, but a disk reconciliation after the first **real-world** E1.1→E1.2→E1.3 run on an actual
plan (`cargotrans-ui/work/plans/range-ux-from-trebble2.md`).

| Item | State | Measurement evidence |
|---|---|---|
| E0.1–E0.5, E0.10 | ✅ | `~/vaults/diagram-hierarchy/` has a structure, `Home.md`, `README.md`; port 27143 in the cheatsheet |
| E1.1 `cto-research` | ✅ run | produced briefing `cargotrans-ui/CONTEXT.md` — six sections, pointer in `AGENT.md` |
| E1.2 `plan-critique` | ✅ run | 4 lenses → 8 blocking findings, including 5 in already shipped code |
| E1.3 `plan-defense` | ✅ run | 5-question table in the plan, 0 gaps |
| E1.4 `acceptance-spec` | ◐ skill exists, not used | descriptor was missing from global-vault — added |
| E1.5 `ship-report` | ❌ | absent from `~/.claude/skills/` |
| E1.6 `post-deploy-check` | ❌ | same |
| E1.7 `multi-model-roles` | ✅ | `~/.agents/rules/multi-model-roles.md` |
| E2.1, E2.2, E2.4, E2.5 | ❌ | `spec-flow` calls only `grilling`; no ledger pointer in `AGENT.md`; `.claude/worktrees/` is empty |

<a id="що-показав-бойовий-прогін--і-чого-в-плані-немає"></a>
### What the real-world run revealed — and what the plan lacks

**1. E2.2 is the costliest unfinished item, proven by execution.** The gates exist, but `spec-flow`
GATE 2 does not call them. Both were run manually because the user asked. They therefore trigger
when someone remembers, not when needed. This is the only item that turns existing skills from “present” into
“active.”

**2. E1.2 has the right DoD and a wrong implementation description.** It says “through `Workflow` `parallel` +
`schema`.” In fact, `Workflow` requires explicit user permission, while the skill itself describes ordinary
subagents. During the run, **one of four lenses failed** on infrastructure, and this was noticed visually.
`multi-model-roles` §3 says a lens that does not return means a red gate. Through `Agent`, no such gate
exists at all.

**3. E1.3 has an unattainable DoD.** “A plan without a rollback section does not pass the gate” — but the skill allows
closing the gap with “out of scope because…”. A plan without rollback therefore **passes** if one
sentence is written. This matches the intent, but the DoD says the opposite and will never be fulfilled as
written.

**4. E1.7 has no application mechanism.** Its DoD is “the rule is visible in both vaults,” meaning **visibility**,
not action. In the run the rule was violated **twice** (lenses inherited the author's tier; the plan author
performed the defense), and this was caught only by reading the rule afterward. A pipeline whose independent
verdicts depend on the orchestrator's memory depends on nothing.

**5. E1.1's freshness gate has nothing to use on the first run.** It compares a “date +
base commit” header with `HEAD`, but existing `CONTEXT.md` files have no header. The first run always means “gate
not run.” The DoD should add: the skill **writes** the header so the gate works from the second run onward.

---

<a id="ci-history"></a>

<a id="історичні-записи-e4e5-з-попереднього-реєстру"></a>
## Historical E4/E5 records from the previous registry

<a id="e4--незалежне-ai-ревю-на-pr--p2"></a>
### E4 · Independent AI review on PRs  (P2)

The thread's key point: the reviewer **does not know** how the code was written — a separate process, clean context.

| # | Task | DoD |
|---|---|---|
| E4.1 | ✅ `dg/.github/workflows/ai-review.yml` — on `pull_request`, `anthropics/claude-code-action@v1` (interface checked against `docs/solutions.md`), yardstick = `.claude/standards.md`. ⚠️ **Not verified with a real PR:** the repository lacks the `ANTHROPIC_API_KEY` secret (`gh secret list` is empty), so the job currently reports `skipped` | YAML is valid; `gh secret set ANTHROPIC_API_KEY` + a test PR remain |
| E4.2 | ✅ Two **separate jobs** = separate runners = separate contexts: `standards` (yardstick, language binding) and `spec-and-edges` (spec / boundaries / WASM↔TS / public API) | two independent comments, not one |
| E4.3 | ✅ The second pass sets exactly one label through `gh pr edit`: `ready-for-human` or `needs-info`, explaining what is missing | label is set automatically |
| E4.4 | **P3, optional:** external vendor as a third reviewer (another CLI through `Bash` with a file brief, or a GitHub bot) — assess friction before doing it | decision recorded, not “done just in case” |

### E5 · Post-deploy  (P2)

| # | Task | DoD |
|---|---|---|
| E5.1 | ✅ `e2e/prod-smoke.spec.ts` + `playwright.prod.config.ts` + `npm run test:prod` + `.github/workflows/post-deploy.yml` (`workflow_run` for Pages). **Run against a live deployment: 3 passed, 5.9 s**, build named in the output | failure is visible without opening it manually |
| E5.2 | ✅ `tools/post-deploy/run.sh` + `yarn post-deploy` — key flows (`authed-chromium` = `*-crud.e2e.ts`) against the **production-line stand** (default `v1` :82). A prod-like environment here is not a public URL, but stands with separate MySQL instances. **Guard verified on both branches:** wrong stand → refusal with instructions; correct but not running → refusal with the compose command. Deliberately does not automate `switch-be.sh` and `cleanup.sh` | ⏳ the flows themselves were not run — the stands are currently down |
| E5.3 | The final post-deploy update is appended to **the same** `ship-report`, not a new file | one report per feature from planning to production verification |

---
