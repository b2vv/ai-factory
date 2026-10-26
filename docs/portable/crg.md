> Optional retained portable profile; the full canonical plan is in `ai-factory/`. This profile does not replace original skill contracts or authorize automatic activation.

# Optional CRG freshness and recovery

CRG is not required by this kit. No server, graph, registration or binary is bundled. The behavior notes below originated from local CRG 2.3.6 fixtures; they are version-specific limitations, not new-machine PASS. Verify the installed tool schema before querying. Graph queries may write derived database metadata; use an authorized location.

<a id="freshness-перед-довірою"></a>
## Freshness before trust

1. Record absolute root, branch, HEAD, scope diff and relevant untracked files. Pass `repo_root` explicitly to every repo-scoped tool. For dirty scope, use verified `base="HEAD"`; for a PR, use its actual base, not an arbitrary `HEAD~1`.
2. Check graph metadata (`git_branch`, `git_head_sha`, `last_updated`, `postprocess_level`) and current scope-file hashes. Matching HEAD/date alone is insufficient: the graph may contain stale/deleted files and omit others.
3. Check coverage: whether required files/symbols exist; separately assess untracked, generated, ignored, unsupported languages and dynamic/framework entrypoints. File counts are only a signal, not a percentage of semantic correctness.
4. Confirm at least one relevant import/caller and its file:line on disk. A graph edge/impact/flow is a candidate; an empty result on an incomplete graph means BLOCKED for the conclusion, not “safe code.”

Fixture 2.3.6 showed: before update, an old caller returns without a freshness warning; incremental update omits a new untracked rename target; even a full build in a Git repo omits untracked files. After staging **only in the synthetic fixture**, update found the new function and its impact. Do not stage user files for indexing. For untracked scope, use direct reading/tests or a separately agreed refresh that explicitly includes those files.

<a id="відновлення-без-зміни-source"></a>
## Recovery without source changes

Keep a consistent SQLite backup before updating; for WAL, use the SQLite backup API/a coordinated checkpoint, not a copy of just `graph.db` during writes. Do not use `immutable=1` with a live WAL/journal; read-only inventory without WAL needs a file-stability check during reading.

The inspected `build_or_update_graph_tool` 2.3.6 implementation performs local parsing, SQLite, FTS/flows/communities, not embeddings/API. `full_rebuild=true, postprocess="full", recurse_submodules=false` is appropriate only after authorization, backup and checking the candidate source list. Do not read .env/credentials; do not run install/init/watch/wiki/embed. Do not change `.gitignore`, git index, security controls or registry as an incidental “repair.”

After refresh, repeat root/revision/hash/coverage and relevant query proofs; retain counts/errors/limitations. One targeted recovery and one recheck; another failure → BLOCKED + file-based fallback. If another session actively changes the working tree, do not call the check a stable snapshot.
