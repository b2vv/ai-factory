# Managed native handoff connection

This is an explicit companion to `kit.py` and `connect-project.py`, not an installer side effect. Package installation alone does not activate hooks. Native handoff uses the installed `runtime/session-size/native.py`, its canonical guard, one operator-selected private store, and an explicit enrolled-root profile. It does not call Docker, read transcripts, launch models, or choose the latest checkpoint.

## Context capacity and hook output

Native context capacity belongs to the host. A transcript's file size is not the
model's current token occupancy: it includes service events, repeated hook output,
encoded images and historical records that can survive compaction. The native
route therefore does not stat/read the transcript, apply the legacy 4/5 MB
thresholds, create byte-triggered drafts, or tell an agent to stop based on bytes.
It does not infer tokens by filtering JSONL records or dividing bytes by a ratio.
Use the host's supported auto-compaction setting instead. A configured target
(such as 600,000 tokens in a supported Claude configuration) remains bounded by the
actual model window; Factory does not change or certify that setting. Codex and
Claude settings are independent. Manual checkpoint/resume remains available.

Identity context is emitted at SessionStart and UserPromptSubmit, and as part of
an actual explicit resume when needed. Routine PostToolUse/Stop calls are silent
after one policy introduction; they can still retry an explicit pending handoff.
Ordinary lock contention without an explicit handoff is silent, not a work stop.
The policy introduction also corrects old 4/5 MB guidance in existing state without
rewriting historical checkpoints, incomplete drafts or claims.

Global hooks and retained project wrappers may both call the same runtime.
Under the shared lock, repeated identity attempts with the same event and valid
prompt/source metadata are coalesced for two seconds. Only a hash and timestamp
are stored, never prompt text. Missing/malformed metadata is not deduplicated;
changed event/source/prompt or an elapsed window permits fresh identity. This is
best-effort output deduplication, not host-delivery acknowledgment. Explicit
handoff validation and claim handling always occur first and remain unchanged.
Do not delete project workflow hooks merely because they call the shared loader.

The canonical guard's legacy callable byte monitor is retained for compatibility;
the managed native entry point explicitly selects host-managed behavior. Historical
Docker/legacy runtimes are not migrated or activated by this change. Native
compaction and actual host receipt still require separate runtime verification.

## Initial connection

First verify the exact package and install the complete selected component set into the stable managed root. The package must include both native.py and session_guard.py with supported handoff API version 1. Do not edit managed files by hand.

Prepare a private JSON connection specification with explicit `home`, `managed_root`, `store`, `roots`, `profile_path`, `registration_root`, `hosts`, and `python` keys. Hosts are a nonempty subset of `claude` and `codex`; roots are unique canonical physical Git roots. The Python executable is a reviewed absolute regular executable, not a shell command or a guessed PATH alias. The profile and registration state must not overlap the managed kit, store, project roots or host settings roots.

An optional `legacy` object names exactly the selected home's `.agents/ai-factory/session-size/session_guard.py` and its exact `before_sha256`. This produces a compatibility loader, not another implementation. Existing project wrappers remain untouched. Optional `retire` entries have exactly `host`, `event`, `command`: only those exact inventoried registrations are retired. A command containing the word Docker is not sufficient identification. Existing archive/status/graph/reuse handlers are retained.

Run the installed `tools/connect-handoff.py --spec /absolute/reviewed-spec.json` to obtain a read-only plan. Review exact paths, commands, before/after signatures, kit identity and interpreter identity. Apply only in a coordinated exclusive writer window with `apply --spec ... --plan-id <exact-plan-id> --exclusive-window`. Apply returns a transaction and private receipt after verifying all writes. It does not write Codex trusted_hash, host permissions or authentication settings. Obtain normal host trust/activation separately; a saved configuration is not evidence that the host invokes it.

The fixed global hook events are SessionStart, UserPromptSubmit, PostToolUse and Stop. Stop is advisory and cannot consume a pending handoff. The native entry point refuses explicit handoffs/manual operations outside enrollment; optional monitoring for unselected roots is a no-op.

## Normal managed update

