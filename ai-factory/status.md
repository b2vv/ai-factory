---
title: "Current capability status and sources"
reviewed: 2026-10-16
---

[Entry point](../docs/legacy/ai-factory-plan-entry.md) · [Status](status.md#capabilities) · [Routes](workflow.md#routing) · [Tasks](roadmap.md#tasks) · [Repository practices](repo-evidence.md#repo-evidence) · [History](history.md#history)

<a id="capabilities"></a>

# Current capability status and sources

The initial status concerns evidence collected on 2026-10-14 and 2026-10-16; Cargo snapshot and onboarding clarifications from 2026-10-17 are listed separately; this refactoring is not a new runtime audit. “Source exists” ≠ “integrated in a specific repository” ≠ “verified on a task.” “Not verified” does not mean “absent.” After a new pilot, update the corresponding row here; do not create a second table in the roadmap or Shared.

Local skills, their resources, and Shared references were checked. The dg/cargotrans-ui repositories, CI, live MCPs, ports, secrets, and deployments were **not checked** in the initial audit; the later Cargo live MCP proof below has its own date and scope. The older results below are historical evidence, not a current PASS.

| Layer | Current source / state |
|---|---|
| Executable skills | `~/.agents/skills/`: 60 SKILL.md files outside synced, another 22 in synced; the counts are an audit snapshot, not the number of unique commands |
| Shared access | `~/.claude/skills` and `~/.cursor/skills` are symlinks to `~/.agents/skills` |
| Shared | `~/vaults/global/skills` and `~/vaults/global/prompts` are separate Markdown references, **not** symlinks to executable skills; automatic synchronization has not been confirmed |
| Vault connections | `4 - Shared` in cassiopeia, cargotrans-ui, courses, and diagram-hierarchy points to `~/vaults/global`; this confirms the path, not MCP operation |
| Rules | `~/vaults/global/rules` → `~/.agents/rules`; this edit does not change configurations or rules |
| Cheat sheet | [skills-cheatsheet.md](../docs/guides/skills-cheatsheet.md); updated together with Shared, but behavior is defined by the corresponding SKILL.md |
A separate narrow CRG pass on 2026-10-16 UTC supplemented this initial audit: live stdio/schema, host discovery, a fixture, and isolated source snapshots were checked; source/active graph replacement, CI/deploy, and model API were not run. Details: [CRG](crg.md); manual model candidates: [models.md](models.md).

## Portable onboarding

[Onboarding](onboarding.md) contains a checklist, manifest, and read-only helper. Its local fixtures and independent forward-review check the bounded onboarding contract, not runtime Claude/Codex discovery, hooks, MCP, or model access. A file/symlink is only detected; configured and behavior-tested require separate evidence. Unverified bindings remain unresolved.

## Single registry

| Capability / ID | Source exists | Integrated in repository | Verified on a task | Evidence and date / limit |
|---|---|---|---|---|
| CRG 2.3.6 | Installed package and 4 corrected skills | Codex: 3 read registrations enabled; Claude Cargo: crg-cargo-read Connected; previous Claude Courses/Cassiopeia preserved | New 4 registrations: exactly 12 tools, direct build dispatch denied; previous fixture/snapshot proofs preserved; Go impact false-negative | [CRG proofs and limits](crg.md): Cargo active snapshot 2026-10-17 / stage / 137e19df: 1212 files, 0 mismatch/deleted; live MCP stats/callers PASS. Other graphs are historical measurements only; backups are valid |
| Three model roles | [models.md](models.md), manual contract | No automatic routing; defaults unchanged | Model API/benchmark not run | Bindings are per-host/session inventory; candidate/catalog, entitlement, and budget are separate; unconfirmed bindings are UNBOUND |
| E1.1 [cto-research](../skills/plan/cto-research/SKILL.md) | Yes, global SKILL.md | dg/cargotrans-ui: not verified; only global links confirmed for spec-flow | No new pilot conducted | Audit 2026-10-14. Freshness: base commit, HEAD, staged/unstaged, and relevant untracked files; without a valid baseline, collect again. Project instructions are not overwritten. |
| E1.2 [plan-critique](../skills/plan/plan-critique/SKILL.md) | Yes, global SKILL.md | dg/cargotrans-ui: not verified; only global links confirmed for spec-flow | No new pilot conducted | Audit 2026-10-14. The skill exists; no new run on a project was conducted. |
| E1.3 [plan-defense](../skills/plan/plan-defense/SKILL.md) | Yes, global SKILL.md | dg/cargotrans-ui: not verified; only global links confirmed for spec-flow | No new pilot conducted | Audit 2026-10-14. The skill exists; no new run on a project was conducted. |
| E1.4 [acceptance-spec](../skills/plan/acceptance-spec/SKILL.md) | Yes, global SKILL.md | dg/cargotrans-ui: not verified; only global links confirmed for spec-flow | No new pilot conducted | Audit 2026-10-14. The skill exists; use in a specific repository was not verified. |
| E1.5 [ship-report](../skills/ship/ship-report/SKILL.md) | Yes, global SKILL.md | dg/cargotrans-ui: not verified; only global links confirmed for spec-flow | No new pilot conducted | Audit 2026-10-14. The skill exists; the old “absent” in the history no longer describes global. |
| E1.6 [post-deploy-check](../skills/ship/post-deploy-check/SKILL.md) | Yes, global SKILL.md | dg/cargotrans-ui: not verified; only global links confirmed for spec-flow | No new pilot conducted | Audit 2026-10-14. The skill exists; a live deployment was not checked. |
| E1.9 [cto-agenda](../skills/plan/cto-agenda/SKILL.md) | Yes, global SKILL.md | dg/cargotrans-ui: not verified; only global links confirmed for spec-flow | No new pilot conducted | Audit 2026-10-14. The skill exists; the current product queue must be determined in the repository. |
| E1.10 [repo-bootstrap](../skills/utils/repo-bootstrap/SKILL.md) | Yes, global SKILL.md | dg/cargotrans-ui: not verified; only global links confirmed for spec-flow | No new pilot conducted | Audit 2026-10-14. 11 inventory items, including 5a: tasks/debt/archive; inspection by default, initialization separately. |
| E2.1/E2.2/E2.6 (global) [spec-flow](../skills/deliver/spec-flow/SKILL.md) | Yes, global SKILL.md | dg/cargotrans-ui: not verified; only global links confirmed for spec-flow | No new pilot conducted | Audit 2026-10-14. Includes side effects/migration/rollback, acceptance-spec, GATE 2 critique+defense+constitution, an independent reviewer, and a report. This does not confirm the state of local repository copies. |
| UI: design-pass and supporting lenses | Yes, [design-pass](../skills/design-pass/SKILL.md), frontend-design, anti-slop-design, ux-review, interface-review | Global links exist; automatic repository integration not confirmed | No real UI pilot conducted | Audit 2026-10-14; method and criteria: [workflow](workflow.md#ui) |
| E1.7: multi-model-roles | Historical record of a rule exists; not rechecked in this pass | Application of the rule in target repositories not confirmed | No new behavioral run conducted | [History 2026-08-25](history.md#history); behavioral DoD: roadmap |
| E1.8: eval | [Codex skill-creator](../../.codex/skills/.system/skill-creator/SKILL.md) available during the audit; Claude plugin not confirmed | Not verified | Eval was not run in these passes | 2026-10-14; task E1.8 |
| QnA: local work | Yes, work/SKILL.md | Yes, documented connection to work/README and agent prompts | Recorded work/038 example exists; no independent rerun | Read-only review 2026-10-16, [evidence](repo-evidence.md#repo-evidence) |
| generic-ui: file-based work and prompt skills | Yes, work/README and validate-spec/analyze-specs/pre-qa-review | Yes, documented links from specs/README; work is optional | Recorded work/002–004 examples exist; no rerun | Read-only review 2026-10-16, [evidence](repo-evidence.md#repo-evidence) |
| generic-ui: role-*/mode-* | SKILL.md files not confirmed in the inspected locations | Mentioned as optional; executability not confirmed | Not verified | Read-only review 2026-10-16; do not declare them installed |
| E0: Obsidian dg | Vault and Shared link exist; other components not rechecked | Live MCP/ports not checked | Not verified | Path audit 2026-10-14; [older records](history.md#history) |
| E2/E3: pipeline integration in cargotrans-ui/dg | Cargo has a local adapter, review, and task workflow; dg not checked here | Cargo integrated at the documentation level; discovery/runtime separate | Cargo052 has pinned test-only review + pattern supplement; not rerun by this onboarding | Reading existing evidence, not a new product/QA/landing PASS; [CRG snapshot](crg.md#cargo-active-snapshot) |
| E4: PR review in CI | Historical workflow record exists; not checked now | Not verified; historically the job was skipped without a secret | No new PR run conducted | [Historical E4 records](history.md#ci-history) |
| E5: post-deploy | Historical scripts/workflow records exist; not checked now | Not verified | Historical dg smoke; cargo flows did not pass then; no new runs | [Historical E5 records](history.md#ci-history) |

## Updating evidence

Record the repository, path/revision and dirty state, date, and the command actually run or artifact inspected. Code/contract changes after verification may require rechecking; an old PASS does not carry over automatically. Use PASS / FAIL / BLOCKED / N/A with a rationale for checks; do not substitute these verdicts for presence/integration states.

## Session-size helper — 2026-10-17

Implementation and disposable fixtures: [contract](../docs/legacy/session-size.md). Global command hooks prepared for Claude 2.1.302 and Codex 0.156.1: SessionStart/UserPromptSubmit/PostToolUse/Stop. Writing a registration does not mean execution: Codex requires review/trust in /hooks; trust and security permissions do not change automatically. Live CLI/model sessions were not run. 5 000 000 bytes is a soft threshold; a complete semantic checkpoint depends on the agent, and there is no automatic restart.

## Selective adoption candidate 0.7.0 (2026-10-18)

One constraint-driven-development skill plus focused design-pass and clean critic input adaptations are present. Existing grilling and entity-e2e-coverage remain unchanged. Offline evidence fixtures and package checks have separate recorded results; live agent trials, native CLI discovery, product Storybook/E2E execution and independent acceptance remain NOT_TESTED/PENDING. [Scope and limits](constraint-adoption.md). No upstream scripts or paid API were run.
