# Skill-routing evaluation set

Status: **RUN 2026-11-23**, toy fixture then the realistic one (1–3 trials per case on it): on the realistic fixture the latest trial is 23 PASS, 2 NO_SKILL, and no trial in any run loaded a wrong skill; see [results/2026-11-23.json](results/2026-11-23.json). A smoke run, not a statistical result. This folder holds definitions, a trace scorer and recorded results; no model launcher is shipped.

[scenarios.json](scenarios.json) lists one user phrase per case, the skill whose description should win (`expected_skill`) and the neighbouring skills that must not be chosen in its place (`not_instead`). The cases cover the clusters where descriptions overlap: interface work, review, and planning gates.

## Running it

Run under the same authorization and metering rules as the [lifecycle evaluation contract](../lifecycle/README.md): an explicitly authorized operator, an existing subscription session, a disposable fixture repository, no credentials or product writes.

For each case start a fresh session with the installed kit, send only `input`, and record which skill loaded first from the raw trace. A case passes when that skill equals `expected_skill`. Loading a `not_instead` skill first is a routing failure; loading it later as a delegated step of the expected skill is not. Record the skill-description bytes under test (kit version or manifest hash), the CLI and model, and the trace per trial. Report passes over trials with the sample size.

### Procedure

[run_routing.py](run_routing.py) never starts a model: `--list` prints the cases, `--parse TRACE` prints the first skill a trace loaded (or `none`), and `--score DIR` scores `DIR/<case id>.jsonl` for every case as `PASS`, `NO_SKILL`, `FAIL_NOT_INSTEAD`, `FAIL_OTHER` or `NOT_RUN`.

1. Confirm the CLI session uses the user's subscription (for Claude Code, `claude auth status` shows the account login, not an API key) and that no API-key or third-party-backend variables are set. Otherwise stop: BLOCKED.
2. Build the disposable fixture with `make_fixture.py <new dir>` (one per case): a small but realistic billing product with several modules and one non-trivial class hierarchy, an admin UI of six screens with real naming and action inconsistencies, a dashboard, a checkout flow, a form, a landing page, a layout mockup PNG, a plan, review comments and a feature branch with one commit. Deterministic; no credentials. A phrase must have a plausible target that is not answerable at a glance, so a skipped skill reflects routing, not a toy repository.
3. Per case, from the fixture root, start a fresh session with only the input and without the file-editing tools (the shell stays available, so run it only in the disposable fixture), for example `claude -p "<input>" --output-format stream-json --verbose --max-turns 4 --disallowedTools Edit,Write,NotebookEdit`, and save stdout as `<case id>.jsonl`.
4. Run `run_routing.py --score <dir>` and record the outcomes with the date, CLI version, model (from the trace's init event) and the kit transaction. Keep traces outside the package.

User-level instructions and memory of the operator's account load in every session and cannot be removed without another login; record that they were present. One trial per case is a smoke run, not a statistical result. `NO_SKILL` (the model asked for context instead of loading a skill) is reported apart from a wrong skill.

## Maintaining it

A description edit that touches a cluster reruns that cluster. Add a case when two skills are observed to compete for one phrase; keep one phrase per distinct branch. A failing case is fixed in the description wording, and the phrase stays as the regression case.
