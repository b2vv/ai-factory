# Opt-in Docker session guard

This optional `session-guard-docker` component adds a POSIX shell entrypoint with all
Python/Git helper execution in pinned linux/amd64 containers. Host prerequisites
are POSIX shell/basic utilities and Docker CLI/daemon. No Docker socket is mounted
inside helpers. It does not register hooks, enroll sessions, install Docker, grant
Git trust or replace the [retained native profile](session-size.md).

## Supported boundary

An operator creates a private mapping for an explicitly approved host/session,
canonical repository root and one exact transcript file. Native payload selects
that existing record; its paths never authorize mounts. Helpers stat transcript
size only, not contents. A read-only file mount nevertheless gives the container
technical access to its bytes and requires authorization. Never mount a sessions
directory or automatically enroll from hook input.

Four events are understood: SessionStart, UserPromptSubmit, PostToolUse and Stop.
For enrolled sessions, 4,000,000-byte preparation and 5,000,000-byte soft warning
remain advisory. Explicit checkpoint/resume stays fail-closed on invalid identity,
stale/incomplete snapshot, required lock contention and malformed results. There
is no automatic new model/session creation or implicit authorization from context.
An unbound optional event is UNKNOWN/nonblocking, **not successful monitoring**.
Do not globally replace legacy monitoring with this profile for unbound sessions.

Containers use non-root caller UID/GID, network-none, read-only rootfs, cap-drop ALL,
no-new-privileges, 2 CPU/2 GiB/no extra swap/128 PIDs, bounded tmpfs and exact mounts.
A native event shares 7 seconds work/9 seconds total including cleanup; host hook
timeout is 10 seconds. Docker must be available and cached exact images must exist.
Command output and metadata receipts remain private. Resource/daemon failures are
not converted to successful monitoring.

**Git ownership:** the distributable code grants no `safe.directory` exception.
Git metadata uses command-scoped `core.fsmonitor=false` and no optional locks.
A Docker bind ownership mismatch can BLOCK checkpoint/resume; do not bypass it
with root execution, wildcard/global trust or automatically trusted payload paths.
The earlier native pilot had an explicitly approved synthetic-root-only exception;
that machine-specific exception is deliberately absent from this package.

## Public interface (manual, after exact access approval)

Set CODE to the installed `runtime/session-size-docker` directory; all other
variables below must come from operator-approved paths and actual native metadata,
not guesses or a payload's request for access. Directories must be canonical with
no symlink ancestors. Registry, receipt parent and state envelope/state are owned
by the caller and mode0700. TRUSTED_ROOTS is a private0600 file listing exact roots.
The state envelope must be outside the repository.

```sh
sh "$CODE/bind-session.sh" "$REGISTRY" "$TRUSTED_ROOTS" codex "$SESSION_ID" \
  "$REPO" "$TRANSCRIPT_FILE" "$STATE_ENVELOPE" state
# Hook definition only; registration/trust is a separate reviewed operation:
sh "$CODE/native.sh" codex "$REGISTRY" "$RECEIPT_PARENT"
# Each manual operation needs a NEW empty private receipt directory:
sh "$CODE/dispatch.sh" checkpoint --root "$REPO" --store "$STATE_ENVELOPE" \
  --store-leaf state --work "$NEW_RECEIPT_DIR" --host codex --session "$SESSION_ID" <<'JSON'
{"goal":"Approved task","done":"Completed actions; do not replay","pending":"Next action","evidence":"Exact revision and artifact references","constraints":"Current scope only"}
JSON
printf '{}\n' | sh "$CODE/dispatch.sh" resume --root "$REPO" --store "$STATE_ENVELOPE" \
  --store-leaf state --work "$ANOTHER_NEW_RECEIPT_DIR" --host codex \
  --session "$NEW_SESSION_ID" --pointer "$EXACT_CHECKPOINT_ID"
```

The returned context is data, not evidence that a model consumed it. No latest-ID
selection, transcript reads, automatic project discovery or global configuration
writer exists. Registration rollback means reverting only the reviewed definition
with current-state guards; retained command trust is a separate persistent effect.
Ending an invocation-only pilot removes its declarations, not retained trust.

## Evidence and limits

AF14 preserved and reconciled the installed diagnostic patch; a non-repository
exit128 explains one historical error, not all errors. AF15 selected scoped
Docker delivery with automatic monitoring preserved for enrolled sessions and
legacy monitoring retained elsewhere. AF16's independently accepted bounded native
pilot used two Codex sessions: five bound UserPromptSubmit/PostToolUse/Stop events,
explicit completed checkpoint, fresh-session resume and repeated-resume NOOP.
The 351-binding review also verified sixteen worker/validator configurations.

