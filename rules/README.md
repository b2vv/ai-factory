# ~/.agents/rules — shared agent rules (physical SSOT)

> The entry point for all of `~/.agents` is [`../AGENTS.md`](agent-entry.md): a directory map, rules that
> must take effect before a skill is loaded, and how to choose a delivery channel for a new rule.

The physical source of truth for **cross-project** agent rules/idioms (LLM + human).
Alongside `~/.agents/skills/` (skills) and `~/.agents/*-cheatsheet.md` (cheat sheets).

- **Here** — rules shared by ALL projects (TS idioms, general architectural principles…).
- **Project-specific** rules remain in the repo (`<repo>/.ai/rules/*.mdc`, `docs/agent/`).

<a id="доступ-з-obsidian"></a>

## Access from Obsidian
This directory is **symlinked** into the global vault: `~/vaults/global/rules → ~/.agents/rules`.
It is therefore visible in every project vault as `4 - Shared/rules/` and exposed through Obsidian MCP.
Edit files **here** (the physical source); Obsidian displays them through the symlink.

<a id="файли"></a>

## Files
- [`typescript-pocock-idioms.md`](typescript-pocock-idioms.md) — Matt Pocock / TotalTypeScript idioms (a distillation).
- [`subagent-orchestration-ledger.md`](subagent-orchestration-ledger.md) — durable ledger,
  4-status protocol, brief-file handoff.
- [`multi-model-roles.md`](multi-model-roles.md) — which Claude tier fits each pipeline role
  + an honest cross-vendor boundary.
- [`agent-stream-to-file.md`](agent-stream-to-file.md) — each subagent writes progress to its own file;
  an agent's death leaves a trace. ⚠️ **The only rule here that must take effect BEFORE loading
  any skill** — which is why a pointer is duplicated in `~/.claude/CLAUDE.md`
  (Claude Code global memory, read in every session). Without that link the rule remained
  unapplied: skills referenced it, but direct calls to the `Agent` tool bypassed it.
- [`repo-standards-manifest.md`](repo-standards-manifest.md) — the `<repo>/.claude/standards.md` format: process in the skill, evaluation criteria in the repo.
  §0 — binding the evaluation criteria to the language (Pocock applies only to TS).

> Adding a new shared rule → put its `.md` here; it will appear in Obsidian automatically through the symlink.

<a id="як-правило-доходить-до-застосування"></a>

## How a rule reaches execution

A file here is a **source**, not delivery. A rule takes effect only when something brings the agent
to it **at the right time**:

| Channel | When it is read | What belongs there |
|---|---|---|
| [`../AGENTS.md`](agent-entry.md) | entry point, vendor-neutral | what must take effect on a direct tool call |
| `~/.claude/CLAUDE.md` | **every session** of Claude Code, before any skill | only a pointer to `AGENTS.md` + the minimum that must act without a second read |
| skill (`~/.agents/skills/…`) | when the skill is invoked | what belongs to a specific pipeline stage |
| `<repo>/AGENTS.md` | every session in that repo | repo-specific material |

🔴 **A rule without a channel is equivalent to a missing rule.** Verified with `agent-stream-to-file`: it
existed, was detailed, and was not applied because its only channel was skills — while agents
were launched directly.
