---
name: crg-review-changes
description: "Structured change review through the local code-review graph (CRG): dependencies, affected flows and candidate test gaps, confirmed against the code. Use when reviewing a diff in a repository with an indexed CRG."
---

## Runtime contract

Before the first CRG call, read and apply the [CRG skill runtime contract](../../../ai-factory/crg.md#skill-runtime-contract): exact host tool names, a recorded root/HEAD/dirty state, graph freshness and coverage for the task scope, the query budget and the read-only limits. Missing or stale coverage means BLOCKED for graph-based conclusions; use direct file search, language tooling and tests instead. Empty callers or impact does not prove dead code or safety.

## Review changes

1. `detect_changes_tool(base="<verified-ref>", changed_files=["relative/path"], include_source=false, repo_root="/absolute/repo", detail_level="minimal")` narrows the change set. It does not refresh the graph or establish its freshness.
2. `get_affected_flows_tool(changed_files=["relative/path"], base="<verified-ref>", repo_root="/absolute/repo")` identifies candidate paths; it has NO `detail_level`.
3. For a risky symbol, use `query_graph_tool(pattern="tests_for", target="<qualified-name>", repo_root="/absolute/repo", detail_level="minimal")`; use `get_impact_radius_tool(changed_files=["relative/path"], repo_root="/absolute/repo", detail_level="minimal")` where needed.
4. Verify concrete findings against current files. Static test links are not executed test coverage. Report PROVEN/SUSPECTED, file:line, remaining checks and graph scope/limitations; give a verdict only within the repository's review contract.

The author's self-check does not satisfy an independent-review gate. A reviewer needs a fresh context, the contract and raw evidence; changing the tool or model alone is insufficient.
