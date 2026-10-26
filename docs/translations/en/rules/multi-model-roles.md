---
title: Multi-model roles — which model tier serves each pipeline role
---

> **Historical English translation — authored derivative.** Original: [rules/multi-model-roles.md](../../../../rules/multi-model-roles.md). Original SHA256: `908d20088fcc0c49a1316ee43e92d671448f2c9336ef287103b2df3cdc2a371f`. Source base: `2c0960885926075502a319a19eafbed901690dde`. The original is unchanged. Historical assertions, statuses, examples, and limitations are retained; this translation does not establish current policy, execution evidence, or activation. Original-language compatibility anchors and literal protocol tokens remain where required.

# 🎛️ Multi-model roles

Cross-project rule: how to distribute pipeline roles (research → planning → critique → defense →
implementation → review → report) across models. Applies to `Agent(model:)`, `Workflow` `opts.model`
and `opts.effort`.

<a id="0-хто-і-коли-це-читає"></a>
## 0. Who reads this and when

The **orchestrator** — the session spawning subagents — reads this before the first `Agent`/`Workflow`.
The orchestrator **delegates the roles in §2 rather than performing them itself**: if it writes the plan
with its own hands, the “planning = `opus`” row never takes effect, because the orchestrator's tier is set
externally (by the session), not by this rule.

---

<a id="1-що-реально-доступно"></a>
## 1. What is actually available

**Inside Claude Code, choosing a model means choosing a Claude tier.** The `Agent` tool accepts
`sonnet | opus | haiku | fable` — **and nothing else**: it has no `effort` field.

**`effort` is available in exactly two places**, neither of which is the default route:
`Workflow` `opts.effort` (`low | medium | high | xhigh | max`) — **where the `Workflow` tool
is available**: not every session has it, and a subagent inside fan-out does not have it at all; or
the frontmatter of your own agent in `.claude/agents/*.md`. Spawn through `Agent` and control is limited
to the tier, so a table row with `effort` is fulfilled **only halfway**; say so explicitly rather than hiding it.

**`subagent_type: "fork"` never counts as another lens.** A fork inherits both the parent's context
and model, and **silently ignores** a supplied `model:` — there is no error, and the verdict looks valid.
Independence (§3) is achievable only with a fresh subagent and clean context.

**GPT / Kimi / Gemini / GML cannot be invoked as agents from here** — this is a tool boundary,
not a setting. Plan the pipeline to be **fully functional using Claude tiers alone**. A one-off
cross-vendor opinion, if ever needed (a file brief for another CLI, a PR bot), is a separate note,
not a step in this pipeline: when this rule is read, the machine may have no other CLI installed.

---

<a id="2-розкладка-ролей"></a>
## 2. Role allocation

| Pipeline role                                               | Tier                                           | Why                                                                           |
| ------------------------------------------------------------ | ---------------------------------------------- | ----------------------------------------------------------------------------- |
| **Planning, architectural alternatives**                     | `opus`                                         | the most expensive mistakes happen here; token cost is tiny compared with rework |
| **Plan critique** ([[plan-critique]])                        | `fable` — **not the planner's tier**; shared pool nearly exhausted → `sonnet` (§2.2) | the lens must be independent; the same model tends to agree with its own text |
| **Plan defense** ([[plan-defense]])                          | at least `sonnet`, **not the plan author**      | the form is fixed, the verdict is not: questions 3 and 5 require judgment about races and irreversibility |
| **Research in repositories / documentation**                 | `sonnet`                                       | reading volume is high, judgments are simple |
| **Task implementation**                                     | `sonnet` (`opus` for cross-boundary changes)     | the plan has already made the decisions; the agent executes |
| **Mechanics** (renames, configuration ports, bulk edits)      | `haiku`                                        | deterministic transformation |
| **Code review**                                             | **a different tier from the implementer**       | the same model reproduces the same blind spot |

The cells deliberately omit `effort` — see §1: `Agent` cannot pass it. When the step uses
`Workflow`, choose `high` for planning and `low` for mechanics.

The number of pipeline tasks (zero, one, many) does not change the tier: the table applies **per role**,
not per task — zero tasks means the role is simply not invoked; one task follows the same rows as N.

<a id="21-коли-потрібного-тіра-немає"></a>
### 2.1 When the required tier is unavailable

Tier names are retired, and an account may not have `fable`. Substitution order for a verdict role:
`fable → opus → sonnet`, **skipping the artifact author's tier** — otherwise the very first substitution
returns the verdict to the author. **Independence matters more than tier**: `sonnet` critiquing someone
else's plan is better than `opus` critiquing its own. If the tier had to be lowered, include a report line
(`тір знижено: fable → sonnet`, meaning “tier lowered: fable → sonnet”), rather than silently substituting it.

