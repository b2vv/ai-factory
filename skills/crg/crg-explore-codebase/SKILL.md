---
name: crg-explore-codebase
description: "Navigate the local code-review graph (CRG): architecture, imports/calls and modules. Use to understand unfamiliar code in a repository with an indexed CRG; it guides reading and does not replace file verification."
---

## Runtime contract

Before the first CRG call, read and apply the [CRG skill runtime contract](../../../ai-factory/crg.md#skill-runtime-contract): exact host tool names, a recorded root/HEAD/dirty state, graph freshness and coverage for the task scope, the query budget and the read-only limits. Missing or stale coverage means BLOCKED for graph-based conclusions; use direct file search, language tooling and tests instead. Empty callers or impact does not prove dead code or safety.

## Explore codebase

1. Use `list_graph_stats_tool(repo_root="/absolute/repo")` when coverage is unclear; it has NO `detail_level` and does not prove freshness.
2. `get_architecture_overview_tool(repo_root="/absolute/repo", detail_level="minimal")` and `list_communities_tool(repo_root="/absolute/repo", detail_level="minimal")` provide candidate module boundaries.
3. Drill into one relevant community with `get_community_tool(community_name="...", include_members=false, repo_root="/absolute/repo")`; it has NO `detail_level`.
4. Trace concrete files/symbols with `query_graph_tool(pattern="imports_of", target="relative/file.ts", repo_root="/absolute/repo", detail_level="minimal")`, or patterns `callers_of`, `callees_of`, `children_of`.
5. If execution structure matters, use `list_flows_tool(limit=5, repo_root="/absolute/repo", detail_level="minimal")` then `get_flow_tool(flow_name="...", include_source=false, repo_root="/absolute/repo")` (no `detail_level`).

Read the few relevant source files and local architecture rules before proposing changes. Communities are analysis output, not authoritative architecture. Use only the steps needed for the question, not the entire list every time.
