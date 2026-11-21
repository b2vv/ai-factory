# Publish a local dashboard observation at a workflow transition

Opt-in, local-only projection of one explicitly chosen primary task record.
This is not a second tracker. It does not change or interpret the primary
record, schedule activity, run project gates, select an agent or install a hook.

At start, after a stage change, handoff or closeout, first reconcile and update
the existing primary task record and current pointer. If the owner has enabled
local dashboard publication, run the shared command in the same transition.
An existing plain Markdown task file works; no dashboard JSON needs to be
written in the project, no optional checkpoint block is required, and the
helper does not infer meaning from prose. The caller selects the primary task
record and explicitly names the transition. Do not select by mtime or publish
a historical record as current. Omit publication entirely when not enabled.

```sh
python3 -B "$KIT/runtime/checkpoint/publish_status.py" \
  --project project-a --root /absolute/registered/project \
  --record /absolute/registered/project/work/current-task.md --task M1 \
  --event stage --stage verification
```

With the same arguments, add `--apply` to actually publish. Without it, the
command asks the existing writer to validate and does not change the feed.
`--event` accepts `start`, `stage`, `handoff`, `closeout`. For `stage` specify
one of `plan`, `implementation`, `verification`, `review`, `qa`, `push`,
`update`. These are boundary labels, not outcomes. `--expect-head` and
`--expect-record-sha256` optionally compare a previously reconciled exact
snapshot. The helper checks current Git HEAD and the selected record before
and after validation; the dashboard writer checks current HEAD again.

The result atomically replaces only the previous transition. It writes the
fixed `<project>.transition.json` record through the dashboard publisher and
never writes or refreshes the separate `<project>.json` evidence. It contains
the caller-declared task ID, typed event/stage, current HEAD and observation
and record timestamps. It contains no evidence gates, source path, prose,
commands or reviewer output. A closeout marker is not proof of completion,
review, human QA, push or update. The command validates the selected local
bytes, not that the caller supplied the right task ID or reconciled the record.

By default a plain Markdown record produces a neutral, unbound transition.
A scoped projection is optional: pass `--scope-id` with a canonical lowercase
slice ID only when the same primary record already has a consistent
[pending-action block](../../ai-factory/task-continuation.md#optional-read-only-pending-action-check).
The helper calculates its scoped snapshot ID by reusing the read-only validator;
it does not accept an arbitrary digest. Revalidate before applying. Existing
unscoped evidence is preserved but cannot certify the new active slice. Gates
are applicable only when separately curated evidence declares the same explicit
task, slice ID, scoped snapshot and full HEAD, and both records are fresh.
Same HEAD alone never moves evidence from one slice to another.

## Local activation and failure boundaries

Use the reviewed installed kit; adding this command to the kit does not install
or activate it on any project. Set up once, outside all projects, an
owner-private file (0600) with canonical absolute paths, then explicitly set
`AI_FACTORY_DASHBOARD_BINDINGS` in the authorized local execution environment,
or pass `--bindings` in the command. Neither produces a project-local hook.
An example shape with placeholders:

```json
{
  "schema": "ai-factory-dashboard-bindings/2",
  "publisher": "/absolute/local/dashboard/bin/dashboard-publisher",
  "feed": "/absolute/local/dashboard/feed",
  "dashboard_projects": "/absolute/local/dashboard/projects.json",
  "projects": {
    "project-a": {"root": "/absolute/registered/project"},
    "project-b": {
      "root": "/absolute/registered/project-b",
      "record_roots": ["/absolute/registered/project-b-records"]
    }
  }
}
```

`dashboard_projects` is the same projects config the dashboard reads
([`runtime/dashboard/projects.example.json`](../dashboard/projects.example.json)
shows its shape). It must register each bound project with exactly the same
`root`, be owned by you and not group/world writable, and lie outside the feed,
project and record roots. The helper passes it to the writer as `-projects`;
project IDs are never hardcoded in the kit. A `bindings/1` file is rejected.

Register only intended projects. `record_roots` is optional and should list
only specific external primary-record directories that the owner intends to
use. Keep the bound feed (0700) separate from the project and any record roots.
Provide the owner's already-reviewed native executable from the local dashboard
source (built once with its documented setup), not an arbitrary script or a
binary from a consumer repository. The binding is the owner's trust decision
about the writer and destination, not a credential or authority for other work. The shared command reuses that executable's
separate transition mode, validation, lock, atomic replacement and 48-hour freshness rules rather than
reimplementing the writer. It does not build, deploy or restart the dashboard.

`VALIDATED` means preview only. `PUBLISHED` means the bound local writer accepted
that transition, the stored sidecar exactly matches the supplied bytes and no source change was detected across the publication.
`UNBOUND` or `BLOCKED` does not change task authorization or gate state. A
publication timeout or missing exact receipt or source change after apply is
`OUTCOME_UNCERTAIN`: inspect the dashboard feed before retrying. Do not
automatically replay or undo: the neutral snapshot may already be visible. A report is advisory local metadata; it establishes no
agent activity, independent evidence truth, or whole-tree freshness.
