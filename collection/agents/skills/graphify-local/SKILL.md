---
name: graphify-local
description: Use Graphify for a requested local code-graph build or query, or as an explicitly selected complement to CRG. Keeps source scope and graph provenance explicit. Not a general replacement for repository research, tests, TypeScript checking, or review.
---

# Graphify local code workflow

Use the installed `graphify` CLI without cloud, LLM/semantic extraction, account setup, hooks, MCP registration or permission changes. This is a bounded adapter, not the upstream broad graph-first workflow. Repository contracts and the user's task remain authoritative; preserve the project's stack and existing CRG/ttsc workflow.

## Select source and evidence

Identify the exact repository root, branch/HEAD, relevant dirty and untracked files, question, allowed source corpus and output directory. Include relevant untracked source when authorized; a clean HEAD alone does not prove graph freshness. Inspect file types and symlinks before copying/indexing. Keep credentials, real `.env`, secrets, transcripts and unrelated documents out of the corpus. Do not execute application code while indexing.

Prefer an isolated source snapshot and a task-specific output outside the repository. Record the scoped file list and SHA256 hashes, tool version, command/options, exclusions, timestamps, exit codes and graph artifact hashes in that output. External dependency/type inputs matter when comparing to ttsc; record their versions or hashes separately. Reading dependency files is not permission to install packages.

For an existing graph, match its manifest to current root, source hashes, dirty/untracked scope and extraction options. Missing, stale or mismatched evidence means UNKNOWN/STALE: use source files/rg or build a fresh authorized isolated graph. Never assume a graph is current because its directory exists or its mtime is recent. Ask only for missing authorization or a consequential scope decision; continue independent permitted research.

## Verified CLI route

The baseline is `graphifyy 0.9.92`; `graphify` is the executable. Check the installed version with auto-refresh disabled. If missing, report the dependency; do not install or upgrade automatically. For another version, inspect local help/source before relying on these flags.

```sh
GRAPHIFY_NO_AUTO_REFRESH=1 graphify --version
```

Set `source_root` to the approved snapshot and `output_root` to a NEW task output directory with no existing graph. Quote both paths. The following mode was exercised locally without semantic extraction:

```sh
GRAPHIFY_NO_AUTO_REFRESH=1 graphify extract "$source_root" \
  --code-only --no-cluster --no-dedup --max-workers 4 \
  --out "$output_root" --timing
```

Output is `$output_root/graphify-out/graph.json`. Preserve logs and manifest alongside it. `--code-only` can still emit locally INFERRED edges; it does not mean all edges are compiler-resolved. It may classify JSON as code and skip symbol-less source, so record actual coverage. Do not pass `--backend`, semantic/deep/label modes, URLs, database DSNs or global merge flags. Do not use add/clone/watch/install/provider/push or remote exports as part of this skill. A requested different operation requires a separately appropriate workflow.

Use the exact graph path for local questions:

```sh
GRAPHIFY_NO_AUTO_REFRESH=1 graphify query "$question" \
  --seed "$symbol" --context call --budget 1200 --graph "$graph_path"
```

For broader relationships omit `--context call` deliberately. Query is bounded BFS context, not an exact exhaustive callers API; it can return callees and neighbors, and its token budget is approximate. Query may write feedback/log metadata near its graph: keep that location within the authorized task output. Path/explain can supplement navigation after checking their local help; no server or MCP is needed.

## Fresh build versus incremental

In the measured 0.9.92 `--code-only --no-cluster --no-dedup` mode, an unchanged incremental extract removed two external dynamic-import nodes/edges. Prefer a fresh graph in a NEW output directory; do not overwrite active graphs or use `--force` on an old mixed semantic graph as a presumed clean rebuild. This is a version/mode-specific observed limitation, not proof every incremental operation fails.

If incremental behavior itself is requested, use disposable graph/source copies. Compare unchanged node/edge sets, changed/deleted symbols and representative source edges before trusting the result. Restore source bytes with guards and retain the original graph/evidence. Exit 0 alone is insufficient. Never refresh an active CRG/ttsc graph as a side effect of a Graphify query.

## Combine evidence, not databases

Use CRG for caller/test context when available; use Graphify for complementary alias/barrel/navigation evidence when useful. Do not require both tools for every task. Compare only matching source snapshots and relevant scope; retain tool name, edge kind, confidence, source file/line and query limits for each claim. Keep raw graphs separate. Deduplicate presentation without erasing provenance or disagreement.

Verify consequential edges in source and, for TypeScript, use available ttsc evidence where appropriate. Both Graphify and CRG have misresolved receiver calls to same-named functions, including false self-calls marked EXTRACTED. Agreement is not independent proof. Distinguish imports, references, direct calls, callback registration and runtime execution. A file-level caller count is not a callsite count.

ttsc can help with exact aliases/types/method targets, but its agent-facing trace may omit module/file endpoints present in the raw dump. A tool's “complete” or “answer” status certifies neither source completeness nor product correctness. Do not manufacture missing edges or promote INFERRED to verified.

## Deliver

Answer the actual question with source-backed conclusions, graph provenance and concrete limitations. Report hit/miss/extra results only against a defined ground-truth scope; avoid universal accuracy or token-saving claims. Keep build/test/browser QA and independent review separate from graph analysis. No commit, deploy, model invocation, configuration change or broader rollout follows from using this skill.
