---
title: "CRG: context verification and integration limits"
reviewed: 2026-10-16
---

[Entry](../docs/legacy/ai-factory-plan-entry.md) · [Workflow](workflow.md) · [Roles](models.md)

# Code Review Graph

`tirth8205/code-review-graph` 2.3.6 is installed locally through pipx; executable `~/.local/bin/code-review-graph`. [Upstream](https://github.com/tirth8205/code-review-graph). Four skills live in `~/.agents/skills/crg/*/SKILL.md`; the Claude mirror does not guarantee host discovery. CRG is structural context, not a compiler, runtime trace or independent reviewer.

## Verified transport and schema

2026-10-16 UTC: `code-review-graph serve --repo <absolute-root>` successfully completes initialize/tools/list over standard MCP stdio; returns 30 tools. After the owner reported an update, executable/package metadata and a new stdio subprocess were rechecked: the local version is still 2.3.6, with unchanged schema and fixture regressions. This task did not update the package. No `--auto-watch`, HTTP, embeddings, installations or new credentials. The host prefix may differ; use the actual tools/list, not short `next_tool_suggestions` from the server response.

Important 2.3.6 arguments:

| Tool | What to pass |
|---|---|
| `get_minimal_context_tool` | `task`, `repo_root`, `base`, `changed_files` when needed; **no** `detail_level` |
| `query_graph_tool` | `pattern`, `target`, `repo_root`, `detail_level` |
| `get_impact_radius_tool` | `changed_files`, `repo_root`, `base`, `max_depth`, `detail_level` |
| `detect_changes_tool` | `base`, `changed_files`, `repo_root`, `include_source=false`, `detail_level`; **does not update the graph** |
| `list_graph_stats_tool` | `repo_root`; **no** `detail_level` |
| `get_affected_flows_tool` | `changed_files`, `base`, `repo_root`; **no** `detail_level` |
| `get_flow_tool` | `flow_id` or `flow_name`, `include_source=false`, `repo_root`; **no** `detail_level` |
| `refactor_tool` | `mode`; for rename — `old_name`, `new_name`; `repo_root`; **no** `detail_level` |

A negative fixture test confirmed: an extra `detail_level` in minimal-context is rejected with a validation error. Do not mechanically add it to every tool.

## Freshness before trust

1. Record absolute root, branch, HEAD, scope diff and relevant untracked files. Pass `repo_root` explicitly to every repo-scoped tool. For dirty scope use the verified `base="HEAD"`; for a PR use its real base, not an arbitrary `HEAD~1`.
2. Compare graph metadata (`git_branch`, `git_head_sha`, `last_updated`, `postprocess_level`) and hashes of current scope files. Matching HEAD/date alone is insufficient: the graph may contain old/deleted files and omit others.
3. Check coverage: whether needed files/symbols exist; separately consider untracked, generated, ignored, unsupported languages and dynamic/framework entrypoints. File count is only a signal, not a semantic-correctness percentage.
4. Confirm at least one relevant import/caller and its file:line on disk. A graph edge/impact/flow is a candidate; an empty result on an incomplete graph means BLOCKED for the conclusion, not “safe code”.

Fixture 2.3.6 showed: before update an old caller is returned without a freshness warning; incremental update does not include a new untracked rename target; even a full build on a Git repository skips untracked files. After staging **only in the synthetic fixture**, update found the new function and its impact. Do not stage user files for indexing. For untracked scope, use direct reading/tests or a separately agreed refresh that explicitly includes those files.

## Recovery without changing source

Preserve a consistent SQLite backup before updating; for WAL use the SQLite backup API/a consistent checkpoint, not a copy of only `graph.db` during writes. Do not use `immutable=1` with a live WAL/journal; read-only inventory without WAL requires checking file stability during reading.

The inspected `build_or_update_graph_tool` 2.3.6 implementation performs local parsing, SQLite, FTS/flows/communities, not embeddings/API. `full_rebuild=true, postprocess="full", recurse_submodules=false` is appropriate only after authorization, backup and checking the source-candidate list. Do not read .env/credentials; do not run install/init/watch/wiki/embed. Do not change `.gitignore`, the git index, security controls or registry as an incidental “repair”.

After refresh, repeat root/revision/hash/coverage and relevant query proofs; retain counts/errors/limitations. One targeted recovery and one recheck; another failure → BLOCKED + file-based fallback. If another session is actively changing the working tree, do not call the check a stable snapshot.

## Host discovery: verification status

- 2026-10-16, after explicit owner permission: Codex user config has `crg-courses-read`, `crg-cassiopeia-read`, `crg-cargo-read`; the CLI parser shows enabled for all three. Cargo Claude local config has `crg-cargo-read`; `claude mcp get` confirmed Connected. Earlier Claude Courses/Cassiopeia registrations were unchanged.
- For each new entry, a fresh stdio subprocess using the actual config args returned **exactly 12** agreed tools; a direct call to the removed `build_or_update_graph_tool` was rejected as Unknown tool. Enforcement is server-side: `serve --tools` removes the rest from the FastMCP registry, rather than merely hiding their descriptions. Allowed: `get_minimal_context_tool`, `list_graph_stats_tool`, `query_graph_tool`, `get_impact_radius_tool`, `detect_changes_tool`, `get_affected_flows_tool`, `list_flows_tool`, `get_flow_tool`, `list_communities_tool`, `get_community_tool`, `get_architecture_overview_tool`, `find_large_functions_tool`.
- New entries do not start watch, build, embed or refactor/apply. `--repo` sets the default root, not filesystem isolation: `repo_root` can be overridden. Codex entries are user-level, available beyond the respective cwd; names record their purpose. Query tools may open/migrate the derived SQLite DB — this is not an OS read-only sandbox. Registration verification performed only initialize/list and a rejected call on an isolated fixture, without queries/rebuilds of active graphs.
- Current host sessions may need a new launch/reload of MCP discovery; a new model turn with these tools was not tested. Evidence: `crg-allowlist-preflight.json`, `crg-allowlist-postflight.json`, `crg-registration-applied.json` in the task working directory. Config backups with mode 0600: `mcp-config-backups/20261016T234627Z/`. Unrelated config values, credentials, model defaults and other permissions were preserved.

## Historical evidence limitations (2026-10-16)

The current concise status is maintained in [status.md](status.md#capabilities). During the work, other sessions changed the original HEAD/graphs, so active DBs were not replaced. Inventory at that time (not current state): Courses metadata had already been updated by external work to c2970173, but current HEAD was 8019b64d; the graph had only 166 files, with 124 hash mismatches. The Cargo graph was then 2026-08-22/beta versus stage; 556 mismatches and 17 deleted entries. Cassiopeia with matching HEAD had 281 mismatches and 93 deleted entries. Time/HEAD alone do not prove freshness.

After the approval blocker was lifted, valid backups of all three derived DBs without WAL were created: source/copy SHA-256 match, metadata size/mtime stable, SQLite quick_check=ok. The initial SQLite backup API attempt failed; its empty file is not a backup. Isolated source snapshots were created for rebuild, checking hashes/HEAD/status before/after copying, without copying .env/credentials or changing the user's git index. The Cargo snapshot includes 13 originally untracked source files. Snapshot graph roots intentionally differ; this is a recovery test, not a deployed active graph.

On snapshots: full structural builds yielded Courses 932, Cargo 1211, Cassiopeia 4888 parseable files; no parse errors/warnings. TS samples from Cargo (`appNavigate → getAppRouter`) and Cassiopeia (`AppBootstrapProvider → InitStatusMessage`) confirmed callers/imports/impact. Courses Go `CanConsume`: callers_of finds 6 callers and imports_of shows an access dependency, but impact returns 0 additional files despite these dependencies. This is a confirmed false negative of that specific impact query, not fixed by rebuild alone; Go impact needs direct search and language/test evidence. Do not generalize a TS-sample PASS to all TS/Go semantics.

Exact counts/revisions, backups and raw proofs: `~/Documents/Codex/2026-10-16/task/` (`crg-readonly-inventory.json`, `crg-stable-backups.json`, `crg-source-snapshots.json`, `snapshot-*-result.json`, `proof-*-result.json`, `crg-recheck-summary.json`, `crg-tools-schema.json`). An active graph requires a separate agreed window without a concurrent writer and a repeated freshness/query check; do not copy a snapshot DB over an active DB because root paths differ.

<a id="cargo-active-snapshot"></a>

## Cargo: completed active refresh — snapshot 2026-10-17

This record supersedes the previous stale status **for Cargo only**. Historical checkout `cargotrans-ui` (local root omitted), branch `stage`, HEAD `137e19df20b32f8a33f76c5a08090c2f8ef0c3bf`. The authorized refresh completed; the source snapshot and git index remained unchanged. Persisted graph: **1212 files, 6882 nodes, 65619 edges**; 1212 hash matches, **0 mismatch, 0 deleted, 0 foreign roots**, SQLite integrity OK; no parse errors/warnings. A consistent SQLite backup was saved before refresh.

Through the current unchanged `crg-cargo-read` registration in a fresh stdio MCP process: initialize/tools/list — 12 tools; **live stats and callers_of PASS**. `appNavigate → getAppRouter` was also confirmed by directly reading the file. This goes beyond a simple listing; however, this proof does not establish injected tools in every current Codex/Claude session. Do not rerun refresh because native list/load is absent in a new chat.

Evidence: [completed report](~/Documents/Codex/2026-10-16/task/crg-cargo-active-refresh/report.md), [snapshot state](~/Documents/Codex/2026-10-16/task/crg-cargo-active-refresh/final-state.json), [MCP queries](~/Documents/Codex/2026-10-16/task/crg-cargo-active-refresh/mcp-query-proof.json). These are local historical artifacts of this host, not dependencies for onboarding another repository.

Limits: the snapshot does not guarantee freshness after changes; tracked/parser coverage does not prove dynamic calls or complete semantics. No parseable untracked exclusions were found on this snapshot, but future untracked files require direct reading. This refresh did not change other graphs. CRG is optional for another repository: separately registration → tool listing → live query → root/HEAD/hashes/coverage; missing/stale → files/rg. Refresh only with separate authorization and an agreed window without a concurrent writer.
