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

For an explicitly registered non-Docker handoff connection, follow the
[managed native handoff contract](managed-native-handoff.md). Initial registration
is an explicit hash-bound companion step, not an installer side effect. Thereafter
complete-component kit updates change the stable canonical runtime for every
enrolled project; run the installed connect-handoff.py verify and reconcile its
identity receipt as part of the update closeout. Do not silently remove its component
or treat saved hook configuration as native-delivery proof.

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
import. The block names the managed root and points agents to its `installed.json`
`latest` for the current identity; it records no version, hash or commit, so a normal
kit update leaves connected projects unchanged (a reconnect is a NOOP). Preserve everything outside managed blocks. An unmanaged import conflict
requires a reviewed surgical migration, not duplicate imports or replacement of
whole local files. Keep local entry files private through the supported ignore
rules. Preserve existing project author changes and stronger local acceptance.

Adapter and read-only search-contract pointers are dependencies, not arbitrary labels.
Both explicit and autodetected pointers must name existing readable regular Markdown
files before planning or applying. A directory, dangling link or missing explicit
path blocks the connection; the mere presence of `.ai/` does not select a route.
Inputs are checked again before publication. This guards observed drift, not a
cross-process lock: coordinate writers for the entire apply window.

When no local Factory adapter is needed, select `--global-only` explicitly. The
managed block then points to the installed kit's workflow, pre-code checkpoint and
review handoff. This choice is retained by subsequent reconnects; an explicit
`--adapter` switches back to a validated local adapter. Project architecture, task
records and stronger local rules remain
in force. This mode does not create a local adapter, copy shared rules or invent an
archive route. An existing search-only contract can still be supplied separately.
A recorded `--search-contract` is retained by later reconnects, like the task index;
if that file is gone the reconnect blocks instead of dropping or replacing the route.
Use `--clear-search-contract` to remove the pointer deliberately.
Do not restore an obsolete version-pinned adapter merely to satisfy a stale link.

The connector owns only its managed blocks. Historical links outside those blocks
require a reviewed, backed-up, narrowly scoped migration preserving all unrelated
text. After update, verify referenced documents are readable, not only that hashes
match or a repeat plan says NOOP. A search-contract file being readable proves its
availability, not credential authorization, endpoint health or complete search.

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

## Registered global archive capture

For explicitly enrolled Claude archive capture, follow [global capture](managed-capture.md).
Normal managed updates reconcile its pinned global registration and approved local-hook
retirements. Installing capture files without that registration does not enroll projects.
Keep exact Git-root routing and existing per-project capture credentials/queues; never
replace them with an operator credential or infer enrollment from a directory prefix.
Add or remove a captured project with `kit.py project install|remove`, which keep the
kit's one project list and the mapping together (see "Adding or removing a project" there).

## Exact legacy instruction migration in normal update

`tools/kit.py update --instruction-spec /absolute/private/spec.json` is an explicit
one-time registration, not a general text-replacement facility. It supports only
five reviewed recipes: the known legacy global Agents/Claude entry bodies, two
known obsolete project transcript-size clauses, and an **existing empty** default
Codex `AGENTS.md`. No project hooks, grants, server settings or task records are
changed. The ordinary complete component selection and package verification still
apply. After registration, the same normal update command without the spec
reconciles the pinned targets. Unknown content is preserved and blocks migration.

The private schema is:

```json
{
  "schema": 1,
  "home": "/absolute/owner-home",
  "managed_root": "/absolute/managed-kit",
  "targets": [
    {"recipe": "legacy-project-size-1", "project": "/absolute/owner-home/project", "fragment": "EXACT reviewed legacy clause"},
    {"recipe": "empty-codex-entry", "project": null, "fragment": ""}
  ]
}
```

