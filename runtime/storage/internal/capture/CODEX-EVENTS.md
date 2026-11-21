# Explicit Codex lifecycle event intake

Status: documented-event subset implemented; native automatic recording OFF.
This endpoint does not install hooks, poll chat stores, read transcript_path, parse
Markdown exports, or prove that the current desktop/cloud host emits these events.
No real conversation has been imported by its synthetic tests.

## Supported input and provenance

POST /v1/capture/codex-event?project=PROJECT&source_instance=SOURCE with project-scoped capture-only authentication or existing operator transport. Capture must be enabled, the project enrolled and consent
for provider codex-hook-v1 enabled. Existing barriers, epochs, budget and fail-closed
rules apply. Body limit is 1 MiB. The operator explicitly maps a trusted source to
one project; cwd is never used to infer membership or grant authority.

UserPromptSubmit requires hook_event_name, session_id, turn_id and a string prompt.
Stop requires the same identity fields and a string last_assistant_message. Missing,
empty or unsupported events fail closed. All other payload fields are ignored and
never persisted: transcript_path, cwd, tools and hidden reasoning are not consumed.
Session and turn IDs must use 1-160 ASCII letters, digits, underscores or hyphens.

Records use provider codex-hook-v1, explicit source_instance, original session_id
and MessageID turn_id/prompt or turn_id/assistant. The assistant parent is
turn_id/prompt. Seq1/2 orders roles only; it is NOT a global turn chronology.
Search returns these original identifiers with the decision text. Identical replay
is idempotent across restart. A changed final answer under the same turn identity
returns a conflict; it is never overwritten or assigned a fresh identity to hide it.
The source mapping must remain stable across retries.

Known-credentials-v1 sanitizes visible text before WAL; it can withhold innocent
examples and miss unknown secrets. This is not approval to import unreviewed inputs.
Input files remain external and unchanged; this transport does not open any files.

## Capture limitations and official contract

Official source: https://developers.openai.com/codex/hooks
UserPromptSubmit supplies prompt; Stop supplies last_assistant_message. These events
are NOT a complete transcript: intermediate assistant messages, interrupted turns,
continuation behavior and missing delivery can create gaps. Generated continuation
prompts are not necessarily human-authored. No event here proves a complete session.
SessionEnd is not an automatic per-turn Markdown export. transcript_path has an
unstable format and is intentionally never read.

Local command hooks do not establish capture for cloud-orchestrated chats, even
when execution is local. The isolated native CLI evidence below applies only to
that local CLI; it does not establish delivery for this delegated conversation.
Do not configure a local hook and claim it works for cloud chats. Any future supported hook/MCP bridge requires explicit scope,
project mapping, trust and runtime permission; no global hook activation is included.

Official CLI export source:
https://developers.openai.com/codex/developer-commands#export-a-conversation-with-export
CLI /export session.md is a separate explicit Markdown export. Its exact message
format requires an operator-selected sanitized sample before a parser is implemented.
Desktop availability is not established by CLI documentation. No internal-history
path knowledge or denied-session access is required for a user-selected export.

## Opt-in v2 Stop snapshots

POST /v1/capture/codex-event-v2 is a separate endpoint. It requires explicit
codex-hook-v2 capture consent and schema_version integer 2. Stop also requires
stop_hook_active boolean; prompt must not contain this flag. Existing auth, consent,
retention, capacity and immediate-before-write authority gates apply unchanged.
Success acknowledges X-AF-Codex-Contract: 2. The catcher requires this version;
there is no fallback to the legacy endpoint or implicit v1 consent inheritance.

V2 IDs are v2/<turn>/prompt and v2/<turn>/assistant/<sha256 of exact sanitized UTF-8
text>. Parent points to the v2 prompt. Hashing happens after known-credentials-v1,
so no digest of withheld raw content is persisted. The sanitizer and snapshot
identity contract are versioned together: changing sanitization semantics requires
explicit compatibility review. Provider is codex-hook-v2 but is not an archive
identity dimension; the ID prefix prevents collisions with historical v1 records.
V1 records, hashes and replay/conflict behavior are preserved.

A native CLI 0.163.0 synthetic experiment confirmed two changed Stops in the same
turn, with stop_hook_active false then true. V2 stores both distinct sanitized
snapshots. Identical text, including a flag change or retry after restart,
deduplicates. Different withheld texts intentionally share the redacted snapshot.
Seq remains role-local; neither digest nor sequence gives chronological order.
The hook cannot know other concurrent hooks' decisions, so snapshots are not
labelled final. If Codex emits a later final Stop and it is accepted and retrieved,
its text is retained. No guarantee covers missing events, interruptions or complete
transcripts. Native evidence is limited to the isolated experiment; live project
activation and actual catcher/search proof remain separate checks.
