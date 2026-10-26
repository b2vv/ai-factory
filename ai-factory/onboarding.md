> Runtime examples below use `$KIT` as an explicitly selected absolute root of this release; `$PREVIOUS_RELEASE` is the immutable prior release when testing upgrades. This path update does not activate or change helper behavior.

<a id="підключення-ai-factory-до-іншого-репозиторію"></a>
# Connecting AI Factory to another repository

[Main entry](../docs/legacy/ai-factory-plan-entry.md) · [Lifecycle](feature-lifecycle.md) · [Sources of truth](workflow.md#source-of-truth)

The goal is to add a compatible route to the existing process and verify it against scenarios real for the repository. This is not a guarantee against every surprise. There is no automatic rollout, installs, permissions, MCP registration/build, hooks, model defaults or external writing. Preserve the stack, architecture and existing tracker. For a new repository, missing contracts remain explicitly undefined; a template does not invent them.

<a id="один-стартовий-запит"></a>
## One starting request

> Connect AI Factory to `<repo-root>` under `~/.agents/ai-factory/onboarding.md`: inventory → manifest → safe preflight → minimal additive adapter → acceptance report. Preserve existing workflow, stack, ADRs and required gates. A documentation adapter and pointers are authorized within this onboarding; do not change the product, config/hooks/permissions/models or run installs/dev/CI/deploy/MCP refresh. Before writing, show the diff, backup/hashguards; a repeat run must be NOOP for an unchanged adapter. Leave unclear policy decisions BLOCKED with an owner; finish with independent review and a fresh forward-test, distinguishing fixtures from runtime evidence.

If only an audit was requested, do not perform adaptation. If minimal changes are already explicitly authorized, do not ask for permission again merely because of a transition between these phases. Ask the owner for new policy, undefined scope or a real approval blocker.

## Startup routing

Before inventory, record the required critique/review/verification route under [review-handoff](review-handoff.md#перед-початком-роботи): a new subagent or an existing separate session, owner/reference, current selection rationale and handoff. Clarify an undefined selection before spawn/send, not before safe investigation. The independent reviewer receives a pinned package; repeated handoff does not create a new reviewer.

<a id="швидкий-початок"></a>
## Quick start

1. Choose the exact root; read-only, verify HEAD/status, ancestor/nested instructions in scope, current work/spec/ADR and owners. Do not read `.env`, credentials or config values. With multiple candidates, resolve the root before writing.
2. Read [repo-bootstrap](../skills/utils/repo-bootstrap/SKILL.md) in check-only mode: Codex `$repo-bootstrap`, Claude `/repo-bootstrap`; if discovery is unconfirmed, read the exact file and label this a fallback. Symlink existence does not prove invocation.
3. Prepare the manifest in the task working directory from the [example](../examples/onboarding/manifest.json). Remove irrelevant candidates, specify actual repository-relative paths and only needed skills. The shared root is an argument, not hardcoded. Run using already available Python 3.9+:

```sh
python3 /path/to/ai-factory/runtime/onboarding/preflight.py \
  --root /path/to/repository \
  --manifest /path/to/task/manifest.json \
  --shared-skill-root /path/to/shared/skills
```

The helper only reads explicitly listed files; JSON result goes to stdout. It runs no repo commands, MCP, hooks or discovery. Without Python, use a manual checklist; no automatic installation. Detailed limits and schema: [helper README](../docs/onboarding-helper.md).

4. Supplement inventory with manual reading: source authority, scripts/prehooks/prerequisites, side effects, semantic conflicts, availability of the required independent reviewer. Do not call absence of conflicts a helper result: it sees only explicitly supplied `conflicts`.
5. Finish the check-only phase without writing to the target repository; manifest/evidence remain in the task workspace. In a separate, already authorized adaptation phase, prepare an additive adapter from the [template](../templates/adapter-full.md). Do not replace existing workflow; prewrite hashes/backups and a bounded file list protect concurrent changes. In old entrypoints, replace only contradictory statements/add pointers; do not layer mutually exclusive rules. New mandatory gates or their relaxation need a named owner and decision.
6. An independent reviewer reads the diff and sources; a fresh context walks through the scenarios below. Record scope, revision, results/blockers and limits in the existing task record. Only then call documentation onboarding configured; runtime is checked separately through authorized actions.

7. Before acceptance, check Obsidian under the [synchronization step](#obsidian-sync): real shared target, currency and authorization scope. Record authorized synchronization or explicit PENDING/fallback in the same report; a symlink is not write permission.

<a id="checklist-адаптації"></a>
## Adaptation checklist

Before changes, inspect the [documentation hygiene matrix](documentation-hygiene.md): logical/physical entrypoints, README/standards, hook effects, local/CI/browser coverage, task/handoff and ADR currency. This refines the existing inventory without a new tracker or transplanting another product's rules.

- [ ] Root/HEAD/dirty scope; applicable instructions; architecture/stack; task/spec/ADR/QA/archive locations identified without migration by default.
- [ ] Request/permissions bound the scope. Acceptance/contracts/ADRs are normative; code/scripts describe actual behavior. A conflict has both sources, an owner decision or BLOCKED dependent work. Code does not legitimize a bug. An already requested fix to an unambiguous contract needs no new decision; one is needed only for an unclear/conflicting norm or a change to it.
- [ ] One primary record for small: scope/acceptance, plan, append-only progress, verdict/evidence/next step. Independent review may be a separate file. Do not automatically merge/delete artifacts of existing tasks. Full route only by risk/contract; resume only invalidated gates.
- [ ] Skills: exact local/shared file, availability/discovery separately, `$skill` Codex / `/skill` Claude or explicit read fallback. One orchestrator; do not run the entire inventory.
- [ ] Pattern applicability includes test helpers; entity E2E/scoped filters include matching/nonmatching and surfaces according to acceptance; evaluate UI copy for layout/zoom/accessible names, open/active states. A build does not prove UI.
- [ ] Commands found statically; side effects/prehooks/transitive calls inspected manually. In particular reset/delete volumes/seed/drain queues/generate/start/install are not read-only probes. The name `check` does not guarantee safety.
- [ ] Review is genuinely independent; PASS has a durable verdict. Helper/Coder/Reviewer are roles, not automatic model bindings. Unconfirmed host/model/effort/budget stay unresolved; do not change defaults.
- [ ] MCP registration, tool availability and graph freshness/coverage are separate. Missing/stale/unknown → file fallback; optional CRG does not block independent work. Do not rebuild/migrate a graph automatically.
- [ ] QA/landing/commit/push/deploy boundaries come from the repository; readiness does not expand the request. A completed identical handoff does not rerun work.

<a id="checks"></a>

<a id="applicability-перевірок"></a>
## Check applicability

This matrix helps justify the set but does not cancel explicit local required gates. For each: requirement source → impact → command/scenario and side effects → verdict/evidence. Reducing a required gate stays BLOCKED until a specific owner decision; the proposal must name the saving and lost protection.

| Impact | Appropriate checks | What must not be assumed |
|---|---|---|
| Docs/process/helper | Links, contract consistency, fixture/negative tests for the helper, independent docs/behavior forward-review | Docs are automatically risk-free; fixtures prove a real host |
| Test helper/callback | Targeted regression, type/lint/format under the contract, pattern applicability | Small cancels mandatory repo gates; RED/GREEN equals mutation |
| Product logic/API/dependency boundary | Affected tests/types, contract/schema/architecture checks; broader builds/generations by dependencies or required gates | A local unit test proves all backends/builds |
| UI-copy/layout/control | Affected locales, wrapping/overflow/zoom, keyboard/accessibility by scope, open/active/error states; actual render | Text-only automatically makes design N/A; an uninspected screenshot is sufficient |
| Entity flow/scoped filter | Acceptance scenarios for each claimed surface/type, matching/nonmatching, persistence/read/update by scope | URL/controls/API alone prove list contents |
| Mutation required by contract/risk | Separate mutant, killed/survived result, current diff and command; restoration of authorized scope | The first RED before a fix is mutation; a sandbox failure grants permission to bypass it |
| Resume without input changes | Check completion/revision/evidence and return the current result | A new handoff automatically invalidates everything |

Execution failure: BLOCKED + exact reason or an already authorized execution mechanism. There is no universal “outside sandbox” requirement. An old PASS does not carry over to changed scope; unchanged scope needs no ritual repetition of all checks unless the local contract explicitly requires it.

<a id="рівні-підтвердження"></a>
## Levels of confirmation

| Level | Evidence |
|---|---|
| detected | File/command/description found; not runtime availability |
| configured | Adapter, pointers, ownership, paths and absence of unresolved normative conflicts verified; separately mark remaining BLOCKED items |
| behavior-tested | A specific scenario ran on a named host/revision with a result; fixture, native forward-test and Claude CLI runtime are different evidence types |
| BLOCKED | Required component/decision/access unavailable, dependent part and next owner named |
| N/A | Capability not needed for this scope, with a reason; an unavailable required gate is not N/A |

The helper never promotes detected to configured/behavior-tested itself. The manifest is inventory input, not a readiness certificate; semantic conflicts, model bindings and actual diff impact require a human/agent.

<a id="перевірка-перед-повторним-використанням"></a>
## Verification before reuse

Isolated fixtures do not change repositories:

```sh
cd /path/to/ai-factory/onboarding
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_preflight.py
```

Required sample for a fresh context: clean new repo; existing partial rules; missing shared skill; normative contract versus code; stale/unavailable CRG; small test-helper; UI-copy affecting layout; repeat of completed handoff. Negative cases: path traversal/symlink/secret input, malformed manifest, config-file ≠ tool availability, empty side-effect indicators ≠ safe command. The forward reviewer receives the request and raw artifacts without a hint at the expected verdict.

Migration is a minimal diff + list of retained rules/changed rules/unresolved decisions, backups and hashguards under the [repeat and restore protocol](onboarding/change-protocol.md). No automatic rollout to other projects. Synthetic fixtures do not cover real Claude/Codex discovery, hooks, MCP, model access, product gates or deploy; check these separately when requested.

## Host-specific acceptance

For each claimed host/session, retain separately: (1) readable exact skill file, (2) discovery evidence with date/source, (3) native tool inventory, (4) invocation result or NOT_TESTED. Absence of a native list/load tool does not disprove already confirmed discovery. An inventory from a previous session does not guarantee the current one but remains dated evidence; do not replace it with “not installed”.

Required review has an exact local/shared SKILL.md or documented local review contract and an independent executor. If the native command is not discovered, explicitly read that file and its references; retain the same scope, pinned diff, acceptance and durable verdict. Missing independent executor/required tool means BLOCKED for that gate. Do not create a global skill for repository-specific review. The helper supports a SKILL.md route; another local contract is checked manually and recorded in acceptance without inventing native invocation.

Models: [provider-independent inventory](models.md); catalog only for this host/session, entitlement and budget separately. No catalog → UNBOUND + specific next step, not installation or a paid probe. Optional CRG: config/listing/live query/freshness are different evidence; files/rg suffice for authorized independent work. Reuse completed proofs only within their pinned scope.

Fill the final result using the [acceptance template](../templates/acceptance-full.md). Required outputs: inventory+manifest, reviewed diff/receipt/backups, repeat NOOP or explicit BLOCKED for a foreign change, independent verdict, fresh scenarios, unresolved owner decisions and next action. For a partial repository, do not create missing tracker/ADR/CI unless needed by the agreed scope. For a new minimal repository, one short entrypoint/adapter and task record suffice; do not invent a stack.

<a id="obsidian-sync"></a>

<a id="obsidian-перевірка-та-погоджена-синхронізація"></a>
## Obsidian: verification and agreed synchronization

1. If the project uses Obsidian/Shared, find the actual vault and resolved target of its Shared link. Check the target of each involved vault; do not infer sharing from the name `4 - Shared`. If the target is the same, there is one canonical note too. No Obsidian in scope → N/A with a reason, without creating a vault/integration.
2. Read only the relevant workflow/report note; compare with canonical sources and current results. Record path, source/revision/date and current/stale/missing. A symlink or yesterday's sync does not prove currency today, live MCP or write permission.
3. If the current request already authorizes this exact synchronization, perform it without asking again. Otherwise leave PENDING: exact target, proposed minimal diff, reason and required authorization scope. If the channel is unavailable — PENDING + repo/task fallback; authorized independent work continues. Do not install tools/MCP, change permissions or create automation.
4. For an authorized write: canonical target, backup/prewrite hashes, reviewed diff; preserve unrelated text, do not copy all normative rules. Update the overview, pointers, separate project results and honest runtime limits. Write the same shared target once. No content change → NOOP, without an artificial new timestamp/report. Concurrent edit → BLOCKED write, not overwrite.
5. Verify links and visibility through actual targets; record SYNCED/NOOP/PENDING/BLOCKED/N/A, evidence and fallback/next action in [readiness](../templates/acceptance-full.md). Filesystem visibility ≠ verified Obsidian UI/MCP. Permission for one sync does not create ongoing permission for later writes. If sync is required by this request and remains pending, do not call the entire scope complete.

This is a separate controlled step after repository adaptation, not a mandatory copy of the report into every vault. Canonical contracts/ADRs/evidence stay in their sources; Obsidian is an overview and links. A local report without this step must not be presented as full completion of `ship-report`.
