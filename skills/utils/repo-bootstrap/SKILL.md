---
name: repo-bootstrap
description: Checks what a repository lacks for the pipeline — standards manifest, briefing, contract pointers, persistence channel, artifacts home, machine gates — and creates missing items on command without inventing content. Use for a new or unfamiliar repository, when connecting a project to the pipeline, or on triggers "initialize the repository", "what is missing from the repository", "repo bootstrap", "set up the project".
---


# repo-bootstrap — inventory of what a repository needs

The global pipeline skills (`code-review`, `spec-flow`, `cto-research`, `cto-agenda`) expect
a set of files at predictable paths. This skill checks which exist and, on command,
creates missing ones.

**Inventory** is the key word: a fixed list whose rows have states `present` / `absent` /
`present, but drifted`. Not “set up the project properly”, but inspect the list and report each row.

For portable onboarding of an existing/partial repository, use the [onboarding checklist](../../../ai-factory/onboarding.md) and its read-only helper. This refines the inventory below; it adds no orchestrator. Table paths are search candidates, not a requirement to migrate the existing structure: the manifest records actual instructions/workflow/standards/artifacts and shared skill root. `detected` does not mean `configured` or `behavior-tested`; file existence does not verify runtime behavior.


## Main rule: do not invent content

The skill **collects** content from what already exists — discovered documents, `package.json` scripts,
CI workflows, remotes. Where the repository has nothing, write `⚠️ absent` with exactly what
is missing, not a plausible standard.

An invented line is worse than an empty one: emptiness is visible; invention looks closed. This is how
dg was found to have no linting at all and no criteria for its Rust portion — both
facts survived only because there was nothing to replace them with.

Questions for a **person** (which documents count as standards, pipeline threshold, branch and
PR target) must not be guessed: either ask or leave `TODO: <the exact question>`. A placeholder naming
an unresolved issue works better than confident invention.


## Two modes

- **Check** (default) — inspect the inventory and show the table; **do not modify the target repository**. When requested, save manifest/evidence in the task workspace.
- **Initialization** — create missing items. Activated only when the user explicitly requests it.

In both modes, an existing file is **not replaced by a template or overwritten automatically**. If the file exists but has drifted from the repository (the manifest
names a command no longer in `package.json`), the state is `present, but drifted`: show the discrepancy,
propose the edit. A separately authorized adaptation phase may apply a targeted patch with backups/hashguards; this is not check-only bootstrap, and its changes are reported separately. An existing instruction authorizing that adaptation does not require repeated approval.

The skill is **idempotent**: a second run on the same repository creates nothing new.


## Inventory

| # | Artifact | How to check | Content source |
|---|---|---|---|
| 1 | `.claude/standards.md` — criteria | file exists; all nine headings present | discovered documents, scripts, CI; format: `~/.agents/rules/repo-standards-manifest.md` |
| 2 | Briefing (`work/CTO-RESEARCH.md` / `CONTEXT.md`) | file exists; **header with date and commit** | delegate `cto-research` |
| 3 | Contract file (`AGENT.md` / `AGENTS.md` / `CLAUDE.md`) | contains pointers to 1, 2 and orchestration rules | a pointer line, not a copy of content |
| 4 | `CLAUDE.local.md` — persistence channel | file exists; **in `.gitignore`** | live-note channel + fallback to artifacts home |
| 5 | Artifacts home (`reports/` or `work/reports/`) | directory exists or convention is named in manifest | — |
| 5a | `work/` — tasks, debt, archive | directories exist; manifest names them **individually** and says where closed work moves | layout by **state**, not topic; archive holds pointers |
| 6 | Machine gates | which scripts actually exist: lint, typecheck, test, e2e, formatter | manifest section; **record missing ones as gaps** |
| 7 | Task tracker and triage labels | `docs/agents/issue-tracker.md` | delegate `setup-matt-pocock-skills` — do not duplicate |
| 8 | CRG code graph (optional) | existing configuration paths; separately registration/availability, root/revision/hash/coverage | inventory only; stale/unavailable → file-based fallback. No install/build/registration in this onboarding |
| 9 | Obsidian vault (optional) | vault exists, MCP port unique | runbook `~/.agents/obsidian-cheatsheet.md` |
| 10 | `work/AGENDA.md` — move queue | file exists | delegate `cto-agenda`; skip for an empty repository |

Rows 8–10 are optional: their absence is a choice, not a gap. Say so instead of marking them
red.

Row 5a has its own trap: a directory named `archive/` may already exist at the repository root and mean
**something completely different** — removed legacy code, not closed tasks (as in dg). Same name, different things:
check what it contains before recording it as the task archive. The row identifier is `5a`.


## Sequence

1. **Reconnaissance** — read what already exists: root/HEAD/status read-only, contract files, `docs/`, `work/`,
   `package.json` scripts (and `Cargo.toml` / `pyproject.toml` for multilingual repositories), `.github/workflows/`.
   Assume nothing: languages and gates come from disk. Do not print credential-bearing remote URLs, real environment values or configuration secrets. Inspect scripts/prehooks/Make prerequisites statically for side effects; do not run command probes/install/reset/MCP for inventory. Tracking/persistence can be repo-first without an external service. An existing normative contract does not automatically lose to code; record the conflict and owner decision separately.
2. **Language** — determine which repository parts use which languages, and **what paths each set of criteria applies to**.
   In a multilingual repository, criteria without path scope apply to everything — and a TS standard
   starts judging Rust.
3. **Table** — show the inventory with each row's state. This is the output of check mode.
4. **Creation** (initialization mode only) — one artifact at a time, from the first row down:
   manifest first because the others refer to it.
5. **Pointers last** — update the contract file once targets exist.


## Completion

The skill is complete when **all** of the following hold:

- [ ] All eleven inventory rows have a state; optional items are called optional, not “absent”.
- [ ] Name repository languages and the paths each set of criteria applies to.
- [ ] In check-only mode the target repository is unchanged; initialization replaced no existing file with a template. Separately approved adaptation patches and discrepancies are explicitly listed.
- [ ] Created content contains no invented standards: every line comes from disk, is `⚠️ absent`,
      or is a `TODO:` question for a person. Count these labels.
- [ ] In initialization mode, the contract file points to the manifest and briefing.

## Reference anti-patterns

This skill's domain anti-patterns are stated inline above (its gate and manifest checks). During plan/implement/review also consult the shared [reference anti-patterns](../../../ai-factory/reference-anti-patterns.md) for the 4-field template and the cross-cutting rules (accessibility REQUIREMENT-vs-preference split; no invented exceptions).