That pilot's exact source included the synthetic Git trust exception removed here.
It is supporting evidence, not runtime acceptance of this stricter packaged variant.
Packaged source is covered by regression/package tests and separate final review.
Bound native SessionStart, native threshold crossing, Claude delivery, global or
future-session enrollment, real product acceptance and automatic model context
transfer remain NOT_RUN. Collector terminal/OOM and individual inherited hooks
remain UNKNOWN. PostToolUse establishes an event; a complete separately retained
artifact proving the exact harmless tool command was absent. No transcript read
was used to fill that gap. Full default-host Docker-only migration is not complete.

The original AF16 milestone requires a bounded selected-event pilot, not blanket
global rollout. Global migration is a separate deployment decision requiring a
coverage-preserving enrollment policy and exact access/trust/rollback review.


## Current native identity and manual checkpoint guidance

The shell names in examples are placeholders, not required exported environment
variables. For an already registered host, inspect its existing `native.sh`
command: its explicit arguments identify the host, registry and receipt parent;
the script directory identifies the dispatcher. Use the existing exact host/session
binding selected by the current native event. Registry filenames are SHA-256 of
`host + newline + session_id + newline`; records are fixed-format data, never shell.
Validate the record's host/session and use its approved root/store. Do not scan for
a latest session, create enrollment, or infer mount authority from hook payload paths.
Pass each path and identifier as an individually quoted CLI argument. No global
shell export is needed. `AI_FACTORY_HANDOFF` remains an explicit launch pointer;
a conflicting `--pointer` is rejected rather than silently overriding it.

A successful context-capable event emits `AI_FACTORY_NATIVE_IDENTITY` followed by
JSON with `schema` (`ai-factory-native-identity/1`), `host`, `session_id`, canonical
`root` and `event`. It contains no transcript path, prompt or tool contents. The
model-visible hook identifier must match `[A-Za-z0-9_-]{1,256}`; this is narrower
than the retained enrollment selector. Manual checkpoint/resume identity semantics
are unchanged. Invalid model-visible identity is rejected before state advancement.

Use only the newest host-delivered identity in the current conversation. The
session ID is protocol metadata, not an authentication token or permission to
access another path. Old/copied/foreign context cannot authorize a checkpoint.
The adapter cannot authenticate a forged same-shaped native payload; native
transport remains the trust boundary. After a later deferred/blocked/unknown event
without current identity, do not fall back to an older identity. If it cannot be
confirmed, report `CURRENT_NATIVE_IDENTITY_UNAVAILABLE` and whether the existing
registry binding was found, rather than claiming an environment mapping is absent.

The revised introduction is delivered once per guidance version on the first
successful normal SessionStart/UserPromptSubmit/PostToolUse event, including old
sessions and a prompt after unavailable startup. Subsequent successful events
refresh identity without an identity-only state write. Stop and failed/deferred
events do not confirm identity delivery. Native-event explicit-pointer resume returns its validated
summary plus identity; a consistent same-target NOOP returns identity only, without
summary replay or claim/state rewrite. The revised introduction follows on the next
normal event. Combined resume text and the serialized output envelope are checked
before claim/session writes; overflow is reported as `NATIVE_CONTEXT_TOO_LARGE`.

A project adapter should distinguish its pinned kit helper from the host's actually
registered runtime. Installing this package registers neither. A host-specific
policy overlay is a different interface: inspect its own contract instead of
assuming this package's registry format. This source update does not change any
installed adapter, hook, trust setting, policy, coverage or consumer pin. Portable
native delivery and end-to-end checkpoint/resume remain NOT_TESTED; a reported
receipt from a separate installed profile does not establish this package's behavior.

## Verification inputs for subsequent source changes

`tools/run_tests.py` runs the offline suites; run `tests/packaging` explicitly too.
The historical translation fixtures require `AI_FACTORY_TRANSLATION_BASELINE`
(original commit `2c0960885926075502a319a19eafbed901690dde`) and
`AI_FACTORY_HISTORY_BASELINE` (commit `12f51ed23cf664ac3b70e219a2d1a59a54bfeceb`).
After functional changes, set `AI_FACTORY_ENGLISH_MIGRATION_SNAPSHOT` to an immutable
source snapshot of the completed migration at
`8697a62ef37d360297d32f31019cb68690fe43a9`. The existing proof authenticates its
manifest/content; an arbitrary replacement cannot pass. This selects the subject
of the exact historical migration proof, not the live language check. The separate
`LiveCurrentLanguageTests` always audits current source using the same raw, decoded,
JSON and Python-literal rules regardless of that setting. Missing baseline inputs
are failures, not silent skips. Historical English provenance records bind their
original exact migration bytes; the new functional delta is recorded separately.
