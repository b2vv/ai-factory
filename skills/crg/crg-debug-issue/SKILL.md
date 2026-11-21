---
name: crg-debug-issue
description: "Locate a defect through the local code-review graph (CRG): callers/callees and impact, with a freshness check and findings confirmed in current files. Use when debugging in a repository with an indexed CRG."
---

## Runtime contract

Before the first CRG call, read and apply the [CRG skill runtime contract](../../../ai-factory/crg.md#skill-runtime-contract): exact host tool names, a recorded root/HEAD/dirty state, graph freshness and coverage for the task scope, the query budget and the read-only limits. Missing or stale coverage means BLOCKED for graph-based conclusions; use direct file search, language tooling and tests instead. Empty callers or impact does not prove dead code or safety.

## Debug issue

1. Locate a symbol with direct search (`rg`) or an already authorized `semantic_search_nodes_tool(query="...", limit=5, repo_root="/absolute/repo", detail_level="minimal")`.
2. Trace `query_graph_tool(pattern="callers_of", target="<qualified-name>", repo_root="/absolute/repo", detail_level="minimal")` and `pattern="callees_of"` as needed. Prefer qualified targets when names collide.
3. Inspect `get_flow_tool(flow_name="...", include_source=false, repo_root="/absolute/repo")`; it has NO `detail_level`. These are inferred structural paths, not observed runtime traces.
4. Use `detect_changes_tool(base="<verified-ref>", changed_files=["relative/path"], include_source=false, repo_root="/absolute/repo", detail_level="minimal")` and `get_impact_radius_tool(changed_files=["relative/path"], repo_root="/absolute/repo", detail_level="minimal")` only if they help test a concrete hypothesis.

Return the hypothesis, current file:line evidence, a deterministic reproduction/check, and what remains unverified. A recent change or graph score alone is not a root cause.
