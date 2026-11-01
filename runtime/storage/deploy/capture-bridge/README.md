# Claude Code capture bridge (Stop-hook delivery)

Delivers REAL current Claude Code messages (the turn's human prompt + the final assistant
answer) to the running AI Factory storage engine via its supported provider endpoint
`POST /v1/capture/claude-code`. This is the delivery bridge only; the vetted Go adapter
(`internal/capture`, provider `claude-code`) stays the sole authority for redaction and
credential sanitization before anything reaches the WAL/archive. No Go code is changed.

## Files
- `capture_bridge.py` — selection + normalization + POST + visible status (all logic; unit-tested).
- `claude-code-stop-hook.sh` — thin `Stop`-hook wrapper that execs the Python with `-I`.
- `test_capture_bridge.py` — normalizer/selector contract tests (`python3 -I test_capture_bridge.py`).

## How it is wired (project-scoped only; never global)
Add a `Stop` hook to the target project's `.claude/settings.json` (or `settings.local.json`),
preserving any existing hooks. Configuration is by environment; **cwd is never used to infer
the project**:

| env | meaning |
|-----|---------|
| `AF_CAPTURE_PROJECT` (required) | storage project UUID — the explicit operator mapping |
| `AF_CAPTURE_OPERATOR_SECRET_FILE` (required) | path to the 0600 `operator.json` (`{"id","secret"}`) |
| `AF_CAPTURE_ENDPOINT` | default `http://127.0.0.1:8780` |
| `AF_CAPTURE_SOURCE` | `source_instance`, default `claude-code-dg` |
| `AF_CAPTURE_STATUS_FILE` | optional append-only status log (payload/secret-free) |

## Authentication — IMPORTANT, this is a temporary risk, NOT least privilege
The storage capture endpoints (`/v1/capture`, `/v1/capture/claude-code`, `/v1/capture/codex-event`)
are all **operator-only** (`requireOperator`). The registry defines an agent `capture` op
(`OpCapture`) but **no HTTP route authorizes capture with an agent/project-scoped token**.
Therefore this hook must present the **bootstrap operator secret**, which grants full
control-plane authority (mint/consent/grant/revoke/purge), not merely capture on one project.
Exposing it to a local hook script is an accepted **temporary risk**, not least privilege.
Mitigations in place: read at call time from a 0600 file, sent only to `127.0.0.1`, never
printed/logged/committed. Removing this risk requires a storage change: an agent-token capture
route (`OpCapture` on the HTTP capture handlers) so a project-scoped credential can replace the
operator secret. That change is out of scope here and is noted for a future narrow patch.

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
