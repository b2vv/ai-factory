# Claude Code capture bridge (Stop-hook delivery)

Delivers REAL current Claude Code messages (the turn's human prompt + the final assistant
answer) to the running AI Factory storage engine via its supported provider endpoint
`POST /v1/capture/claude-code`. This is the delivery bridge only; the vetted Go adapter
(`internal/capture`, provider `claude-code`) stays the sole authority for redaction and
credential sanitization before anything reaches the WAL/archive.

## Files
- `capture_bridge.py` — selection + normalization + queued POST + visible status.
- `capture_queue.py` — private transactional spool, sanitizer and retry leases.
- `test_capture_queue.py` — synthetic durability/fault/parallel/worker tests.
- `claude-code-stop-hook.sh` — thin `Stop`-hook wrapper that execs the Python with `-I`.
- `test_capture_bridge.py` — normalizer/selector contract tests (`python3 -I test_capture_bridge.py`).
- `test_capture_auth.py` — subprocess/loopback authentication tests with synthetic credentials.

## How it is wired (project-scoped only; never global)
Add a `Stop` hook to the target project's `.claude/settings.json` (or `settings.local.json`),
preserving any existing hooks. Configuration is by environment; **cwd is never used to infer
the project**:

| env | meaning |
|-----|---------|
| `AF_CAPTURE_PROJECT` (required) | storage project UUID — the explicit operator mapping |
| `AF_CAPTURE_AGENT_CREDENTIAL_FILE` | private scoped credential JSON: `principal_id`, positive integer `epoch`, nonempty `secret` |
| `AF_CAPTURE_OPERATOR_SECRET_FILE` | legacy operator credential file; choose exactly one credential mode |
| `AF_CAPTURE_ENDPOINT` | default `http://127.0.0.1:8780` |
| `AF_CAPTURE_SOURCE` | `source_instance`, default `claude-code` |
| `AF_CAPTURE_STATUS_FILE` | optional append-only status log (payload/secret-free) |

## Authentication and rollout boundary
The three capture endpoints accept an existing project-scoped agent grant with the
`capture` operation through `X-Principal-Id`, `X-Grant-Epoch` and `X-Secret`. The
bridge reads these fields from `AF_CAPTURE_AGENT_CREDENTIAL_FILE` at call time.
Keep the file private (0600); never put credential values in settings or Git.
Exactly one of the agent and operator credential file settings must be selected.
Malformed or conflicting configuration refuses delivery; there is no fallback.

A capture-only grant permits ingestion within its granted project across the
supported providers and source instances. It does not permit archive reads, search,
consent changes, grant administration or deletion. Scope is enforced by the server,
not inferred from cwd or trusted from the caller's project UUID. Revoked or stale
grants fail closed. Authorization is repeated under the writer fence before any
new durable acceptance, alongside the existing consent and retention checks.
A completed revoke blocks subsequent acceptance; it does not undo work already
accepted before the revoke. Consent and deletion gates still govern publication.

The existing operator transport remains supported for compatibility. An explicitly
present operator header takes precedence, including empty/invalid values; it never
falls back to an agent credential. Duplicate authentication headers are rejected.
A valid operator header is not demoted by stray single-valued agent headers.
Operator credentials retain full control-plane authority and are not the scoped
mode. New installations should use capture-only project credentials after explicit
approval. This source change does not issue keys, install hooks or activate consent.
Deploy the compatible server and bridge before selecting scoped mode; older servers
refuse agent capture. Keep existing working integrations until their scoped replacement
has passed verification. No historical backfill is performed by this bridge.

## Privacy / safety guarantees
- **Non-text payload never leaves the process.** `thinking`, `tool_use`, `tool_result` blocks
  are forwarded as **type only** (no bytes). The adapter still records the redaction, so the
  vetted drop is exercised and auditable; hidden reasoning/tool output is never transmitted.
- **Session identity.** Only transcript lines whose `sessionId` equals the hook's `session_id`
  are considered; a stale/wrong `transcript_path` cannot capture another session (counted as
  `other_session_lines`).
- **Nothing silently lost.** Unrecognized top-level line types and unrecognized content block
  types are counted and surfaced in the status by **counts only** (never content or untrusted type names), so a
  future contentful type is observable rather than dropped in silence. Known bookkeeping line
  types and `image` blocks are dropped quietly (they are never conversation history).
- **Visible status, no secrets/payload.** Each run emits one compact JSON status line to stderr
  (and to `AF_CAPTURE_STATUS_FILE` if set) with `delivered`, `http_status`, `accepted`,
  `committed`, `redactions`, `selected` roles, and the drop counts above — never message text,
  never the secret.

