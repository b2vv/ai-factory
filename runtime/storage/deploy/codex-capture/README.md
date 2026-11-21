# Codex capture catcher (lifecycle-event delivery)

Implements delivery of supplied Codex lifecycle events (user prompts and assistant Stop text)
to the running AI Factory storage engine via its supported provider endpoint
`POST /v1/capture/codex-event-v2`. This is the delivery catcher only; the vetted Go adapter
(`internal/capture`, provider `codex-hook-v2`, `AdaptCodexSnapshotEvent`) stays the sole authority
for redaction and credential sanitization before anything reaches the WAL/archive.

Companion to `../capture-bridge` (Claude Code). Same privacy/fail-safe discipline; the
difference is the Codex hook transport and the way a project is selected.

## Files
- `codex_capture_catcher.py` — selection + normalization + POST + visible status (all logic; unit-tested).
- `codex-capture-hook.sh` — thin command-hook wrapper that execs the Python with `-I`.
- `test_codex_catcher.py` — routing / normalization / sanitization contract tests (`python3 -I test_codex_catcher.py`).
- `test_codex_catcher_auth.py` — loopback auth / isolation / denial tests with a synthetic server and synthetic credentials.

## Native input and v2 delivery contract

Native field definitions come from the [official hooks reference](https://learn.chatgpt.com/docs/hooks).
A private synthetic experiment on CLI 0.163.0 observed one UserPromptSubmit and two
Stops with the same turn ID, changed assistant text and stop_hook_active false then
true. Existing global session hooks also ran and added monitoring warnings. This
proves that continuation can emit changed text under the same turn; it does not
prove desktop/cloud parity, project activation or transcript completeness.

The catcher forwards native session_id, turn_id and prompt for UserPromptSubmit,
or last_assistant_message plus a required boolean stop_hook_active for Stop. Both
initial and continued Stops are forwarded. It adds schema_version=2 as a Factory
transport envelope field, not a claimed native Codex field. Other fields, including
transcript_path, model and permission_mode, are discarded; cwd is used only to
select an explicit mapping. SubagentStop and all other event types are ignored.
Session/turn IDs must match ^[A-Za-z0-9_-]{1,160}$ exactly.

POST /v1/capture/codex-event-v2 requires separate codex-hook-v2 capture consent.
There is no v1 fallback. An old server returns 404 without accepting a legacy
record. Delivery is reported only after a valid success response with the
X-AF-Codex-Contract: 2 acknowledgement. It means the server accepted the request;
committed counts and independent retrieval determine archive availability. The API
serializes an empty Go redaction slice as null; null and arrays are accepted,
but an omitted redactions field or another type is an invalid response.

The server sanitizes text using known-credentials-v1 before assigning v2 IDs:
- prompt: v2/<turn_id>/prompt;
- Stop snapshot: v2/<turn_id>/assistant/<sha256 of sanitized UTF-8 text>;
- snapshot parent: v2/<turn_id>/prompt.

The digest is derived metadata, not a native message ID. Distinct sanitized Stop
texts coexist; identical snapshots deduplicate across retries, restart and flag
changes. Different credential-bearing texts can intentionally collapse to the same
redacted snapshot. The flag does not change the stored record. Seq 1/2 represents
roles, not callback order. These records are Stop snapshots: a callback cannot know
whether another concurrent hook will continue the turn. No snapshot is labelled a
guaranteed final answer. Historical codex-hook-v1 records and hashes are unchanged;
the v2 prefix is needed because provider is absent from archive identity.

## How a project is selected (explicit mapping, never cwd-inferred authority)
Codex supports user and project hook sources. This shared-hook design uses an explicit
operator mapping file given by `AF_CODEX_CATCHER_MAP`:

```json
{ "projects": [
  { "root": "/abs/path/to/project",
    "project": "<storage-project-uuid>",
    "source_instance": "<stable-codex-source>",
    "credential_file": "/abs/path/to/<project>.cred.json" }
]}
```

The event's own `cwd` field selects the single row whose `root` is `cwd` or a parent of it
(longest-prefix, on a directory boundary). A `cwd` under no mapped root is a **no-op**:
nothing is read or sent. `cwd` only picks the row — the server independently authorizes the
row's scoped credential against the row's project UUID (`requireCapture` →
`authz.Authorize(..., OpCapture)`), but a spoofed `cwd` can select another mapped credential readable by this process. The mapping is routing, not isolation from untrusted same-user events. Keep the mapping file local (not committed); it holds
UUIDs and credential-file paths.

## Credentials (least privilege)
Each row points at an AGENT capture credential JSON `{principal_id, epoch (int>0), secret}` —
reuse the project's EXISTING capture-only key (e.g. from
`storage-alpha/secrets/project-capture-20261106/<Project>.cred.json`). An operator secret is
**refused** (treated as an invalid credential → no-op); this catcher can never hold
control-plane authority even if mis-pointed. Keep each credential file `0600`; never put a
secret in the mapping, in settings or in Git.

