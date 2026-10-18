# Read-only preflight

Requires an already available Python 3.9+ and its standard library. No install step.
The helper inventories declared paths and command metadata; it does not configure a repository.

Prepare a non-secret manifest from `manifest.example.json` in the task workspace, without
writing to the target repository. Replace the example paths with its existing instructions,
workflow and dependency files. A manifest is explicit input, not an overwrite or bootstrap
instruction. A repository-owned manifest may be added later as part of an approved adapter.

```sh
python3 /path/to/preflight.py --root /path/to/repository --manifest /path/to/task-workspace/manifest.json --shared-skill-root /path/to/shared/skills
```

Omit `--shared-skill-root` if unavailable: shared skills will be BLOCKED. It must be an explicitly
trusted root. `--manifest` accepts either one explicit absolute external file or a path relative
to the repository root. An external manifest grants read access only to itself; paths listed
inside it remain relative to the repository root (or the explicitly selected shared skill root).
The external manifest path must contain no symlink component or sensitive filename; use its
canonical physical path if your OS temp directory is an alias. Repository paths must be relative.
Absolute inventory paths, traversal, symlinks (including
internal aliases), `.env*`, credential/secret/token files and `.aws`, `.ssh`, `.git` contents
are rejected. Resolve a legitimate alias by configuring its real path within the selected root;
do not weaken the guard. The helper reads only the manifest and allowed `package.json`/Makefile
command files and explicitly declared review SKILL.md files and existing adapter destinations for SHA256 comparison (up to 1 MiB each); other paths are checked for existence only. MCP config contents
are never read. Do not run on a tree being modified concurrently: path checks are not an OS sandbox.

Output is JSON on stdout. Redirection is an explicit caller choice, preferably to the task
workspace. No repository files are written, commands executed, network accessed, tools installed,
or settings/permissions/registrations changed. No raw scripts or config values are printed.

## Interpret results

- `detected`: file or directory exists at an allowed path. This is inventory only.
- `configured`: always false in this helper; mark separately only after reviewing an additive adapter.
- `behavior_tested`: always false; real Codex/Claude discovery, hooks, model roles and MCP behavior require separate permitted verification.
- `DETECTED`: existence verified; `UNKNOWN`: runtime or command effects unresolved; `BLOCKED`: missing required path, unsafe input, declared conflict, stale/unavailable integration.
- `N/A` applicability requires absence of the declared impact. Scope flags are human input, not semantic analysis of a diff. UI copy and test-helper changes trigger assessment, not automatic exemption.

All listed skills are treated as required inventory entries. Omit inapplicable optional skills
and record their N/A reason in the task/adaptation record. Integration declarations are observations
supplied by the operator; even `available` + `fresh` is not upgraded to runtime proof by this helper.
Conflicts are explicitly declared as `{"id":"acceptance-v-code"}`; the tool cannot discover semantic
contradictions automatically. Resolve them against acceptance/contracts/ADRs; implementation is evidence
of current behavior, not authority to legalize a bug.

`package.json` command names receive heuristic side-effect indicators. Makefile targets receive
file-wide indicators, intentionally conservative because prerequisites, includes and variables can
hide effects. Unsupported command formats need manual inspection. Empty indicators never certify
safety. Inspect transitive commands manually before execution. Gate reductions remain unresolved
until the governing repo contract permits them; RED/GREEN does not count as mutation testing.

Small tasks use one main task record and separate review/evidence only when required. Completed
handoffs route to evidence verification rather than repeated work. This policy output advises the
operator; it cannot prove that a model followed the route.

## Isolated verification

```sh
cd /path/to/helper
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_preflight.py
```

Fixtures are generated in temporary directories: clean repo, existing partial rules, missing shared
skill, declared contract/code conflict, stale/unavailable CRG, small test helper, UI copy/layout and
completed handoff. Negative cases cover escape/symlink/secret paths, malformed input and false
runtime/safety claims. This verifies helper behavior only, not a real Claude or Codex runtime.

## Optional manifest extensions (backward compatible)

These fields are explicit operator declarations. Omission retains old inventory behavior;
acceptance still requires a supported review route for each intended host. No host/model names
are inferred from another application or provider.

- `hosts`: objects with `host`, `session`, optional `discovered_skills` and `native_tools`
  string arrays, `discovery_evidence` reference, and `review: {source: "local"|"shared", path: "…/SKILL.md"}`.
  Discovery is `DECLARED` only with an evidence reference, otherwise `UNKNOWN`. An omitted native tool list is UNKNOWN (`null`); an explicit empty list is a declared empty inventory. Neither disproves discovery. Invocation remains `NOT_TESTED`. Review requires an
  allowed, readable, nonempty SKILL.md: output `FILE_FALLBACK` supplies the exact absolute path
  and hash, or `BLOCKED`. Read it and its references completely; retain independent reviewer,
  pinned scope/diff and acceptance evidence. File fallback is not an execution result or proof
  that the skill's semantics/references are valid. Adapter planning also reads explicitly declared destination bytes for hash comparison.
- `models`: per-role objects with `host`, `session`, `role` (`helper`, `coder`, `reviewer`),
  optional `candidate`, `catalog` (string array), `catalog_evidence`, `entitlement`
  (`unknown`|`available`|`unavailable`), `budget` (`unknown`|`approved`|`denied`). Catalog and
  evidence must belong to this exact host/session, also declared in `hosts`. Never copy an
  unrelated app's catalog. Candidate states distinguish `SESSION_UNKNOWN`, `CATALOG_UNKNOWN`,
  `UNSELECTED`, `MISSING`, `LISTED`; entitlement and budget stay separate. Unresolved conditions
  yield `UNBOUND` with concrete next steps. `VALIDATED_DECLARATION` only validates supplied
  inventory; it never binds a model, proves entitlement or invokes a paid probe.
- `adapter_files`: planned destination `path` plus exact lowercase `sha256` of the proposed
  bytes. Read-only planning returns `PROPOSE_ADD` for a missing file, `NOOP` for matching bytes,
  or `BLOCKED` for different/unsafe/unreadable content. Existing files require a reviewed merge,
  recorded baseline hash and backup before an authorized writer acts. Repeat preflight after
  application; matching content yields `NOOP`, never another copy. The helper does not perform
  a merge, rollback, write or acceptance approval. Use canonical destinations; semantic duplicate
  rules in different files still require inventory review.

Declare each host/session once. Use evidence references without secret values. Fixtures additionally
exercise independent discovery/native tools, both hosts' identical file fallback, unknown/missing
models and cross-session rejection, plus repeated additive planning with a concurrent edit preserved.
No fixture establishes real CLI discovery, invocation, entitlement, MCP or model-runtime PASS.
