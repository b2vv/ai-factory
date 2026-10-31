# Storage alpha contract and evidence limits

This is an owner-authorized experimental/default-off alpha, not full acceptance.
Independent storage review remains BLOCKED. Automatic DrainOnce reclaim is absent;
full WAL intake fails closed. Backups and backup-dependent destructive operator
activation are deferred. Publication does not activate real capture or databases.

## Archive query and receipts

Archive queries use a total order of session, sequence, source instance and message
ID. Mongo performs an indexed keyset scan with at most 1000 records / 8 MiB per
window and an operation deadline. A response contains at most the requested limit
(default 100, maximum 1000). Filtering and retention run before exposing records.
`next_cursor` is an authenticated encrypted continuation bound to project and
filters. Follow it even when a filtered window has no hits. `total` is present only
when `total_exact` is true; a partial window does not claim a global count. Search is
labelled `literal_substring_nfc_casefold`: NFC and Unicode case folding affect only
comparison copies, never original payload or identity bytes. This is not tokenized
full-text or stemming. Mixed English/Ukrainian synthetic fixtures use Unicode escapes
in the English-only source tree. Offset
compatibility is limited to the bounded first window. This is live pagination,
not a snapshot across concurrent additions or deletions.

Receipt identity is the canonical JSON tuple of project, source instance, session
and message ID. Legacy WAL aliases remain resolvable while retained. Archive
lookup distinguishes real errors from absence. Foreign project receipt lookup
returns not_found on all paths, including a BLOCKED journal. Health ingestion
counters require the operator secret. `processed` means checkpoint-covered, not
archive committed: quarantine can be processed while remaining durably retained.

## Control failures and helpers

A control persistence error can follow durable acceptance. HTTP reports 503 and
an unknown outcome; restart reconciles the control WAL before serving authority.
It is not safe to interpret the error as proof that an operator-requested grant
was never accepted. All runtime authority readers must honor control BLOCKED.

`cmd/identity-operator` accepts one bounded JSON request on stdin and operates on
the same control state under the exclusive process lock. Operations are status,
project, enroll, consent, grant and revoke. It needs no Docker or running API.
It cannot run concurrently with a server holding that control directory. The
same-OS-user trust boundary applies; secrets must not be supplied in command-line
arguments or recorded in transcripts. Python identity/token tooling remains
separate and does not become a second registry.

## Workflow cutover

`cmd/workflow-operator` performs an explicit offline cutover using `-state`,
`-document`, `-revision`, `-to`, `-dsn-file`, `-edits-frozen` and a project UUID.
For this offline helper the server must be stopped for the same control directory; external editing of
the dedicated workflow file must remain frozen until completion. A supplied
revision is the SHA-256 of the complete file. PostgreSQL credentials come from an
owner-only bounded file and are not echoed.

The v1 dedicated generated Markdown document contains canonical JSON task rows:
ID (stable nonempty string), Version (positive integer), and Fields (string map).
The document checksum covers the complete structured block. Human prose belongs
in a separate file. Noncanonical documents, manual edits and source-revision
changes are rejected. This does not import arbitrary existing task/stage/gate
Markdown formats; arbitrary-format adapters remain open. The operator can refresh this dedicated
Markdown-authoritative index using `-to index`, without changing authority. The
source revision is verified before and after the transaction; removed entities
leave the derived index. Task, stage and gate rows can carry stable IDs and their
kind/links in Fields. This is not a parser for unrelated Markdown conventions.

`GET/PUT /v1/workflow/task` provides scoped reads and fenced PG writes. Reads from
Markdown-owned projects report the index as potentially stale. Concurrent CAS,
stale epochs, project-specific revoke and backend errors are integration tested.

An authenticated operator can also use `POST /v1/workflow/cutover` on the running
server with project, dedicated document path, revision, destination, expected
authority epoch and explicit edit-freeze confirmation. Agent grants cannot invoke
this route. It keeps the shared server running and revokes only the selected
project on opt-out. Paths refer to explicitly operator-mounted server files.

A cutover holds the same authority fence as writes, verifies actual import/export
bytes, persists a receipt, then persists the flip in the single control WAL.
Receipt-only recovery retains old authority. Exported file bytes alone do not
transfer authority. PostgreSQL import is transactional; CAS cannot create a row
against a nonzero expected version or skip versions. Read errors are not absence.
The return to Markdown revokes workflow access for that project while preserving
other projects on a multi-project grant. Explicit grant reissue can authorize new
access. The old Manager EnablePG/DisablePG methods are in-memory fixture helpers;
they are not the durable production cutover entry point.

