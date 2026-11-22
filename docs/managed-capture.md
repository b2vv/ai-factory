# Global Claude archive capture

The managed kit supplies one shared dispatcher and bridge. A command-hook
registration is separate from installing those files. An explicitly approved
private mapping enrolls exact physical Git roots, each with its own existing
capture-only credential, source identity, queue directory and private status file.
No credential values or machine paths belong in this repository's portable package.

A global Claude `Stop` hook routes by the event's canonical working directory and
verified Git root. It does not treat arbitrary child directories or nested repositories
as enrolled by prefix. Unknown projects are ignored before opening their transcript
or any credential. Git failures, symlink ambiguity, duplicate identities and malformed
mappings fail closed. The server still checks grant scope and consent on every send;
a local mapping cannot grant server access or restore revoked consent.

## Normal update, not a separate hidden installation

Initial enrollment requires an explicit reviewed capture specification. Supply it to
the normal managed-kit update, retaining the complete selected component set. Review
the combined plan before execution under an exclusive configuration-writer window.
Once registration succeeds, later normal updates reconcile the pinned registration
without asking agents to repair each project by hand. Changing enrolled scope is a
new explicit specification change, not an incidental package update.

## Adding or removing a project: the kit's project list

Once the kit has a project list (`<kit>/.ai-factory-state/projects.json`), the list owns
the mapping and the registered specification's `projects` rows are only the historical
first enrollment. The global hook command and the registration stay unchanged. Each
command below prints a plan; add `--apply` to write:

- `kit.py project migrate --root <kit> [--include-root <root>]` builds the list once from the
  registered rows and any project-local capture hooks of the named roots. It writes only the
  list and stops unless the list regenerates the current mapping byte-for-byte.
- `kit.py project install --root <kit> --project <root> --capture-credential <file> [--id <uuid>]`
  connects the project (managed block, import, ignore rules), adds its list entry and its
  mapping row. `--no-capture` lists it without capture. The credential file must already
  exist; issuing archive grants on install is a later step.
- `kit.py project remove --root <kit> --project <root>` removes the managed block, the entry
  and the mapping row; archive data, grants and credential files are kept.
- `kit.py project list --root <kit>` prints entries and capabilities, never route paths.

A write takes the kit lock, backs up every file it may change, writes the list last and
restores the backup on failure; an interrupted write is restored by the next write command.
It refuses while a kit update is unfinished and when the mapping was edited outside the
kit. A linked worktree is captured as its main checkout's project. After the list changes
the mapping, rolling back a capture or instruction transaction recorded before that change
is refused, because its recorded mapping no longer matches.

The update must verify package integrity before loading its connector and bind its
plan to the exact specification, installed state and host-file before/desired hashes.
A package install alone without an authorized registration never activates capture.
Use the CLI help for the exact plan, execute and recovery options shipped with the
version being installed; never substitute an unreviewed sequence of manual edits.

### Registration specification

The private specification has `schema: 1`, `home`, `managed_root`,
`registration_root`, `mapping_path`, `python`, and `projects`. Each project row names
`root`, `project` (UUID), `source_instance`, `credential_file`, `queue_dir`, and
`status_file`. The optional `retire` list names exact `path`, `command`, and
`hook_sha256` values. Obtain these from an authorized local inventory, not from a
portable example containing invented identities. The mapping and registration store
must be private; credentials remain in their original approved files.

Initial read-only plan (append every previously selected `--component`):

```sh
python3 -B "$PACKAGE/tools/kit.py" update --package "$PACKAGE" --root "$KIT" \
  --capture-spec "$PRIVATE_SPEC" --component core --component capture-bridge
```

The two components shown are a minimal example, **not** permission to remove the
other components in an existing kit. Execute the exact reviewed plan with
`--execute --exclusive-window --plan-id '<combined-plan-id>'` and the same inputs.
On subsequent updates omit `--capture-spec`: the existing pinned registration is
reconciled automatically. Retain the returned integrated transaction ID and exact
package for guarded rollback. No rollback or retry should be inferred from a generic
error; inspect the reported phase and its linked receipts first.

## Safe migration from project hooks

Inventory the exact old command and full hook definition digest for each registration
to retire. A filename or the word `capture` is not proof of ownership. Preserve
unrelated hooks, matchers, permissions and project work. Include accidentally installed
parent-directory hooks explicitly rather than assuming they are inherited.

Publish the global registration before retiring the identified local hooks. During
any overlap, both routes must preserve the same endpoint, project, source, principal,
queue directory and immutable transcript record IDs. The durable queue, not an
assumption about host ordering, deduplicates repeated events. Do not stop active
sessions. Host settings reload and native invocation require separate observation.

The transaction is atomic per file, not atomic across all host/project files. Record
private backups and before/after signatures before mutation. An interruption is a
blocked reconciliation task, not permission to replay. An exclusive writer window
is required: a digest check plus rename is not true compare-and-swap against unrelated
writers. The registration receipt binds whole settings-file signatures: even an
unrelated later settings edit can block reconciliation or rollback. This is an
explicit review/reconciliation requirement, not permission to overwrite that edit
or a claim of automatic merging. Rollback must restore the local hooks before removing the global hook, and
must refuse unknown edits. Retain queued records and delivery receipts on rollback.

## Delivery and acceptance

The hook uses the existing bounded private durable queue. A timeout is ambiguous;
workers retry identical frozen payloads, and a successful hook exit is not evidence
of delivery. Existing project-scoped supervisors remain necessary for retry without
new user turns and for login recovery. Do not put credentials in supervisor arguments
or logs. A new dispatcher does not backfill previously missed conversations.

Verify separately: package signatures, global registration, exact mappings, retired
managed duplicates, private status paths, running scoped workers, queue counts, native
Claude events and a complete paginated search. A zero-hit page with a cursor does not
establish absence. Use clearly labeled synthetic turns and report them as retained test
records. Tests of restartable workers do not establish Mac reboot behavior. Model
choice is separate from command-hook registration: the host invokes the command.
