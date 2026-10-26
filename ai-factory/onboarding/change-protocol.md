<a id="additive-зміна-повтор-і-guarded-restore"></a>
# Additive change, repeat and guarded restore

[Entry](../onboarding.md) · [Acceptance](../../templates/acceptance-full.md)

This is a protocol for an already authorized writer, not an automatic apply command. Preflight remains read-only. Receipt/backup/diff files live in the task workspace, not an additional repository tracker. Repeating uses the same canonical adapter and entry marker/path.

<a id="перед-записом"></a>
## Before writing

1. Inventory identifies one existing authoritative entry and task workflow. If an adapter/pointer already exists, read it; do not add another directory, block or rules copy. Semantic duplicates are checked manually; an exact hash alone does not find them.
2. Record root, branch, HEAD and scoped dirty/untracked state. Select explicit files, check resolved paths and the absence of symlink/secret/config targets. For an existing entry, the change is only a minimal pointer/alignment of a descriptive fact. Do not overwrite a normative conflict without an owner decision.
3. For each file retain a receipt: absolute target, existed_before, baseline SHA256 (or null), byte-for-byte backup path (or null), proposed SHA256, diff, authorization/source, operation status. The backup includes existing foreign dirty bytes; this is not permission to overwrite them. Do not put secrets in the receipt.
4. Inspect the full diff and independent review. Immediately before each write, recheck existence/type/parent paths and baseline SHA. Any change → BLOCKED for that file, not force overwrite. The short apply requires an agreed window without a concurrent writer: a hashguard is not an OS lock. Preserve existing file permissions. Write only reviewed bytes, then verify applied SHA and mark the receipt applied.
5. After apply, check links/anchors, adapter compatibility and receipt. `adapter_files` in the manifest holds canonical destinations and desired SHA: preflight must return NOOP for matching bytes. Different bytes → BLOCKED/reviewed merge, not automatic reapply. Do not treat NOOP as semantic acceptance or runtime PASS.

<a id="restore-лише-власного-застосованого-diff"></a>
## Restore only your own applied diff

Restore requires a request in the current scope; a backup's existence alone does not instruct you to roll work back. Do not use git reset/checkout/clean or a full repository snapshot.

- The receipt has applied=true and applied SHA. Recheck target type/path and **current SHA == applied SHA**. Otherwise → BLOCKED; preserve the concurrent change. A manual merge with the owner is needed, not overwrite.
- Existing file: verify backup SHA == baseline SHA, restore only its bytes/permissions, verify baseline SHA. New file: remove only that exact applied file under the guard; do not recursively remove directories or remove unrelated files.
- Partial apply: restore only recorded applied entries; leave untouched files alone. Record per-file restore results; do not call a multi-file transaction atomic.
- Repeat restore: baseline already restored or own new file already absent → NOOP. Other content → BLOCKED. Keep backup/receipt as evidence.

Minimal disposable rehearsal: add → repeat NOOP; existing merge preserving owner bytes; concurrent edit → apply/restore BLOCKED; own applied bytes → baseline restore; new file → exact removal; repeat restore NOOP. This checks the protocol on fixtures, not authorization to work on other repositories.
