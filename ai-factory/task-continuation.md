# One task index, one current record

Use the project's existing index and phase/task records. Do not transplant another
project's directory tree, add a second tracker, or treat a shell command as a task
scheduler. The current user request and local contracts remain authoritative.

## Navigation and ownership

- The task index contains task identity, state and a pointer to its primary record
  and final result. Keep completed/superseded pointers; do not reopen them merely
  because an old handoff says "next". Preserve the project's status vocabulary.
- The primary task or phase record contains scope, acceptance, per-task
  [READY/BLOCKED](pre-code-checkpoint.md), decisions, writer/reviewer, evidence and
  the [pending next action](review-handoff.md#pending-next-action). A phase can have
  independently ready and blocked slices. Batch approval is not per-task READY.
- An agenda explains which direction to choose and why, not what is currently
  executing. Briefing is a dated cache of facts, not normative acceptance. At start,
  handoff and closeout, reconcile their current-work pointers with the primary
  record and actual relevant Git/WIP. Rebuild an agenda when the direction or
  blocker changes, or the user asks what is next, not after every tool call.
- Record one active writer and the independent review route. Update the index's
  state/pointer when the primary record changes state. Do not duplicate the detailed
  evidence there. If the two disagree, report the conflict and reconcile from current
  evidence; never quietly pick whichever copy looks newest.

For a clear new task, establish its own pointer without resuming unrelated work.
For "continue", read the explicit task pointer, verify HEAD and relevant scoped
bytes, and recover the exact next action. Multiple candidates require an explicit
choice, not recency. Saved records are context, never new authorization. A fresh
session still follows [continuation confirmation](review-handoff.md#pending-next-action).
Compaction of an already active task does not require restarting its lifecycle.

## Reconcile each candidate with the current direction

When recommending or resuming a task, first compare its actual scope with the
current approved roadmap/direction, applicable owner decisions, delivered slices
and dependencies. This is part of task selection, not a question the owner should
have to repeat after every roadmap change. A short sourced note is enough for an
obvious simple task; no new file or mandatory JSON block is required.

1. If the owner stopped work to change direction, preserve that stop and the full
   earlier task/plan history. Identify the selected current roadmap and its approval
   evidence. A newer date, fresh roadmap draft or copied instruction is not execution
   permission, a priority override or an automatic supersession decision.
2. Read the candidate's scope, relevant current and historical sections, delivered
   reports/artifacts and predecessor outputs. Match by behavior and acceptance,
   not just task IDs: a differently named roadmap slice may already have delivered
   the same feature. A status word alone is not the output a dependent task needs.
3. In the existing primary record, state which parts are aligned and unfinished,
   already delivered, partial overlap, conflicting, or unknown. Cite exact sources
   and explain the correspondence. Check both positive evidence and coverage limits;
   an empty list of found work is not proof that no implementation exists.
4. Resolve a stale index/header from an explicit current primary record and sourced
   supersession, not filename/date/position alone. Unresolved current/current or
   owner-decision conflict is NEEDS_RECONCILIATION. A known scope conflict, duplicate,
   partial overlap or unfinished/missing predecessor output blocks the dependent
   implementation. Independent unaffected work may still be recommended within its
   own scope and permission. Do not silently close, delete, supersede or rewrite an
   old task to manufacture consistency.
5. Recommend one specific remaining action with the cited rationale. Do not rerun a
   completed predecessor. A retired task's replacement is a pointer, not permission
   to execute that replacement. Reconcile/rescope through the existing owner and
   task record, then apply per-task readiness and current authorization. Preserve
   completed stages and the existing assigned reviewer when scope is unchanged.

Reading the current roadmap once at session start is insufficient if direction,
relevant delivery or dependencies changed later. Recheck the affected candidate at
recommendation/resume/handoff boundaries; do not restart unrelated accepted work.
Source interpretation and scope completeness remain the agent/operator's job.

## Optional read-only pending-action check

When machine checking helps, place exactly one `ai-factory-pending-action` fenced
JSON block in the existing Markdown primary record, or use that record's JSON
form. Do not maintain a separate JSON mirror. The portable schema is explicitly
`ai-factory-pending/1`; historical project-local schema `1` is not silently migrated.
A [complete synthetic example](../examples/checkpoint/pending-action.json) shows
the fields; replace its fixture identities and hashes with actual current evidence.
Markdown without JSON remains supported by the manual contract.

```sh
python3 -B "$KIT/runtime/checkpoint/pending_action.py" \
  --root /explicit/canonical/repository \
  --record /explicit/canonical/existing-task.md --task TASK-ID
```

`KIT` means the reviewed installed managed kit, not a development branch. The
helper reads only the explicitly selected record, scope and completion evidence,
and read-only Git root/HEAD. It does not enumerate tasks, write bindings or state,
claim a task, confirm continuation, dispatch review, send messages, install hooks
or access a session-handoff store. It can read a primary technical record outside
consumer Git history. Scope paths stay relative to the repository; evidence paths
stay relative to the primary record's directory with no `..` or symlinks. All
paths are explicit canonical paths. Secret/config paths are refused heuristically,
not universally detected: never put credentials or private transcripts in inputs.

The schema requires task/revision/stage, root/HEAD, a nonempty map of scoped file
SHA-256 values (`null` declares an absent/deleted path), writer/reviewer and review
mode, action ID/owner, next action, contact/delivery/authorization-source descriptions,
state/transfer, runtime availability, required-final-verdict flag and a checks list.
`superseded` is also supported when explicit ordering evidence establishes its
replacement; it never auto-follows that replacement. `waiting`, `blocked` and `paused` require `next_check`; unavailable runtime requires
`blocked`. A reviewer must differ from the writer; `existing_session` requires an
assigned reference. These are declarations, not authenticated identities.

For `completed`, list the applicable checks. Every required check must be PASS;
a PASS includes an existing evidence `path`, its `sha256`, and `snapshot_id` (the
helper's digest of root/HEAD/scope, available from an earlier consistent read).
An optional non-PASS/N/A needs a reason. Check applicability and evidence truth are
still the operator's responsibility. Required final review needs `verdict_received`,
package ID, verdict path/hash and a verdict matching task/revision/root/HEAD/scope/
package/reviewer, `outcome: ACCEPTED`, no blocking findings, and nonempty evidence.
Otherwise an explicit local `review_na_basis` is required. Use the existing review
package/gates to establish real acceptance; this checker cannot replace them.

| Output | Meaning |
|---|---|
| `CONSISTENT` + `REVALIDATE_AUTHORIZATION` | Explicit record and scoped bytes agree; check current request, readiness and permissions before any action |
| `RECONCILE_DELIVERY` | An attempted send has an uncertain result; inspect its receipt before any retry |
| `WAIT` | Waiting, sent or acknowledged; do not resend or manufacture a verdict |
| `DO_NOT_RESUME` | Completed or paused; no automatic continuation |
| `BLOCKED` | Invalid/stale input or an explicitly blocked task; reconcile the primary record |

Exit 0 means declaration consistency, including honest WAIT/PAUSED/BLOCKED task
states, not readiness or successful execution. Invalid/stale inputs exit 1. Two
read passes catch observed edits; they do not lock writers or provide an atomic
filesystem snapshot. Unlisted files are outside coverage. Recheck before acting.
There is no proof of review independence, omitted gates, evidence truth, transport
exactly-once semantics or native agent compliance.

## Optional evidence-backed ordering check

For an ambiguous candidate or roadmap pivot, the same primary JSON block can include
`ordering`. The helper remains read-only. Do not create a parallel task list or JSON
mirror to invoke it. Without this block, old calls retain their behavior and report
ordering `NOT_CHECKED`, not "no contradictions". If this step needs mechanical evidence
checking, explicitly add `--require-ordering` to the command above. Missing evidence
then returns NEEDS_RECONCILIATION with exit 1.

The supplied declarations are:

- `observations`: up to 64 unique `id`, `kind` (`task` or `decision`), `subject`,
  normalized `value`, and `source` objects. Task values are planned, pending,
  in_progress, waiting, blocked, paused, completed, superseded or unknown. Decision
  values are allow, block, defer or unknown for one explicitly named topic. A
  superseded task additionally names its `replacement`, never itself.
- `supersedes`: optional observation IDs for the same kind/subject, plus a `resolution`
  source quoting the actual supersession basis. Acyclic links retire older claims;
  time, file order and a role label do not. The helper verifies the citation, not
  whether the source truly has authority to supersede another decision.
- `dependencies`: explicit predecessor `task_id` and `outputs` evidence objects.
  Each relevant predecessor needs an unambiguous completed observation and at least
  one current output. Missing/uncompleted/superseded predecessors block; the helper
  does not silently substitute a replacement or recursively schedule a graph.
- `decision_topics`: the applicable observed owner-constraint subjects. Conflicting
  live values need reconciliation; block/defer blocks implementation. An allow claim
  is not security approval, new authorization or proof of source authorship.
- `direction`: `task`, `roadmap`, `approval` and `coverage` sources, a short `rationale`,
  `assessment` (aligned/conflict/duplicate/partial/unknown), and a `completed` list.
  Each delivered item names its `task_id`, `relation` (distinct/overlap/duplicate/unknown)
  and `evidence`. An empty delivered list still needs sourced coverage rationale.
  Here roadmap can be the current agreed direction/task contract where no roadmap
  exists. Semantic correspondence is declared by the agent and independently checked
  where required; it is not inferred from prose by this helper.

Each source/output/evidence object has a relative `path`, full-file `sha256` and
exact `quote` (8–4096 characters), plus optional `base: repository` or `base: record`
(the default). All named files are bounded, path-checked and re-read for observed drift.
For prose already in the primary Markdown record, use `base: primary`, omit `path`,
and hash the UTF-8 quote itself. That quote must occur outside the pending-action
JSON block; quoting a claim only inside its own JSON cannot serve as evidence.
The whole primary record is already checked for concurrent changes. This avoids a
self-referential full-file hash or a second primary document. Pure JSON records use
external existing source references instead.

The helper does not parse arbitrary roadmap/task Markdown into claims. It detects
contradictory supplied live observations and the declared conflict/overlap states,
checks referenced bytes/quotes, and returns RECONCILED, NEEDS_RECONCILIATION, BLOCKED
or DO_NOT_RESUME. RECONCILED still requires readiness and current authorization.
When blocked, `next_action` asks for reconciliation and the old instruction is kept
only as `recorded_next_action`. It does not rewrite task state. Irrelevant task
conflicts do not automatically block an independent candidate. Omitted subjects,
incorrect interpretations and forged/misclassified approval are not detected.

When ordering is present, the checkpoint `snapshot_id` also binds that complete
ordering declaration. Completed checks must bind this ID; required final verdicts
also include the matching `ordering_snapshot_id`. Changes to direction/claims/evidence
therefore require affected evidence and review revalidation. Without ordering, the
legacy root/HEAD/scope digest is unchanged.

## Global delivery and project binding

The normal full-component [managed-kit update](../docs/managed-kit-connections.md)
delivers this core helper and shared rules. Global skills keep their current shared
installation; no task-specific skill copy is needed. The project connector's
explicit `--task-index` points AGENTS.local.md at an existing Markdown index. It
preserves that pointer on subsequent reconnects; `--clear-task-index` removes only
the managed pointer. It does not create or edit the index, migrate the local workflow,
or install a hook. Keep project-specific rules in AGENTS.local.md/the local adapter.

Task recovery and size-triggered checkpoint/resume are separate. If the optional
Docker guard is actually installed and registered, its manual route must use that
same trusted mapping and exact checkpoint ID. A historical `DEFAULT_STORE` call,
a registered capture hook, or files in an old host profile do not establish that
route is active. Do not mix profile syntaxes/stores or fix an unproven mismatch by
silently retargeting live hooks. First inspect, then test an isolated selected-store
round trip. Native hook activation and fresh-session delivery need separate proof.
