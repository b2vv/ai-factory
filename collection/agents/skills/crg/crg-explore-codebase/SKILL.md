---
name: crg-explore-codebase
description: "Навігація локальним CRG: архітектура, imports/calls і модулі; для розуміння коду, не заміни перевірки файлів."
---

## Runtime contract

Use the exact tool names/arguments exposed by the current host. Verified against code-review-graph 2.3.6 via MCP tools/list on 2026-10-16 UTC; a host namespace prefix may differ. Do not call short names returned in `next_tool_suggestions` without matching them to tools/list.

Before trusting results, record the absolute `repo_root`, branch, HEAD and relevant dirty/untracked state. Check graph metadata and indexed-file hashes/coverage for the task scope; `last_updated`, matching HEAD or successful startup alone is insufficient. See [CRG checks and recovery](../../../ai-factory/crg.md). Missing/stale coverage means BLOCKED for graph-based conclusions; use direct file search, language tooling and tests instead. Empty callers/impact does not prove dead code or safety.

Start the task query with `get_minimal_context_tool(task="...", repo_root="/absolute/repo", base="<verified-ref>", changed_files=["relative/path"])`. It has NO `detail_level` argument. Use `base="HEAD"` for working-tree changes; use a verified task/PR base for committed changes. Avoid implicit server cwd and unverified `HEAD~1`.

Pass `detail_level="minimal"` only when the tool schema supports it. Prefer at most five targeted query calls and about 800 output tokens for a simple question; these are a soft budget, not a reason to omit evidence. After one corrected retry, use the file-based fallback rather than looping or silently treating failure as clean.

Keep this workflow read-only unless the user has authorized implementation. Build/update writes the derived graph and needs the task's authorization plus a consistent backup. Do not install packages, start watchers, generate embeddings/wiki, or change permissions as an implicit prerequisite. Semantic search can invoke an embedding provider; use it only after confirming the permitted provider/model and egress. Core graph queries need no LLM.

## Explore codebase

1. Use `list_graph_stats_tool(repo_root="/absolute/repo")` when coverage is unclear; it has NO `detail_level` and does not prove freshness.
2. `get_architecture_overview_tool(repo_root="/absolute/repo", detail_level="minimal")` and `list_communities_tool(repo_root="/absolute/repo", detail_level="minimal")` provide candidate module boundaries.
3. Drill into one relevant community with `get_community_tool(community_name="...", include_members=false, repo_root="/absolute/repo")`; it has NO `detail_level`.
4. Trace concrete files/symbols with `query_graph_tool(pattern="imports_of", target="relative/file.ts", repo_root="/absolute/repo", detail_level="minimal")`, or patterns `callers_of`, `callees_of`, `children_of`.
5. If execution structure matters, use `list_flows_tool(limit=5, repo_root="/absolute/repo", detail_level="minimal")` then `get_flow_tool(flow_name="...", include_source=false, repo_root="/absolute/repo")` (no `detail_level`).

Read the few relevant source files and local architecture rules before proposing changes. Communities are analysis output, not authoritative architecture. Use only the steps needed for the question, not the entire list every time.
