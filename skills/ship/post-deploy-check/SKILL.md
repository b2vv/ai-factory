---
name: post-deploy-check
description: Re-runs key feature scenarios in production, compares behavior with the test environment, checks logs and integrations, and appends the result to the same report. Use after rollout, or on triggers "check production", "post-deploy", "verify after deployment".
---


# post-deploy-check — the feature in production, not in a test

Work does not end at deployment. This checks the one thing a test environment cannot supply:
**behavior with real data and real infrastructure**.

**Discrepancy** is the key word. A scenario green in tests and green in production adds no
knowledge. The skill's value lies precisely in the rows where production differs from tests; they are the reason
to come here.


## 1. Find the feature report

The report is in the artifacts home (`.claude/standards.md` → `## Artifacts`, the manifest section heading), with an empty
Post-deploy section. Append the result **there**, not in a new file.

If there is no report, say so and ask which file to write to. Do not create a second report for a feature
that already has one.


## 2. Establish what is actually accessible

Before running checks, name what you can actually inspect in this project:

- production URL or Pages build — whether it is up, which build is there now;
- logs — whether access exists, and from where;
- integrations — which external systems the feature touches and whether their responses are visible;
- database — read-only access, if any is configured.

**Call unavailable things unavailable.** Frontend repositories or embed SDKs often simply have
no logs or database — that is a valid answer. A skipped check explicitly marked skipped is honest;
a silently skipped check turns the report into a signature on unverified claims.


## 3. Re-run key scenarios

Take the happy-path rows and those touching real data from report §2 (`ship-report`).
Run them **in production**, following the same path a user would take.

Do not pull in the whole suite: boundaries and failures are already covered by tests, and reproducing them
in production costs more than it helps. Focus on what breaks specifically because of real data, scale and latency.

For each row: expected (from the table) → actual in production → **matched / differed**.


## 4. Inspect what tests do not show

- **Scale and latency** — real data is larger and slower than fixtures.
- **Cache and CDN** — whether an old build is served; which build actually opened.
- **Permissions and roles** — a production account sees something different from a test account.
- **Integrations** — an external system responds differently from a mock.


## 5. Append to the report

The Post-deploy section of the same file:

- **Deployed** — what, where, when, which build/commit.
- **Checked** — the §2 rows re-run, with a verdict.
- **Production ⟂ test discrepancies** — a separate list; explicitly write an empty list too.
- **Logs and integrations** — what was inspected; unavailable items called unavailable.
- **Problems** — or “none”.

A discrepancy found here is not fixed silently: it becomes either a correction or a row in
§6 “Risks and limitations”.


## Completion

The skill is complete when **all** of the following hold:

- [ ] State which of (production URL / logs / integrations / database) are accessible and which are not.
- [ ] State which build or commit opened in production — not “deployed”, but what is there now.
- [ ] Every re-run row has a verdict; state the re-run count out of the total.
- [ ] A production ⟂ test discrepancy list exists, even if empty.
- [ ] The result is appended to **the same** feature report.