The example clause is a placeholder and will be rejected. Only the built-in
SHA-256 identities of reviewed fragments are accepted; replacement bytes are
created by the updater, never supplied by the spec. Keep the real spec private
(owner-only file). Global targets are fixed under the declared home; project
recipes target only the declared checkout's `CLAUDE.local.md`. No discovery scan,
symlink migration, unknown variant normalization, or automatic registration occurs.
The empty Codex recipe matches the **whole existing file**, not an empty substring.
Other recipes still reject empty fragments. A nondefault `CODEX_HOME` or any global
`AGENTS.override.md`, including a dangling link, blocks the default Codex recipe.

Generated global entries explicitly require reading the installed canonical entry
before work, skills and delegation. They preserve the shared source-of-truth,
bounded subagent progress and launched/returned accounting rules. The Codex entry
also explicitly routes to the verified repository-root `AGENTS.local.md` when
present. Claude receives its supported `@` import as well; no assumption is made
that Codex parses Claude-style imports or discovers `~/.agents/AGENTS.md` itself.
Project managed blocks similarly include an explicit reading instruction alongside
Claude syntax. Static pointer verification is **not** evidence that an already-open
or new native session actually loaded those instructions.

The default update is a read-only plan. Review its exact target hashes and execute
only with `--execute --exclusive-window --plan-id <id>`. There is one shared-home
writer binding, root lineage, and a pending barrier: normal updates/rollbacks cannot
bypass an unfinished instruction transaction. Existing registered capture may be
included only when its plan changes **no host configuration** and no registration.
Private receipts contain full original documents and must not be published.
Targets retain their original modes; receipt/state directories are private. Arbitrary
appended user instructions remain byte-for-byte intact; unknown/ambiguous policy
fragments block instead of being guessed or silently deleted.

This is a journaled **multi-resource operation, not an atomic group**. Preimages are
validated and durably saved before delegated installation. A partial failure reports
`BLOCKED` with its outer transaction ID and leaves a pending journal. Do not replay,
clear markers, or roll back a subordinate kit/capture transaction directly. Use the
**same reviewed package's updater** (retain the package for recovery):

```sh
python3 -I -B /absolute/reviewed-package/tools/kit.py rollback \
  --root /absolute/managed-kit --transaction <outer-id>
# After inspecting that fresh rollback plan:
python3 -I -B /absolute/reviewed-package/tools/kit.py rollback \
  --root /absolute/managed-kit --transaction <outer-id> \
  --execute --exclusive-window --plan-id <rollback-plan-id>
```

Rollback restores the exact captured preimage, including an empty Codex file only
when it was originally empty. An initially canonical file stays canonical. All
restore bytes, target states, latest lineage and delegated transaction ownership
are checked before restoration; foreign edits or uncertain child outcomes block.
The shared-home writer binding remains after rollback, preventing another managed
root from independently taking over the same instruction targets.

### Why this transaction boundary

The shared-home binding is intentionally permanent: silently allowing a second
managed root to take over the same global instruction files would leave two
independent rollback histories able to overwrite one another. Root takeover needs
an explicit separately reviewed migration, not an automatic retry or owner-file
removal. A root-only lock was rejected because two roots can address the same home.

The outer journal is necessary because installing the canonical kit and updating
host pointers are separate resources. A direct edit followed by a kit update has
no common preimage or child ownership evidence; automatically replaying a failed
subordinate operation can also select a historical transaction with the same plan.
The chosen recovery binds new receipt identity, latest lineage, capture dependency
files and preimages, then uses each subordinate's existing guarded rollback. Exact
owned terminal pending cleanup is allowed only after full restored-state validation;
foreign edits remain blocking. Rollback CAS uses the validated plan's signatures,
never a freshly observed replacement baseline.

Legacy residue detection uses a fixed codepoint-length/SHA-256 commitment table for
reviewed obsolete fragments. The raw personal instruction prose remains in the
private registration. This is exact bounded matching, not general language detection,
regex rewriting, or an exception to the repository's source-language rules.
