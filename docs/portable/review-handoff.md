> Optional retained portable profile; the full canonical plan is in `ai-factory/`. This profile does not replace original skill contracts or authorize automatic activation.

<a id="startup-routing-та-передача-на-незалежний-review"></a>
# Startup routing and handoff to independent review

This contract supplements the current workflow; it creates neither another tracker nor an orchestrator. Small keeps one primary task record; insert the fields below into it. The evidence bundle is a derived snapshot for verification, not a second plan. Local standards, gates and owner decisions remain in force.

<a id="перед-початком-роботи"></a>
## Before starting work

For each required critique/review/verification, the session records and shows the user:

> Checks/critique/review: `<goal>` → `<new subagent | existing separate session | UNRESOLVED>`; owner `<name/role>`; session/agent reference `<exact ID or pending>`; selection basis `<current instruction/user response>`; package delivery owner `<owner>`; shared test environment access `<not needed | agreed slot/owner | BLOCKED>`.

The user's explicit choice takes precedence. If the current instruction unambiguously defines the route, record it without asking again. Otherwise ask **before spawning or sending**: “For `<goal>`, should I launch a new subagent or use an existing separate session? If existing, what is the exact name/ID and who delivers the package?” Without an answer, the route remains UNRESOLVED; independent safe inventory/planning may continue. Do not substitute a subagent after a timeout. A session's existence is not completed review.

For `new subagent`, append the returned ID to the same record after authorized spawn; for `existing session`, do not guess an ID from a similar name. Permission to choose a method does not automatically authorize messaging another session: explicit delivery instruction is needed, or the user performs it. Do not create a duplicate reviewer when one is already assigned; do not duplicate handoff through a repeated request. Label ordinary author verification separately as author checks, not independent review.

<a id="пакет-передачі"></a>
## Handoff package

Minimum self-contained package in the existing evidence location:

- task ID, author session ID, selected route/owner/reviewer reference and delivery status `prepared/delivered/responded` in the primary record;
- exact repo/root, branch, resolved base commit, HEAD; explicit file scope with tracked dirty and relevant untracked files, SHA-256 of current and baseline bytes, exact diff;
- acceptance and relevant contracts: exact path + SHA-256 + snapshot copy of the required document (or a self-contained extract with provenance), not just the author's summary;
- evidence: command/scenario, exit code, PASS/FAIL/BLOCKED/NOT_TESTED/N/A, scope/revision, raw artifact/hash, limitation; unrun checks do not become PASS;
- constraints, non-goals, permissions, resource limits, unresolved decisions, next owner.

Do not copy .env/credentials/config secrets, transcripts or full irrelevant logs. If a source cannot be safely delivered, name the missing evidence and mark the dependent gate BLOCKED. Use explicit paths for external shared documentation; code scope does not expand automatically.

One `package ID + assigned reviewer reference` pair has one handoff in the current record. Repeating the same package is NOOP, not another message or spawn. The helper sends nothing and does not manage sessions.

<a id="контракт-reviewer"></a>
## Reviewer contract

The reviewer works independently: reads pinned acceptance/contracts, diff and source snapshots themselves, checks the live root/snapshot before and after verification, and assesses scope sufficiency and relevant untracked files. The author's summary is navigation only. Read-only by default: no source/config/index changes. A permitted local review artifact may be written only to the designated evidence location. Needing a test does not authorize reset/seed/install or shared test-environment access; first agree on the operation, owner, slot and side effects. Distinguish the reviewer's own checks from accepted pinned raw author evidence.

Each finding: `file:line`, concrete consequence, evidence/reproduction or verification method, blocking/nonblocking, confidence. Verdict: reviewer reference, package/snapshot ID, checked scope/axes, findings, checks/evidence and limitation. Missing/empty/incomplete response means **review NOT_TESTED, required gate BLOCKED**. The author does not present self-review as independent PASS. Helper structural validation does not prove a person's/agent's independence or the truth of their declarations.

<a id="зміни-після-review"></a>
## Changes after review

PASS applies only to the checked snapshot/scope. After fixes, produce a final delta from the reviewed snapshot; the reviewer identifies affected criteria/checks and gives a verdict on the final package ID. Unchanged evidence may be explicitly accepted if its inputs did not change. Do not repeat the entire gate for an irrelevant edit unless the local contract requires it. Do not carry old PASS onto changed acceptance/diff/untracked files. A base/HEAD change requires provenance reconciliation, not automatic repetition of every test. The reviewer separately confirms expanded/narrowed scope; new relevant files must be included.

<a id="опційний-stdlib-helper"></a>
## Optional stdlib helper

[review_package.py](../../runtime/review/review_package.py) works on a Git repo with HEAD and UTF-8 text files: at most 100 scope files, 1 MB/file, 8 MB of unique blobs. It runs no repo commands/tests/CLI/MCP; only read-only Git queries. No install, network, dispatch, hooks or permission changes. Symlink paths, secret-like names/content and configurations are rejected; this is defense in depth, not a universal secret scanner. Use canonical paths (on macOS `/private/...` instead of symlink `/tmp` for a fixture).

```sh
python3 "$KIT"/review/review_package.py route manifest.json
python3 "$KIT"/review/review_package.py capture manifest.json /absolute/existing-evidence/review
python3 "$KIT"/review/review_package.py assess /absolute/package-ID --response response.json
python3 "$KIT"/review/review_package.py delta /absolute/old-ID /absolute/new-ID
```

The [manifest example](../../examples/review/manifest.json) and [response example](../../examples/review/response.json) are forms, not ready approvals or PASS. Replace paths/IDs and declarations with actual ones. The package contains `package.json` and `objects/<SHA256>`; open the diff blob and source/reference blobs through the manifest. Metadata/package ID and every blob are checked on load; repeated capture of unchanged scope yields the same ID/NOOP. Two collection passes reject observed concurrent edits; they do not lock the writer after capture, so recheck freshness before verdict/apply. A snapshot is explicit file scope, not a full repo audit; ignored/out-of-scope files are not automatically covered. Irrelevant changes outside scope do not invalidate it.

`assess` checks integrity, current scope/reference/evidence hashes, route, response identity/coverage and required check declarations. This is a **structural status**, not a tool-created review. Empty response, missing evidence, wrong reviewer or stale package are blocked. Unsupported format means a manual equivalent with the same fields and honest NOT_TESTED, not installing new tools.

Tests: `python3 -B "$KIT"/review/test_review_package.py`; all Git fixtures are disposable. Other live sessions/CLI/test environments are not used for simulation.