1. Coordinate one writer and run the existing full-component `kit.py plan`/reviewed update protocol. Keep the native session component selected. The stable hook command and compatibility loader continue to point to the managed path, so updated runtime bytes reach every enrolled consumer without copying or editing per-project code.
2. Run `connect-handoff.py verify --spec ...` from the installed kit. This validates installed receipts/signatures, required API, exact registered bytes and interpreter binding. `kit_changed: true` reports a new valid kit identity; it does not mean hooks failed.
3. Re-run the read-only registration plan and apply its reviewed identity-only transaction when required. An unchanged profile/command preserves configuration bytes. Repeat plan/apply must be NOOP. Removing the runtime component, incompatible API, unexpected settings drift or pending transactions is BLOCKED, never a false success.
4. Check actual native delivery separately in the intended hosts and project contexts. Already-running sessions may cache host settings or context. Do not stop them or claim a kit update rewrites model memory. No native delivery test is implicitly authorised by verification.

## Public checkpoint and exact resume

All public routes require the reviewed profile. Hook guidance emits the exact installed command with current host/session/root. Use only the current host-delivered identity, never a hash reconstructed as a UUID. `native.py checkpoint --profile ... --host ... --session ... --cwd ...` reads the five-field sanitized JSON summary from stdin. Each field is at most 1600 characters; the entire encoded record and delivery context must also fit their bounds.

`native.py resume --profile ... --host ... --session ... --cwd ... --id <exact-id>` is explicit and snapshot-bound. The canonical guard's old independent `--store` CLI delegates to this profile-required route. The legacy loader fixes its profile and rejects an alternate profile/store. Existing incomplete records remain incomplete; neither migration nor an unknown source identity authorises completing them by substitution.

A checkpoint reuses a matching ID only while complete, unclaimed and within its validity window. Refresh after expiry or consumption creates a new immutable generation. A same-target repeat after a recorded claim does not replay the summary, including after later working-tree changes. A partial state/claim pair is blocked for manual reconciliation. Persisting a claim gives at-most-once emission, not an acknowledgment from the host: a postclaim output/transport failure is OUTCOME_UNCERTAIN, not confirmed delivery. Never delete claim markers to retry.

## Recovery and rollback

Multi-file registration cannot be globally atomic. Every before/after state is hash-bound and recoverable. An interrupted PREPARED/pending transaction blocks another apply. Inspect its private receipt, then use `rollback --spec ... --transaction <exact-id> --exclusive-window`. Rollback checks all affected targets before restoring exact prior bytes/modes; a foreign edit blocks it. Do not clear the pending marker or overwrite drift. Repeating an already completed rollback is NOOP.

Rollback of registration and rollback of kit files are distinct. Follow the existing kit rollback plan contract for package files and reverify compatibility afterward. Neither rollback deletes session history, imports Docker stores, changes authentication/trust or stops Docker resources. Restoring previous Docker registration bytes can restore the old broken behavior; that is an operator recovery choice, not the desired deployment.

## Evidence boundaries

Isolated fixtures test schema/claims, upgrade/NOOP/rollback, failure injection and unrelated-hook preservation. They do not prove native discovery, trust, model access or delivered context. A source checkout with another writer is not an approved packaging input. Full source/release gates, exact independent final review, a live writer window and native output receipt remain separate prerequisites.

### Explicit reconciliation of the reviewed Claude compaction setting

When an owner has added `autoCompactWindow: 600000` after registration, normal
plan/verify still rejects whole-file drift. The narrow `reconcile-plan` and
`reconcile-apply` modes accept `--accept-settings-sha256 <reviewed-current-hash>`.
They recover the registered settings from integrity-checked transaction evidence,
require every other JSON value (including hooks and permissions) and file mode to
be unchanged, and preserve the current settings bytes exactly. All other registered
targets retain strict drift checks. Apply requires the exact plan ID and
`--exclusive-window`; no settings, trust, session store, or claims are rewritten.
A subsequent normal verify must be VERIFIED and normal plan NOOP.

This is not a generic drift adoption option: missing baseline evidence, other
settings edits, a different threshold, stale hash, changed hooks or pending
transactions block reconciliation. Rolling back its receipt-only transaction
restores the old registration receipt, including its previously stale relationship
to the preserved user settings; it does not undo the owner's compaction setting.
