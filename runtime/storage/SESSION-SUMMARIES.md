# S1 — Automatic archive session summaries

Status: IMPLEMENTED_SOURCE_ACCEPTED; runtime activation authorized and tracked separately. Owner confirmed the proposed test seams and local explicitly
extractive generation on 2026-11-10. Independent scoped Spec and Standards accept
the implementation. Production activation remains OFF/unapproved; live calibration
is PARTIAL. Whole-storage alpha acceptance remains BLOCKED.
Index: [Factory roadmap E6.1](../../ai-factory/roadmap.md#archive-session-summaries).
This is the single primary task/spec/plan; private raw evidence is separate.

## Checkpoint and ownership

Source baseline: `840d90fc1c7bd84de8708c8dd4af2983128ed306`, initially clean.
Main repository, one Codex writer on `feat/session-summaries`; no worktree/clone.
Existing independent reviewer: `/root/retrieval_review`. Full planning uses four
clean-context plan-critique lenses and an independent defense; implementation review
is separate. Relevant impact was checked by direct code/file search rather than an
unverified graph. Foreign edits block only affected scope; do not stash/reset them.
Current stage: completed source verification on main successor
`5abf824550299da4030ab58f446e60a999b94040` without reverting the non-Docker
handoff repair. Stash `ed833a13ca1ca5ad90bc2490f7c05f2c2d866aaf` and verified
private backup remain intact. S1.2b1 consent Spec/Standards accepted. Pipeline
plan/critique/defense accepted. Mongo adapter, worker, serving/search gates and
retained projection cancellation are implemented. Final source integration, finite
mutation evidence and scoped independent acceptance passed. Exact package export,
metadata verification and exporter fixtures passed; no live activation.

## Owner decisions and scope

The owner approved automatic asynchronous session summaries: MongoDB retains original
messages and distinct derived summary records; PostgreSQL indexes both, never becomes
archive authority. Defaults: active deadline 30 minutes from the first new message
after previous coverage, or 15 minutes after last activity, whichever occurs first.
Only new original messages start a timer. Input-byte protection is secondary; message
count is not the principal trigger. Settings need validation on real sessions.

A summary identifies project/provider/source/session, branch provenance (unknown when
not reliably known), exact source identities and hashes, observed coverage/cutoff,
generation, creation time, generator/version and freshness. Original messages remain
facts; a committed archive checkpoint proves neither complete native capture nor
provider-history completeness. Late source events use capture/arrival time for these
timers, not their historical event timestamp.

Excluded: implicit historical backfill, provider transmission, credentials/grants,
project/host hooks or trust changes, live DB/schema migration, deployment or release.
The request does not choose a model or authorize sending archive text externally.
Local executable inventory found no Ollama/llama-server and no responding local Ollama
endpoint. Existing Codex/Claude access is not authorization to upload archive text.
The owner selected the first option: local explicitly extractive generation without
LLM. Output must identify itself as excerpts, not semantic synthesis. No external
model provider, archive upload or production rollout is authorized.

## Research and reuse

- `internal/archive/archive.go`: TypeSummary already exists. Record identity/content
  hashes include the current Record; adding fields can invalidate old identities.
- `internal/archive/metadata.go`: captured_at, source_event_time and committed
  generation/ordinal are outside Record. Legacy historical times remain unknown.
- `internal/capture/capture.go`: accepts supplied summary text; no automatic generator.
- `internal/control/archive_transaction.go`, `internal/ingest`: reuse source reserve /
  WAL / majority Mongo commit / retry recovery and existing budget gates.
- `internal/search`: existing archive projection already indexes typed records.
- `internal/api/{message,context,recent,search}.go` and retention: every serving path
  must validate derivation/source policy, not only the summary's own capture epoch.
- `cmd/factory/main.go`: asynchronous drain/index workers exist; generation must not
  run in capture requests or hold the authority fence during model execution.
- `internal/control/control.go`: unknown mutation kinds fail closed. A future explicit
  summary-format activation witness must make pre-feature readers refuse the state;
  a documentation-only downgrade prohibition is insufficient for privacy.

There is no existing product task tree in this source checkout; the existing roadmap
is the index. Do not copy another project's task directory or add a parallel tracker.

## Plan and readiness by slice

### S1.1 — Provider-independent scheduling and coverage contract

Proposed public seam: `summary.Plan(config, now, input)` returning a bounded decision,
trigger reason, selected new-message coverage and next due time; no IO, network,
model call, database, timer goroutine or live source text is required for this slice.
Inputs are one explicitly complete bounded session/branch observation at a supplied
source cutoff; incomplete observations return NOT_READY, not a false idle decision.
Completeness in S1.1 means all originals and accepted coverage for the supplied
scope from activation through the fixed cutoff, not a single archive page. A caller
seeing `Window.More` must continue; exceeding its bounded observation budget returns
NOT_READY with backlog diagnostics, not a partial idle/active decision. Multi-page
bounded aggregation for large sessions belongs to S1.4 and remains a readiness gate;
this first seam does not claim every session size is supported.
IDs include project/provider/source/session/branch-known state. Never treat Seq as a
reliable clock or infer a Git branch from ParentID. Unknown branch is explicit.

The default deadline is min(first-uncovered captured_at + 30m,
last-uncovered captured_at + 15m). `now` before any supplied capture/activation time
or caller-supplied clock floor is refused. A wall-clock retreat still later than all
those times is not detectable by this pure function; it does not promise detection.
The future worker must supply/persist an observation floor and revalidate it after
restart, or explicitly report clock continuity unknown. Unknown times or incompatible
generation/coverage are explicit refusal/revalidation, not invented timestamps. No uncovered originals means no job. Summaries never trigger
summaries. Full identity, payload hash AND canonical scheduling metadata (generation, ordinal,
capture/source-event timestamps and legacy flag) define an exact retry. Conflicting
payload or metadata under the same identity, or reused project/generation ordinal
for different identities, is an error; deduplication order cannot choose a deadline. Repeated Seq across sources is allowed.
New late arrivals are uncovered by identity/hash, not skipped by a prior ordinal.

The input-byte limit applies to complete original records; a due size-protection job
selects a deterministic bounded prefix. It must not silently truncate a message or
claim uncovered messages as summarized. A single oversized record is explicit
BLOCKED_NEEDS_CHUNKING; chunk semantics require a later reviewed extension. Scan / reference
bounds protect memory and are not a fixed message-count summary trigger.

Coverage evidence manifests bind sorted source references/hashes, scheduling metadata,
generation, observed cutoff, branch status and generator/config version. Separate this
evidence digest from the job identity: the job key binds selected source coverage and
processing-policy/config/generator version, but excludes invocation time AND the
observation cutoff. An unrelated commit advancing the cutoff must not mint a new job
for unchanged selected coverage. Durable reconciliation/CAS for competing intents
belongs to S1.2; do not claim exactly-once generation from a pure digest alone. Unknown legacy time
cannot start an automatic clock. Require an explicit activation baseline containing
project, source generation, committed ordinal and activation time; project/generation
must match the observation and 0 <= activation ordinal <= observed cutoff. Missing,
stale-generation or future baselines refuse planning. Only original records with
committed ordinal strictly greater than this baseline are eligible. Thus late source
event times with newly committed ordinals remain eligible; empty previous coverage
never means summarize all history. Persisting this baseline belongs to blocked S1.3
activation, not an in-memory default or a fabricated zero baseline.

#### S1.1 validation and deterministic decision rules

Archive identity remains exactly (project, source instance, session, message ID),
as in `archive.IdentityKey`; provider/branch are job-scope/provenance constraints,
not extra identity fields. Reject any foreign project/provider/source/session,
conflicting branch declaration, invalid UTF-8/empty required IDs or IDs over 4096
UTF-8 bytes (provider at most 256). Validate all identities/conflicts before treating
any item as previous coverage. Require canonical v2 metadata in the supplied source
generation, positive unique ordinals <= observed cutoff, and the matching explicit
activation baseline. Repeated canonical envelope is a retry; same identity with any
payload/metadata disagreement or different identities at the same ordinal is an error.

Configuration requires positive active/idle durations and input/observation/reference
byte budgets; input <= observation, input <= 8 MiB, observation <= 32 MiB, reference
budget <= 1 MiB. Starting defaults: 30m/15m, 256 KiB input, 8 MiB observation,
256 KiB references. These byte defaults are implementation assumptions to validate
on real sessions, not an owner-observed safe size. Unknown branch stays explicit;
a named branch is not inferred from Seq, text or an unrelated project Git checkout.

Use min/max captured_at across all eligible uncovered originals for first/last
activity. Sort the selected prefix by committed ordinal ascending, never Seq or
source-event time. Byte accounting is the exact length of canonical
`archive.EncodeEnvelope` JSON plus one newline per input envelope; no partial
message or Unicode split. This bounds that input stream, not a future model prompt's
framing/token cost; an adapter must budget its complete request separately. Previous
coverage does not consume the new-input stream budget. Oversized source/observation/
reference inputs return an explicit refusal/backlog, not an empty-success decision.

At total new-input bytes >= input budget, size protection is due immediately; choose
the largest nonempty ordinal prefix within the budget. An oversized first record
blocks pending coverage, without silently skipping it for later smaller records.
Otherwise dueAt = min(first+active, last+idle), with inclusive `now >= dueAt`. Choose
the earlier time's reason; an exact active/idle tie is idle. Size protection takes
precedence if also due. Below every deadline and byte bound, return next due time
without a job. Validate now/activation/capture/floor timestamps and checked additions
within the supported UTC JSON time range; overflow, zero or out-of-range time
refuses. Do not claim to detect an unobservable wall-clock retreat.

S1.1 READY: planning gate accepted and owner confirmed the testing seams.
This slice does not claim a deployed background generator or persisted summaries.

### S1.2 — Generator and durable publish

Generator choice is resolved as local extractive. S1.2a below is the proposed pure
generation slice; persistence/serving changes still require their affected design
gate before code. No arbitrary URL/command provider, secret fallback or network.

#### S1.2a — Local extractive content seam (planning accepted; code review open)

`GenerateExtract(config, now, input, outputOptions)` calls the accepted `Plan` itself,
then returns a typed document plus that decision; NOT_READY produces no content.
It does not trust a caller-mutated Ready flag. Repeating the pure planning work is
bounded and avoids a new provider framework or a separate mutable capability token.
No persistence, model invocation, network or consent mutation occurs here.
The built-in extractor owns ID/version `local-extractive-prefix/1`. A public
`ExtractiveVersion(outputOptions)` derives its effective processing version from
that ID plus canonical semantic options (currently excerpt byte length). Validate
options first; GenerateExtract accepts only an empty generator label or this exact
derived version, refusing incompatible caller labels. Bind that effective version
into the Plan input before calling Plan; callers predicting job IDs use the same
function. Changing excerpt policy changes JobID; unchanged policy remains stable.
The maximum-document admission limit does not change text when output fits, so it
is excluded from the semantic generator version; lowering it never deletes an
already accepted record or authorizes partial output. Changes to extraction rules
require a built-in version bump, rather than relabeling arbitrary output as local.


The compact JSON document format is `ai-factory.session-extract/1`, kind
`extractive`, with an explicit notice: prefix excerpts, not a semantic summary;
originals remain facts. It includes JobID, generated_at (supplied valid UTC `now`),
full coverage manifest and evidence hash. Each selected original contributes exactly
one ordered excerpt with identity, role, original UTF-8 byte length, start=0/end
offset and truncated flag. Choose the longest UTF-8-valid prefix <= excerpt byte
limit; do not normalize/rewrite source text, label guessed decisions, omit a source
silently or claim an excerpt contains the whole original when truncated. Unknown
branch/capture completeness remains explicit. Empty text yields an empty excerpt.

Defaults to validate: 1024 bytes per excerpt and 1 MiB compact document maximum.
Both are positive configurable generation options; excerpt <= document, document
<= 1 MiB. These protect a local aid, not an LLM context window. Budget the full JSON
including manifest, metadata, escaped text and delimiters, not only text lengths.
Bound input/field counts and cheap string lower bounds before large serialization;
then admit header and each bounded excerpt with exact encoded sizes. If the complete
proof plus one excerpt per source cannot fit, return explicit OUTPUT_BUDGET without
a partial document or silently claiming coverage. The future worker reports backlog
and needs an explicit smaller input budget/replan; no message drop or automatic cap
expansion. Config/clock/UTF8/schema errors fail closed. Pure extraction proves no
consent, retention, durable commit, serving currentness or index freshness.

JobID remains a coverage/processing key; generated_at and observed-cutoff evidence
can differ on repeated pre-publication observations. S1.2b must recover prior durable
WAL work and lookup the job before accepting another body. The first durable accepted
body wins; later retries reuse it, not overwrite it or claim exactly-once computation.
This is a required persistence gate, not achieved by this pure helper.

Tests at the approved summary/publish seam: exact Unicode boundary, literal source
fragments and role/identity offsets, empty/not-due cases, output exact byte budget,
malformed options/time and large-input allocation refusal. Generator/version labels, changed excerpt policy versus admission-only bounds,
forged caller labels and structured provenance are checked through actual output,
not wording snapshots.

S1.2a defense (independent planning acceptance received on 2026-11-10):

| Question | Exact pure-extraction answer |
|---|---|
| Malformed input | Reuse Plan validation; validate output options and actual extractor identity before planning; bound complete escaped JSON and return no partial document on budget/schema/time error. |
| Dependency failure | No dependency/provider/network in this slice. Durable store and policy failures remain explicitly unimplemented downstream gates. |
| Race/repetition | Same inputs/semantic options produce the same coverage key and literal prefixes. generated_at/cutoff evidence may differ; S1.2b must recover and reuse the first durable body before accepting a retry. No exactly-once computation claim. |
| Empty/bounds | NOT_READY yields no document; empty originals have empty excerpts, byte endpoints stay UTF-8 valid, every selected source has one excerpt or the whole document is refused. |
| Rollback | Source-only optional helper, no persisted state or host changes; removing it needs caller checks. No live downgrade/erasure is authorized by this slice. |

Use existing authoritative Mongo archive and WAL protocol for TypeSummary. Preserve
original Record shape/identity. Store versioned derivation/provenance outside original
Record metadata or as a strictly recognized derived payload; choose the exact encoding
in the affected design gate before code. Do not add an independent authoritative PG
summary table. Durable jobs/checkpoints must be derived from authoritative source and
persisted accepted summaries or Mongo metadata, not an in-memory exactly-once claim.
Crash after durable acceptance and before receipt completion must reuse/reconcile the
same job, never mint duplicate jobs or silently accept changed generator text.

Snapshot bounded source under authority, release locks for generation, then re-read
source hashes, generation and current consent/deletion policy immediately before
WAL/Mongo acceptance. Reject stale work. Serialize with existing capture/delete authority
and retain budgets/backpressure. Generator errors/timeouts have bounded backoff and
observable diagnostics without source text; capture does not wait for generation.

### S1.3 — Serving, indexing and activation compatibility

BLOCKED on exact encoding/policy design. Summary generation needs an explicit configured
local project/provider derivation opt-in; capture consent alone does not authorize
external processing. Separate capability/epoch semantics cannot be conflated with capture
epochs. Before serving/indexing, validate all covered original identities/hashes and
current policy. Removed/withdrawn/revoked sources withhold stale summaries. Backend
failure is unavailable, not an empty set or valid summary. Rebuild PG from Mongo.
New source messages label prior coverage partial; invalidated input requires a new
version rather than editing historical original records. Re-generation must be safe.

An explicit control witness must precede first new-format writes and cause old readers
to refuse at startup. Activation is default OFF. Downgrade requires reviewed quiescence,
export/reconciliation; never delete originals or simply disable serving guards.

### S1.4 — Runtime and real-session verification

BLOCKED on prior slices and authorization for actual session processing. Add a separate
bounded worker with stop/join ordering and configurable scheduling/input/time budgets.
Reuse existing accounting and mutation fences; no new scheduler framework. Validate
against isolated Mongo/PG and synthetic consent/retention changes, crash/retry/restart,
late writes and index rebuild. Then evaluate representative real sessions under the
chosen local/authorized generator without claiming native capture completeness.
No production rollout or automatic new consent/grant is implied.

## Acceptance and test seams (owner confirmed, including consent counters)

| ID | Scenario | Observable result / test boundary |
|---|---|---|
| A1 | No new originals / summary-only input | No job; Plan decision |
| A2 | Continuous activity through 30m | Due at active deadline; fake clock |
| A3 | Earlier 15m idle, including exact boundary | Due at idle deadline, never before |
| A4 | Byte safety limit / oversized single message | Bounded exact coverage / explicit chunking blocker |
| A5 | Late arrival, restart, duplicate/conflicting identity or metadata, ordinal collision | Deterministic job; late source not skipped; payload/metadata/ordinal conflict fails |
| A5b | Same selected coverage, unrelated commit advances observed cutoff | Same job key; evidence manifest reflects changed observation |
| A5c | More pages / observation resource bound exceeded | NOT_READY until complete scoped observation; explicit backlog when over bound |
| A6 | Unknown time, now before supplied clock floor/capture/activation, incomplete scan, unknown branch | Explicit unverified/refusal; no invented chronology; unobservable wall-clock retreats not claimed |
| A6b | Baseline ordinal 10, old timed record 8, new late-event record 11 | Only 11 eligible; missing or wrong-generation baseline refuses |
| A7 | Provider failure/timeout or crash around durable commit | Capture independent; bounded retry; idempotent publish |
| A8 | Revocation/deletion/source change before publish or serve | No derived text published/served; fences + HTTP seams |
| A9 | Cross-project/source/session and forged derivation | Refused; no scope expansion |
| A10 | Mongo down / PG down, restart/rebuild | Mongo remains authority; honest availability/index status |
| A11 | Old reader / downgrade after activation | Refusal, originals and rollback evidence preserved |
| A12 | Representative real sessions under selected generator | Measured settings/quality/coverage, explicit limitations |

No tests have been run for new code; no required gate is PASS by declaration.
Test seams proposed: pure Plan decision; durable worker/policy publish boundary;
existing archive/search serving HTTP boundary; isolated Mongo/PG adapter contracts.
The TDD skill requires owner confirmation before tests at a new seam.

## Side effects, migration, rollback and defense

S1.1 changes source only and has no persistence migration; rollback removes the optional
module after caller checks. Later slices require a versioned compatibility witness,
bounded budget reservations and verified isolated upgrade/rollback before any live action.
Persistent control/Mongo/PG actions are separate from source implementation and remain off.
A source commit/push or live rollout is not implied by planning status.

| Defense question | S1.1 answer / retained downstream gate |
|---|---|
| Malformed input | S1.1 validation rejects mixed scope, metadata/ordinal conflicts, beyond-cutoff records, invalid baseline/config/time/reference bounds. No source or persistent writes. |
| Dependency failure | S1.1 has no IO or provider dependency. Later generator/store failure behavior remains BLOCKED in S1.2; no self-awarded integration pass. |
| Races and repetition | Deterministic ordinal prefix; full-envelope retry equality; job key excludes invocation time/observation cutoff. Durable CAS/source-policy revalidation is a separate S1.2 gate. |
| Empty and boundary | A1/A4/A5/A6, inclusive exact byte/deadline rules and explicit overflow/oversize/backlog refusal above. |
| Rollback | S1.1 source-only optional module removal; no live state. S1.3 compatibility/persistence rollback needs isolated proof before activation. |

Independent defense accepted these five answers on 2026-11-10 against design digest
`bdba0f10c8fa277cbdf09c53f9b5aa9d7a9ee3b92c413be7b10da842b727651b`.
This verdict is not implementation or runtime acceptance.

## Next action

Keep the verified source/package bytes bound to their evidence. Any new edits need
appropriate affected checks. Live activation is a separate operator decision: use a
compatible version, verified recovery procedure and current grants/consents. Complete
unavailable-source evaluation before claiming full calibration. Do not erase retained
witnesses to force downgrade. No host installation or runtime operation is implicit.


## Historical planning checkpoint — 2026-11-10

Historical snapshot below is superseded for implementation status by the current
verification checkpoint at the end; its original scope/evidence is retained.

Four clean-context plan-critique lenses launched / four returned. AI-slop and
complexity: explicit clean. Logical lens: two blockers (clock evidence, activation
baseline); edge lens: two blockers (metadata equality, cutoff-dependent job identity)
and one nonblocking observation-budget issue. All were incorporated into S1.1/A5/A6,
and both affected lenses returned zero open findings after the final defense delta.
Independent plan-defense: ACCEPT. Raw append-only verdicts are retained privately;
this section records results, not a second tracker or an invented runtime proof.

| Gate | Actual state | Scope / limit |
|---|---|---|
| Source/runtime research | PASS | Source base above; running Factory health, Mongo/PG up; no automatic generator found by bounded code inspection |
| Four-lens plan critique | PASS | Four launched/four returned; zero open findings for S1.1 |
| Independent plan defense | PASS | Existing reviewer; S1.1 only, pre-evidence design digest above |
| TDD seam confirmation | PASS | Direct owner confirmation on 2026-11-10; test implementation now authorized |
| Generator selection | PASS | Owner selected local explicitly extractive without LLM; external text transmission remains unauthorized |
| New implementation/unit/mutation tests | IN_PROGRESS | 31 summary-helper top-level tests and 47 control top-level tests pass locally linux/amd64; control code has open review findings; actual CI not executed |
| Mongo/PG integration, restart/rebuild and real-session evaluation | NOT_RUN | Downstream gates, not substituted by helper fixtures |
| Production activation / rollout | NOT_RUN | Not authorized or attempted |

Additional local inventory found no `lms`, `mlx_lm.server`, `mlx_lm` or `llama_cpp`
in the checked executable/Python environment, no matching server process and no
responding loopback LM Studio-compatible inventory on port 1234. This is bounded
availability evidence, not a claim that no model files exist anywhere on the host.
No archive text was sent to a model. Runtime, hooks, credentials, project files and
stashes were not modified. Direct owner confirmation (test seams and local extractive)
arrived after this initial planning record; it authorizes source implementation/tests,
not production deployment or external processing. No elapsed time or preselected
question option is consent.

### S1.2b1 — Retained summary consent and activation baseline

This next slice changes durable control only. No generator goroutine, API serving,
summary writes, live state mutation, implicit consent or rollout is included.
The existing operator `SetConsent(project, provider, "summary", enabled)` is the
only activation operation; ordinary capabilities keep their current protocol.
A new retained WAL mutation `summary_consent_v1` holds the requested enabled flag
and, on enabling, an explicit baseline with project/provider, current archive
metadata generation/committed ordinal, UTC activation time and next summary consent
epoch. No record-format/identity change, new database or parallel state log.

Enable requires operator, known bounded project/provider, current consent epoch
strictly below MaxInt64-1 (reserve the terminal epoch for revoke), archive policy
revision below MaxUint64, completed metadata-v2 migration, an attached ready budget
ledger with no pending intent, no pending archive operation, valid generation and
ordinal, and valid current time. Historical Projection receipts alone are not
pending work; the ledger identifies outstanding projection ownership. Repeated enable
is a new explicit baseline/epoch (as existing SetConsent semantics), not an
idempotent no-op. Future automatic work starts strictly after that baseline.
A record newly captured with an old source event time remains eligible by new
committed ordinal. No existing history is silently backfilled. Unchanged archive
state across replay is required for the witnessed baseline. Generation changes
require another explicit enable; they never reset to ordinal zero automatically.

Under the existing d.mu authority fence, validate first, persist granting witness
before registry enable, then apply the same replay implementation and advance
archive policy revision once. Store the latest baseline in a typed struct map keyed
by struct{Project,Provider string}, not delimiter concatenation. Return detached
value via SummaryActivation(project,provider), which checks control readiness.
No private text is retained in this map/WAL witness. Each new mutation records the expected next consent epoch; it must match the
registry epoch transition during replay. Enable may never consume MaxInt64. A
revoke already at MaxInt64 is a no-op only when disabled and revoked-through is
MaxInt64; otherwise refuse and block control, never increment/wrap. Out-of-order or malformed
witness blocks opening instead of inventing a baseline. Refuse a legacy generic
`set_consent` summary enable encountered during replay: it cannot establish the
required baseline. Legacy generic summary revoke may remain monotone-safe, but
must not fabricate an activation. Capability text comparisons are exact.

Revoking summary consent is allowed even before metadata activation. Preserve
existing authority-reducing ordering: apply registry revoke and policy revision
first, then append the new retained witness. A failed append leaves consent
revoked in memory and control blocked/unacknowledged under existing persistence
semantics. If archive policy revision is already exhausted, still apply the
revocation and attempt its retained witness, then keep all control authority
BLOCKED and return an error; replay of that terminal witness also blocks opening.
No failed or terminal operation is reported as acknowledged success. Keep the previous activation record for audit, but effective enabled
state and epoch always come from current registry consent. Re-enabling stamps a
new baseline and epoch; revoked-through never decreases, and old derived records
are never resurrected by this operation. This slice exposes no source content.

Unknown mutation kinds already block pre-feature readers. Tests must run the actual
840d90f binary on isolated state containing the summary witness (metadata migration
also exists, so that binary understands it), with no intake records required and
no backend connection. Positive control must prove that same old binary can open
otherwise identical pre-witness control via its existing `identity-operator` synthetic capture-revoke
operation (a fixture-only provider with no records). The baseline status command
retains decoder EOF and cannot be the positive control; do not count that unrelated
failure as compatibility proof or silently patch the old executable. Execute the
same operation after adding the witness and require the exact unknown-kind error. A timed-out process, unrelated backend failure or fixture skip
is not downgrade refusal proof. An old-reader refusal is intentionally irreversible
by binary downgrade alone; disabling config or revoking consent does not remove
retained witness. Supported rollback is the compatible new binary with generation
disabled, or an explicitly restored preactivation full state together with latest
retained revocations/deletions; do not erase safety history to make an old binary run.

Plain deterministic control tests cover operator/validation/activation and empty
archive baseline, concurrent captures versus enable using the existing fence,
revoke/regrant, restart exact baseline/epoch, failed persistence and malformed replay.
Real Mongo/PG tests belong to later publish/projection slices, not this control-only
slice. Actual old-binary refusal is a separate explicit executable fixture with a
skip remaining NOT_TESTED. All fixtures use synthetic state, not live state.

| # | Question | Closed by section | Verdict |
|---|---|---|---|
| 1 | malformed input | S1.2b1 enable validation and strict replay | closed |
| 2 | dependency failure | S1.2b1 existing WAL persistence semantics; no backend IO | closed |
| 3 | race and repeated invocation | S1.2b1 existing authority fence, explicit new epoch each enable | closed |
| 4 | empty and boundary data | S1.2b1 ordinal-zero is valid only as witnessed empty archive, epoch exhaustion refused | closed |
| 5 | rollback | S1.2b1 retained witness downgrade refusal and compatible disabled binary | closed |


## Historical helper implementation checkpoint — 2026-11-10

This is an earlier hash-bound snapshot, not the current implementation verdict.
Boundary tests were subsequently authorized and the listed consent defects fixed.

- S1.1: Plan core source SHA256
  `ff790428e6e2e740ccfa1dda5077f348a6bad5f6b9745090dd9def7bb9291a17`;
  20 top-level tests, 9 independent compiled mutations killed by assertions.
- S1.2a: extractor source SHA256
  `6b31d78ae20b134fcb4f1d0a6499778ee009a05a78b17a0f0334d9441bbafbdc`;
  11 top-level tests, including bounded allocation and separate full-document
  refusal paths. Final aggregate helper run: 31 top-level tests PASS.
  Exact test source SHA256
  `7e8377570fd7279a7502091f706c5e6a532689ee048a3319244a9a7e596e305b`.
  Final test-only rebind: independent Spec ACCEPT and Standards ACCEPT, zero open
  findings within pure extraction scope.
  Semantic and individual serializer/admission mutation logs are private evidence;
  redundant count/positive-document/exact-header guards are survivors with explicit
  equivalence arguments, never invented kills. Combined multi-return mutation is
  supplemental only; four independent return mutations provide individual proof.
- Allocation measurement initially used separately calibrated benchmarks whose
  JSON pool GC behavior could mask a prefix guard mutant. Replaced by fixed warm
  calls and five-call byte-allocation measurements, restoring GC/process settings.
  Latest ordinary baseline PASS; individual prefix/preflight mutant now fails.
  This proves allocation behavior, not a physical process RSS cap.
- S1.2b1 planning: four clean-context lenses launched/four returned; two counter
  blockers incorporated, affected logical/edge rechecks clean. Independent defense
  accepted. Current source code is NOT accepted: legacy generic summary-revoke
  replay needs overflow protection; terminal no-op needs exact MaxInt64 epoch
  rather than the wider outer negative-or-max condition. Boundary-fixture seam
  confirmation is pending before dependent TDD changes.
- Control fixtures: full local regression has 47 top-level PASS and one unrelated
  preexisting archive-old-server fixture SKIP (ARCHIVE_OLD_SERVER absent). New actual
  summary-old-reader fixture DID execute and PASS using the actual baseline
  840d90f identity-operator binary, 238 Go/module files bound to that revision.
  It succeeds before activation, rejects the exact unknown `summary_consent_v1`
  kind after activation, and needs no intake directory/backend. The old status
  command has a preexisting decoder-EOF bug; fixture uses the same successful
  synthetic-provider capture revoke before/after the witness. No old-source patch.
- Publish/serve/index/worker integration, Mongo/PG service proof, recovery/rebuild,
  real-session calibration and whole-source independent acceptance are NOT_RUN.
  Release manifest/checksums currently describe the pre-code task snapshot and must
  be refreshed by the normal packaging process after reviewed implementation bytes;
  no current release/package PASS is claimed.
- One existing checkout/feature branch; no worktree, commit, push or deployment.
  Original records, host runtime, kit, consumers, credentials, hooks, consents and
  stashes were not changed. Synthetic local fixtures are not a production rollout.


### S1.2b1 affected counter clarification

Owner confirmation of privacy testing already includes near-limit consent states;
no repeated approval is required. `PlanSummaryConsent(current, enabled)` is the
pure counter part used by both live mutation and replay, not an authority grant.
Synthetic valid/invalid states may test near-limit transitions directly. Private
control fixture arrangement may set a max policy revision to inject the otherwise
infeasible boundary, while observing public SetConsent/reopen behavior; this does
not claim 2^64 actual operator operations.

The new summary consent witness has an explicit optional `terminal` deny marker.
It is revoke-only, without activation data, computed under d.mu from exhausted
policy before Registry becomes blocked. Apply revoke first and attempt persistence
despite ErrBlocked; never acknowledge terminal success. Replay of this retained
marker blocks even if the consent epoch is already a terminal revoked no-op.
Reject marker on enable or with activation. This is the accepted terminal-deny
contract made explicit on disk, not a new grant or automatic recovery mechanism.
Independent affected design review accepted these invariants before implementation.

### S1.2b2 / S1.3 / S1.4 — Bounded automatic pipeline (proposed gate)

This concrete plan supersedes the earlier downstream outline. Source-only optional
feature; no production deployment, consent grant, index creation or capture change.
Reuse Mongo original collection + control/WAL transactions + PG archive projection.
No model/network provider, queue service or second authoritative summary store.

**Identity and source format.** Add optional `derived_kind` to archive.Metadata,
empty omitted from JSON/BSON and preserved by Mongo envelope conversion. Only value
`session-extract/1`, only nonlegacy TypeSummary; every original's Record and existing
empty metadata serialization/hash remain byte-identical. `ArchiveTransaction.Reserve`
keeps ordinary metadata empty. A separate ReserveSummary operation sets this marker
only with matching current summary activation/consent/generation and no pending
foreign work. The retained summary consent witness precedes all such writes. Do not
recognize derived records from arbitrary text or message IDs: old/manual summaries
and historically colliding IDs remain ordinary records. New capture requests reject
the reserved `af-summary-v1/` message namespace before durable intake; existing rows
are preserved. A legacy identity collision on publish returns conflict, no overwrite.
Unknown derived kinds or malformed combinations refuse parsing, not legacy fallback.

**Stored contract.** Canonical strict JSON TypeSummary Text wrapper format
`ai-factory.stored-session-extract/1` contains current summary consent epoch,
activation baseline and ExtractDocument. Bound full wrapper <=2MiB before large
serialization; embedded document <=1MiB and references/input retain Plan bounds.
Canonical bytes are required (no duplicate/unknown fields or trailing data).
Record retains original project/provider/source/session, TypeSummary, assistant role,
Seq0/ParentIDempty, stable reserved MessageID from job digest; capture ConsentEpoch is
the minimum covered original epoch, separate from summary-processing epoch. Archive
captured_at is actual acceptance time; source event time unknown. Every excerpt
remains a literal UTF8 prefix, never semantic synthesis. Store original sources as
facts, not copied authoritative substitutes.

`VerifyStored(envelope, originals, now)` validates strict wrapper, exact scope/type,
metadata derived kind/generation/ordinal, supported versions/options/config/clock,
source hashes + canonical scheduling metadata, roles/withdrawal and literal byte
ranges, complete selected-source mapping/order, job identity and evidence digest.
It does not grant access. Separate policy requires current enabled exact summary
epoch, actual matching activation and current capture retention for record AND
all sources. Exact summary epoch means an explicit re-enable starts a new derived
lineage and withholds prior derived generations; originals remain searchable under
their existing capture policy. Missing/changed source withholds invalid derivation;
backend errors remain unavailable, never deletion or valid proof.

**Progress without lifetime-history scans.** Add an optional typed Progress to Plan
input/manifest: `AfterOrdinal, PreviousJobID`, default activation baseline. Require
activation<=After<=cutoff; a nonempty previous job accompanies progress above baseline.
Bind Progress into job identity and skip originals<=After. Caller must establish it
from an authoritative marked accepted head, not arbitrary integer/time/Seq. Existing
pure calls without progress preserve their behavior. Every accepted head covers an
ordinal prefix of eligible originals for exactly its project/provider/source/session,
from its verified previous frontier through its last selected source ordinal. Only
originals enter coverage. Previous head identity is bound into the next job; final
write checks that head still matches. Thus induction over serialized accepted heads
establishes prefix progress; no unbounded chain walk or full coverage union in memory.
Head sources receive factual verification even if their old capture epochs are now
withheld, because a historical processing checkpoint is not serving permission.
Missing/changed head source is explicit invalid-checkpoint refusal requiring repair,
not reset/backfill. Supported deletion barriers and capture revocations are rechecked
and exclude scopes/old originals; they never resurrect prior content.

Add narrowly scoped Mongo read APIs (and deterministic MemStore counterparts):
next eligible session key after (source,session); latest marked summary head for a
session/generation after activation and through committed cutoff; ordinal pages of
eligible original messages for that session. Filter by project/provider/generation,
activation/progress lower bound, upper cutoff, capture revocation cutoff and withdrawn
false; group discovery is keyset ordered, never an unbounded distinct body fetch.
All queries have maxTime, bounded results/bytes and explicit errors. Use additive
nonunique named index `archive_summary_scope_v1` on project/provider/source/session/
generation/ordinal and a consent/order index only if isolated explain/contract tests
show needed. No second collection. Provide explicit versioned idempotent index
preparation/inspection through migration-operator using existing capacity/reservation
and postverification protocol; startup refuses SummaryEnabled if indexes absent,
never creates indexes implicitly. Existing metadata-v2 installations remain valid
when optional feature is disabled. No live migration is performed here.

For one session, scan after verified frontier. Stop once canonical observed input
bytes reach input cap, or at source exhaustion. After a complete ordinal prefix page,
its last scanned ordinal is a truthful smaller observed cutoff even when global
source is ahead; Plan Complete then means all eligible originals through that cutoff.
A reached byte cap permits size processing without loading the rest of a long session.
Below the cap, continue pages to the fixed global cutoff before idle/active decisions.
No partial-page/exhaustion guess, no fixed message-count trigger. A single oversized
original remains explicit needs-chunking/config refusal, as accepted S1.1. This avoids
a permanent observation ceiling caused solely by lifetime session length.

**Worker and acceptance.** Config SummaryEnabled defaults false; configurable positive
active/idle seconds default1800/900, poll default5s, input/excerpt/document limits
validated with existing Config/ExtractOptions bounds. No arbitrary command/URL.
One joined background worker separate from capture/drain. Per tick process at most
one session from one explicit current summary activation, rotating activation and
session keys; bounded discovery/scans and explicit diagnostic failures, no text logs.
Set consent alone does not start worker when feature switch is off. Reject backfill:
only originals strictly after actual activation and current progress qualify.

Snapshot ready generation/committed cutoff/policy/activation under existing fences;
release locks for indexed source reads and pure generation. Reconstruct head/progress
and floor from accepted GeneratedAt; retain an in-memory observed clock floor during
process lifetime. After restart, continuity since the last accepted extract is unknown,
reported as such; do not fabricate persistent poll-time evidence. Refuse now behind
known source/activation/accepted-head times. Before accepting any new body, recover
owned WAL work, lookup stable identity and reuse first durable accepted body. Under
existing mutate+control fence recheck current activation/consents/barriers, source
hashes, generation/policy and expected head before reserve/CommitEnvelope. No LLM or
generation under that fence. New later source ordinals wait for next tick. Existing
capture shares only the bounded final transaction, not timer/generation work.
Mongo acceptance remains terminal; PG outage never creates another authority.

**Recovery and projection.** Introduce error-aware envelope gate variants of existing
RecoverEnvelope/ProjectArchive/RecoverProjection, retaining old Record/bool wrappers
for compatibility. Metadata is required to distinguish true derived records without
rewriting historical identity. For derived records gate verifies sources and policy;
transient error stops work before cancel/checkpoint advance, false means permanent
policy/stale proof. Use existing reserve/majority source/commit/process protocol.
Committed-source recovery never recreates a disappeared record. For index/recovery,
existing writer-fence IO remains bounded; generator stays outside. Trim each indexed
raw page to one TypeSummary plus its preceding ordinary records; More stays true.
Recovery+next page may validate two summaries, bounded by per-document caps. Plain
record gates remain policy-only and IO-free. PG rebuild projects validated Mongo;
checkpoint caught_up is raw committed source projection, never native completeness
or proof that every session has generated an extract.

**All serving paths.** Prepare exact derivation/source proof outside final authority
for query/message/context/search/recent, then recheck requester+summary/capture policy
inside their existing snapshot fence. Context does not follow a derived record as
an original thread link. Keep retention.Serve policy-only. Legacy/manual summaries
have no claimed verified provenance and keep current retention behavior. A page
inspects at most one TypeSummary (to classify metadata and bounded covered sources),
trimming raw candidates before the next summary, preserving More and cursor at last
fully inspected raw position. Normal index cursor uses prior ref identity hash;
recent uses the unconsumed ref.Before; archive uses existing raw Position. Missing
or withheld candidates still advance; backend failure returns503, not an empty hit.
No unresolved candidate is skipped, no exact-total claim, and small page+cursor is
valid. Message lookup has one anchor. Context stops before a second summary and
reports incomplete rather than omitting unverified links. Source reads are bounded
by admitted head input/reference bytes and an elapsed deadline (cannot cancel an
already running context-free lookup; allow at most its existing DB timeout overrun).
No permanent dense-page503 merely because many summaries share a page.

**Validation and delivery gates.** Red/green at approved scheduler/publish/policy and
HTTP seams; plain deterministic tests must discriminate guards when service tests
skip in CI. Isolated real linux/amd64 Mongo/PG prove marker roundtrip, named index
inspection/keyset queries, restart/idempotency/recovery and PG rebuild. Test native
process asynchronous tick after synthetic capture, no synchronous generation,
30m/15m boundaries via injected time seam (process test uses configured short positive
values), byte prefixes, long session progressing across pages, interleaved sessions,
late inserts, barriers/revoke/grant races, source errors versus absence, all five read
paths, dense summary cursor traversal and source identity isolation. Bind mutation
proof and independent final Spec/Standards review to exact bytes. Real-session timing
and size calibration is separate authorized local read evidence or explicitly
NOT_TESTED, never fixture success presented as native capture completeness.

| # | Question | Closed by this plan | Verdict |
|---|---|---|---|
|1|Malformed input|Strict marked source/JSON, bounded options/proofs, no legacy fallback for malformed derived data|closed|
|2|Dependency failure|Error-aware gates stop before cancel/advance; Mongo remains authority; bounded worker retry, explicit backlog|closed|
|3|Race/repeat|Existing authority lock, exact head/source/policy recheck, stable job lookup+WAL recovery first accepted body wins|closed|
|4|Empty/bounds|No new originals no job; fixed-cutoff session prefix, one-summary candidate budgets preserve cursor; oversized singleton explicit|closed|
|5|Rollback|Defaultoff compatible binary; retained control witness prevents old reader even empty intake; additive index and old-record bytes preserved, no erasure downgrade|closed|


#### Pipeline critique corrections (four launched / four returned)

The AI-slop and complexity lenses returned clean. Logical and edge lenses returned
four blocking contract gaps. The following corrections govern implementation.

1. **Head reads are not serving reads.** Capture revoked-through and withdrawn
filters apply to original discovery/input pages only. Latest marked head selection
uses exact project/provider/source/session/generation, summary activation epoch and
committed cutoff, without capture-serving filters. Verify its bounded source facts
independently of retention; do not expose its text because of this internal read.
Reject the newest malformed/missing-source head, never silently fall back. Test
capture revoke/regrant with unchanged summary activation: old head remains historical
frontier, old excerpts remain withheld, only new eligible originals start a timer.

2. **Worker aggregation headroom.** The worker derives its observation budget as
MaxInputBytes + archive.ScanBytes + archive.EnvelopeScanRecords, within Plan's32MiB
cap; it does not reuse a smaller/equal pure-planner observation option. Below input
cap only, fetch one additional complete source page (<=8MiB,<=100 envelopes), count
canonical JSON plus one newline each, and stop at the first crossing page. Therefore
held bytes always fit this derived budget before calling Plan. Pure Plan may still
accept equal input/observation budgets for callers with already bounded observations;
that is not the worker aggregation contract. Tests use two fitting singletons whose
combined page crosses the input cap, equal requested input/observation in a pure
fixture versus safely derived worker budget, oversized remaining pages, repeated
ticks and eventual complete selected-prefix progress. Single oversized original
remains needs-chunking, never skipped.

3. **Cursor bounds.** Archive query admits UTF8 project/query/provider <=4096 bytes;
Position IDs each <=4096. Encode validates bounds before serialization. Raise the
bounded authenticated cursor limit to256KiB (plaintext <=192KiB), including recent
parameter admission. Six4096-byte strings escaped sixfold need147456 bytes plus
fixed JSON/AEAD framing; base64 remains below256KiB. Enforce emitted bound and the
same decoder limit, never emit unusable tokens or omit continuation silently.
Existing issued small tokens remain compatible. Test real multi-page HTTP queries
with max-size/control-character source/session IDs, withheld candidates and every
emitted cursor accepted/progressing, plus over-limit refusal. Claims apply to the
Factory endpoint; a separately configured proxy may impose a smaller URI limit.

4. **Permanently invalid pending projections need a terminal transition.** Extend
existing ArchiveProjection protocol with retained cancellation witness
`archive_summary_projection_cancel_v1`, bound to the exact saved projection and
current pending ledger evidence. No cancellation on transient source/PG error.
Policy mismatch or permanent source/proof denial may cancel any owned action
(project/rebuild/advance/complete), without trying to validate old desired policy
against current authority as if it were a fresh write.

Under the existing writer fence, Resume the exact original intent; persist the
cancellation witness using that same liability, before destructive derived cleanup.
New projection reservations include conservative cancellation-WAL/high-water costs.
A surviving older reservation lacking sufficient capacity stays explicitly blocked
until capacity/recovery is provided; do not refund unknown liability. Apply records
which exact prior op is cancelled, so restart never replays it as a normal project.
Then idempotently delete this project's archive_index rows and archive_checkpoint
in one PG transaction (not workflow/document/source tables). Verify no project
rows/checkpoint remain via scoped NOT EXISTS, and only then Finish the original
intent through a dedicated FinishCancelledProjection exact-witness proof method.
The cancellation marker is retained; a later normal reservation supersedes its
in-memory current marker under the same fence, not by erasing the journal. If PG
is unavailable or cleanup/readback is uncertain, keep witness+intent and retry the
same cleanup. Crash after witness/before cleanup, after SQL commit/before Finish,
and after Finish/before rebuild all recover idempotently. Next ordinary projection
sees missing checkpoint and rebuilds under current policy. Mongo/WAL source, capture
commitment and access remain unchanged. Source permission is always checked at
serving, so stale PG rows during cleanup are never authority. Disabling PG while
its intent remains unresolved stays a startup refusal, not automatic release.

Tests prove plain transition/evidence behavior and isolated actual PG reserve→
uncertain write→revoke or missing source→restart→cancel+verified empty→Finish→
current-policy rebuild/new source admission. Error-aware source failures retain the
intent/checkpoint; tests must discriminate source absence from temporary error.
Cancellation is authority-reducing for derived data only; old binaries refuse its
unknown retained control kind, even if no new summary source row survives. Rollback
uses a compatible disabled binary and retained revocations, never erases witness.


Stored format1 branch rule: current v2 original metadata cannot attest a Git branch.
Seal/Decode require explicit unknown branch for automatic stored extracts; pure Plan
may still bind an explicit caller label without claiming that stored-source proof.
Future branch metadata support requires a reviewed format/provenance extension.


## Exclusive writer handoff — 2026-11-10

The owner requested priority for a separate urgent non-Docker handoff correction in
this same checkout/manifests. All summary reviewers and test/mutation processes are
idle/completed. No live data, hooks, kit, consumers or services were changed by S1.
Preserve this WIP without merging or releasing it. Only this task's explicit owned
paths may be shelved; no other stash/reset/clean or worktree. Private handoff evidence
records base/branch, each file hash/mode, a verified backup and exact stash object.
The pre-code release metadata remains unfinished and must not be mistaken for a
current release. On resume preserve the intervening fix, restore/reconcile S1 onto
its latest source and rerun affected checks/review before any publication.

#### First vertical slice: reuse the established Mongo index

Implementation inspection found an additional accounting prerequisite for the
previously proposed new compound index: existing `EnvelopeReservationBytes` and
logical inventory charge only the currently declared keys. Adding another index
for every old v2 row would need a separately witnessed global accounting upgrade,
quiescent old intents and recovery before creation. It is not a harmless startup
optimization and is outside the smallest working automatic-summary slice.

This first implementation therefore supersedes the new-index/preparation step:
reuse the existing `archive_metadata_v2_order` index, explicitly hint it for
project/generation/ordinal-constrained reads, project session-discovery headers and
use bounded top-one keyset selection. No new DDL, index keys or schema-cost change.
Require the existing read-only MetadataSchemaReady inspection; the existing
versioned metadata migration remains the explicit prerequisite. Do not add a
summary-only installer or create indexes from runtime. A future measured scope-index
extension needs its own accounted preparation, compatibility and recovery review.

Session-head and original scans remain bounded/paged by committed ordinals. Mongo
query timeouts remain unavailable/backlog, never exhaustion. This removes a lifetime
client observation ceiling but does not promise constant query cost or a latency SLA
for arbitrary archive size. Isolated real-Mongo fixtures must prove exact scoped
queries, Unicode/boundaries, marker roundtrip, multiple pages, keyset progress and
explain use of the established index (no unbounded body fetch or implicit DDL).
Report measured size/latency and actual limits; validate the defaults on authorized
real-session evidence separately before any activation.

The indexed text of a marked extract is its verified literal excerpts joined by
newlines, not the JSON provenance wrapper. Source/metadata hashes still bind the
entire immutable record/envelope. Preserve original record indexing except represent
NUL as a token boundary (PostgreSQL text cannot carry NUL), keeping the original
source unchanged. Query normalization uses the same boundary rule. Test literal
newline/control/Unicode terms on real PG; do not infer valid JSON from HTTP200.
Malformed derived data must fail the error-aware projection gate before indexing.
Plain/manual summaries retain their current source-text meaning. A matching snippet
must identify its verified excerpt-text basis or remain explicitly unavailable;
never imply offsets refer to the JSON wrapper when using projected literal text.


### Historical checkpoint immediately after writer return

The owned WIP is restored over main5abf824; the non-Docker handoff repair and
private stash/backup are retained. Actual isolated Mongo happy-contract and legacy
parity RED→GREEN executed with pinned linux/amd64 images; all test resources were
removed. No new index or live schema operation was introduced. Bounded stored-proof,
source resolver, late-insert/head progress and crossing-page fixtures pass. Independent
preliminary Spec legacy-filter finding and Standards JobID allocation finding were
fixed and discriminated; this is not full implementation acceptance. HTTP message,
query and context now preflight the authoritative marker/provenance and recheck policy
under the final fence; verified excerpt text is their search/snippet basis. Long escaped
identity cursor RED→GREEN passed. Remaining search/projection/recovery/automatic-worker,
mutation, integrated E2E and final package/review gates stay open.

**Reachable revocation boundary.** An unresolved ledger intent prevents an unrelated
control WAL reservation. A revoke attempted in that state is applied in the current
process, but persistence returns an unacknowledged error and blocks that process.
Restart restores the previous durable consent, not the failed in-memory reduction.
Do not describe this as durable revocation or fail-closed across restart. Recover the
owned projection, then retry and verify the revoke. The new cancellation E2E uses
permanently missing source, not an invented successful revoke between a surviving
projection reservation and recovery. Policy-mismatch transition fixtures are separate
from reachable end-to-end evidence. Stronger pending-revoke guarantees require a
separate retained authority protocol review; no combined mutation is added here.

New projection reservations retain a cancellation liability amount in their receipt;
zero means a historical reservation without this provision. It is checked against the
exact cancellation WAL/high-water cost. Cancellation retains the same operation and
ledger evidence until positive scoped PG cleanup/readback proof; the source checkpoint
is unchanged. The subsequent isolated PostgreSQL tests exercise this cleanup and retained retry;
that proof is recorded below, separately from the control-only fixtures.


## Historical pipeline checkpoint before final repairs — 2026-11-10

Source remains uncommitted on the existing `feat/session-summaries` checkout above.
No new worktree, source clone, deployment, live consent change or provider call was
performed. A fresh private backup of all 65 owned changed source/doc/metadata files
was created and archive contents rehashed after reconnection; the earlier handoff
backup and stash remain retained. Private evidence is excluded from the package.

Implemented: explicit default-off asynchronous worker; bounded original observation
and factual prior-head progress; local UTF-8 prefix extraction; separate marked Mongo
records; exact immutable-body WAL recovery; error-aware PostgreSQL projection and
retained project-scoped cancellation; ID/query/context/search/recent serving gates;
verified excerpt search/snippet text and cursor continuation through withheld pages.
Original payload/hash identity, manual summaries and existing empty metadata retain
their contracts. No new database schema or index is installed.

Observed isolated linux/amd64 service evidence (all synthetic resources cleaned):

- Actual Mongo adapter: legacy exclusion, Unicode/control-character 4096-byte IDs,
  complete 100/100/5 raw pages, stable cutoff and later arrival under a new cutoff.
- Actual PostgreSQL: cancellation after permanently missing/changed covered source,
  transient source refusal without cancellation, SQL commit followed by failed
  readback and restart retry, foreign-project rows preserved, fresh rebuild.
- PostgreSQL plus HTTP: wrapper metadata cannot match excerpt terms; NUL/newline
  boundaries, current revocation/rebuild policy, search and recent continuation.
- Actual Factory process with Mongo and PostgreSQL: feature off by default, explicit
  opt-in, asynchronous source/search, derived insert outage with first durable WAL
  body retained, process restart recovering that exact body, second restart no
  duplicate. This is a Factory process test, not native-agent completeness proof.

Targeted review regressions pass for stale prior-head sources, aggregate five-second
proof budget, pre-reservation clock/proof refusal, capture regrant without resetting
progress, summary revoke between observation and publish, identical session/message
IDs across sources, withheld empty pages and residual unaccepted-reservation recovery.
Cancellation during recovery previously started discovery (observed RED); context
checks and gates now stop further stages (observed GREEN). An accepted per-project
recovery transaction may finish consistency steps before cancellation returns. One
legacy source call may overrun the proof deadline by its own timeout; no immediate
backend or OS IO cancellation guarantee is made.

Prior scoped helper reviews remain historical hash-bound evidence. Independent
review closed the cancellation finding; final pipeline mutation inventory/results,
current-code Standards acceptance, full regression and exact-package verification
remain IN_PROGRESS. Actual external CI is NOT_TESTED. Whole-storage alpha acceptance
remains BLOCKED independently of this feature. Do not label this checkpoint a release
or rollout PASS.

### Explicit operator contract (not activation)

The existing test-harness/OCI entry point accepts `-session-extracts` in addition
to its required state/config/token arguments. It enables scheduling only when Mongo
archive and metadata schema are ready; it creates neither schema nor consent. Existing
per-project/provider summary consent/activation, capture consent, retention and
committed generation still gate every job. Without the flag, no automatic extracts
are generated even if consent exists. No backfill before activation is performed.

| Option | Default | Meaning |
|---|---|---|
| `-extract-active-after` | `30m` | Eligibility from first uncovered captured_at |
| `-extract-idle-after` | `15m` | Eligibility from last uncovered captured_at |
| `-extract-poll` | `5s` | One scope/session examination per tick; backlog adds latency |
| `-extract-max-input` | `262144` | Whole-original input safeguard in bytes |
| `-extract-max-references` | `262144` | Serialized coverage-reference safeguard |
| `-extract-max-excerpt` | `1024` | Literal UTF-8 prefix cap per selected original |
| `-extract-max-document` | `1048576` | Complete extract-document byte cap |

Durations and byte limits are validated before startup. Scope/session discovery is
header-only with existing-index hint, simple collation and timeout; query cost is
not proven constant or production-scale. One oversized first record, unsupported
original role, invalid newest head or missing/changed prior covered source blocks
that session with an error rather than silently skipping it. Other sessions are
visited by subsequent bounded cycles. Original order is committed ordinal, never
Seq/event time. Branch is explicitly unknown when source cannot prove it.

Only the server's operator health adds `session_extracts` with enabled,
last-cycle-failed, kind=extractive and capture-completeness=unknown. This is not
backlog, freshness, capture completeness or an exact total. Generation shutdown is
joined before drain shutdown and before intake/control close.

### Calibration and rollout limits

The 30m/15m defaults are owner-selected, not empirically tuned production guarantees.
Boundary, continuous-activity, idle, size and restart behavior are tested with
synthetic clocks and real isolated services. Representative whole-history captured_at
and size/role distributions have not been established: the default read-only search
CLI does not request the supported recent/captured_at mode. Bounded authorized
observations through a reviewed private parameter adaptation are recorded below. Do not broaden credentials, use operator access or activate
summary consent to fill that evidence gap. A local metadata-only
evaluation and explicit production rollout remain required before claiming real-session
calibration or activating the worker. No archive text may be sent to a model provider.


Additional current verification: full linux/amd64 Go unit/process regression passed;
10 offline exporter fixture cases passed. Exact temporary manifest export/verification
passed for 840 payload/metadata files and 581 checked links. These package bytes are
an intermediate evidence snapshot, not a final review or install; any subsequent
source/test/doc edit requires rebinding and package regeneration.

An isolated Mongo profile captured the actual production discovery find command,
then explained that command on 10/100/1000 synthetic 1KiB originals. The established
`archive_metadata_v2_order` hint was used, one header returned, and 10/100/1000 keys
and documents examined respectively (observed execution 1/0/3ms). This demonstrates
linear candidate scanning in that fixture despite a bounded returned header; it is
not a constant-cost or production performance guarantee. Profiling touched only the
disposable test database; the live database and indexes were unchanged. Before
production scale, evaluate project size/session distribution and timeout/backlog;
any additional index requires separately accounted migration review.


### Review repairs and bounded live-read evidence

Independent Spec source review accepted the current scoped pipeline after closing
raw backend-diagnostic disclosure in archive query, the missing reserved capture
namespace guard, and cancellation boundaries. Archive query now returns a fixed 503
for proof/backend outages; missing/changed covered facts remain withheld, not an outage.
Incoming exact `af-summary-v1/` IDs are preflighted across the whole batch before
attempt intake or WAL. Generic, Claude and Codex-v1 routes are tested with and without
metadata. Historical colliding originals/manual summaries remain unchanged/readable;
recapturing them, including exact retries, is refused. Near-prefix IDs are distinct.
Internal summary publication does not enter this capture guard.

Initial pipeline mutation diagnostics executed 189 compiled variants with 10 passing
baselines: 64 assertion kills and 125 survivors, never 189 kills. Independent
classification found 75 missing discriminating cases and 50 supported-state
redundancies. Repairs add actual no-WAL-poison reservation assertions, caller-retreat
clock tests, source/authority boundaries, factual head changes, accepted-identity loss,
legacy identity collision, exact cache-envelope binding, multi-excerpt newlines,
withheld raw cursor advancement, derived context stop reason, dense search/recent,
independent SQL row/checkpoint cleanup proofs, old unprovisioned replay, and process
startup/default-off checks. A fresh targeted packet is being rebound; no exhaustive
whole-pipeline mutation PASS is asserted merely from its case count. Allocation/shape
and lifecycle inventories must also close before final Standards acceptance.

The later full integration run passed every package except a newly added replay test
whose oracle treated the expected explicit ErrBlocked refusal as unexpected. That
oracle is fixed and its focused baseline passes. It was a test failure, not a mutation
kill or evidence of permissive replay. Final full regression/review/package rebinding
remain required after the remaining test refinements.

A private, independently reviewed adaptation of the existing secure search client can
request the supported recent/captured_at mode on the same GET endpoint and existing
four project search-only bindings. Its planned output is aggregate metadata only;
timer replay would still be time-sorted sample analysis, without authoritative ordinal,
activation, exact envelope/reference cost or size-trigger execution. Unknown timestamps
excluded by the server are not counted by a returned-window unknown counter.

That live-read command was DENIED before execution by automatic approval review:
direct permission for reading four private project sources was required. Trusted current history was checked; general
continuation did not supply that exact permission. No retry, alternative credential,
indirect database query or access workaround occurred. The owner then explicitly approved that exact bounded read. One authorized retry
executed: three scoped traversals returned usable timing observations, while the
remaining source returned HTTP503 and was not retried or treated as empty.
Real-session evaluation is PARTIAL, not full calibration or runtime acceptance. No model-provider request, summary
consent, deployment or project modification occurred.


### Consolidated final admission/lifecycle proof

The final bounded review inventory adds JSON array/depth/token-work limits, public
DecodeStored empty-object-array allocation refusal, outer identity and authority
pre-serialization admission, typed source/excerpt count and field/encoded-byte
budgets, stored wire labels/reference scope, and aggregate actual-source input/ref
verification. Tests distinguish encoded expansion from literal text bytes and check
nil-versus-empty array expansion at the final document budget. The retained final
size guard is necessary: a nil Excerpts field serializes as null while the accounting
header uses an empty array. No correlated guard removal or later parsing error is
claimed as early allocation proof.

The actual root process uses a small startSessionExtractWorker lifetime owner that
returns cancellation plus join. Its deterministic fixture holds a legacy discovery
call: stop cannot return before that call is released, then cancels the long poll and
joins before resources close. Main retains LIFO registration after drain and before
intake/control close. CLI tests include invalid plan/options/poll, Mongo prerequisite,
operator-visible default-off health across a quiet polling window, and a legacy-ready
non-simple-collation index that refuses summary startup without LISTEN or implicit DDL.

Local timing observations exercise both active and idle thresholds in authorized
live samples. Their time-sorted hypothetical replay excludes activation, ordinal
order and exact envelope/reference/size-trigger execution; text byte counts are only
a lower-bound proxy. Traversal exhaustion proves neither complete sessions nor native
capture, and the unavailable source remains untested. No timing/size default was tuned
from this limited evidence alone. Private sources, IDs, transcripts, credentials,
consumer names and aggregate business measurements stay out of this portable package.


## Original source acceptance snapshot before the activation request

Independent Spec: ACCEPT. Independent Standards: ACCEPT, zero open blockers within
the agreed S1 inventory. The whole-storage alpha verdict remains BLOCKED and is not
replaced by this scoped result. Reviews inspected author-run evidence; the author did
not award independent acceptance to their own work.

| Gate | Final source state | Evidence boundary |
|---|---|---|
| Pure planning/extraction and current consent slices | ACCEPT | Earlier hash-bound helper proof reused only for unchanged constructs |
| Entire Go module, actual isolated MongoDB/PostgreSQL, actual Factory process | PASS | linux/amd64 pinned builder; all packages passed and fixture resources cleaned |
| Post-integration five-test extension | PASS | Exact prior test contents preserved as prefix; production Go bytes unchanged |
| Finite supporting-condition/serialization mutation inventory | PASS | 285 unique variants: 228 assertion-detected regressions, 57 independently supported equivalents; 11 passing baselines; no invalid/inconclusive runs counted |
| Source Spec / Standards review | ACCEPT / ACCEPT | Exact current source/test bindings and survivor reasoning retained privately |
| Final exact package export and metadata recheck | PASS | 845 exported payload/metadata files, 581 checked links, 10 exporter fixtures; accepted clock fix included; no installation or release |
| Authorized live timing/size-proxy evaluation | PARTIAL | Three sources returned bounded observations; one returned HTTP503, not empty |
| External CI | NOT_TESTED | Local fixtures are not CI proof |
| Production activation / deployment | OFF / NOT_RUN | No summary consent, grants, hooks, runtime image or service state changed |

The final context tests distinguish default proof deadline from caller cancellation:
a six-second legacy lookup is allowed to finish, then returns DeadlineExceeded with
no second lookup or partial proof. Cancellation with a missing-result callback stays
a transient context error, not permanent source invalidation. Unavailable resolvers
and >1MiB embedded documents are refused before covered-source IO. Encoded header and
nil-array expansion checks independently enforce complete-document admission.

Supported recovery preserves the first durable body, source identity and provenance.
Turning the feature flag off stops new generation with a compatible binary; it is not
a downgrade migration. Existing summary-consent/cancellation witnesses and derived
records must remain retained. An older incompatible reader refuses; do not remove
WAL/control records, reset generations or guess historical cancellation liabilities.
No S1 production backup/restore or rollback rollout is claimed from isolated process
restart tests alone.

A session-specific invalid/oversized input can block that session; a source-query,
schema or authority error can block its scope or the worker's recovery stage. Operator
health is only last-cycle failure, not persistent per-session backlog or completeness.
Other scopes may advance on later cycles when shared recovery/authority allows it.
The existing-index discovery is linear in the measured candidate corpus; production
scale, complete native capture, branch reconstruction and optimal tuning are excluded.


### Closed accepted-WAL clock classification finding

A final audit found a concrete defect after the preceding acceptance snapshot:
a regressed verifier clock was classified as ErrInvalidStored, so a still-reserved
but accepted summary WAL body could be terminally cancelled/marked processed during
source recovery; the analogous index gate could cancel a saved PG projection.
The independent reviewer confirmed the finding and suspended final Spec acceptance.
That earlier acceptance snapshot was superseded during the repair; both independent
reviewers have now accepted the repaired source and its current-production integration.

RED tests demonstrated accepted-WAL cancellation and HTTP404 under clock rollback.
The fix introduces distinct transient ErrVerifierClock after structural DecodeStored
validation. Internally malformed captured_at<generated_at remains permanently invalid.
A private trusted proof-clock dependency defaults to wall UTC, is set before concurrent
use in fixtures and has no HTTP/runtime configuration setter. This enables deterministic
recovery/serving tests without changing the host clock. A zero or unrepresentable
verifier time and a time before captured_at are transient; structurally malformed
stored timestamps remain permanently invalid.

Accepted-WAL recovery preserves the original body, ordinal, ledger and progress while
the verifier clock is invalid. Message/context/query serving returns generic HTTP503
until correction. An actual PostgreSQL test preserves the saved projection receipt,
rows and cancellation state, then completes the same checkpoint after clock correction.
The direct WAL recovery fixture and separate process-restart fixture establish their
respective contracts; the clock fixture alone is not a process-restart test.

The entire current-production Go module passed again with isolated MongoDB/PostgreSQL
and the actual Factory process on linux/amd64; owned resources were cleaned. The only
subsequent test delta adds a passing year-10000 verifier-time case without removing
assertions. The affected clock packet detected all eight tested regressions across four
passing baselines; repeated constructor comparisons are not added to the earlier 285
unique-variant count. Scoped Spec and Standards both ACCEPT with zero remaining blockers.
No production activation, external CI or whole-storage acceptance is implied.


## Authorized activation follow-up

The owner subsequently authorized activation, commit and push. The original accepted
S1 implementation was committed separately. Runtime rollout discovered a real
responsiveness problem on an isolated restored archive: metadata projection could
hold shared writer locks across 100 separately metered records. The bounded follow-up
inspects one metadata record per writer transaction and marks any uninspected tail
incomplete. General coordinator callers retain the original 100-record default.
Mandatory ledger accounting remains; metadata uses its authoritative fenced ledger
rather than an additional unfenced preflight. Legacy usage/base admission is retained.

Only successful metadata checkpoint advancement is a catch-up signal. Legacy scans
can revisit matching rows and never trigger fast pacing. The worker captures a finite
project sweep (at most 64 calls), checks cancellation between steps, releases locks
between records and permits eight short 25ms progress intervals before the ordinary
backoff. Quiet work and errors retain backoff. These are work bounds, not hard
wall-clock latency guarantees; IO and retained recovery may take longer.

### First-ever summary enable preserves the original index

The distinct retained kind `summary_initial_consent_v2` is permitted only for disabled
summary consent at epoch zero with revoked-through zero and no prior activation.
It retains the existing archive policy revision because no automatic extract could
have been authorized by that scope before its first activation. The new committed
baseline excludes historical messages. Existing migration, generation, ordinal,
time, pending-operation, ledger and policy-exhaustion checks remain mandatory.

Every historical `summary_consent_v1` record retains its original policy increment
on replay. Repeated enables, revokes and regrants also retain invalidation/rebuild
behavior. The initial exception is explicit in the retained kind; it is never inferred
while replaying a historical v1 witness. Previous S1 readers must refuse the new kind,
so post-activation flag-off/recovery requires the compatible updated binary. The flag
is not a downgrade or an instruction to remove retained records.

Metadata readiness is per project. A ready global schema or another migrated project
does not prove that a newly connected legacy archive has its own complete witness.
Before activation, use the existing explicit offline metadata migration where needed,
with an exclusive writer window, verified backup/restore rehearsal and preservation
of original content and identities. Startup and consent do not silently migrate it.

The current follow-up source and compatibility have independent scoped Spec and
Standards ACCEPT. Current root, API and control tests passed across explicitly layered
runs with actual isolated MongoDB/PostgreSQL; unchanged packages retain their prior
full-module evidence. A combined API package-timeout run remains NOTPASS, followed by
a passing same-byte API-only rerun. No timeout or infrastructure failure counts as a
passing baseline or a detected mutation.

The bounded-index packet has 16 detected comparisons and three passing baselines.
The first-enable packet has seven detected comparisons, one independently supported
redundancy and two passing baselines: the retained prior-epoch-zero check plus
PlanSummaryConsent's expected-step equality independently enforce epoch one. These
packets are separate from the earlier 285-variant inventory; counts are not combined
into a claim of exhaustive mutation coverage. Actual prior-S1-reader positive/refusal
and compatible flag-off/restart proofs passed on isolated state.

Final exact package export and metadata verification PASS: 847 files, 581 links
and ten exporter fixtures, with no installation or release. Source acceptance does not certify external CI,
whole-storage alpha acceptance or an unobserved production result. The owner authorized
runtime activation separately; its backups, per-consumer operations and live evidence
remain private operational records rather than portable package data.