## Backup and restore

`internal/backup` implements logical snapshot/restore with complete-payload SHA-256,
version, timestamp and project authority epochs. The default CLI writes v2 framed
streaming snapshots (20 GiB file bound, 16 MiB frame bound), reading bounded archive
windows; legacy v1 snapshots remain readable with their 32 MiB bound. The complete
stream is verified before the first restore write. `cmd/backup-operator` exposes offline create, restore and expire using private
credential files. The backup repository enforces an aggregate 20 GiB budget,
including partial/unknown regular files, and serializes concurrent writers.
Publication is exclusive and synced; existing backups are never overwritten. It verifies restored Mongo
records and PostgreSQL tasks against the snapshot. Restore requires empty
project targets, current offline control ownership and matching workflow authority.
It never restores old grants or replaces the control registry. Current consent
cutoffs and deletion barriers filter archive records before writing them. A stale
or unavailable current control lineage requires operator recovery, not a fallback
to backup authority. Snapshots older than 30 days are rejected.

Restore is not a cross-database atomic transaction. An error reports partial
counts; the destination must stay offline until reconciled. This implementation
provides an explicit expiry command that verifies every named backup before deleting
only snapshots older than 30 days. Unknown files remain counted against the budget;
corrupt or future-dated snapshots refuse the entire expiry pass. There is no installed
background scheduler. Operators must freeze external writers and backup-file changes
during the explicit maintenance window and both restore verification passes.
Immutable backup bytes are not erased by deleting a live project.

## Reclamation and remaining gates

The explicit Reclaim primitive preserves pending/quarantined/opaque legacy
records and checks canonical records against archive payloads before compaction.
It is not connected to the worker or an automatic threshold. Automatic wiring
was rejected by approval review pending the receipt/metrics contract and has not
been retried. The proposed contract uses archive-backed canonical receipts after
reclamation; archive downtime then makes those lookups unavailable, and WAL
counters describe retained records rather than lifetime traffic. Legacy aliases
continue occupying WAL space. Approval and acceptance evidence for this operational
tradeoff remain unresolved. No routine fixed-cap self-recovery is claimed.

Other open gates include complete live-data reservation accounting, automatic
WAL reclamation prerequisites. Total control-lineage loss is a documented fail-closed
boundary, not an established extra mandatory recovery case. Scheduled invocation of the explicit backup expiry command is not activated. B5 implementation/testing
was approved for isolated synthetic databases. `cmd/migration-operator` supports
the reviewed workflow and derived-index migrations: it requires a verified current
backup, matching source/rows, Markdown authority and completed durable cutover
with project-scoped grant revocation where applicable. Unknown schemas or unmet
conditions refuse. It opens in maintenance mode without implicitly upgrading.
The executable down/up/restore synthetic test passed; independent review of
these changes is still required. Real provider-history compatibility, native host helper binaries,
replica-set and power-loss evidence are not established by synthetic Docker tests.

## Response and configuration boundaries

Final authorization and a bounded immutable JSON response snapshot are serialized
with authority mutations. Network delivery starts after the authority and mutation
locks are released. Revocation prevents subsequent authorized snapshots; it cannot
withdraw response bytes already authorized and queued for delivery. Oversized
responses fail closed with an operation-state inspection warning. No blocked
slow-client review probe was rerun; the independent re-review is INCOMPLETE/BLOCKED.

Disabling new capture does not disable access to retained archive records, receipts,
erasure, or replay of previously accepted records. PostgreSQL-only workflow writes
have their own usage meter and do not require Mongo or capture to be enabled.

## Derived index and lifecycle (schema 2)

PostgreSQL now holds rebuildable archive references, normalized token vectors and
source hashes. `GET /v1/search/query` requires the separate scoped `search` grant;
`archive.query` alone does not authorize it. A bounded keyset window is matched
with PostgreSQL `simple` tokenization after NFC/case folding. The response is
labelled `tokenized_simple_nfc_casefold`. Every hit is revalidated against current
Mongo payload bytes and the final privacy/authority fence. The index is never a
fallback archive. Empty filtered windows may still have an authenticated encrypted `next_cursor`.

