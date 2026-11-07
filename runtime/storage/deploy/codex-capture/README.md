# Codex capture catcher (lifecycle-event delivery)

Delivers REAL current Codex CLI turns (the turn's user prompt + the final assistant answer)
to the running AI Factory storage engine via its supported provider endpoint
`POST /v1/capture/codex-event`. This is the delivery catcher only; the vetted Go adapter
(`internal/capture`, provider `codex-hook-v1`, `AdaptCodexEvent`) stays the sole authority
for redaction and credential sanitization before anything reaches the WAL/archive.

Companion to `../capture-bridge` (Claude Code). Same privacy/fail-safe discipline; the
difference is the Codex hook transport and the way a project is selected.

## Files
- `codex_capture_catcher.py` — selection + normalization + POST + visible status (all logic; unit-tested).
- `codex-capture-hook.sh` — thin command-hook wrapper that execs the Python with `-I`.
- `test_codex_catcher.py` — routing / normalization / sanitization contract tests (`python3 -I test_codex_catcher.py`).
- `test_codex_catcher_auth.py` — loopback auth / isolation / denial tests with a synthetic server and synthetic credentials.

## Verified hook contract (not invented)
Field names are taken from the official docs <https://learn.chatgpt.com/docs/hooks> and the
running server source (`internal/capture/codex_event.go`, built from `b1c195e` into the
deployed image `sha256:8eaa1669`). Confirmed with Codex CLI `0.163.0`.

Common stdin fields on every command hook: `session_id`, `transcript_path`, `cwd`,
`hook_event_name`, `model`. Event-specific:

| Event | Fields the catcher reads | Sent to the server |
|-------|--------------------------|--------------------|
| `UserPromptSubmit` | `session_id`, `turn_id`, `prompt`, `cwd` | `{hook_event_name, session_id, turn_id, prompt}` |
| `Stop` | `session_id`, `turn_id`, `last_assistant_message`, `cwd` | `{hook_event_name, session_id, turn_id, last_assistant_message}` |

Two events per turn share one `session_id` + `turn_id`; the server links them
(`turn_id/prompt`, `turn_id/assistant`, parent = `turn_id/prompt`). `SubagentStop` also
carries `last_assistant_message` but is **ignored** so a sub-agent message is never recorded
as a top-level turn. Every other field (`cwd` beyond routing, `transcript_path`, `model`,
`permission_mode`, `stop_hook_active`) is dropped and never transmitted. `session_id`/`turn_id`
must match `^[A-Za-z0-9_-]{1,160}$` (server `eventID`); a non-match is a quiet no-op.

## How a project is selected (explicit mapping, never cwd-inferred authority)
Codex installs a SINGLE global `~/.codex/hooks.json`, so — unlike the per-project Claude
bridge — the project cannot come from a per-project env. It comes from an explicit,
operator-authored mapping file given by `AF_CODEX_CATCHER_MAP`:

```json
{ "projects": [
  { "root": "/abs/path/to/project",
    "project": "<storage-project-uuid>",
    "source_instance": "codex-hook-v1",
    "credential_file": "/abs/path/to/<project>.cred.json" }
]}
```

The event's own `cwd` field selects the single row whose `root` is `cwd` or a parent of it
(longest-prefix, on a directory boundary). A `cwd` under no mapped root is a **no-op**:
nothing is read or sent. `cwd` only picks the row — the server independently authorizes the
row's scoped credential against the row's project UUID (`requireCapture` →
`authz.Authorize(..., OpCapture)`), so a wrong or spoofed `cwd` cannot capture into a project
the credential is not granted for. Keep the mapping file local (not committed); it holds
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

## Privacy / safety guarantees
- **Server is the redaction authority.** The prompt / assistant text is forwarded verbatim;
  the Go adapter applies `known-credentials-v1` before the WAL. The catcher never claims to
  sanitize conversation content.
- **Visible status, no secrets/payload.** Each run emits one compact JSON status line to
  stderr (and to `AF_CODEX_STATUS_FILE` if set) with `event`, `role`, `project`,
  `source`, `session_id`, `turn_id`, `delivered`, `http_status`, `accepted`, `committed`,
  `redactions`, and a `skipped`/`error` REASON — never message text, never the secret,
  never the server response body.
- **Nothing blocks the turn.** Any error (unparseable event, bad mapping, unreadable
  credential, HTTP/connection failure, denial) is recorded in the status and the hook exits 0.
- **Idempotent.** Re-delivering the same `turn_id` re-POSTs the same record; the server
  dedups an identical record and returns a 409 conflict for a *changed* answer under the same
  turn identity (never a silent overwrite). The catcher keeps no cursor.

## Install boundary (NOT done by shipping this)
Installing the wrapper into `~/.codex/hooks.json` requires establishing per-hook trust
(`config.toml` `trusted_hash`) and preserving any existing hook chain (on this machine
`hooks.json` is already used by the session-size handoff `native.sh`). That is a separate,
explicitly authorized operation. Shipping this directory changes no hook config and no trust.

## Scope
Codex CLI only. No backfill, no other providers, no transcript/rollout file reading, no
Markdown-export parsing, no global hook activation, no Go/adapter change, no image rebuild.
Real native Codex emission is **NOT_TESTED** here until the Codex usage limit lifts and hook
trust is established by the owner; the server path is proven by the tests and by the
synthetic integration test `internal/api/codex_event_integration_test.go`.
