# Feature lifecycle: one existing task, proportional work

Use [workflow](workflow.md), [roles](models.md), [review contract](review-handoff.md), and [skill routing](skill-routing.md). The repository's contracts, architecture, tracker and current user scope remain authoritative. This kit supplies a reusable core, not a second orchestrator or permission to roll out configuration.

## Select a route

- Small: bounded understood change, concise acceptance and plan in one existing task record, relevant checks, independent review where the local contract/risk requires it, short report. No mandatory new folder, ADR, interview or fan-out.
- Full: unclear behavior, cross-module/API/auth/data/migration risk or complex UI. Research → acceptance/spec/plan → required decisions and independent critique → implementation → verification → independent review → fix/final delta → QA/report.
- Resume: select the exact named handoff, verify root/revision/dirty evidence, inspect completed operations before doing anything again. A stale checkpoint is context to reconcile, not authority to replay work.
- Partial setup: inventory existing rules with preflight; identify conflicts and propose only a minimal adapter. Do not bootstrap tools or replace the stack.

## Stages, owners and gates

| Stage | Owner and output | Gate / next action |
|---|---|---|
| Scope | Author and product owner: goal, non-goals, observed acceptance, unknown decisions | Unknown consequential requirement blocks only dependent work |
| Research | Helper gathers primary file:line evidence; author updates the existing briefing when authorized | Match base/HEAD plus dirty/untracked; stale graph means source fallback |
| Plan | Author: files, dependencies, acceptance IDs, checks, effects, migration/rollback or justified N/A | Local plan approval; independent critique/defense when selected |
| ADR | Local decision owner: lasting choice, alternatives, consequences, supersession | Apply the local ADR threshold; no ADR mechanically per ticket |
| UI design | Author: existing tokens/components, states, responsive/keyboard/error scenarios | Actual browser render/interaction evidence is needed after implementation |
| Implement | Author: one complete slice, behavioral regression proof and current journal | Red/green when required by the local test contract; no imposed toolchain |
| Verify | Authorized operator: commands, exits, exact inputs and artifacts | Required applicable gates PASS; skipped/unavailable remains NOT_TESTED/BLOCKED |
| Review | Approved independent context reads pinned acceptance, sources and raw checks | Findings with file:line/impact/verification; missing response never PASS |
| Final delta | Reviewer identifies changed criteria after fixes | Reuse only demonstrably unaffected evidence; do not carry stale PASS |
| Close/handoff | Existing task owner: achieved behavior, checks, limitations, next owner | Local QA/merge/archive rules; commit/push/deploy only when authorized |

## Planning lenses

Use bundled acceptance-spec for happy/boundary/failure observable scenarios; plan-defense for invalid input, dependency failure, race/repeat, boundaries and rollback with exact plan references. plan-critique means four independent lenses (filler, logic gaps, excess complexity, edge cases), not four headings written by the author. Record launched/returned counts. Use the user-selected existing session(s) or authorized new contexts; a missing required lens keeps that gate BLOCKED. Do not run this full process on every small change.

## Evidence and risk

Read scripts and transitive prerequisites before executing tests/builds: reset, seed, generation, containers and network may mutate state. Coordinate shared resources; preserve local required gates until their owner explicitly changes them. Regression RED→GREEN is not mutation-testing evidence. Sandbox failures are BLOCKED or use an explicitly permitted route, not permission bypass instructions.

UI copy can affect wrapping, locale, focus names, zoom and open/active states. Verify applicable empty/loading/error/success, keyboard/focus, recovery, viewport/locale and reflow. Inspect captured images; a created screenshot or green build alone does not prove UI quality. Existing UI/design/entity skills are optional extensions with separate provenance/dependencies, not silently bundled here.

A short ship report in the same task records acceptance result, changed behavior, checks/evidence, review status, remaining risks and next owner. External notes are links/summaries only when requested; no automatic vault writes. Post-deploy checks require a separately authorized deployment and exact build identity. Missing runtime evidence is named, not filled with plausible success.