A capture-only grant permits ingestion within its granted project only. It does not permit
archive reads, search, consent changes, grant administration or deletion. Revoked or stale
grants fail closed. Scope is enforced by the server, not trusted from the caller.

## Transport and status boundaries
The destination is pinned to `http://127.0.0.1:8780`. Other `AF_CODEX_ENDPOINT` values are refused before network access. Proxy environment variables and HTTP redirects are disabled.

## Privacy / safety guarantees
- **Server remains the redaction authority.** Before private local persistence, the
  catcher applies the shared Go-compatible known-credentials detector. The adapter
  validates/sanitizes again before WAL. Neither is a universal secret detector.
- **Visible status, no secrets/payload.** Each run emits one compact JSON status line to
  stderr (and to `AF_CODEX_STATUS_FILE` if set) with a supported-event enum, `role`, `delivered`, `http_status`, bounded integer `accepted` and `committed`,
  `redactions`, and a `skipped`/`error` REASON — never message text, never the secret,
  never the server response body.
- **Nothing blocks the turn.** Any error (unparseable event, bad mapping, unreadable
  credential, HTTP/connection failure, denial) is recorded in the status and the hook exits 0.
- **Idempotent snapshots.** The server deduplicates the same sanitized snapshot and
  preserves changed Stop text as another v2 record. The catcher keeps no cursor and
  claims no event chronology or complete session.

## Install boundary (NOT done by shipping this)
Installing global or project-local hooks requires native review of each exact definition
through `/hooks` or the desktop hook review UI. Preserve every existing hook chain,
including session-size handoff hooks. Never bypass trust or infer it from publication.
Installation and production trust are separately authorized operations; shipping this
directory changes neither hook configuration nor trust.

## Scope and activation

This source supports the CLI native event shape described above. Native delivery
through this updated catcher, live v2 deployment, project consent, configured
mapping and trusted production hook definitions require their own exact verification.
No production activation follows from fixture success or publication. Interrupted
turns, missing callbacks, delivery failure and non-Stop assistant messages can still
leave gaps. No backfill, transcript reading or Markdown parsing is performed.

Mapping roots and credential paths must be canonical absolute paths without symlink
components. Duplicate roots are refused. File/input/response reads are bounded.
Production destination is pinned to http://127.0.0.1:8780; proxies and redirects are
disabled. Fixtures substitute an ephemeral listener only within the test.


## Durable v2 delivery queue

This component now depends on `capture-bridge` for the reviewed private SQLite
spool, known-credential sanitizer and bounded status writer. Install both through
the normal managed-kit component dependency resolution. Do not copy this file alone
into an immutable/versioned runtime directory.

