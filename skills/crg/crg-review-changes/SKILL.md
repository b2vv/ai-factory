---
name: crg-review-changes
description: "Structured change review through the local CRG: dependencies, affected flows and candidate test gaps; confirm findings against the code."
---

## Runtime contract

Use the exact tool names/arguments exposed by the current host. Verified against code-review-graph 2.3.6 via MCP tools/list on 2026-10-16 UTC; a host namespace prefix may differ. Do not call short names returned in `next_tool_suggestions` without matching them to tools/list.

Before trusting results, record the absolute `repo_root`, branch, HEAD and relevant dirty/untracked state. Check graph metadata and indexed-file hashes/coverage for the task scope; `last_updated`, matching HEAD or successful startup alone is insufficient. See [CRG checks and recovery](../../../ai-factory/crg.md). Missing/stale coverage means BLOCKED for graph-based conclusions; use direct file search, language tooling and tests instead. Empty callers/impact does not prove dead code or safety.

Start the task query with `get_minimal_context_tool(task="...", repo_root="/absolute/repo", base="<verified-ref>", changed_files=["relative/path"])`. It has NO `detail_level` argument. Use `base="HEAD"` for working-tree changes; use a verified task/PR base for committed changes. Avoid implicit server cwd and unverified `HEAD~1`.

Pass `detail_level="minimal"` only when the tool schema supports it. Prefer at most five targeted query calls and about 800 output tokens for a simple question; these are a soft budget, not a reason to omit evidence. After one corrected retry, use the file-based fallback rather than looping or silently treating failure as clean.

Keep this workflow read-only unless the user has authorized implementation. Build/update writes the derived graph and needs the task's authorization plus a consistent backup. Do not install packages, start watchers, generate embeddings/wiki, or change permissions as an implicit prerequisite. Semantic search can invoke an embedding provider; use it only after confirming the permitted provider/model and egress. Core graph queries need no LLM.

## Review changes

1. `detect_changes_tool(base="<verified-ref>", changed_files=["relative/path"], include_source=false, repo_root="/absolute/repo", detail_level="minimal")` narrows the change set. It does not refresh the graph or establish its freshness.
2. `get_affected_flows_tool(changed_files=["relative/path"], base="<verified-ref>", repo_root="/absolute/repo")` identifies candidate paths; it has NO `detail_level`.
3. For a risky symbol, use `query_graph_tool(pattern="tests_for", target="<qualified-name>", repo_root="/absolute/repo", detail_level="minimal")`; use `get_impact_radius_tool(changed_files=["relative/path"], repo_root="/absolute/repo", detail_level="minimal")` where needed.
4. Verify concrete findings against current files. Static test links are not executed test coverage. Report PROVEN/SUSPECTED, file:line, remaining checks and graph scope/limitations; give a verdict only within the repository's review contract.

The author's self-check does not satisfy an independent-review gate. A reviewer needs a fresh context, the contract and raw evidence; changing the tool or model alone is insufficient.

## Reference anti-patterns

This skill's domain anti-patterns are stated inline above (its independent-review and evidence rules). During plan/implement/review also consult the shared [reference anti-patterns](../../../ai-factory/reference-anti-patterns.md) for the 4-field template and the cross-cutting rules (accessibility REQUIREMENT-vs-preference split; no invented exceptions).
