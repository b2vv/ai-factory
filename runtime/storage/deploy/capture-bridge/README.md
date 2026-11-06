# Claude Code capture bridge (Stop-hook delivery)

Delivers REAL current Claude Code messages (the turn's human prompt + the final assistant
answer) to the running AI Factory storage engine via its supported provider endpoint
`POST /v1/capture/claude-code`. This is the delivery bridge only; the vetted Go adapter
(`internal/capture`, provider `claude-code`) stays the sole authority for redaction and
credential sanitization before anything reaches the WAL/archive.

## Files
- `capture_bridge.py` — selection + normalization + POST + visible status (all logic; unit-tested).
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
| `AF_CAPTURE_SOURCE` | `source_instance`, default `claude-code-dg` |
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
  types are counted and surfaced in the status by **type name only** (never content), so a
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
  (409), never a silent overwrite. The bridge keeps no cursor; the server is the source of truth.
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
