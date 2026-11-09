# Managed kit updates and global skill discovery

Factory skills are installed once in an explicitly selected managed kit. Global
agent discovery links to that installed kit. Project-specific Factory wiring lives
in AGENTS.local.md; CLAUDE.local.md may import it. Preserve project AGENTS.md as its
existing project contract. Do not inject Factory policy blocks there, vendor shared
skills into projects, or create project-local links to a development checkout.
The source repository's maintainer AGENTS.md is not a cross-project entry point.

## One update writer, complete component selection

Inspect the current managed inventory, installed.json, latest receipt integrity,
actual signatures, pending transaction and unmanaged files first. A running agent
alone does not prove a writer; coordinate actual writers and recheck touched files.
Use the installer's lock and exclusive-window contract. Four consumers do not mean
four concurrent updates of the same kit.

Build and independently verify an exact package using the normal manifest/export
workflow. Do not include local credentials, routes, caches or private evidence.
The installer's default plan is read-only. Every requested `--component` contributes
to the **complete desired set**, not an incremental addition: retain all existing
needed components and inspect every proposed removal. Never update with only the
new skill's component. Use explicit source/destination paths and the reviewed
plan ID for `kit.py update --execute --exclusive-window`.

Keep checksums and receipts as integrity evidence. Projects reference the stable
managed root rather than a development branch or commit-specific checkout. A kit
update is an explicit reviewed publication; it is not a background Git pull.
Source Git changes must not block product work merely because the source checkout
is dirty or on a task branch. Runtime hooks, images, credentials, grants and data
remain separately controlled; installing helper files does not activate them.

## Recovery of inconsistent historical metadata

Mismatch means BLOCKED, not permission to rewrite installed.json or forge a receipt.
Preserve the full current kit, state, unmanaged files and exact overlay differences.
Only restore metadata from independently verified authoritative original bytes,
using guarded before hashes, backups and a separate recovery record. Do not call
that intermediate overlay receipt-consistent when it is not.

Rehearse a normal full-component update on an isolated copy, including retained
unmanaged data, repeat NOOP and rollback. A new genuine transaction can establish
forward consistency; retain the old discrepancy in its before-state and recovery
evidence. Rollback to an already-inconsistent baseline restores that historical
limitation too. Verify new installed/receipt equality and actual signatures before
connecting projects. Concurrent changes block the affected action, never trigger
reset, clean, untracking or blind retry.

## Global discovery, not project-local shared skill links

Run the connector from the **installed kit**, never the development checkout:

```sh
sh "$KIT/tools/connect-skills.sh" --dry-run "$GLOBAL_SKILLS"
```

Review the exact results before applying the same explicit target. The target may
be the existing shared global directory used by multiple agents; do not replace
that mixed root. Preserve local/custom skill directories and unrelated aliases.
The connector is additive. A dangling link, missing SKILL.md or link to another
location is a CONFLICT, not ALREADY. It is preserved for explicit owner review;
matching text at a different source does not prove the right dependency target.
Do not use identical-adoption or retarget other aliases implicitly.

One-time repair of a known erroneous alias needs its own exact old/new target,
backup, ownership check and guarded atomic replacement. Confirm each actual target
and installed content; printing ALREADY is not itself acceptance. Dependent skill
references should resolve inside the same reviewed installed kit.

## Project-local rules and adapters

Use the existing `connect-project.py` plan/apply workflow after kit identity is valid.
It writes the delimited connection block in AGENTS.local.md and a CLAUDE.local.md
import. Preserve everything outside managed blocks. An unmanaged import conflict
requires a reviewed surgical migration, not duplicate imports or replacement of
whole local files. Keep local entry files private through the supported ignore
rules. Preserve existing project author changes and stronger local acceptance.

For explicit task navigation, add `--task-index work/tasks.md` (or the project's
existing Markdown index) to the connector plan, review it, then apply. The target
must already exist inside the project; its bytes are never copied or rewritten.
The managed block retains this pointer on later reconnects without the flag. Use
`--clear-task-index` to remove only that pointer, or `--task-index` to change it.
Missing, ambiguous or changed inputs block the affected connection. This delivers
navigation through AGENTS.local.md, not a second tracker, automatic task selection
or hook registration. See [task continuation](../ai-factory/task-continuation.md).

The installer does not clean project AGENTS.md or project-local symlinks. Retire
only proven task-owned blocks/links with exact baseline guards and recoverable
backups. Do not repeat cleanup another project agent already completed. Resolve
symlinked project aliases to reviewed physical files without weakening path guards.
Keep search-only routing separate from capture; no key substitution, grant expansion,
backfill, hook activation or trust change is implied.

## Verify each consumer and keep the limits honest

Verify the complete install receipt and actual managed signatures, retained local
files and repeat update NOOP. Check native discovery separately in each real project
context: installed canonical paths, enabled state, no dangling/older shared aliases,
and unchanged unrelated skill entries. Files/fixtures prove neither model access
nor invocation. Preserve existing live capture and verify authorized search routes
without emitting secrets or archive text.

Already-loaded session instructions may remain cached. Arrange rereading or a new
session at a safe boundary; do not terminate active work or claim a kit update changes
model memory. The supported guarantee is the current reviewed installed kit, not
continuously latest remote main or automatically refreshed running sessions.
