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
  `tool_result` (internal), and any unknown block type. Prohibited structured fields never
  enter a record.
- Non-message lines (`summary`, `system`, meta) are skipped; summaries are never original
  history (D5). Malformed lines fail closed.

LIMITATIONS (honest):
- Verified only against SYNTHETIC fixtures of the assumed shape. The exact upstream Claude
  Code transcript schema is NOT a verified contract here, and fidelity to a REAL transcript
  is **NOT_TESTED** (no real transcript is read in this phase).
- Content-level redaction of secrets embedded in free-text message bodies is NOT performed;
  only structured prohibited fields/blocks are dropped. Free-text DLP is out of scope and
  NOT_IMPLEMENTED.

## Second provider (e.g. a non-Claude assistant) — NOT_IMPLEMENTED

No adapter exists. This is NOT merely NOT_TESTED: there is no parser code for any other
provider's native format. Implementing one requires a verified public-interface shape and
synthetic fixtures for that format, plus its own justification entry here.

## Real-data capture — NOT ENABLED

No real session history is read in this phase. Enabling capture against real sources requires
separate per-source consent + allowlisting and explicit owner authorization of specific
sources and data.
