<a id="agentsmd--точка-входу-до-agents"></a>

# AGENTS.md — entry point for `~/.agents`

Vendor-neutral SSOT for agent work. Readable by any tool; for Claude Code,
`~/.claude/CLAUDE.md` points here; for Cursor, `~/.cursor/` does so through symlinks to `skills/`.

**Edit here.** `~/.claude/skills` and `~/.cursor/skills` are symlinks to `~/.agents/skills`,
and `~/vaults/global/rules` points to `~/.agents/rules`. An edit through any mirror changes the original.

---

<a id="що-де-лежить"></a>

## Where things live

| Directory / file | What it is |
|---|---|
| [`rules/`](README.md) | cross-project rules: subagent orchestration, model roles, repo standards manifest format, TS idioms |
| `skills/` | skills (54), the physical source for all tools; grouped into `plan/ deliver/ arch/ git/ crg/ ship/ utils/ pt/`; flat symlinks retained for backward compatibility |
| `skills-cheatsheet.md` | skill cheat sheet: how / where / why / prompts |
| `obsidian-cheatsheet.md` | working with a vault through MCP |
| `ai-factory-plan.md` | development plan, not an operational document |

---

<a id="-правила-які-мусять-спрацювати-до-завантаження-будь-якого-скіла"></a>

## 🔴 Rules that must take effect **before** loading any skill

The other rules in `rules/` arrive through skills — a skill loads, reads the rule, and applies it.
The following does **not work** that way: it is needed when no skill has been invoked yet.

<a id="1-сабагент-пише-хід-у-власний-файл"></a>

### 1. A subagent writes progress to its own file

Before **every** subagent launch, give it a working-file path and a requirement to append as it proceeds.

```
WORKING FILE: <path>
Append AFTER EVERY STEP (append, not rewrite). The first entry comes before the first tool:
a `ДАЛІ:` line (NEXT) stating what you intend to check. Then use the compatibility labels ФАКТ / РІШЕННЯ / ДАЛІ / ПИТАННЯ (FACT / DECISION / NEXT / QUESTION).
Final answer = a concise summary of the file.
```

Parallel agents — **different files**. An agent crashed → first **read the file**, then decide:
empty = did not run (retry once on another tier); partial findings = retry with “continue, do not repeat”.

Does not apply to trivial one-step agents.

**Why this is here, not only in `rules/`:** it was there — detailed, 112 lines long, and **was not
applied**, because its only channel was skills, while agents were launched directly. The full rule,
with evidence from two series of agent deaths: [`rules/agent-stream-to-file.md`](agent-stream-to-file.md).

<a id="2-мовчазний-агент--не-чистий-агент"></a>

### 2. A silent agent is not a clean agent

`null`, an empty response, or a crash **do not mean “no findings”**. That is an agent that did not
complete its work, and it cannot be counted as clean: count launched versus returned agents
**numerically** and state the discrepancy explicitly. Details — [`rules/multi-model-roles.md`](multi-model-roles.md) §3.

---

<a id="як-додавати-правило"></a>

## How to add a rule

1. A file in `rules/`, an entry in [`rules/README.md`](README.md).
2. **Choose a delivery channel** — without one, the rule will not take effect:
   - must act on a direct tool call → here, in the section above;
   - belongs to a pipeline stage → in the corresponding skill;
   - specific to the repo → in `<repo>/AGENTS.md`.

🔴 A rule without a channel is equivalent to a missing rule.
