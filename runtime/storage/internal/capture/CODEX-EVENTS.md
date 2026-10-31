# Explicit Codex lifecycle event intake

Status: documented-event subset implemented; native automatic recording OFF.
This endpoint does not install hooks, poll chat stores, read transcript_path, parse
Markdown exports, or prove that the current desktop/cloud host emits these events.
No real conversation has been imported by its synthetic tests.

## Supported input and provenance

POST /v1/capture/codex-event?project=PROJECT&source_instance=SOURCE with the existing
operator authentication. Capture must be enabled, the project enrolled and consent
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

Local command hooks are unsupported with cloud orchestration even when execution
is local. The current delegated workflow has not supplied actual event deliveries;
there is no automatic bridge enabled. Do not configure a local hook and claim it
works for cloud chats. Any future supported hook/MCP bridge requires explicit scope,
project mapping, trust and runtime permission; no global hook activation is included.

Official CLI export source:
https://developers.openai.com/codex/developer-commands#export-a-conversation-with-export
CLI /export session.md is a separate explicit Markdown export. Its exact message
format requires an operator-selected sanitized sample before a parser is implemented.
Desktop availability is not established by CLI documentation. No internal-history
path knowledge or denied-session access is required for a user-selected export.
