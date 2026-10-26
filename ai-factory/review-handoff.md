> Runtime examples below use `$KIT` as an explicitly selected absolute root of this release; `$PREVIOUS_RELEASE` is the immutable prior release when testing upgrades. This path update does not activate or change helper behavior.

<a id="startup-routing-та-передача-на-незалежний-review"></a>
# Startup routing and handoff to independent review

This contract supplements the current workflow; it creates no additional tracker or orchestrator. Small retains one primary task record; insert the fields below there. An evidence bundle is a derived snapshot for review, not a second plan. Local standards, gates and owner decisions remain in force.

<a id="перед-початком-роботи"></a>
## Before starting work

In the current primary record, write the review goal, `review_mode=existing_session` for an already assigned additional session or `review_mode=independent_subagent` if there is no additional session; writer/reviewer reference (pending until authorized spawn), selection rationale, current contact mechanism, delivery owner, authorization source and coordination of shared-resource checks. The owner's explicit choice takes precedence. Do not ask again about an already determined route; mark genuinely unknown required information BLOCKED with an owner for clarification.

Selecting the mode does not start review/security or authorize new external sessions. Existing-session uses the already assigned reviewer without duplication; independent-subagent is a separate context under current authorization, with its reference recorded after launch. Author self-review is not independent review. Selected runtime unavailable → BLOCKED, without silent fallback or PASS. After compaction/resume, restore the saved mode and pending action rather than choosing anew. A confirmed route does not mean review completed; report author checks separately.

<a id="пакет-передачі"></a>
## Handoff package

Minimal self-contained package in the existing evidence location:

- task ID, author session ID, selected route/owner/reviewer reference and transfer status `prepared/sent/acknowledged/verdict_received` in the primary record;
- exact repo/root, branch, resolved base commit, HEAD; explicit file scope with tracked dirty and relevant untracked files, SHA-256 of current and baseline bytes, exact diff;
- acceptance and relevant contracts: exact path + SHA-256 + snapshot copy of the required document (or a self-contained excerpt with provenance), not just the author's paraphrase;
- evidence: command/scenario, exit code, PASS/FAIL/BLOCKED/NOT_TESTED/N/A, scope/revision, raw artifact/hash, limitation; an unrun check does not become PASS;
- constraints, non-goals, permissions, resource limits, unresolved decisions, next owner.

Do not copy .env/credentials/config secrets, transcripts or complete irrelevant logs. If a source cannot be handed over safely, name the missing evidence and BLOCKED dependent gate. Use explicit paths for external shared documentation; code scope does not expand automatically.

One pair `package ID + assigned reviewer reference` has one handoff in the current record. Repeating an already transferred package is NOOP, not another message or spawn. Unknown delivery requires checking the receipt; confirmed nondelivery may be retried under current authorization in the same handoff. The helper sends nothing and does not manage sessions.


<a id="pending-next-action"></a>

<a id="наступна-дія-яку-не-можна-втратити"></a>
## The next action that must not be lost

After `/clear`, a new startup or resume, a valid pending record is only a reason to briefly show task/checkpoint and ask “Continue?”. Do not execute task/review/send until the user's current response; Stop must not force continuation during this wait. An explicit new user request to continue this exact task may serve as confirmation. After confirmation, applicable authorized steps proceed without another question at every gate; permissions do not expand. Consent from another or previous session does not carry over.

Compaction within an already confirmed active task preserves continuity: restore its specific next action without asking again. If a response was still pending before compaction, continue waiting; do not start a question loop. Unbound without a task stays quiet; schema/bind help is available only on demand. This is scoped workflow UX, not a new security approval rule or permission to start review.

At startup and after compaction/resume, first read the explicit primary task record. Record `review_mode=existing_session` for an already assigned additional session or `review_mode=independent_subagent` if there is no additional session. Restore this choice, writer/reviewer, current authorized contact mechanism and pending action; do not request already known IDs/permission again, create a new external session or duplicate review. An independent subagent has a separate review context; the author's inline self-review is not a substitute. If the runtime does not support the selected mode or permission is missing, record BLOCKED and the unblocking owner, without silent switching or PASS. Choosing the mode does not by itself start review, security or other work.

