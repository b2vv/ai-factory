---
name: crg-refactor-safely
description: "Plan refactoring through the local CRG: impact, rename preview and dead-code candidates; changes only within the authorized scope."
---

## Runtime contract

Use the exact tool names/arguments exposed by the current host. Verified against code-review-graph 2.3.6 via MCP tools/list on 2026-10-16 UTC; a host namespace prefix may differ. Do not call short names returned in `next_tool_suggestions` without matching them to tools/list.

Before trusting results, record the absolute `repo_root`, branch, HEAD and relevant dirty/untracked state. Check graph metadata and indexed-file hashes/coverage for the task scope; `last_updated`, matching HEAD or successful startup alone is insufficient. See [CRG checks and recovery](../../../ai-factory/crg.md). Missing/stale coverage means BLOCKED for graph-based conclusions; use direct file search, language tooling and tests instead. Empty callers/impact does not prove dead code or safety.

Start the task query with `get_minimal_context_tool(task="...", repo_root="/absolute/repo", base="<verified-ref>", changed_files=["relative/path"])`. It has NO `detail_level` argument. Use `base="HEAD"` for working-tree changes; use a verified task/PR base for committed changes. Avoid implicit server cwd and unverified `HEAD~1`.

Pass `detail_level="minimal"` only when the tool schema supports it. Prefer at most five targeted query calls and about 800 output tokens for a simple question; these are a soft budget, not a reason to omit evidence. After one corrected retry, use the file-based fallback rather than looping or silently treating failure as clean.

Keep this workflow read-only unless the user has authorized implementation. Build/update writes the derived graph and needs the task's authorization plus a consistent backup. Do not install packages, start watchers, generate embeddings/wiki, or change permissions as an implicit prerequisite. Semantic search can invoke an embedding provider; use it only after confirming the permitted provider/model and egress. Core graph queries need no LLM.

## Refactor safely

1. Check `get_impact_radius_tool(changed_files=["relative/path"], repo_root="/absolute/repo", detail_level="minimal")` and, where useful, `get_affected_flows_tool(changed_files=["relative/path"], repo_root="/absolute/repo")` (no `detail_level`).
2. For a rename, call `refactor_tool(mode="rename", old_name="...", new_name="...", repo_root="/absolute/repo")` and inspect the complete preview. Modes `suggest` and `dead_code` produce candidates only. `refactor_tool` has NO `detail_level`.
3. Confirm callers/imports and dead-code claims in current files and language tooling, including untracked code, dynamic entrypoints and framework conventions.
4. Apply changes only within the user's authorized implementation scope. `apply_refactor_tool(refactor_id="...", repo_root="/absolute/repo", dry_run=false)` writes source and is NOT a review/debug query; never invoke it during a read-only task. An authorized caller may use `dry_run=true` for a diff; inspect current schema first.
5. Run applicable deterministic checks, then refresh/revalidate the graph under the task's authorization. `detect_changes_tool` only analyzes differences; it does not update the index or prove a refactor correct.

Record acceptance, changed files, test results and remaining graph limitations in the existing task journal. A zero-impact result on incomplete coverage is BLOCKED, not PASS.