The queue is persisted **before** network delivery. It retains exact sanitized UTF-8
JSON bytes, scoped by `codex-hook-v2`, endpoint, project, source and principal. The
private queue directory defaults to `capture-queue` beside the credential file, or
explicit canonical `AF_CODEX_QUEUE_DIR`. No credentials/headers are persisted.
Private conversation text remains confidential plaintext (0700/0600, not encrypted);
unknown/unlabelled secrets may remain. See the shared
[queue durability, limits and lifecycle](../capture-bridge/README.md#durable-queue-source-feature-deployment-is-explicit).

### Snapshot identity and ACK

- Prompt identity: `v2/<turn_id>/prompt`. Changed prompt under the same session/turn
  is a visible conflict, never overwrite.
- Stop identity: `v2/<turn_id>/assistant/<sha256(sanitized UTF-8 text)>`. Different Stop
  text in one turn is a distinct snapshot, not a conflict or silently discarded answer.
- The native `stop_hook_active` value is strictly validated first. Because it is
  shape-only in the server contract and not record identity/content, the frozen
  transport flag is canonicalized to `false`. Identical text under either valid flag
  produces identical payload/ID; credential-redacted texts collapse the same way as Go.
- Retries send **exact queued bytes**, without re-encoding or applying a newer sanitizer.
  The server's current authorization, consent, retention and redaction still apply.
- Delivery ACK requires HTTP200, `X-AF-Codex-Contract: 2`, `accepted:1`, valid
  nonnegative bounded integer `committed`, properly typed `redactions`, no drain error,
  and exactly the expected receipt `[project, source, session, derived_message_id]`.
  No v1 fallback. Success does not establish search freshness or native callback coverage.

The shared queue retains blocked4xx, performs bounded backoff for transient failures,
reserves attempts before I/O and uses60-second leases with at most20 attempts. Full
queue/disk is a visible failure with no silent eviction. Preserve source evidence for
unqueued events; this catcher does not read/reconstruct old transcripts. Completed
local receipts suppress routine replay; receipt capacity is finite and needs explicit
operator lifecycle management, as described in the shared queue contract.

### Worker without further Codex turns

Use the same explicit mapping and additionally `AF_CODEX_WORKER_PROJECT=<UUID>`.
Exactly one mapping row must match; no implicit all-project sweep or cwd inference:

```sh
sh codex-capture-hook.sh --status
sh codex-capture-hook.sh --flush
sh codex-capture-hook.sh --worker
sh codex-capture-hook.sh --retry-blocked
```

Each worker re-reads mapping/credentials, attempts at most one due event every30seconds
and uses the same8-second whole-step /2-second network bounds as Claude. It must be
supervised for restart/login recovery; no supervisor or trust configuration is installed
by this code. Changing mapping source/endpoint/principal selects another partition:
old queued records must be reconciled explicitly, never adopted by a new identity.
`--retry-blocked` is an explicit remediation action after resolving the failure, not
permission to restore consent or bypass401/403. Use one supervisor per selected project.

Do not modify an old hash-addressed runtime in place, or rewrite trusted hashes to
make a changed hook appear previously approved. Retarget an existing hook to the managed
wrapper only through the owner's standard `/hooks` / desktop review workflow, preserving
all unrelated hook definitions. Already-running native sessions are not restarted here.

### Tests and verification limits

`test_codex_queue.py` exercises immutable retry, timeout-after-commit, worker restart,
flag/redaction snapshot collapse, changed snapshots/prompts, parallel hooks, capacity,
privacy, provider isolation and exact ACK denial. It also compares24 events against the
actual Go adapter (explicit skip without Go/server source). Existing selector, auth and
security suites plus Claude regressions remain required. All fixtures are synthetic.
Native event emission, reboot, project consent and live route/trust are separate checks;
passing fixtures does not mean a production hook is connected.

### Reproducible supervised native activation

`worker.launchagent.example.plist` is a portable template, not an installer. Substitute
an existing private mapping and its exact project UUID, an absolute Python executable,
the installed managed-kit location, and a private log path. Use one distinct label per
project. Reuse the approved mapping credentials; never embed credentials in the plist.
Validate the plist and mapping before loading it. Keep the worker and hook on the same
managed catcher and mapping so both select the same durable queue partition.

Before retargeting native hooks, back up each hooks.json and record its digest. Check
that the digest still matches immediately before the atomic replacement. Change only
the catcher executable path in the two existing UserPromptSubmit and Stop commands;
preserve map, status path, timeout, event names and every unrelated hook. Never modify
an old hash-addressed runtime in place. In a fresh native session use `/hooks`, select
the specific project Archive hook under each event, review, then trust it individually.
Do not trust all hooks: unrelated global hooks may separately require review. Never
write trusted hashes manually or bypass hook trust. Existing active sessions are not
restarted; they may need their own approved refresh or a fresh session to load changes.

Acceptance requires a harmless labeled native turn, queued status, worker completion,
and both prompt and assistant found by search through the terminal empty cursor.
A transport timeout is not failure proof: inspect the queue and server receipt before
repeating anything. For rollback stop only the corresponding workers, restore backed-up
hook definitions through review, use the managed-kit rollback transaction, and retain
queue databases for explicit reconciliation. Login/reboot recovery must be reported
separately from a process-restart test; LaunchAgents require a logged-in user session.