Keep a short block in that same record (not a new tracker): `task/stage + snapshot/package ID; review_mode; writer; reviewer; contact mechanism + delivery owner + authorization source; action ID + next action + owner; transfer state + evidence pointer; required final verdict + evidence pointer; blocker/next check`. Use an already working contact route/address, not an arbitrary similar name. For independent_subagent the reference stays pending until authorized launch; afterward retain the real reference and reuse the same reviewer. Do not store tokens or credentials.

After each stage, update the block and perform only the applicable next action already authorized by the current scope. Small/full and local gates determine applicability; do not invoke all skills or the entire pipeline. If the action depends on another executor or permission, record the wait/blocker instead of pretending completion.

| State | Next applicable action |
|---|---|
| Stage completed, required checks not yet performed | Applicable authorized checks; without permission for side effects — BLOCKED |
| Checks sufficient, required review not yet handed off | Prepare the exact package and hand it to the already assigned reviewer through the current authorized contact route |
| `prepared` | The file is ready, but that is not delivery; send belongs to the delivery owner |
| `sent` | Preserve the actual transport result; await ACK/response, do not resend because of compaction |
| `acknowledged` | The reviewer confirmed the specific package; await verdict, ACK is not PASS |
| `verdict_received` | Verify reviewer, package/snapshot, scope, findings and required evidence; FAIL → authorized fix and affected re-review; valid final verdict → next local stage |
| Delivery unknown, held/refused, no response or stale evidence | WAITING/BLOCKED with reason and next check/owner; do not treat timeout as PASS or duplicate delivery |

`sent` requires an actual sending result; `acknowledged` requires the assigned reviewer's response to this exact package. An author-written result file, the words DONE/PASS or a successful hook do not replace an independent verdict. A complete valid reviewer response may both confirm receipt and contain the verdict — no separate ACK ping is needed. For manual transfer, owner confirmation is evidence of send, not reviewer ACK or verdict.

Before send, record intent/attempt for the action ID; afterward, record the actual result in the same record. If a failure occurred between them, delivery is unknown: first check existing correspondence/receipt, without automatic resend. This record prevents blind retries but does not promise exactly-once transport. A retry for a new package ID or after confirmed nondelivery requires current authorization; do not create a new reviewer.

Resume starts with the specific pending action and verification of the relevant snapshot. Unchanged accepted stages are not repeated; a material delta reopens only affected gates under the local contract. Before compaction/ending the current turn, save the current block. WAITING/BLOCKED permits ending a turn with an honest status and next check, but not declaring the task DONE. DONE is possible only after all applicable local gates and the required final verdict on the final snapshot; if review is N/A, a local rationale is required, not a new waiver.

<a id="delivery-state"></a>
<a id="delivery-state-та-security-завершення"></a>
## Delivery state and security completion

The single transport contract is `prepared` → `sent` → `acknowledged` → `verdict_received` in the existing pending-action record above. For historical security reports, `PREPARED`, `SENT`, `VERDICT_RECEIVED` are aliases for the corresponding lowercase states; `AWAITING_DELIVERY` is a WAITING reason with a delivery owner/next action, not a separate transport state. Legacy `delivered` means `sent` only with delivery evidence; `responded` means `verdict_received` only with a valid response from the required reviewer to this snapshot. ACK is not acceptance; a full valid verdict may also confirm ACK. This documentation delta does not change runtime schemas/helpers.

DONE is blocked by any unresolved applicable required check or required independent final verdict. Missing runtime proof leaves VERIFICATION_INCOMPLETE; missing verdict leaves REVIEW_PENDING: these are reporting outcomes, not transport states. N/A needs an applicability reason; changing a required requirement needs an explicit owner decision. An aggregate build/fixture/merge does not replace a required row. This is an instruction contract, not automatic CI enforcement. For scoped security work — [proposed adapter](../adapters/security/review.md).

