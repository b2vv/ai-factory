# Documentation hygiene during onboarding and alignment

Use this checklist inside the existing inventory, adapter and acceptance record. It adds no tracker, mandatory product gate or automatic repository rewrite. Local architecture, contracts, human QA and commit authority remain unchanged.

## Compare before editing

| Surface | Evidence to inspect | Smallest justified correction |
|---|---|---|
| AGENTS / CLAUDE entrypoints | Logical entry path, physical symlink target, shared adapter and checkpoint routes | Repair missing pointers; resolve links from the entry actually used by the host. File access is not native invocation. |
| Standards / README | Current scripts and accepted contracts, dated scope and limitations | Correct descriptive drift. Code describes implementation; it does not cancel acceptance or ADR. |
| Commands and Git hooks | Scripts, pre/post hooks and transitive effects; actual CI event and branch filters | State writes, generation, reset, seed, network and graph refresh effects. A docs-only change may still invoke mutating commit hooks. Do not disable them implicitly. |
| CI / browser evidence | Exact revision, executed job/check, skip behavior, rendering and interaction evidence | Separate configuration, successful command exit and actual coverage. A successful skip is not test PASS. |
| Task index / ledger / handoff | Existing task states, archive pointers, exact active record and revision | Correct stale summaries and broken links; preserve historical rows and append-only meaning. Never choose the latest note/wave by mtime. |
| ADR currency | Decision date, scoped historical claim and accepted later decision | Add a factual dated note only when supported. Preserve the decision body; unresolved policy conflicts need their owner. No ADR for every documentation edit. |
| Pre-code readiness | Existing grilling, impact, dependencies and independent critique/review | Link to the existing checkpoint. Do not introduce a second plan or relax local Small/Full requirements. |

Remote names are local aliases, not stable host identities. Verify the actual host without exposing credentials; mark historical alias descriptions as historical. A current directory listing is not proof of QA completion or deployment. Avoid permanently hardcoding transient queue contents in an entrypoint.

## Ownership and scope before a commit

For every candidate change distinguish **provenance** from **authorization**. Receipts, verified backups and exact before/after hunks can establish authorship; they do not expand the current commit scope. Compare the reviewed delta with current HEAD/index/worktree, preserve foreign hunks even in the same file, and report ambiguous changes. Never stage private local instructions or credentials as workflow documentation.

Read the exact local rule for each consequential action. Independent review PENDING does not by itself prove a universal local-commit prohibition: a repository may gate commit, merge, acceptance or release differently. Quote the applicable rule; do not invent a waiver or weaken a real gate. Record pre/post hook effects separately from intentionally requested checks. Publication of a shared candidate does not grant product commit/push permissions or independent acceptance.

## Verification and regression scenarios

Use scoped diff checks, file-link resolution (including logical symlink entrypoints), pin/manifest hashes and before/after foreign-work guards. Run relevant existing helper fixtures when shared packaging or helpers change. Do not launch product checks just to inspect their configuration. Capture a fresh review package after HEAD or relevant bytes change; old evidence remains dated and scoped.

For independent forward review, provide raw sources for these situations and ask the reviewer to explain the applicable rule and next safe action:

1. README says every push runs CI, while workflow filters name only selected branches.
2. Documentation-only verification is lightweight, but the normal commit hooks generate files or update a local graph.
3. Logical CLAUDE entry is a symlink and uses root-relative links; physical-path-only validation reports a false missing link.
4. A QA index claims an empty directory, while task records remain; an older ADR describes a previous implementation stage.
5. A fully proven old onboarding hunk is outside the current narrow commit authorization.
6. Review is pending and the local rule gates either commit or only acceptance/merge; the evaluator must distinguish the two without changing policy.

Record source, finding, proposed correction, retained differences, author checks, independent verdict and limitations in the existing acceptance record. Synthetic/static results do not prove host discovery, live hooks, MCP or browser behavior.
