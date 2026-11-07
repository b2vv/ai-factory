# Shared source mode: latest reviewed local main

This opt-in mode shares one owner-selected physical Factory source path across
projects. Rules, lifecycle guidance, skills and their relative references resolve
from that path. Projects do not select a commit, release cache or version pin.
An observed revision or checksum is evidence, not the project update selector.
Import shared `rules/agent-entry.md`, not the source repository's maintainer AGENTS.
Local project contracts and permissions remain authoritative.

This mode does not install the kit or change its managed installer. Retain existing
package checksums, historical pins, receipts, license/provenance records and runtime
locks. Do not edit managed installation state to pretend it represents source mode.
Hooks, executable bundles, credentials, grants, Docker images and database rollout
remain separately controlled dependencies; a guidance update does not update them.

## Three distinct operations

1. **Read files:** the next qualified file read sees the current bytes at the shared
   path. A global skill-folder symlink can point to the same canonical skill as a
   project alias. Change only an explicitly authorized alias, preserve other local
   skills and mixed global roots, and retire only verified obsolete selectors.
2. **Update Git:** fetch changes objects and remote-tracking metadata; it does not
   update the shared working tree. A fast-forward changes files and needs a reviewed
   target plus a coordinated reader/writer window. No background pull is implied.
3. **Reload consumers:** already-loaded instructions and skill metadata are cached
   context. Refresh discovery or start a new session at an agreed boundary. Do not
   terminate active work or claim that a symlink/Git update rewrites model memory.

The guarantee is **latest reviewed local main**, not continuously latest remote or
identical instructions in every active session. Multiple files in one existing Git
checkout cannot be published atomically to uncoordinated readers. If a safe window
is unavailable, defer the update; independent work may continue under its recorded
accepted context. Do not create worktrees/clones against the owner's constraint.

## Inspect and check remote without updating files

Use the explicit owned source root and the already-authorized origin. Verify its
URL matches the intended repository without printing embedded credentials. Do not
create credentials, change remotes or substitute another source on denial.

```sh
factory=/absolute/owned/factory-source
factory_git() {
  git -C "$factory" -c core.hooksPath=/dev/null -c core.fsmonitor=false \
    -c maintenance.auto=false -c gc.auto=0 "$@"
}
factory_git symbolic-ref --quiet --short HEAD
factory_git status --porcelain=v1 --untracked-files=all
factory_git rev-parse HEAD
factory_git ls-remote --exit-code --refs origin refs/heads/main
```

Require branch `main`, a clean tracked payload and no pending Git operation. Inspect
index/staged changes and untracked files; preserve ignored local wiring too. Resolve
all active source writers/readers explicitly. The remote check may require network
approval; denial/unavailability means remote currency UNKNOWN, never latest PASS.
These commands implement no scheduler, source lock or enforced session boundary.

## Fetch, review, then fast-forward

During the coordinated window, fetch only main. No implicit submodule update,
pruning or automatic maintenance is needed:

```sh
factory_git fetch --no-tags --no-recurse-submodules --no-prune \
  origin refs/heads/main:refs/remotes/origin/main
factory_git rev-parse refs/remotes/origin/main
```

Record the current HEAD and exact candidate SHA in the existing task/update record.
Apply Factory's normal independent review and relevant tests to the actual delta.
Validate provenance, license and manifest/checksum changes; origin membership and
self-consistent hashes alone do not prove review or trustworthy behavior. Commit
IDs in this one-time review record are not per-project version pins.

Immediately before applying, recheck the same HEAD, clean branch/index, pending Git
state and retained local files. A concurrent change ends the window; inspect rather
than retry blindly. With the accepted exact candidate in `reviewed_target`:

```sh
factory_git merge-base --is-ancestor HEAD "$reviewed_target"
factory_git merge --ff-only --no-overwrite-ignore --no-autostash "$reviewed_target"
```

Require the ancestry check to succeed before running merge. `--ff-only` refuses
divergence; `--no-overwrite-ignore` protects ignored-file collisions. Local edit or
untracked-path collision failures must preserve the work, not trigger reset, clean,
stash, forced checkout, rebase or deletion. Git's locks do not coordinate independent
file writers; this recipe still requires the explicit window. Failures or uncertain
results require inspecting HEAD, index, files and process completion first.

After success, verify HEAD equals the reviewed target, branch remains main, tracked
payload is clean, current manifest/checksums match, and retained private local files
are unchanged. `shasum -a 256 -c checksums.sha256` is an integrity check, not a new
review. Normal exact-package export/verification may reject undeclared local wiring;
preserve it and use the documented manifest-only review package, never hide/remove
private files to force an export PASS.

Finally check discovery from each real project context and its exact resolved paths,
enabled state and unchanged unrelated skills. A duplicate scope pointing to the
same reviewed content is different from an enabled older copy. Discovery proves
neither model invocation nor product UI acceptance. Recheck applicable source
contracts before changing helper behavior or deploying a runtime.

## Evidence and recovery

Record before/after HEAD, remote observation, dirty/index state, exact delta review,
checks, local-file hashes and native discovery results in the existing task record.
For an alias change, retain its exact old target and guard replacement/rollback;
for an obsolete local selector, back up and verify exact bytes before removing it.
Do not replace global roots or delete the old managed kit. A post-update rollback
is a separately reviewed operation, not an automatic hard reset of shared source.
