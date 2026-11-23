# Local AI Factory dashboard

A read-only, local view for the projects you list in a projects config. The
dashboard reads explicitly published status records, not agent activity,
working-tree code, archives, raw task logs, or chat transcripts. It displays
Unknown for missing, invalid, stale or mismatched records.

## Projects config

The kit ships no project list. Create a JSON file **outside the checkout**
(for example `$HOME/.config/factory-dashboard/projects.json`) from
[projects.example.json](projects.example.json) and pass it with
`-projects /absolute/path/projects.json` or `DASHBOARD_PROJECTS`. Without a
valid config the dashboard and the publisher refuse to start.

The file is a JSON array (1–32 entries, at most 64 KiB) of objects:

- `id` (required): `^[a-z0-9][a-z0-9-]{0,62}$`, unique. It names the feed
  files `<id>.json` / `<id>.transition.json` and the route `/api/details/<id>`.
- `name` (required): display name, plain text up to 80 characters.
- `root` (required): clean absolute path of an ordinary Git checkout, without
  commas, quotes or control characters. Only its `.git` metadata is read.
- `workflow` (optional): a short plain-text rule shown with the project.
- `aliases` (optional, up to 8): `[{"id": "<route-id>", "task": "<task-id>"}]`.
  An alias serves `/api/details/<route-id>` only while the project's current
  record has exactly that task ID. Alias IDs share the namespace of project IDs.

Unknown members, duplicate members or IDs, relative or unclean roots, trailing
data, symlinked or oversized files are rejected as a whole.
`go run . -projects FILE -list-projects` validates the file and prints the
`id<TAB>root` lines that the container launcher mounts.

With a managed kit the file need not be kept by hand: the kit generates
`<kit>/.ai-factory-state/dashboard-projects.json` from its project list (see
`docs/managed-capture.md`, "The dashboard's project list"). Point
`DASHBOARD_PROJECTS` at it and recreate the containers after it changes.

## Run

Go 1.27.4, Node.js and npm are needed. The lockfile pins React, react-markdown
and esbuild. Build the untracked browser bundle before compiling Go. If the
package cache is populated, dependencies can be installed offline:

```sh
npm ci --offline --ignore-scripts --no-audit --no-fund
npm run build
GOPROXY=off go run . -projects "$HOME/.config/factory-dashboard/projects.json" -feed /absolute/private/feed
```

Open <http://127.0.0.1:8732/> on that host. To run in the existing local Kiri
context, build the statically linked Linux/amd64 scratch image with
`sh docker-local.sh build` after building the browser bundle. The image runs
as a non-root user; the launcher passes your user and group IDs as the
`DASHBOARD_UID`/`DASHBOARD_GID` build arguments (default 65532). The launcher
requires `DASHBOARD_PROJECTS` and `DASHBOARD_FEED` (absolute host paths
without commas, quotes or newlines); the feed stays outside the checkout. It
validates the projects config with the dashboard itself, mounts the config
read-only and each project's `.git` at `/inputs/projects/<id>/.git`, and the
container reads them via `-roots-under /inputs/projects`. Run `sh docker-local.sh run` only after confirming that the engine
honors host-loopback publication. Verify actual listeners for IPv4 and IPv6;
a Host header check is not a network access restriction. The local listener
also refuses any request carrying proxy headers (`Forwarded`, `Via`,
`X-Forwarded-*`, `X-Real-IP`, `CF-Connecting-IP`, `True-Client-IP`): it has no
login and must never sit behind a proxy or tunnel. Do not use Kiri Share
to publish internal reports. Never build or replace
the service for a record update. The container has a dedicated bridge,
loopback-only publishing, no Docker socket, non-root user, read-only root,
dropped capabilities, and restart policy `unless-stopped`. Its only evidence
content mount is `feed/` (read-only), plus the projects config and each
configured project's read-only `.git` metadata to verify HEAD. It mounts no project working tree.
The reader supports ordinary SHA-1 Git checkouts with loose/packed refs; Git
worktree indirection and reftable are unsupported and fail closed.

## Optional Kiri Share view

This is a separate authenticated Dashboard. The owner sees the same information
as on port 8732. Colleagues see only the configured project names, their status
labels, and the read time. Their account cannot retrieve reports, task titles,
revisions, evidence sources, or the full dashboard assets. The normal Dashboard
remains on port 8732 without a login. **Never point Kiri Share at port 8732.**

The share listener is closed by default. With `DASHBOARD_SHARE_AUTH=off`
(or omitted), all requests on it return 403, including requests that carry
credentials. It does not then open or mount a credentials file. To allow
logins, use `DASHBOARD_SHARE_AUTH=on` and a regular mode-0600 file outside
the checkout.

