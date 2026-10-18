# Selective constraints and behavior evaluation

The constraint-driven-development skill is an optional focused lens within the existing lifecycle. Use it when a failing gate tempts a weaker check, or a review changes tests/thresholds/suppressions. Preserve the project stack, existing task/checkpoint, independent reviewer and commit authority. Do not bootstrap a second workflow.

At each task boundary, including the second task in a sprint: select the active task and establish its checkpoint before code. On resume verify task, root/base/HEAD and scoped dirty/untracked inventory. A graph is context only: refresh by an authorized route or use direct file evidence and record reduced graph confidence. After review, HEAD or scoped-byte drift requires a final-delta decision. Tests and UI remain distinct evidence.

The offline helper in runtime/constraints/evidence_check.py validates declared evidence completeness, exact snapshot matching, signal dispositions, task readiness and required UI state coverage. It never runs a model, Git, shell, network or product command. It is not a semantic oracle, a regex weakening detector, or proof that referenced evidence is true. PASS means the supplied record satisfies this schema only.

[Behavior evaluation contract](../evals/lifecycle/README.md) defines comparable adversarial cases and a fail-closed, subscription-only opt-in procedure. Live behavior remains NOT_RUN. Offline fixtures are reported separately. No claim of equal or better model quality is justified before matched trials.

The adoption preserves existing entity-e2e-coverage and grilling: omitted views and fact-versus-decision interviews are already covered. It adds no duplicate interview or doubt-driven orchestration skill. Package provenance pins the upstream source and preserves MIT notices.

## Reuse existing Storybook and E2E

Map acceptance → existing story/state or E2E scenario → runtime evidence with revision, command/run ID and result. Storybook demonstrates isolated component states; E2E demonstrates integrated create/view/edit/result flows. Story existence is not execution, and a Storybook PASS cannot establish entity integration. Select only relevant existing gates; add a missing test only for a demonstrated coverage gap within authorized scope. Agent behavioral evaluation checks this selection, actual execution/evidence, omitted views and preservation of assertions; it does not reimplement product E2E.

### Impact-based evidence matrix

Map each affected acceptance criterion to the most appropriate existing level and actual evidence: unit/component tests for component logic, contracts and interactions; Storybook for isolated states and any interaction, visual or a11y checks already configured; E2E for integrated flow/result. Inspect existing scripts/configuration before assuming Storybook addons or tests exist. Do not duplicate identical assertions across levels. Explain omitted relevant levels; retain mandatory local gates even where coverage overlaps. Unit/component PASS does not prove the persisted entity view or entire flow. A story can exercise configured interactions and accessibility, but does not by itself establish cross-route persistence/integration.