**A role absent from the §2 table** — the orchestrator maps the task to the row closest in nature:
judgment about architecture/alternatives → “Planning”; reading and synthesis without decisions → “Research”;
deterministic transformation without judgment → “Mechanics”. If the mapping is unclear, use `sonnet`
(this rule's default) and state the reason in the report (`роль поза таблицею: <назва>`, meaning
“role outside the table: <name>”), rather than saying nothing.

<a id="22-критика-чотири-лінзи-дорогим-тіром--найдорожчий-рядок-конвеєра"></a>
### 2.2 Critique: four lenses on an expensive tier — the pipeline's most expensive row

`plan-critique` multiplies cost by four: one run = four subagents. An expensive tier is especially
noticeable here because this is the only role with built-in fan-out.

**What a lens actually does.** Three of the four follow a fixed list — AI slop, excess complexity,
edge cases: the questions are known in advance, and the work is **disciplined coverage**, not depth
of reasoning. Such a step needs a clear completion criterion, and any tier from `sonnet` upward
can fulfill it. The fourth — **logical gaps** — is the only one that must trace what follows from what;
this is judgment, and it alone benefits from a more expensive tier.

**Default arrangement — inexpensive breadth, expensive depth:**

1. All four lenses on `fable` (one condition: it is not the plan author's tier). If the shared pool
   is tight, use `sonnet`; the basis and limits of this choice are under “When `fable` is appropriate” below.
2. The “logical gaps” lens uses the same tier, or a more expensive one if the plan is architectural.
3. **Escalate on a finding, not in advance:** send blocking findings, and only those, to a more
   expensive tier for confirmation. Escalate a few lines, not four full runs over the plan.
4. Synthesis (deduplication across lenses, blocking / non-blocking decisions) is where an expensive
   tier pays off most: the input is already short, and the cost of error is a missed blocker.

This way the expensive tier sees **findings**, not the entire plan four times.

**What you must not do to save money:** collapse the four lenses into one “check everything at once” run.
Then the first finding frames the rest, fan-out degenerates into a single lens with a longer prompt —
and the very property you paid for disappears. Lower the **tier**, not the number of lenses.

**No model has its own separate wallet.** Limits have two levels: a common window, **shared across all
models**, which receives tokens from every tier, and above it a family sub-limit (“You've hit your Opus
limit”) that only that family can exhaust. A model consumes **both**. Therefore “Fable — 8%” means only
“you will not hit its own ceiling”, not “this tier is free for the shared pool”
([docs: manage costs](https://code.claude.com/docs/en/costs), “When a developer asks about a limit”).

Consequence: **moving a role between tiers does not free the shared pool** — it only changes the speed
at which it drains. Savings come from **request volume and count**, meaning escalation on a finding
(item 3 above), not from model selection.

**When `fable` is appropriate.** The reason is not a separate wallet but the **family ceiling**.
Exhausting the shared window stops all work; exhausting a family sub-limit does not: after “You've hit
your Sonnet limit”, switching to another family lets work continue. Thus `fable` keeps critique alive
when the planner and implementer have already consumed their family's ceiling — while automatically
satisfying §3 (a different tier from the plan author).

Read `/usage` rows as follows:

| What you see | What it means for critique |
|---|---|
| `fable` low, shared pool low | use `fable` — independence at no extra cost |
| `fable` low, **shared pool high** | the bottleneck is not the tier: reduce volume (escalate on findings); tier is secondary |
| `fable` high | critique is hitting its own ceiling — lower to `sonnet`, skipping the author's tier (§2.1) |

Thus “move to `fable` to save the shared pool” makes no sense — whereas “stay on `fable` to avoid
competing for the planner family's ceiling” does.

**Before changing tiers, measure rather than guess.** `/usage` (the `w` key selects the weekly view)
has an **attribution** section: consumption broken down by skills, subagents, plugins and MCP servers,
plus **behavior flags** for anything taking ≥10% — long context, cache misses. If long context turns
out to be the largest contributor, the critique tier is irrelevant and session habits need to change.

---

<a id="3-правило-незалежності"></a>
## 3. Independence rule

The main point is not “a more expensive model is better” but **different eyes at different steps**.

- The model that wrote an artifact **does not** issue its verdict. Planner ≠ critic,
  implementer ≠ reviewer. This is achieved **only** through a fresh subagent: `fork` inherits model
  and context (§1).
- **Record the author's tier rather than recalling it.** The task writes `model=<тір>` to the ledger
  **at dispatch**, not on completion ([[subagent-orchestration-ledger]] §1) — otherwise, after compaction
  between DONE and review, the answer is absent exactly when it is needed. Steps outside tasks
  (plan, critique, defense) record their tier wherever their verdict lands — in the plan or report.
  If the author's tier is unknown (resume, someone else's or a human artifact, missing or unreadable
  ledger row with a tier), treat it as `opus` and obtain a verdict from another tier (`fable` or `sonnet`),
  rather than guessing. The placeholder `<тір>` means `<tier>`.
- Isolation of lenses within a step is defined by the skill itself (`plan-critique` §2: a separate
  subagent, clean context) and is not repeated here. Different tiers among lenses are unnecessary:
  context separates them; a different tier is needed only **against the artifact's author**.
- **A lens that does not return is a red gate, not “clean”.** Agent `null` (skip, crash after retries)
  = lens did not run: retry once on another tier with the same clean context; another `null` means
  the gate is red, and the report names the missing lens.
- Disagreeing verdicts are a signal, not noise: disagreement shows where the artifact is ambiguous.
  Resolve it by editing the artifact, not by voting.
- **A second round of critique** uses a different critic from the first, or examines only the edited
  lines: after changes, the plan contains text dictated by the first critic, who would be judging their own contribution.
- If **only one tier** is available, use it but in a clean context, and include the report line
  `незалежність: порушена (один тір)` (“independence: violated (one tier)”). Silent execution is forbidden.
- **The same step is launched twice** (a race, two tabs, two sessions orchestrating one pipeline,
  an unnecessary retry) — the tier does not change: the role determines it, not the invocation instance,
  so both runs use the same tier and independence rule. Which result is canonical is decided by
  the durable ledger ([[subagent-orchestration-ledger]] §1: the first `dispatched` row wins), not this
  rule; it guarantees consistent tiers across runs, not deduplication of the invocation itself.
- **Rollback of tier selection.** If a cheap tier spoiled a step, or independence was violated and
  the verdict is wrong, rerun the step on the tier assigned by §2 in a new clean subagent; the ledger
  gets a new `dispatched` row, and the old one is not rewritten retroactively. Tokens spent on the
  spoiled run and code already committed or pushed under the false verdict are sunk costs: this rule
  does not recover them. Rolling back the code itself (revert, force-push) is a git operation outside
  this rule and is irreversible on a shared branch for anyone who already fetched the previous version.
  The rule guarantees only that the rerun uses the correct tier and independence, not that the effects
  of the first run disappear.

---

<a id="4-коли-тір-не-має-значення"></a>
## 4. When tier does not matter

Do not spend `opus` on a step with a **verifiable completion criterion** that requires no judgment:
running gates, filling a fixed table, updating a file header. A cheap tier with a clear criterion
yields the same result. Be careful at the boundary: a fixed answer **form** does not imply a
deterministic **verdict** (see the “Plan defense” row in §2).

<a id="5-захист-plan-defense"></a>
## 5. Defense (plan-defense)

| # | Question | Covered by | Verdict |
|---|---|---|---|
| 1 | Malformed input | §2.1 “A role absent from the §2 table” (role outside the table); §3 “If the author's tier is unknown” (artifact with no known author); §2.1 “Tier names are retired, and an account may not have `fable`” (tier absent from account) | covered |
| 2 | Dependency failure | §1 “where the `Workflow` tool is available… not every session has it” (no `Workflow`); §2.1 “Substitution order… `fable → opus → sonnet`” (required tier unavailable); §3 “A lens that does not return is a red gate” (subagent `null`/dead); §3 “missing or unreadable ledger row with a tier” (ledger unreadable) | covered |
| 3 | Race and repeated invocation | §3 “The same step is launched twice” (same step twice, two sessions for one pipeline); §3 “A second round of critique uses a different critic” (repeated critique); parallel lenses explicitly out of scope because the skill defines isolation (§3 “Isolation of lenses within a step is defined by the skill itself… and is not repeated here”) | covered |
| 4 | Empty and boundary data | §2 “The number of pipeline tasks (zero, one, many) does not change the tier” (zero/one task); §3 “If only one tier is available” (single tier); §3 “If the author's tier is unknown (resume, …)” (entering midway through the pipeline); §3 “…otherwise, after compaction between DONE and review, the answer is absent exactly when it is needed” (compaction mid-pipeline) | covered |
| 5 | Rollback | §3 “Rollback of tier selection” (rerun on assigned tier, new `dispatched` row, token and committed-code sunk costs, git rollback outside this rule) | covered |

<a id="-повязане"></a>
## 🔗 Related

- `~/.agents/rules/subagent-orchestration-ledger.md` — ledger + 4 statuses for parallel work
- `~/.agents/ai-factory-plan.md` — the pipeline in which these roles operate