Copy [share.env.example](share.env.example) and
[share.accounts.example](share.accounts.example) into a private directory
outside the checkout. From `runtime/dashboard/`, run:

```sh
config="$HOME/.config/factory-dashboard"
mkdir -p -m 700 "$config"
(umask 077
  cp -n share.env.example "$config/share.env"
  cp -n share.accounts.example "$config/share.accounts"
)
chmod 600 "$config/share.env" "$config/share.accounts"
```

Edit `share.env`: set the exact assigned hostname and the provider domain it
belongs to (`DASHBOARD_SHARE_DOMAIN`, passed as `-share-domain`; required
whenever sharing is configured). The hostname must be exactly one DNS label
under that domain; wildcards, ports, schemes and other hosts are rejected.
When ready, change `off` to `on`. In
`share.accounts`, replace the example logins and all hash placeholders.
Each line is `login role sha256-digest`, with a single space between fields
and no comments or blank lines. `full` grants the same view as port 8732;
`status` grants only project names, status labels, and read time. Unlisted
logins have no access. Role names are lowercase and logins are case-sensitive.
Delete any unused example row.

Use a different password for each login: 8 to 256 printable ASCII characters
without spaces (a random 32-byte, 64-hex-digit password is recommended). Hash the
password's text without a trailing newline and put just the lowercase SHA-256 digest
in the file. After 20 wrong logins within a minute the share listener answers 429 to
every login attempt until the minute has passed. Keep passwords in an approved
password manager, never in a URL, shell argument, repository, or logs. The
example placeholders are deliberately invalid.

Source only your own reviewed local config and pass the full image ID to the
launcher:

```sh
. "$HOME/.config/factory-dashboard/share.env"
sh docker-local.sh share IMAGE_ID
```

Use the exact issued name, not a wildcard. The share container uses a
separate bridge and publishes only `127.0.0.1:8734`. The launcher does not
create a tunnel. Before connecting one, verify the host-loopback listener and
that a request to port 8734 with the exact Host but without credentials gives
401. Requests for local or other hosts are forbidden even with credentials.
Check that a status login returns only the projected status and all
private routes return 404 for that login. Verify full Dashboard behavior with
the separate full login.

Only then may an explicitly approved Kiri Share HTTPS link target
`127.0.0.1:8734`. The URL is public: the application's login restricts access,
not the link. Kiri handles browser HTTPS, so trust its service with the Basic
Auth headers and all responses, including the reports sent to the owner. Verify on the actual HTTPS link that an
unauthenticated viewer gets a login challenge, a valid login works, and a
detail URL remains unavailable to the status account. If the host is unknown, identify it before
pointing the tunnel at a data-serving process. Kiri Share forwards `Host: localhost:8734`
with the public name in `X-Forwarded-Host`; the share listener (never port 8732) maps
only that exact shape — its own loopback authority, one `X-Forwarded-Host` equal to the
share host and one `X-Forwarded-Proto: https` — to the share host; any other forwarded
value is refused, and login is still required. If a tunnel does not preserve the
authentication header, disconnect the share rather than relaxing the checks. Use a separate channel to distribute the credential.
Distribute only the appropriate individual login and password. Use separate browser profiles or private
windows to test each role; browsers may reuse Basic Auth for the same hostname.
To revoke one login, remove it from the file and recreate only the share
container. If removing the last login, turn authorization off to return 403,
or disconnect the share entirely.

## Publish without rebuilding

The publisher does not generate or infer evidence. Create or revise a private
JSON status using the current task record, its verified evidence, and the full
local `git rev-parse HEAD` of that project. Follow the record format below; do not carry another task's timestamp or
approval forward. Do not include secrets, private raw material, absolute paths or URLs.

```sh
GOPROXY=off go run . -publish < next-status.json        # dry run; no writes
GOPROXY=off go run . -publish -apply < next-status.json # atomic local replacement
```

See `go run . -help` for the `-projects` and `-feed` options.
Pass `-feed` to native runs when using an existing private feed. For a new
standalone feed, create a directory outside the checkout with mode 0700. Each
configured project has one fixed filename, `<id>.json`. Publishing also needs
`-projects`; a record for an unconfigured project is rejected.
The writer checks the record's project/revision, timestamps, source references
and state compatibility, then uses a lock and atomic rename with file mode
0600. A publish must have a strictly later observation timestamp than any
existing record for that project. A syntactically damaged existing record
requires inspection instead of blind replacement. No product agents or hooks
publish automatically yet. The browser picks up the replacement on its next
poll (~10s) without any image build, container restart, or repo edit.

## Status contract: `factory-dashboard/status/1`

- `schema`, `project`, full `revision`, `taskId` (lowercase slug), `title`,
  `state`, `updatedAt` (RFC 3339), and `next` are required.
