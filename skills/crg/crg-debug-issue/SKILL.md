---
name: crg-debug-issue
description: "Locate a defect through CRG callers/callees and impact, checking freshness and confirming findings in the current files."
---

## Runtime contract

Use the exact tool names/arguments exposed by the current host. Verified against code-review-graph 2.3.6 via MCP tools/list on 2026-10-16 UTC; a host namespace prefix may differ. Do not call short names returned in `next_tool_suggestions` without matching them to tools/list.

Before trusting results, record the absolute `repo_root`, branch, HEAD and relevant dirty/untracked state. Check graph metadata and indexed-file hashes/coverage for the task scope; `last_updated`, matching HEAD or successful startup alone is insufficient. See [CRG checks and recovery](../../../ai-factory/crg.md). Missing/stale coverage means BLOCKED for graph-based conclusions; use direct file search, language tooling and tests instead. Empty callers/impact does not prove dead code or safety.

Start the task query with `get_minimal_context_tool(task="...", repo_root="/absolute/repo", base="<verified-ref>", changed_files=["relative/path"])`. It has NO `detail_level` argument. Use `base="HEAD"` for working-tree changes; use a verified task/PR base for committed changes. Avoid implicit server cwd and unverified `HEAD~1`.

Pass `detail_level="minimal"` only when the tool schema supports it. Prefer at most five targeted query calls and about 800 output tokens for a simple question; these are a soft budget, not a reason to omit evidence. After one corrected retry, use the file-based fallback rather than looping or silently treating failure as clean.

Keep this workflow read-only unless the user has authorized implementation. Build/update writes the derived graph and needs the task's authorization plus a consistent backup. Do not install packages, start watchers, generate embeddings/wiki, or change permissions as an implicit prerequisite. Semantic search can invoke an embedding provider; use it only after confirming the permitted provider/model and egress. Core graph queries need no LLM.

## Debug issue

1. Locate a symbol with direct search (`rg`) or an already authorized `semantic_search_nodes_tool(query="...", limit=5, repo_root="/absolute/repo", detail_level="minimal")`.
2. Trace `query_graph_tool(pattern="callers_of", target="<qualified-name>", repo_root="/absolute/repo", detail_level="minimal")` and `pattern="callees_of"` as needed. Prefer qualified targets when names collide.
3. Inspect `get_flow_tool(flow_name="...", include_source=false, repo_root="/absolute/repo")`; it has NO `detail_level`. These are inferred structural paths, not observed runtime traces.
4. Use `detect_changes_tool(base="<verified-ref>", changed_files=["relative/path"], include_source=false, repo_root="/absolute/repo", detail_level="minimal")` and `get_impact_radius_tool(changed_files=["relative/path"], repo_root="/absolute/repo", detail_level="minimal")` only if they help test a concrete hypothesis.

Return the hypothesis, current file:line evidence, a deterministic reproduction/check, and what remains unverified. A recent change or graph score alone is not a root cause.

## Reference anti-patterns

This skill's domain anti-patterns are stated inline above (its cause-not-symptom and evidence rules). During plan/implement/review also consult the shared [reference anti-patterns](../../../ai-factory/reference-anti-patterns.md) for the 4-field template and the cross-cutting rules (accessibility REQUIREMENT-vs-preference split; no invented exceptions).
