# Implemented offline managed install/update/rollback

`tools/kit.py` is an executable Python CLI for a dedicated staged toolkit directory. POSIX/macOS, Python 3.9+ stdlib. It performs no network, subprocess, authentication, dependency install or host registration. Windows is unsupported. It does not merge project instructions or publish global skills.

Default is read-only `plan`. `install`, `update` and `rollback` also only plan unless passed `--execute`, the exact `--plan-id`, and `--exclusive-window`. That flag attests a coordinated period with no uncoordinated writers; it is not an OS sandbox or a lock on all external editors.

## Integrity and boundaries

The source release manifest declares exact paths, components and hashes. Every shipped file is checked, including omitted optional components; unlisted files, symlinks, traversal, sensitive/reserved destinations and hardlinked files are rejected. A source checkout's root `.git` directory is excluded and never installed. Checksums identify bytes but are not a signature: establish trusted release provenance separately before running any Python file.

Core is always selected. Repeat `--component planning`, `--component review`, `--component session-guard`, `--component graphify` for desired optional components. Installation copies only selected files into one dedicated root. Selected-state metadata remains under `.ai-factory-state`; optional files linked from documentation may intentionally be absent. Keep the original complete release as the source for future operations; a subset installation is not a complete release bundle.

Plan compares every managed file's current hash/mode with the recorded baseline. An existing unmanaged file blocks even if its bytes happen to match; local edits are never silently adopted. Unknown components fail. Components omitted on update are intentionally removed only if their managed bytes remain unchanged; the plan makes those removals visible. Unmanaged files are preserved.

Apply rechecks the plan under a nonblocking advisory lock, writes baseline backups and a checksummed receipt before payload changes, and records a pending transaction. Per-file writes use same-directory temporary files, fsync and atomic publication; additions use no-clobber links. Updates recheck hashes immediately before atomic replacement. Multi-file application is not atomic. No filesystem API here guarantees compare-and-swap against a noncooperating editor racing after the final check: the exclusive writer window is a required precondition. Detected edits block without forcing them away.

A partial failure leaves the receipt and pending transaction; new updates are blocked until explicit rollback. Rollback plans only the latest/pending transaction, verifies receipt/backups, and restores only current bytes matching its applied hash/mode. Already-restored baseline bytes are skipped. A changed target blocks rollback. New owned files are removed individually; directories and foreign files are retained. Restored operations are repeatable NOOP. Do not manually delete state or lock files to bypass a failure.

## Commands

Set SOURCE to the complete trusted release, TARGET to a dedicated canonical absolute destination, and read the plan before execution. No command below registers anything globally.

```sh
python3 "$SOURCE/tools/kit.py" --package "$SOURCE" --root "$TARGET" \
  --component planning --component review --component session-guard --component graphify
python3 "$SOURCE/tools/kit.py" install --package "$SOURCE" --root "$TARGET" \
  --component planning --component review --component session-guard --component graphify \
  --execute --exclusive-window --plan-id '<reviewed-plan-id>'
# For a new complete release, plan again with the full desired component set; then:
python3 "$SOURCE/tools/kit.py" update --package "$SOURCE" --root "$TARGET" \
  --component planning --component review --component session-guard --component graphify \
  --execute --exclusive-window --plan-id '<new-reviewed-plan-id>'
python3 "$SOURCE/tools/kit.py" rollback --root "$TARGET" --transaction '<receipt-id>'
python3 "$SOURCE/tools/kit.py" rollback --root "$TARGET" --transaction '<receipt-id>' \
  --execute --exclusive-window --plan-id '<rollback-plan-id>'
```

If an interrupted operation returned no transaction ID, inspect only the private `TARGET/.ai-factory-state/pending.json` pointer and its exact receipt. Preserve the original release and state. Resolve local edit conflicts manually; do not force/reset/clean the destination.

Automated project adapters, global aliases/hooks/MCP, tool downloads, host authentication, model routing and Windows support remain outside this implementation. Independent review and real host acceptance remain pending, distinct from isolated author tests.
