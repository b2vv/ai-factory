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

## Skill runtime contract

Shared by the four `crg-*` skills; each skill reads this section before its first CRG call.

Use the exact tool names/arguments exposed by the current host. Verified against code-review-graph 2.3.6 via MCP tools/list on 2026-10-16 UTC; a host namespace prefix may differ. Do not call short names returned in `next_tool_suggestions` without matching them to tools/list.

Before trusting results, record the absolute `repo_root`, branch, HEAD and relevant dirty/untracked state. Check graph metadata and indexed-file hashes/coverage for the task scope; `last_updated`, matching HEAD or successful startup alone is insufficient. See [Freshness before trust](#freshness-before-trust) and [Recovery without changing source](#recovery-without-changing-source). Missing/stale coverage means BLOCKED for graph-based conclusions; use direct file search, language tooling and tests instead. Empty callers/impact does not prove dead code or safety.

Start the task query with `get_minimal_context_tool(task="...", repo_root="/absolute/repo", base="<verified-ref>", changed_files=["relative/path"])`. It has NO `detail_level` argument. Use `base="HEAD"` for working-tree changes; use a verified task/PR base for committed changes. Avoid implicit server cwd and unverified `HEAD~1`.

Pass `detail_level="minimal"` only when the tool schema supports it. Prefer at most five targeted query calls and about 800 output tokens for a simple question; these are a soft budget, not a reason to omit evidence. After one corrected retry, use the file-based fallback rather than looping or silently treating failure as clean.

Keep this workflow read-only unless the user has authorized implementation. Build/update writes the derived graph and needs the task's authorization plus a consistent backup. Do not install packages, start watchers, generate embeddings/wiki, or change permissions as an implicit prerequisite. Semantic search can invoke an embedding provider; use it only after confirming the permitted provider/model and egress. Core graph queries need no LLM.

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

- Register read-only CRG servers only after explicit owner permission, one named entry per repository (for example `crg-<project>-read`), and confirm with the host's own CLI (parser shows enabled / `claude mcp get` shows Connected). Leave unrelated existing registrations unchanged.
- For each new entry, a fresh stdio subprocess using the actual config args returned **exactly 12** agreed tools; a direct call to the removed `build_or_update_graph_tool` was rejected as Unknown tool. Enforcement is server-side: `serve --tools` removes the rest from the FastMCP registry, rather than merely hiding their descriptions. Allowed: `get_minimal_context_tool`, `list_graph_stats_tool`, `query_graph_tool`, `get_impact_radius_tool`, `detect_changes_tool`, `get_affected_flows_tool`, `list_flows_tool`, `get_flow_tool`, `list_communities_tool`, `get_community_tool`, `get_architecture_overview_tool`, `find_large_functions_tool`.
- New entries do not start watch, build, embed or refactor/apply. `--repo` sets the default root, not filesystem isolation: `repo_root` can be overridden. Codex entries are user-level, available beyond the respective cwd; names record their purpose. Query tools may open/migrate the derived SQLite DB — this is not an OS read-only sandbox. Registration verification performed only initialize/list and a rejected call on an isolated fixture, without queries/rebuilds of active graphs.
- Current host sessions may need a new launch/reload of MCP discovery; a new model turn with these tools was not tested. Keep preflight/postflight evidence and mode-0600 config backups in the task working directory. Unrelated config values, credentials, model defaults and other permissions were preserved.

## Lessons from historical measurements (2026-10-16/17)

Per-project counts, revisions and local evidence paths from the original measurements were removed from this public version. The generic lessons remain:

- Other sessions may change HEAD/graphs during the work; do not replace an active DB while a concurrent writer exists. Metadata updated by external work, a low file count or many hash mismatches/deleted entries show a stale graph even when HEAD matches. Time/HEAD alone do not prove freshness.
- Back up derived DBs consistently before any rebuild: source/copy SHA-256 match, stable size/mtime, SQLite `quick_check=ok`. A failed backup API attempt that leaves an empty file is not a backup.
- Rebuild on isolated source snapshots, checking hashes/HEAD/status before/after copying, without copying .env/credentials or changing the user's git index. Include originally untracked source files deliberately. Snapshot graph roots differ from active roots; never copy a snapshot DB over an active DB.
- Confirm a few callers/imports/impact samples per language against the files. Impact queries can return confirmed false negatives (for example, Go impact returning 0 files while callers_of and imports_of show dependencies), which a rebuild alone does not fix; use direct search and language/test evidence. Do not generalize a TS-sample PASS to all TS/Go semantics.
- An authorized active refresh is complete only when the persisted graph has full hash coverage (0 mismatch, 0 deleted, 0 foreign roots), SQLite integrity OK and no parse errors, with a consistent backup saved before refresh. A live query (stats, callers_of) through the unchanged read-only registration in a fresh stdio process goes beyond a tool listing, but does not prove injected tools in every current session. Do not rerun a refresh only because native list/load is absent in a new chat.
- Local evidence artifacts of one host are not dependencies for onboarding another repository.

Limits: a snapshot does not guarantee freshness after changes; tracked/parser coverage does not prove dynamic calls or complete semantics. Future untracked files require direct reading. A refresh of one graph does not change other graphs. CRG is optional for another repository: separately registration → tool listing → live query → root/HEAD/hashes/coverage; missing/stale → files/rg. Refresh only with separate authorization and an agreed window without a concurrent writer.
