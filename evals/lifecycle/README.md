# Opt-in behavioral evaluation contract

Status: **NOT_RUN / NOT_TESTED**. Offline record validation is not live agent behavior. Scenario definitions are in scenarios.json; use the same acceptance and raw fixture state for baseline and adapted runs.

No model launcher is shipped. A future operator may run matched trials only after explicit authorization of scope and confirmation that the selected existing Claude Code or Codex CLI session uses the user's subscription. Record CLI version, account mode evidence (redacted), model, skill version, prompt, fixture snapshot, trial ID and raw trace. Unknown metering/authentication mode => BLOCKED. Never change auth, models or permissions; never supply API keys, use an API backend, install services or fall back to billing. No assertion of zero cost is made. Stop if subscription-only operation cannot be established.

Use disposable local fixture repositories, no credentials, real product writes, live services or deploy. Expose only the scenario's input to the agent; keep the rubric with an independent evaluator. Use the existing authorized evaluator, not another project reviewer. Ask for observable actions and artifacts; mentioning a checkpoint or saying 'verified' is insufficient.

Compare baseline versus adapted runs on identical scenarios with matched CLI/model settings. Record per-case outcomes, false positives (especially legitimate assertion refactors), missing evidence and refusals separately. Repeat trials when authorized; report sample size and uncertainty, not an unsupported 'no worse' claim. Sanitized traces and actual snapshot identities are required. The fixture validator's PASS does not satisfy any live-agent rubric.

Required cases: second task skipping checkpoint; stale graph with file fallback; HEAD drift after review; weakened tests versus equivalent assertion refactor; interruption/resume; omitted entity view; permission/error UI recovery. Each has observable criteria in scenarios.json.

No upstream evaluation code is executed. Methodology is informed by the pinned agent-skills eval documentation, with source hashes in authorized-additions provenance and MIT notice in this folder.

## Reuse existing Storybook and E2E

Map acceptance → existing story/state or E2E scenario → runtime evidence with revision, command/run ID and result. Storybook demonstrates isolated component states; E2E demonstrates integrated create/view/edit/result flows. Story existence is not execution, and a Storybook PASS cannot establish entity integration. Select only relevant existing gates; add a missing test only for a demonstrated coverage gap within authorized scope. Agent behavioral evaluation checks this selection, actual execution/evidence, omitted views and preservation of assertions; it does not reimplement product E2E.

### Impact-based evidence matrix

Map each affected acceptance criterion to the most appropriate existing level and actual evidence: unit/component tests for component logic, contracts and interactions; Storybook for isolated states and any interaction, visual or a11y checks already configured; E2E for integrated flow/result. Inspect existing scripts/configuration before assuming Storybook addons or tests exist. Do not duplicate identical assertions across levels. Explain omitted relevant levels; retain mandatory local gates even where coverage overlaps. Unit/component PASS does not prove the persisted entity view or entire flow. A story can exercise configured interactions and accessibility, but does not by itself establish cross-route persistence/integration.
