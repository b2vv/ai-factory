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
committed counts and independent retrieval determine archive availability.

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
- **Server is the redaction authority.** The prompt / assistant text is forwarded verbatim;
  the Go adapter applies `known-credentials-v1` before the WAL. The catcher never claims to
  sanitize conversation content.
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