## Confirmed behaviors
- **Retry / idempotency.** Re-running on the same turn re-POSTs the same `uuid`-keyed records;
  the archive `Put` is a no-op for an identical record (WAL exact-key dedup collapses it), so a
  replay adds no duplicate. A *different* answer under the same `uuid` is a server-side conflict
  (409), never a silent overwrite. The bridge keeps no transcript cursor; the durable queue retains delivery receipts. The server remains the source of truth.
- **Incomplete last line.** The transcript is read line-by-line; a truncated/partial final JSON
  line fails to parse and is skipped and counted (`skipped_unparseable_lines`), never fatal.
- **POST / server failure.** Any HTTP or connection error is recorded in the status (`http_status`
  / `error`, body never echoed) and the hook exits 0 — a Stop hook never blocks the session.
- **cwd identity.** `cwd` from the hook payload is ignored for membership; the project is the
  explicit `AF_CAPTURE_PROJECT` mapping only.

## Stable identifiers
Records carry the transcript's real `sessionId` (session), message `uuid` (message), and
`parentUuid` (parent). The "turn" anchor is the user message `uuid`, which equals the assistant
record's `parentUuid`; search returns these with the decision text.

## Scope
Claude Code only. No backups, no other providers, no global hook, no Go/adapter change,
no image rebuild or container recreate.

## Durable queue (source feature; deployment is explicit)

The Stop hook now **persists before POST**. The private SQLite spool defaults to
`capture-queue/` beside the configured credential file, or the explicit absolute
canonical `AF_CAPTURE_QUEUE_DIR` (existing parent required). It is separate from
Git, the transcript and the archive. Directory 0700, database/journal 0600; wrong
owner, broader permissions, symlinks and hardlinked database files are refused,
not automatically repaired. It requires a local POSIX filesystem with working
SQLite locks/fsync, not a network/synced/cloud folder. No credentials or auth
headers are stored. Route + principal partitioning prevents cross-project replay;
credential epoch/secret rotation can use the same partition, but changing principal,
endpoint or source selects a **different** partition. Drain the old scope explicitly
before a mapping change; it is never silently adopted by a different identity.

The spool retains selected **private conversation text**. It is not encrypted and
is not suitable for a shared/untrusted account. Before persistence, joined visible
text matching the Go `known-credentials-v1` patterns is wholly redacted; hidden
reasoning/tool bytes never enter the spool. This is not a universal secret detector:
unlabelled passwords or unknown encodings can remain, as in the source transcript.
The Go adapter remains the final authority; local sanitization is defense in depth.
IDs, parent links, roles and exact queued NDJSON remain immutable on retry. The
same batch identities with different payload is a visible conflict, not overwrite.

### Delivery states and limits

- `queued:true`: enqueue transaction committed or matching existing item found.
  `delivered:true`: this turn has a validated successful server ACK; **not** proof
  of fresh search visibility. A drained older item is reported separately as
  `drained_delivered`. Error while enqueueing may leave durability uncertain; inspect
  queue/status before assuming a missing or delivered turn.
- Successful ACK requires HTTP 200, all expected identity receipts in order,
  `accepted == record count`, nonnegative integer `committed`, no `drain_error`.
  `committed` is a global drain count on older servers, so it need not equal batch size.
- Timeout/transport/invalid ACK, 408, 429 and 5xx retain payload and retry with
  exponential backoff from 5 seconds to one hour. The attempt is committed **before**
  network I/O; a crash consumes it. Lease is 60 seconds; restarted workers wait for
  an outstanding lease and replay identical bytes. Server idempotency handles
  acceptance-before-timeout/crash; local compact receipts prevent routine repeats.
- Other 4xx, including revoked/expired authorization 401/403 and conflicts 409,
  become retained `blocked`. After 20 attempts an item is retained blocked too.
  Neither new hooks nor secret rotation automatically reactivate it. Consent and
  retention are rechecked by the server for every attempt. The queue never bypasses
  these gates. Some failure responses can mean partial acceptance: **do not change IDs**.
- Limits per partition: 1000 undelivered entries (including blocked/leased),
  32 MiB retained payload, plus at most 10000 completed receipts. Done receipts
  cannot fill the undelivered quota. Under count pressure only oldest-created
  done receipts are pruned, transactionally with ACK/enqueue; pending/blocked
  data is never evicted. Full outstanding quota still reports
  `queue full; turn not queued`; callers must retain/reconcile the original turn.
- Queue status exposes configured `receipt_limit` and durable cumulative
  `receipts_pruned`. `receipts` is retained cache size, not lifetime delivered total.
  Local dedup/conflict memory is finite. An evicted replay sends the same frozen
  identities/payload to the server, which remains the durable conflict/dedup
  authority. Rechecked consent, grants and deletion barriers still apply:
  revoked/old-consent replay can become blocked403/409; never generate new IDs
  or automatically retry blocked records to work around this.
