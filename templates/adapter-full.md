<a id="ai-factory--адаптер-наявного-workflow"></a>

# AI Factory — existing workflow adapter

Fill this template with repo facts; it does not establish them by default. Mark unknowns unresolved with an owner; remove inapplicable candidates. Do not copy Cargo/personal paths.

| Field | Actual path / rule / source |
|---|---|
| Root, HEAD, relevant dirty scope | ... |
| Task branch / base / one writer | Main repository; [branch ownership](../ai-factory/workflow.md#task-branches); foreign/unknown WIP → STOP and coordinate, runtime isolation separately |
| Instructions and precedence | ... |
| Normative acceptance/contracts/ADR | ... |
| Stack/architecture — preserve | ... |
| Primary task record; append-only progress | ... |
| Small/full/resume triggers | ... |
| Startup critique/review/verification routing | review_mode=existing_session / independent_subagent; assigned session retained; no additional session → independent_subagent; unavailable runtime → BLOCKED; selection alone does not launch review; owner; exact reference/pending; current authorization; delivery owner; shared-resource coordination |
| Pending next action at startup/stage/resume | In the existing record: review_mode=existing_session or independent_subagent (independent context), writer/reviewer, current contact mechanism/delivery owner/authorization, action ID/owner, prepared/sent/acknowledged/verdict_received + evidence, blocker/next check; [contract](../ai-factory/review-handoff.md#pending-next-action). When copying, replace the link with the actual shared source. No duplicate review/resend; only the applicable action; required final verdict before DONE. |
| Independent review / evidence / QA / archive | ...; package ID, root/base/HEAD, scoped diff/untracked hashes, pinned acceptance/contracts/evidence; raw reviewer response and final-delta verdict |
| Required gates; applicability source; side effects | ... |
| Local/shared skill paths; invocation/fallback | ... |
| Optional MCP availability/freshness/file fallback | ... |
| Obsidian/Shared canonical target and relevant note/report | ...; currency, current authorization, SYNCED/NOOP/PENDING/BLOCKED/N/A, fallback; no copies per vault |
| Host/session discovery; native tools; invocation | Separate evidence/status; a missing list/load does not disprove discovery |
| Required review exact file + references / independent executor | ...; file fallback with the same evidence or BLOCKED |
| Helper/Coder/Reviewer actual bindings | UNBOUND; same-host/session catalog, entitlement, budget and next step separately |
| Canonical adapter path; receipt/backup; repeat | ...; NOOP on exact hash match, conflict → BLOCKED |
| Commit/push/deploy owner and instruction | ... |

Code/scripts show the current fact; acceptance/contracts/ADR define the required behavior. Record a conflict rather than automatically resolving it in favor of code. The user's scope/permissions take precedence.

Small has one primary record containing scope/acceptance, plan, journal and result; separate independent review/evidence only as required by the gates. If the current contract requires more, first obtain a specific owner decision. Existing tasks are not migrated automatically.

Before invoking a required skill, check its exact file and discovery: Codex `$name`, Claude `/name`; reading a file is a fallback, not invocation proof. Pattern — according to structural impact, including test helpers; entity/scoped-filter proof and UI-copy layout — according to acceptance. One orchestrator, without launching all skills.

<a id="migration--рішення"></a>

## Migration / decisions

After clear/new startup/resume: bound pending → short task/checkpoint + “Continue?”, wait for the current response without task/review/send; unbound → silence. Consent applies only to the current session/task; permissions remain unchanged. Compaction of an already approved active task preserves continuity without asking again; waiting confirmation does not activate Stop-driven continuation.

| Conflict or gap | Minimal additive change | Owner/decision | Check and status |
|---|---|---|---|
| ... | ... | unresolved | Dependent portion BLOCKED |

Lowering a required gate: state the time saved and protection lost, with a link to the decision; without it, the gate remains. RED/GREEN is bug proof; mutation has separate evidence. Blocked execution means BLOCKED or an authorized mechanism, without bypassing the sandbox.

<a id="приймання-підключення"></a>

## Integration acceptance

The record contains detected/configured/behavior-tested separately, source/revision/result for checks; N/A with a reason; independent review, forward scenarios and a next action. Config/symlinks do not prove runtime behavior. No automatic installs/registrations/hooks/permissions/models or rollout.

Before writing or restoring, apply the [change protocol](../ai-factory/onboarding/change-protocol.md) in shared onboarding; in the copied adapter, replace this link with the actual shared path or state the required rules here. Summarize using the [acceptance template](acceptance-full.md), in the existing task record. The adapter owner does not become the owner of source contracts; do not copy normative tables unnecessarily, link to them.

## Documentation consistency

Use the [shared checklist](../ai-factory/documentation-hygiene.md) in this same record. For each applicable gap: source/path/revision → factual correction or owner decision → preserved local difference → check. Explicitly identify logical/physical entry paths, hook effects, local/CI/browser coverage, task/handoff pointers and ADR currency. Provenance hunks do not expand authorization; commit, merge and acceptance gates are defined by exact local rules. Unperformed independent review remains PENDING.
