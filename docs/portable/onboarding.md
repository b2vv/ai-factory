> Optional retained portable profile; the full canonical plan is in `ai-factory/`. This profile does not replace original skill contracts or authorize automatic activation.

# Three routes, one entry

This kit is the reusable default entry for new projects when selected by the user; selecting it does not authorize tool installation or impose a stack. Existing instructions and architecture remain authoritative. Read [workflow](workflow.md) and select one route.

## New project

1. Establish product scope, intended stack, acceptance criteria and repository location. Leave unknown decisions unresolved rather than inventing them.
2. Propose one short AGENTS.md entry and a CLAUDE.md pointer to it, plus one current task record. Use [adapter](../../templates/adapter-portable.md) only where useful; do not create empty process folders or mandatory ADRs for every task.
3. Inventory already available test/build tools. Record relevant commands and effects. No automatic dependency, hook, MCP, model or skill installation follows.
4. Review the proposed files and apply only when that creation is authorized. Verify links and perform a separate harmless per-host discovery/handoff pilot if requested.

## Existing project or version update

1. Read existing entry files, contracts/ADRs, skills, task lifecycle and gates. Use the read-only helper with an explicit non-secret manifest; fill the example to match the project.
2. Compare the installed adapter version/hash with the candidate. Preserve stack, architecture, task IDs, journal and current small/full thresholds. Separate descriptive corrections from policy decisions.
3. Prepare an explicit minimal diff and per-file baseline/proposed hashes. Do not replace a whole entry file or create a second tracker. Missing capabilities are findings, not permission to install.
4. After authorized application, verify exact bytes and links. Same desired bytes yield NOOP; concurrent/different bytes require review. Use [guarded change protocol](change-protocol.md). Reassess affected evidence; do not copy an old PASS to a new snapshot.

## New PC

1. Obtain the approved private release using the user's existing authenticated method; never embed credentials in this kit. Verify checksums before trusting payload files.
2. Inventory OS, shell, Python 3.9+, installed Codex/Claude versions and explicit skill roots. Dependency/host inventory is manual; the bundled offline installer stages only this toolkit, never dependencies.
3. Stage the selected components using the explicit commands below; then separately choose whether a canonical shared skill directory is wanted. Inspect existing paths, symlinks, ownership and collisions before proposing any link or copy. Do not assume a machine's Codex/Claude discovery behavior from another host.
4. The implemented staged installer uses core/optional components, old/new hashes, backups and guarded rollback. Global skill discovery links remain a separately reviewed setup. No automatic global configuration, permissions, model routing or MCP.
5. Test the helper fixtures locally, then separately verify discovery/invocation/file fallback for each host. Graphify is optional; if absent, report it rather than install it. Bind models from that host's actual catalog/entitlement/budget.
6. Record detected/configured/behavior-tested separately. Unverified hosts/tools remain UNKNOWN or NOT_TESTED. Keep machine-specific evidence outside the portable payload.

## Concrete commands and acceptance

Set SOURCE to the canonical complete release, KIT to a dedicated staged installation, REPO to the intended project, and MANIFEST to a non-secret inventory JSON in the task workspace. Populate the example with real local paths; an unchanged example is not acceptance.

```sh
python3 -B "$SOURCE/tools/verify_release.py" --root "$SOURCE"
python3 -B "$SOURCE/tools/run_tests.py"
python3 -B "$SOURCE/tools/kit.py" plan --package "$SOURCE" --root "$KIT" --component planning --component review --component session-guard --component graphify
# Review changes, then explicit install under the writer-window contract:
python3 -B "$SOURCE/tools/kit.py" install --package "$SOURCE" --root "$KIT" --component planning --component review --component session-guard --component graphify --execute --exclusive-window --plan-id '<plan-id>'
python3 -B "$KIT/runtime/onboarding/preflight.py" --root "$REPO" --manifest "$MANIFEST" --shared-skill-root "$KIT/skills"
```

For a new project: acceptance is one agreed entry/adapter, preserved intended stack, one task record, real commands/effects and clearly unresolved choices. Authoring those project files is a separate authorized change; the installer will not do it.

For an existing project: preflight first; compare current instructions and installed kit version, propose only the local adapter delta, preserve existing skill contracts and task history, obtain the selected existing review session's verdict on the exact diff. A new kit version is not permission for project rollout.

For a new PC: the isolated suite and staged installer must pass, repeat plan must yield NOOP, and selected files must match release hashes. Then separately check exact-file fallback/native discovery for each host, independent review route, Git/root requirements and explicit private session store. Hook activation/MCP/model access remain pending until separately configured and observed. Missing optional components are N/A only if the selected workflow does not require them.

For an update or rollback use the [implemented installer contract](../portability-design.md). Pass the complete desired component set on every update; omitted components are removed only with matching managed baselines. Do not replace local instructions wholesale or add another tracker.