- Another worker can prune the current receipt before the hook reads it.
  `current_state:receipt_evicted`, `delivery_confirmation:not_retained` and
  `delivered:false` mean local confirmation is unavailable, **not proof of failed
  delivery**. `drained_delivered` describes the attempted item separately. This
  observation does not enqueue another copy. Use archive search for verification.
- SQLite reuses freed pages; logical rows/payload are bounded under consistent
  limits. Existing database files retain their historical high-water size; no
  automatic VACUUM or claim of immediate physical shrinking. The additive
  statistics table is compatible with existing rows. Restart existing scoped
  workers after a managed upgrade to converge old in-memory queue code, preserving
  leases; do not restart the archive or create extra workers.
- Delivered payload is removed with SQLite secure-delete; small hashed receipts
  remain. This does not certify forensic erasure from snapshots/backups/storage.
  Queued payload is never deleted on denial, age, retry exhaustion or capacity pressure.
  Deleting a spool is an explicit operator data-loss decision after stopping hooks
  and worker, checking pending/blocked status and preserving required records.
  No built-in purge command is provided in this release.

### Recovery without another hook

The hook makes at most one send attempt after enqueueing. Status emission has
its own short deadline and refuses FIFO/symlink/nonprivate file targets. It does not spawn a
background process. It is bounded by an 8-second whole-process alarm, 5-second
network wall budget / 4-second socket timeout, SQLite-native busy wait capped at 1 second per statement and clamped to the remaining hook deadline, a 1MiB
hook input limit, the last 32MiB of the transcript (a longer transcript is read from its tail, where the turn to capture is) and clamped read retries. It always exits 0, but status
errors must not be treated as delivery. These are POSIX process bounds, not a
real-time guarantee against a hung kernel/filesystem. Durable acceptance can occur
after the client deadline, so increasing timeout is not the correctness fix.

The same wrapper accepts (with the **same project/source/credential environment**):

```sh
sh ./claude-code-stop-hook.sh --status         # safe counts/oldest age, no text
sh ./claude-code-stop-hook.sh --flush          # one due item, bounded attempt
sh ./claude-code-stop-hook.sh --worker         # loop: one bounded attempt every 30s
sh ./claude-code-stop-hook.sh --retry-blocked  # explicit remediation only; resets attempt budget
```

`--retry-blocked` does not send or restore consent. Use it only after checking why
items were blocked and fixing authorization/service state. Retry remains subject to
current server consent/retention. **Never** use it as an automatic 403 loop.

A worker must run under an explicitly configured supervisor to recover after no
further hooks, logout, process crash or a Mac restart. `worker.launchagent.example.plist`
is a non-installed template: substitute explicit paths and project environment,
review it, and obtain deployment authorization. One supervisor per route/principal.
A hard wall deadline exits the worker with the durable lease retained; the
supervisor must restart it, after which the lease expires before replay.
It needs the same private credential file, not a copied secret. Keep the supervisor
pointing at the managed installation, not a temporary source checkout. macOS user
LaunchAgents start after login, not before it. Logs/status require normal retention
management; no unbounded payload logs are emitted. Worker emits attempted/errors/
blocked status, not idle polls. **Without a running worker or later hook, queued data
stays durable but delivery is not automatic.** Source tests do not prove live rollout.

### Verification and scope

`python3 -B test_capture_queue.py` tests offline/503 retention, response loss after
commit, byte-identical replay and receipt dedup, process restart/transaction death,
lease expiry/attempt ceilings, parallel writers, capacity, redaction, permissions,
route isolation, malformed ACK and recovery by a separately started worker.
`test_capture_auth.py` and `test_capture_bridge.py` remain required.
`test_sanitizer_parity.py` differentially checks 806 cases against the Go source
patterns; it explicitly skips if Go or server source is absent. These suites are
also included in `tools/run_tests.py` (non-storage-only mode).

This change does not install a supervisor, change live kit/hooks, migrate old missed
turns, fix server latency or change Codex capture. Codex's separate v2 catcher still
uses single-POST delivery and needs its own scoped queue integration.

### Shared global registration

For explicit multi-project enrollment, the managed `claude_capture_dispatcher.py`
provides one global Claude Stop entry with exact Git-root routing. Normal `kit.py
update` handles the approved registration and guarded retirement of duplicated
project hooks. See [global capture and update](../../../../docs/managed-capture.md).
Installing the bridge alone does not enroll or enable capture for any project.