<a id="контракт-reviewer"></a>
## Reviewer contract

The reviewer works independently: reads pinned acceptance/contracts, diff and source snapshots, verifies the live root/snapshot before and after review, assesses scope sufficiency and relevant untracked files. The author's summary is navigation only. Read-only by default: no source/config/index changes. A locally authorized review artifact may be written only in the designated evidence location. A need for a test does not authorize reset/seed/install or shared-environment access; first agree the operation, owner, slot and side effects. Distinguish the reviewer's own checks from accepted pinned raw author evidence.

Each finding: `file:line`, specific consequence, evidence/reproduction or verification method, blocking/nonblocking, confidence. Verdict: reviewer reference, package/snapshot ID, checked scope/axes, findings, checks/evidence and limitation. An absent/empty/incomplete response means **review NOT_TESTED, required gate BLOCKED**. The author does not present self-review as an independent PASS. Helper structural validation does not prove human/agent independence or the truth of its declarations.

<a id="зміни-після-review"></a>
## Changes after review

PASS applies only to the reviewed snapshot/scope. After fixes, prepare a final delta against the reviewed snapshot; the reviewer determines affected criteria/checks and gives a verdict on the final package ID. Unchanged evidence may be explicitly accepted if inputs have not changed. Do not repeat the entire gate for an irrelevant edit unless the local contract requires it. Do not carry an old PASS over to changed acceptance/diff/untracked files. A base/HEAD change requires provenance verification, not automatically repeating all tests. The reviewer separately confirms expanded/narrowed scope; new relevant files must be included.

<a id="опційний-stdlib-helper"></a>
## Optional stdlib helper

[review_package.py](../runtime/legacy/review/review_package.py) works on a Git repo with HEAD and UTF-8 text files: at most 100 scope files, 1 MB/file, 8 MB of unique blobs. It runs no repo commands/tests/CLI/MCP; only read-only Git queries. No install, network, dispatch, hooks or permission changes. Symlink paths, secret-like names/content and configurations are rejected; this is defense in depth, not a universal secret scanner. Use canonical paths (on macOS `/private/...` instead of symlink `/tmp` for a fixture).

```sh
python3 "$KIT/runtime/legacy/review/review_package.py" route manifest.json
python3 "$KIT/runtime/legacy/review/review_package.py" capture manifest.json /absolute/existing-evidence/review
python3 "$KIT/runtime/legacy/review/review_package.py" assess /absolute/package-ID --response response.json
python3 "$KIT/runtime/legacy/review/review_package.py" delta /absolute/old-ID /absolute/new-ID
```

The [manifest example](../examples/review/manifest.json) and [response example](../examples/review/response.json) are forms, not ready approvals or PASS. Replace paths/IDs and declarations with actual values. The package contains `package.json` and `objects/<SHA256>`; open the diff blob and source/reference blobs through the manifest. Metadata/package ID and each blob are checked at load; repeating capture on unchanged scope yields the same ID/NOOP. Two collection passes reject observed concurrent edits; they do not lock the writer after capture, so freshness is rechecked before verdict/apply. The snapshot is an explicit file scope, not a full repository audit; ignored/out-of-scope files are not automatically covered. Irrelevant out-of-scope changes do not invalidate it.

`assess` checks integrity, current scope/reference/evidence hashes, route, response identity/coverage and required check declarations. This is a **structural status**, not a review produced by the tool. Empty response, missing evidence, a different reviewer or a stale package are blocked. An unsupported format requires a manual equivalent with the same fields and honest NOT_TESTED, not installing new tools.

Tests: `python3 -B "$KIT/tests/legacy-tests/review/test_review_package.py"`; all Git fixtures are disposable. Live third-party sessions/CLI/environments are not used for simulation.