The worker rebuilds at most 16 records from one project's bounded archive window
per cycle. Index errors do not retract an archive commit or retain the archive
queue for PG. Current usage measurement and serialized encoded reservations also
apply to this writer; exact physical-allocation bounds are not proved
by those encoded reservations. Operator health reports index availability/cycle
failure without exposing global diagnostics to agents. Restart restarts the
idempotent derived scan; no second durable authority registry is introduced.

Receipt `state` retains compatibility diagnostics and gains `indexed` when a
current PG source hash matches. `lifecycle_state` exposes pending,
durable_accepted, archive_committed, indexed, failed and cancelled; blocked
remains ambiguous rather than falsely failed. Pending/failed/cancelled requests
before durable acceptance are bounded RAM observations (10-minute TTL, maximum
10,000 hashed identities), labelled `observation=ephemeral_request_10m`. They are
not ACKs or a persistent failure audit and disappear on restart. Durable WAL and
archive proof always override these observations, including ambiguous Accept
errors and retries. Durable quarantine maps to cancelled lifecycle while retaining
its quarantine diagnostic and WAL evidence. No raw rejected payload is persisted.

A durable index-required marker is written before the first derived enrollment.
If PG is later disabled, complete project purge refuses until the known index is
reachable. With PG enabled, purge erases archive, derived indexes and eligible WAL
frames; partial failure remains explicit. Restore invalidates the destination's
derived index before source restoration, under current authority; rebuilding is
from current Mongo and explicitly enrolled Markdown, never stale index contents.

Migration 0002 binds the new tables through the existing global schema registry,
so a schema-1 image refuses startup rather than serving a purge path unaware of
indexes. The component also checks its own version witness. Guarded schema 2/1
rollback verifies locked shapes, current backup/source/cutover requirements and
bounded index source proofs: archive identities/hashes must occur in the verified
backup; document references must match their current authoritative ledger. Missing,
changed or oversized proofs refuse. No CASCADE is used. The initial workflow
rollback's current-authority requirements still apply.

## Explicit Markdown document adapter

`cmd/document-operator` runs offline against the exclusive current control state.
It accepts one bounded JSON request on stdin with Operation (`upsert`, `delete`,
`index`), Project, Root, Ledger, ID, Path and ExpectedRevision, and requires
`-exclusive-window`. Indexing additionally uses a private `-dsn-file`. There is no
crawler, automatic enrollment, host installation or hook activation.

Each enrolled source begins with `<!-- factory-document-id: "stable-id" -->`.
The remaining human Markdown bytes are never rewritten. A separate checksummed
Markdown ledger records stable ID, relative path, complete source revision,
monotonic version and deletion tombstones. Rename requires the old path to be
absent and preserves ID; deletion requires the source to be absent and retains its
last revision. A tombstoned ID cannot be reused; a new document needs a new ID.
Conflicting ledger revisions, edited generated ledger bytes and symlink/escaping
paths refuse. This is the specified adapter format, not support for arbitrary
existing Markdown conventions.

`GET /v1/documents/query` requires a scoped `search` grant and returns bounded
metadata/provenance, including current tombstones. Stale source/ledger references
are withheld and flagged `derived_stale`; PG data is not promoted to source
truth. Project barriers and final grant checks still apply. Source bodies and the
authoritative ledger remain user-owned files and are not included in the logical
Mongo/workflow backup; they must remain available for document rebuild/rollback.
A lost ledger cannot be reconstructed from deleted files and must not be silently
replaced with a new one while claiming prior tombstone continuity.

## Maintenance bounds and accepted contract clarification

D4 specifies a live-data cap including DB/index/control/dedup metadata and admission
before reservations exceed limits. It does not explicitly define allocated DB pages,
DB journals, filesystem quotas or an aggregate block-allocation metric. Encoded payload
reservations alone do not cover every named component; that accounting issue remains
open. A system quota is an optional stronger enforcement mechanism, not an inferred
mandatory architectural requirement. No system quota changes are implemented.

P7/P13 require current epochs/barriers during restore and authority recovery evidence.
They do not explicitly require recovering after every copy of the control lineage is
lost. Restore with retained current registry remains supported; absent current authority
refuses. An external freshness witness would be additional scope, not a new requirement.

Explicit reclaim selection uses bounded 128-record / 16-MiB reads of the existing WAL
format. Appends preserve scanning of the captured prefix; generation replacement,
shrinkage or same-size mutation restarts selection. Before any maintenance marker/checkpoint or
staging write, the old generation, staged generation and transition metadata must fit
the configured WAL cap. Insufficient room refuses without eviction or cap increases.
The final generation validation/install/reopen still performs linear work bounded by
the configured input byte cap; it is not an incremental flip or a wall-clock latency
promise. Automatic DrainOnce reclaim wiring remains OFF pending normal reevaluation.

