# Skill-routing evaluation set

Status: **NOT_RUN / NOT_TESTED**. This folder holds definitions only; no model launcher is shipped and no result is claimed.

[scenarios.json](scenarios.json) lists one user phrase per case, the skill whose description should win (`expected_skill`) and the neighbouring skills that must not be chosen in its place (`not_instead`). The cases cover the clusters where descriptions overlap: interface work, review, and planning gates.

## Running it

Run under the same authorization and metering rules as the [lifecycle evaluation contract](../lifecycle/README.md): an explicitly authorized operator, an existing subscription session, a disposable fixture repository, no credentials or product writes.

For each case start a fresh session with the installed kit, send only `input`, and record which skill loaded first from the raw trace. A case passes when that skill equals `expected_skill`. Loading a `not_instead` skill first is a routing failure; loading it later as a delegated step of the expected skill is not. Record the skill-description bytes under test (kit version or manifest hash), the CLI and model, and the trace per trial. Report passes over trials with the sample size.

## Maintaining it

A description edit that touches a cluster reruns that cluster. Add a case when two skills are observed to compete for one phrase; keep one phrase per distinct branch. A failing case is fixed in the description wording, and the phrase stays as the regression case.
