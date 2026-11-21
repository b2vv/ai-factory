> Optional retained portable profile; the full canonical plan is in `ai-factory/`. This profile does not replace original skill contracts or authorize automatic activation.

# Additive change, repeat and guarded restore

[Entry](onboarding.md) · [Acceptance](../../templates/acceptance-portable.md)

This is a protocol for an already-authorized writer, not an automatic apply command. Preflight remains read-only. Receipt/backup/diff files are stored in the task workspace, not in an additional repo tracker. Repeating uses the same canonical adapter and entry marker/path.

## Before writing

1. Inventory identifies one existing authoritative entry and task workflow. If an adapter/pointer already exists, read it; do not add another directory, block or rule copy. Check semantic duplicates manually; an exact hash does not find them by itself.
2. Record root, branch, HEAD, scoped dirty/untracked state. Select explicit files, check resolved paths and absence of symlink/secret/config targets. For an existing entry, the change is only a minimal pointer/reconciliation of a descriptive fact. Do not rewrite a normative conflict without the owner's decision.
3. For each file, keep a receipt: absolute target, existed_before, baseline SHA256 (or null), byte-for-byte backup path (or null), proposed SHA256, diff, authorization/source, operation status. The backup includes others' already-existing dirty bytes; this does not authorize overwriting them. Do not write secrets into the receipt.
4. Inspect the full diff and independent review. Before each write, recheck existence/type/parent paths and baseline SHA. Any change means BLOCKED for that file, not force overwrite. The short apply needs an agreed window without a concurrent writer: a hashguard is not an OS-lock. Preserve existing file permissions. Write only reviewed bytes, then verify applied SHA and mark the receipt applied.
5. After applying, check links/anchors, adapter compatibility and the receipt. `adapter_files` in the manifest contains canonical destinations and desired SHA: preflight must return NOOP for matching bytes. Different bytes → BLOCKED/reviewed merge, not automatic reapply. Do not treat NOOP as semantic acceptance or runtime PASS.

## Restore only your own applied diff

Restore requires an instruction in the current scope; having a backup does not itself direct rollback. Do not use git reset/checkout/clean or a full repo snapshot.

- The receipt has applied=true and applied SHA. Recheck target type/path and **current SHA == applied SHA**. Otherwise, BLOCKED: preserve the concurrent change; a manual merge with its owner is needed, not overwrite.
- Existing file: verify backup SHA == baseline SHA, restore only its bytes/permissions, verify baseline SHA. New file: remove only this exact applied file under the guard; do not recursively delete directories or remove unrelated files.
- Partial apply: restore only written applied entries; leave untouched files alone. Record per-file restore results; do not call the transaction atomic across multiple files.
- Repeat restore: baseline already restored or own new file already absent → NOOP. Different content → BLOCKED. Backups/receipts remain as evidence.

Minimum disposable rehearsal: add → repeat NOOP; existing merge preserving owner bytes; concurrent edit → apply/restore BLOCKED; own applied bytes → baseline restore; new file → exact removal; repeat restore NOOP. This checks the protocol on fixtures, not permission to work on other repos.
