<a id="матриця-й-перевірка-звіту"></a>

# Matrix and report validation

A human-readable table in the current plan is sufficient; JSON is needed only for the validator. Create the baseline before testing, reconcile it with the original QA/spec and give it to the reviewer separately from the report. The validator cannot recover a QA ID removed from the baseline itself; the reviewer checks the source.

<a id="формат"></a>

## Format

Examples: [contract](example-contract.json), [report](example-report.json). All values in them and in [cases](cases.json) are **synthetic**, even `executed: true`: these are validator fixtures, not browser-test evidence.

Contract: `revision`, `diff`, `qa` (the complete scoped ID/source inventory) and `rows`. Each row has a unique `id`, `qa_id`, `field`, `expected`, `expected_source`, `surface`, `state`, `action`, `assertion`, `channel` (`ui/api/db`), `required`. Multiple fields in one QA finding need separate rows. `expected` is a deterministic textual description of the value/format; for a transform, include its rule and source. Do not use “correct”.

`required: false` specifically means N/A and requires `na_reason` and `na_source`. Do not change required to false because a browser/role/server is unavailable. For a newly agreed scope, preserve the old baseline diff and the owner's decision.

Report: current `revision`, `diff`, `run_id`, `environment`, `fixture_id`, `results`. Each result: `id`, `status`; for non-PASS, `reason` (except N/A, whose reason is in the baseline). PASS has `evidence`: the same five run fields, `executed: true`, actual `surface/state/channel/assertion`, `artifact`, an `assertion_id` unique within that artifact, and `observed`. One trace can contain many independent assertions; one assertion does not close different obligations. For a manual test, the locator is a specific record step, not a general screenshot.

`diff` is the tested diff fingerprint, including relevant untracked files, not just a branch or the word “dirty”. Check it against the checkout and test deployment; the report cannot itself prove that the stated revision was actually open. For a rerun, record a new run and new evidence; preserve baseline acceptance and explicitly update its tested identity.

Invocation (Python 3, no additional libraries):

```sh
python3 ~/.agents/skills/entity-e2e-coverage/scripts/validate_matrix.py contract.json report.json
python3 ~/.agents/skills/entity-e2e-coverage/scripts/test_validate_matrix.py
```

Exit 0: bookkeeping complete for the supplied baseline. Exit 1: malformed/incomplete/FAIL/BLOCKED or suspicious inconsistency; reasons are in JSON. `browser_execution_proven` is always false. The script does not open artifacts, compare the DOM, run a browser, infer expected/observed correctness from text or verify metadata truthfulness. Matching but fabricated metadata will pass; review the actual test/trace and independent source.

<a id="реалістичний-приклад"></a>

## Realistic example

QA-41 requires the name Depot Cedar in detail and edit; after a change, Depot Birch. QA-42 separately requires the display label `Kyiv region` for reference `r-17`, keeping the region unchanged. Comparing the edit value with response `name` does not prove detail. Persistence API may expect `r-17`; the UI must expect a label from an independent fixture.

For dates, separately record whether `2026-10-17` is a calendar date without a timezone or a timestamp converted to a specified zone; do not truncate to the day if QA checks the time. For boolean `false`, check the actual contractual label/unchecked state, not the presence of truthy text. For null/empty and nested references, record the placeholder/absence/label actually promised by the spec. Add only fields and states within the current scope.

Cases A–E contain different reports for the depot workflow, suitable for independent review without live-environment access. They include create→edit without view evidence, a complete cycle, edit-only UI with documented N/A, an unavailable required view and a lost QA field. The test script checks expected verdicts; do not present synthetic complete as product PASS.

<a id="умовні-поля-для-filters--keyboard--visual"></a>

## Conditional fields for filters / keyboard / visual

Only when acceptance includes these requirements, add row `kind`: `filter-matching`, `filter-nonmatching`, `keyboard` or `visual`, and `entity_type`. Evidence repeats both fields; channel is `ui`. Other CRUD rows remain unchanged.

For a declared filter scope, add contract `filter_scopes: [{"entity_type": "truck", "surface": "list", "source": "acceptance AF-1"}]`. Each pair requires separate required matching/nonmatching rows. The reviewer reconciles declared types/surfaces with acceptance: the parser cannot find omitted scope in external prose. Do not include inapplicable filters in filter_scopes; an optional row with `required: false`, N/A/source/reason documents a scoped exclusion.

A required keyboard row also has `input_method` (`simulated-browser-key` or `manual-key`), `key` and `ui_effect`; evidence repeats them. `dispatch-submit` is not keyboard input. These fields record the declared method rather than proving a keypress.

For scoped visual states, create separate required `kind: visual` rows with specific `surface/state/assertion`; for example open-popover, active-trigger, chips. A default screenshot cannot substitute for another state. The reviewer, not the parser, checks the actual inventory and image comparison.

Optional report `claimed_pass_rows` contains IDs of rows for which the summary claims PASS; unknown/non-PASS IDs are rejected. The field does not analyze summary text or an external checklist. PARTIAL/BLOCKED with a reason allow an honest report, but a required row leaves coverage incomplete (exit 1). Justified N/A does not close required scope.

[Scoped fixtures](scoped-cases.json) synthetically check missing entity coverage, keyboard substitution, uncovered active state, overclaim and scoped N/A. They are not browser-run results.
