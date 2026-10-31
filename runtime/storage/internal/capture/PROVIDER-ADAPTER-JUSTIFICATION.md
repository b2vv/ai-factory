# Provider capture-adapter justification (D5 / AF3)

D5: no provider priority is selected by the owner; the first supported capture adapter must
be justified from verified public-interface capabilities, and both providers start
UNKNOWN/NOT_TESTED. This file records the status honestly.

## Generic (transport-neutral) fixture path — IMPLEMENTED, synthetic-only

`capture.Adapt(ProviderFixture)` is a neutral ingestion shape used for synthetic fixtures and
tests. It is NOT a provider format; it exists so the ingestion/consent/redaction/serve path
can be exercised without binding to any provider's native schema.

## claude-code (Claude Code session JSONL) — PARSER IMPLEMENTED, fidelity NOT_TESTED

`capture.AdaptClaudeCodeJSONL` is a REAL parser of a JSONL transcript whose assumed public
shape is one JSON object per line with `type`, `uuid`/`parentUuid`/`sessionId`, and
`message.role` + `message.content[]` blocks (`text`, `thinking`, `tool_use`, `tool_result`).

- Capability captured: original user-visible **text** blocks of `user`/`assistant` messages,
  with provenance (session, message id, parent, per-message sequence). This matches the D5
  archive goal (original user-visible history).
- Redacted BEFORE any record exists: `thinking` (hidden reasoning, P5), `tool_use` and
  `tool_result` (internal), Unknown block types now refuse the whole batch. Prohibited structured fields never
  enter a record.
- Recognized non-message lines (`summary`, `system`) are skipped; unknown event types,
  missing identity, role mismatch, unsupported content shapes and malformed lines refuse
  the whole batch. Summaries are never original history (D5).

LIMITATIONS (honest):
- Verified only against SYNTHETIC fixtures of the assumed shape. The exact upstream Claude
  Code transcript schema is NOT a verified contract here, and fidelity to a REAL transcript
  is **NOT_TESTED** (no real transcript is read in this phase).
- Known embedded credential indicators are now withheld BEFORE records/WAL by
  `known-credentials-v1`. An indicator withholds the entire message text, including
  nested or multiline secret-bearing structures. This can remove harmless examples.
  Unlabelled passwords, unknown credential formats/encodings and obfuscation may remain:
  this is NOT a complete secret detector or approval to import arbitrary histories.
- Sanitization changes payload bytes. Retry with the same rules is deterministic;
  re-importing existing identities from an older sanitizer may conflict. Never assign
  new identities merely to bypass conflicts, overwrite old data, or silently claim
  a complete archive. Original source files are never rewritten by these adapters.

## Native Codex transcript / Markdown adapter — NOT_IMPLEMENTED

No native transcript/Markdown adapter exists. A narrow documented lifecycle-event
subset is supported separately in [CODEX-EVENTS.md](CODEX-EVENTS.md); its transport
does not imply native automatic recording or complete conversation fidelity. Implementing one requires a verified public-interface shape and
synthetic fixtures for that format, plus its own justification entry here.

## Real-data capture — NOT ENABLED

No real session history is read in this phase. Enabling capture against real sources requires
separate per-source consent + allowlisting and explicit owner authorization of specific
sources and data.

## Codex export route (documentation checked; no private source access)

Official Codex CLI documentation describes `/export session.md` after a turn finishes,
which saves a conversation as Markdown. Source:
https://developers.openai.com/codex/developer-commands#export-a-conversation-with-export
This is a user-selected export route, not permission to access internal session stores.
No native Codex JSONL or exported-Markdown adapter is implemented here. Exact exported
message boundaries, stable identities, provenance and omission of hidden/tool material
must be verified on an explicitly selected sanitized sample before adding one. Do not
rename a Markdown export to JSONL or feed it through the synthetic fixture adapter.

Needed from the operator: exact allowed local export paths, project mapping, provider
and export version, stable source/session identifiers, and intended date/session range
(new plus historical is authorized for the four selected projects). Supply only a
small sanitized format sample initially. Do not supply credentials or hidden reasoning.
The documented CLI route does not establish availability in every desktop/web surface.
