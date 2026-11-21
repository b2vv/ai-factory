---
name: crg-refactor-safely
description: "Plan a refactor through the local code-review graph (CRG): impact, rename preview and dead-code candidates, changing only the authorized scope. Use before a rename, move or removal in a repository with an indexed CRG."
---

## Runtime contract

Before the first CRG call, read and apply the [CRG skill runtime contract](../../../ai-factory/crg.md#skill-runtime-contract): exact host tool names, a recorded root/HEAD/dirty state, graph freshness and coverage for the task scope, the query budget and the read-only limits. Missing or stale coverage means BLOCKED for graph-based conclusions; use direct file search, language tooling and tests instead. Empty callers or impact does not prove dead code or safety.

## Refactor safely

1. Check `get_impact_radius_tool(changed_files=["relative/path"], repo_root="/absolute/repo", detail_level="minimal")` and, where useful, `get_affected_flows_tool(changed_files=["relative/path"], repo_root="/absolute/repo")` (no `detail_level`).
2. For a rename, call `refactor_tool(mode="rename", old_name="...", new_name="...", repo_root="/absolute/repo")` and inspect the complete preview. Modes `suggest` and `dead_code` produce candidates only. `refactor_tool` has NO `detail_level`.
3. Confirm callers/imports and dead-code claims in current files and language tooling, including untracked code, dynamic entrypoints and framework conventions.
4. Apply changes only within the user's authorized implementation scope. `apply_refactor_tool(refactor_id="...", repo_root="/absolute/repo", dry_run=false)` writes source and is NOT a review/debug query; never invoke it during a read-only task. An authorized caller may use `dry_run=true` for a diff; inspect current schema first.
5. Run applicable deterministic checks, then refresh/revalidate the graph under the task's authorization. `detect_changes_tool` only analyzes differences; it does not update the index or prove a refactor correct.

Record acceptance, changed files, test results and remaining graph limitations in the existing task journal. A zero-impact result on incomplete coverage is BLOCKED, not PASS.
