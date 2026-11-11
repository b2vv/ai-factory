# Runtime helpers

Factory's runtime contains optional helpers, not one automatically running agent
service. Use the selected component's contract before executing it. Installing
files does not enroll a project, register hooks, start databases or change grants.

| Area | Purpose and entry point |
|---|---|
| Onboarding | `onboarding/preflight.py`: read-only project inventory; [contract](../docs/onboarding-helper.md) |
| Review | `review/review_package.py`: snapshot-bound review packages with hardened Git reads |
| Native handoff | `session-size/native.py` and the canonical `session_guard.py`: profile-required checkpoint/resume without Docker; [registration, update and recovery](../docs/managed-native-handoff.md) |
| Archive | `storage/cmd/factory`: local archive/capture/search service; MongoDB holds archive records, PostgreSQL holds the derived search index; [storage contract](storage/TAKEOVER-CONTRACT.md) |
| Archive search | [Read-only client](storage/deploy/search-client/README.md): configured project search-only access and bounded pagination |
| Capture | [Claude bridge](storage/deploy/capture-bridge/README.md) and [Codex catcher](storage/deploy/codex-capture/README.md): delivery adapters, with separate consent, credentials and host activation |
| Session excerpts | [Summary worker](storage/SESSION-SUMMARIES.md): opt-in asynchronous local extractive records, provenance and source-policy checks |
| Security scanners | [Scanner runner](scanners/README.md): explicitly selected inputs and isolated checks, not automatic product scanning |

## Compatibility components

`legacy/review/review_package.py` retains the original Git invocation policy.
`legacy/session-size/session_guard.py` retains the original default home-store
contract. These are explicit compatibility variants, not aliases for the current
native handoff route. Select exact paths; never resolve a helper by basename alone.

The optional `session-size-docker` component is retained for separately selected
legacy installations. Its [manual/store contract](../docs/session-size-docker.md#manual-operations-use-the-enrolled-store)
is not the setup route for managed non-Docker handoff. Do not register both paths
implicitly or migrate existing state merely because the package contains them.

Package fixtures prove helper behavior within their tested scope. Installed
configuration, live host delivery, archive completeness and model invocation need
separate evidence. See [managed kit connections](../docs/managed-kit-connections.md)
for component preservation and consumer verification during updates.