Maintenance also accepts an explicit peak ceiling derived from current measured
live/free budgets, and preserves policy-withheld records even if an older archive
copy exists. Admission arithmetic refuses negative usage and overflow. These do
not complete overall D4: archive duplication/index expansion and control growth
still need one coherent reservation model. Current DB-size measurements and encoded
write estimates are different quantities; they must not be presented as an exact
shared cap. A prepared automatic DrainOnce patch was rejected again before execution
pending fresh explicit owner approval; it has not been applied or rerouted.


## Shared-budget corrections (not full D4 acceptance)

The ingestor now reserves the WAL record plus the BSON archive document and declared
Mongo index-key representations. Accepted but unprojected archive liabilities are
reconstructed from the durable WAL on restart. Duplicates consume no new reservation;
terminal quarantine releases only its future projection liability, retaining WAL bytes.
A monotonic counter covers writes, including partial failures, and projections that
occur after another request samples usage. Exact-fit tests distinguish this from
incorrectly charging the same pending liability twice.

The factory composition uses SetSharedUsageMeter for control and data admission.
Control persistence reserves its WAL mutation and metadata staging bytes before
writing. Refusal returns not_accepted and blocks serving authority, including after
an in-memory revocation, rather than acknowledging an unpersisted mutation. The
standalone control helper currently checks local default limits only; that is not a
complete external-store shared budget. SetUsageMeter remains a capture-only test
injection point and does not replace production SetSharedUsageMeter wiring.

These are minimum known representation reservations, not a new definition of the
accepted live-data metric and not a proof of Mongo/PG physical allocation bounds.
Complete admission for offline document/index, restore and workflow-cutover writes,
backend-specific metadata/staging growth, and consistent configured accounting across
standalone helpers remain unfinished. D4 and overall acceptance remain open.

## Whole-writer budget inventory and pending metric decision

Restore v1/v2 now preflight the entire permitted archive/workflow transfer through
ReserveExternalBytes before either destination is touched. Cutover reserves import
rows or the full Markdown temporary copy before transfer. Document-operator uses
budgeted ledger/index/required-marker variants; marker duplicates reserve zero.
Workflow CAS includes project/primary-key representations and uses the live-only
admission dimension. Explicit ReclaimWithUsage retains pending archive liability
under the ingest lock when computing the maintenance peak. DrainOnce is unchanged.

Known serialized minima and pre-write denial are not the complete durable budget
ledger. External reservations survive ambiguous failures in the current process,
but are not a persisted cross-process accounting inventory. Offline helpers still
use default local accounting, not the server's complete backend/configured usage.
Backend startup schema/index creation, PG full-text/index representation, watermark
staging and all active external generated-file inventory need one consistent metric.

Owner decision pending: (A) a versioned logical live-byte inventory of every managed
row/index entry, control/dedup record, generated metadata and staging copy, with WAL
and DB duplicates counted separately, or (B) the current backend allocated-size
measurements as the hard admission metric. A permits exact encoding-based reservation
and must explicitly exclude database allocator slack/journals from that logical cap;
physical free headroom remains measured separately. B requires a demonstrated backend
allocation reservation mechanism; serialized estimates do not establish it. Neither
choice is silently adopted. The accepted documents name components and numeric limits
but do not resolve these units. No system quota requirement is inferred.

## Owner scope update: logical-v1 budget and deferred backups

The live cap uses versioned logical representations of managed data, declared
index entries, control/dedup metadata and temporary generations. Physical free
headroom is checked separately. This is not a MongoDB/PostgreSQL allocated-page
quota. Durable accounting must cover server and offline writers under the same
exclusive control-state ownership fence; unknown outcomes retain liability.

Backup/restore delivery is deferred by the owner's 2026-10-31 scope decision.
Existing implementation and evidence are retained, but backup-operator and the
backup-dependent destructive migration-operator entry points refuse activation.
No total-disk/state-loss recovery guarantee is made. Ordinary process restart,
WAL durability, authorization, revocation and deletion barriers remain required.

Automatic DrainOnce reclaim wiring remains unapplied after a renewed approval
review rejection. Explicit synthetic maintenance tests do not establish automatic
reclamation acceptance. The separate independent security review remains blocked.
