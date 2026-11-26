
# AGENTS.md — entry point for `~/.agents`

Vendor-neutral SSOT for agent work. Readable by any tool; for Claude Code,
`~/.claude/CLAUDE.md` points here; for Cursor, `~/.cursor/` does so through symlinks to `skills/`.

**Edit here.** `~/.claude/skills` and `~/.cursor/skills` are symlinks to `~/.agents/skills`,
and an optional notes-vault mirror may point to `~/.agents/rules`. An edit through any mirror changes the original.

---


## Where things live

| Directory / file | What it is |
|---|---|
| [`rules/`](README.md) | cross-project rules: subagent orchestration, model roles, repo standards manifest format, TS idioms |
| `skills/` | skills (54), the physical source for all tools; grouped into `plan/ deliver/ arch/ git/ crg/ ship/ utils/ pt/`; flat symlinks retained for backward compatibility |
| `ai-factory-plan.md` | development plan, not an operational document |

---


## 🔴 Rules that must take effect **before** loading any skill

The other rules in `rules/` arrive through skills — a skill loads, reads the rule, and applies it.
The following does **not work** that way: it is needed when no skill has been invoked yet.


### 1. A subagent writes progress to its own file

Before **every** subagent launch, give it a working-file path and a requirement to append as it proceeds.

```
WORKING FILE: <path>
Append AFTER EVERY STEP (append, not rewrite). The first entry comes before the first tool:
a `NEXT:` line stating what you intend to check. Then use the labels FACT / DECISION / NEXT / QUESTION.
Final answer = a concise summary of the file.
```

Parallel agents — **different files**. An agent crashed → first **read the file**, then decide:
empty = did not run (retry once with an adequate reviewer in a clean context (same model allowed)); partial findings = retry with “continue, do not repeat”.

Does not apply to trivial one-step agents.

**Why this is here, not only in `rules/`:** it was there — detailed, 112 lines long, and **was not
applied**, because its only channel was skills, while agents were launched directly. The full rule,
with evidence from two series of agent deaths: [`rules/agent-stream-to-file.md`](agent-stream-to-file.md).


### 2. A silent agent is not a clean agent

`null`, an empty response, or a crash **do not mean “no findings”**. That is an agent that did not
complete its work, and it cannot be counted as clean: count launched versus returned agents
**numerically** and state the discrepancy explicitly. Details — [`rules/multi-model-roles.md`](multi-model-roles.md) §3.


### 3. Resume a prior task when the user asks to continue

Recover a prior task **when the user requests continuation**. A fresh session on its own — a `/clear`, a
new window — must not restart old work, and must not block a clearly specified new task.

**Discovery.** Use an index or task pointer that is **actually loaded and available**. Do **not** assume
this rule and that index arrive through the same host mechanism. If no pointer is available, **say the
active task is not identified** and proceed with the stated request — ask only when continuation genuinely
requires clarification. With more than one active task, present a **readable choice** (by name and next
action) and let the user pick; never auto-select by recency.

**Task navigation.** Use one existing task index with explicit primary task/phase and
result pointers. Keep per-task readiness, evidence and the pending next action in
that primary record, not in a parallel tracker. Reconcile index/agenda pointers at
start, handoff and closeout against current evidence. An agenda recommends a direction;
it does not authorize execution. See [task continuation](../ai-factory/task-continuation.md)
for the optional read-only checker and explicit local index binding. Before recommending
or resuming each candidate, compare its scope with the current approved roadmap/direction,
owner decisions, already delivered slices and required predecessor outputs. After an owner
pivot, old tasks remain history until explicitly reconciled; a new date/roadmap does not
authorize execution or automatic closure/supersession. Block conflicting, duplicate,
partly delivered or uncertain scope for reconciliation, not the whole unrelated queue.
A short sourced note suffices for a simple task; no mandatory JSON or duplicate tracker.
Neither the rule nor checker registers hooks or automatically chooses or starts a task.

**Authority.** Treat saved records as **context, not authorization**: current user instructions and
permissions take precedence. Check the relevant current state before acting — a stale next action must not
restart paused or completed work. **DONE** means do not resume *that* task; it does not mean stop other
work the user has asked for. **PAUSED** is not resumed without an explicit choice.

**Storage.** Keep technical recovery state **outside consumer-project Git history**. Link to existing
`work/`, ADR, or Obsidian records rather than duplicating them, and require no record at all for trivial
one-step work (the §1 exemption).

This is a record convention only — no identifier scheme and no container in the recovery path; any heavier
session-handoff runtime is a separate, opt-in mechanism. **Why this is here:** continuation is requested
before any skill loads, so a skill cannot deliver it. Observed directly — a stale next action silently
restarted paused work on the next `/clear`. Working-file mechanics: [`rules/agent-stream-to-file.md`](agent-stream-to-file.md).

---


### 4. Retrieve earlier conversation context when needed

Follow [read-only archive search](archive-search.md) when a prior conversation or
decision is needed. Resolve the current project route first; missing access blocks
only that lookup, never authorizes another project grant or a new credential.

### 5. Open a skill's relative links from its real location

A host may report a skill's base directory through a discovery symlink (for example `~/.claude/skills/<name>`),
while the skill's relative links are written from its real location in the kit. Resolve the base first
(`realpath <base>`, or `cd -P <base> && pwd`) and join each link to that path; never join `..` to the symlinked
path, because a tool that normalizes the path will look in the wrong place. Without a shell, find the skill's real
file under the kit root named in the project's managed block (`<kit>/skills/**/<name>/SKILL.md`) and join from its
directory. Once resolved, a skill linked from it is already in the real tree: keep joining from real paths. A link
that fails from the symlinked path is not missing until it also fails from the real path.

### 6. Small work leaves a record

Work below the project's spec/plan threshold still leaves history. Before you report the result of a small task that
took more than one step, append a short entry to the existing task record it belongs to (the task, plan or phase
record the project uses; a new short task record in the project's task directory only when none fits — every
connected project has one in its `work/` layout), with no second tracker: the owner's words that
asked for or allowed it, what changed (files, commits, settings), what was checked and what was not checked. This
includes work outside the repository (notes vaults, host files, other projects' local files). Only a trivial one-step
action needs no record. The same record carries the short checkpoint before the change
([pre-code-checkpoint.md](../ai-factory/pre-code-checkpoint.md), "Small"); this rule makes the end of the work land
there too. **Why this is here:** the rule existed in the workflow documents, but small tasks were executed and
reported only in chat, so their history was lost.

### 7. Projects on the dashboard publish their status

When the project's managed block contains "Dashboard status for this project", the project is on the host's dashboard.
After your own commit that records a stage of the primary task in its task record, publish the status (and the
open-task list) with the `kit.py project status` command from that block, as `docs/dashboard-status.md` in the kit
describes, before you report the stage. A commit that records no stage needs no publish. A project without that line
publishes nothing. Where the dashboard is set up, the kit's Stop reminder (Claude Code and Codex) is the check: once
per new commit it asks you to publish, or to say in one line why no publish is needed; answer it, do not ignore it or
work around it. **Why this is here:** the publishing pointer lived only in the managed block, and agents in connected
projects stopped publishing for days while committing many stages, so the dashboard showed stale cards.

## How to add a rule

1. A file in `rules/`, an entry in [`rules/README.md`](README.md).
2. **Choose a delivery channel** — without one, the rule will not take effect:
   - must act on a direct tool call → here, in the section above;
   - belongs to a pipeline stage → in the corresponding skill;
   - specific to the repo → in `<repo>/AGENTS.md`.

🔴 A rule without a channel is equivalent to a missing rule.