- `sources` contains 1–12 references with `id`, `kind`, `role`, `label`, and
  `recordedAt` (RFC 3339). Reference labels describe evidence for operators;
  the dashboard does not open them. Roles: `operator-curated`, `author-recorded`,
  `review-recorded`. Use the actual time of the evidence; do not reset it to the
  publish time. Accepted-plan evidence must be a recorded review.
- `stages` contains exactly Plan, Implementation, Tests, Review, Push, Update
  in that order. Each entry has `name`, `state`, `detail`; any non-Unknown
  state must refer to an explicit `sourceId`. See `validStage` for the accepted stage/source pairs. Evidence families are
  `plan-review`, `work-record`, `test-record`, `push-receipt`, `update-receipt`.
  Push is not merge, Review does not stand in for human QA; this version cannot
  publish a final independent code-review pass.
- Optional `markdown` is a curated summary, not the original source.
  Reports are at most 4 KiB; status files are at most 16 KiB. The renderer
  suppresses raw HTML, images and clickable links. Configured project routes
  `/api/details/{project}` serve only fresh, matching summaries; configured
  aliases apply only when the original task ID matches. JSON omits Markdown.
- Records expire after 48 hours from the publisher's **observation** timestamp;
  clock skew over 30 seconds into the future is rejected. The service compares
  the record's full revision to current local HEAD while reading it. That is a
  freshness guard, not proof of uncommitted bytes or independent sign-off.
  Updating `updatedAt` without rechecking the evidence is not a new observation.
- A record that is otherwise valid but no longer current (HEAD moved, or older than 48 hours)
  is shown as **Stale** ("Застаріло"): its task, title and last next action with the reason,
  all six stages Unknown and no details. Its content is checked in full first (text, path/URL
  guard, 40-hex revision, sources, stages, state); a record failing that check shows the bare
  "not confirmed" card. A present transition file keeps its own behavior. The status-only share
  view shows the state `Stale`.

## Open-task list: `factory-dashboard/queue/1`

`-publish-queue [-apply]` reads one `<project>.queue.json` record from stdin (dry-run by default;
same private feed directory, lock and 0600 file as the status). Members: `schema`, `project`
(a configured id), `updatedAt` (not in the future, strictly later than the published one),
`items` (0–64) and `omitted` (≥ 0). Each item: `id` (task slug, unique), `title` (≤ 120 bytes),
`state` (`In progress`, `Ready`, `Proposed`, `Paused`, `Blocked`), `summary` (≤ 560 bytes),
optional `blockedBy` (≤ 120 bytes, only with `Blocked`) and `recommended` (at most one).
Text follows the status rules (no paths, URLs or control characters); the file is at most 32 KiB.
The list is not bound to a revision: it is shown under the stages with its publish time, marked
outdated after 7 days; an invalid file is ignored. `items: []` clears it. The status-only share
view never shows it. Agents publish it with `kit.py project queue`.

## Checks

```sh
npm run build
node --test ui/markdown.test.js ui/queue.test.js ui/status.test.js
GOPROXY=off go test ./...
GOPROXY=off go vet ./...
```

## Workflow transition feed

The optional shared Factory projection invokes the local executable's
`-publish-transition` mode. Like the curated writer it defaults to dry-run;
`-apply` replaces only `<project>.transition.json`. The strict
`factory-dashboard/transition/1` schema accepts project ID, full HEAD,
task ID, typed event (start, stage, handoff, closeout), stage only for stage
events, record and observation timestamps, and an optional exact scope pair.
It accepts no gates, raw file paths, source payload or Markdown. Publisher
and transition stream both stay local and use the existing private feed
directory and lock. The existing per-project gate records are not overwritten.

- A valid transition supplies a neutral event, not approval or delivery.
  An invalid, expired, or currently unrelated transition suppresses old
  evidence as applicable; it never falls back to presenting old active gates.
- A curated `factory-dashboard/status/1` record remains visible as a labeled legacy snapshot when
  there is no transition, but it has no scope proof. A status/2 record needs a
  matching current transition before any gates are presented as applicable. To make evidence
  applicable to a transition, a separately curated `factory-dashboard/status/2`
  record must supply both `scopeId` (canonical slice slug) and
  `scopeSnapshot` (the exact scoped checkpoint SHA-256). The task,
  project, full HEAD, slice and snapshot must all match, and both records
  must pass the same freshness bounds. This is exact declared evidence
  association, not an additional live read of uncommitted source or a
  guarantee of reviewer independence.
- Only the typed transition observation changes across same-scope moves.
  Curated evidence bytes, report detail, and their original timestamps
  are unchanged. A different task or slice at the same HEAD shows
  current gates Unknown and disables active details, including legacy aliases.
