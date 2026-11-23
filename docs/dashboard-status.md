# Publishing a project's status to the dashboard

For agents working in a project whose managed block (AGENTS.local.md) contains
"Dashboard status for this project". Without that line, the host has no dashboard
configured for the project: skip this.

## When

After a stage of the project's **primary task** is recorded in its task record:
plan accepted, implementation recorded, tests run, review done, push, update/install,
closeout. Publish **after your own commit** for that stage, if any: the command binds
the status to the project's current HEAD, and the dashboard shows it only while HEAD
stays there. A later commit by anyone shows the card as "Застаріло" (stale) until the
next stage is published. That is the intended signal, not an error.

## How

Write the status JSON from the task record, then run the command from the managed
block, first without `--apply` (validation only), then with it:

    python3 -I <kit>/tools/kit.py project status --root <kit> --project <id> < status.json
    python3 -I <kit>/tools/kit.py project status --root <kit> --project <id> --apply < status.json

The command adds `schema`, `project`, `revision` (current HEAD) and `updatedAt` (now).
Do not set them yourself. It prints the publisher's verdict and never the record text.

## The JSON

Fields: `taskId`, `title`, `state`, `next`, `sources`, `stages`, optional `markdown`.
The full contract is the "Status contract" section of the dashboard's README.md, in
the dashboard source directory configured on this host (`kit.py project dashboard
--source`); the publisher rejects anything else. In short:

- `taskId`: lowercase slug; `title` ≤ 160 characters; `next` ≤ 560 characters.
- `sources`: 1–12 references `{id, kind, role, label, recordedAt}`. `kind` is one of
  `plan-review`, `work-record`, `test-record`, `push-receipt`, `update-receipt`;
  `role` is `review-recorded`, `author-recorded` or `operator-curated`; a `plan-review`
  must be `review-recorded`. `recordedAt` is when the evidence was recorded, not now.
- `stages`: exactly Plan, Implementation, Tests, Review, Push, Update, each
  `{name, state, detail, sourceId}`. A stage without evidence is `Unknown` with no
  `sourceId`.
- Stage states with their evidence kind: Plan `Accepted` (plan-review); Implementation
  `Recorded` or `Probes recorded` (work-record); Tests `Recorded pass`, `Partial evidence`
  or `Blocked` (test-record); Review `Final verdict not recorded` or `Plan only`
  (work-record or plan-review); Push `Recorded` (push-receipt) or `Not recorded`
  (work-record); Update `Recorded` (update-receipt) or `Not recorded` (work-record).
- `state` must agree with the stages: `Verified locally` needs Tests `Recorded pass`;
  `Decision needed` needs Tests `Blocked`; `Verification pending` needs Tests
  `Partial evidence` or `Unknown`; `Plan accepted` needs Plan `Accepted` and
  Implementation `Unknown`; `Recorded` needs at least one stage with evidence.

## Rules

- Evidence only from the task record and its recorded reviews, tests and receipts.
  Never infer a pass, a review or a push. If a stage has no recorded evidence, it is
  `Unknown`.
- No file paths, URLs, secrets or personal data in any text field: the publisher
  rejects them, and the status can be shown on a shared view.
- A refusal (HEAD moved, an observation not later than the current one, another
  publish in progress) is reported, not worked around. Do not retry in a loop.

## The open-task list (queue)

With the status, publish the project's open tasks so the owner can see what each one
carries and choose the next one without opening the repository:

    python3 -I <kit>/tools/kit.py project queue --root <kit> --project <id> --apply < queue.json

The input is `{"items": [...]}`, built from the project's task index: **every task that is
not closed** (not DONE, not CANCELLED), in the order you want shown. Each item is
`{id, title, state, summary, blockedBy?, recommended?}`:

- `id`: the task id as a lowercase slug (for example `t24`); `title` ≤ 120 bytes.
- `state`: `In progress`, `Ready`, `Proposed`, `Paused` or `Blocked`.
- `summary`: one plain sentence or two (≤ 560 bytes) from the task record: what the task
  changes and why it matters.
- `blockedBy` (only with `Blocked`): what it waits for, for example `T05`.
- `recommended: true` on at most one item: the task you propose next.

The command adds `schema`, `project`, `updatedAt` and `omitted`; do not set them. If the
list exceeds 64 items or 32 KiB it keeps your order and drops items from the end, and
the card says how many were not shown. Publish `{"items": []}` when no task is open. A
project without a task index publishes no queue; its card then says the list is not
published. The list is not bound to HEAD: it stays shown after later commits, with its
publish time, and is marked outdated after 7 days. The same text rules apply (no paths,
URLs, secrets or personal data).
