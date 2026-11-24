# Agenda — next move

**Date:** 2026-11-24 · **Based on briefing:** work/CTO-RESEARCH.md at e7cdc70. Rebuilt, not appended: when the
briefing is rewritten, re-check the move below.

## Sources visited (candidate count)

| Source | Candidates | Note |
|---|---|---|
| Open tasks (the task index, kept outside the repository; GitHub issues) | 0 | all 33 index rows DONE or CANCELLED; 0 open issues |
| Recorded debt and leftovers in task records | 5 | no `tech-debt/` directory; leftovers noted in done task records and owner session notes (kept outside the repository) |
| Briefing "Risks" | 5 | plus 2 already covered elsewhere (outage scope → C5; kit move → not now) |
| Unchecked boxes | 0 | the only `- [ ]` items are the reusable checklist in ai-factory/onboarding.md:44-52, not promised work |
| Skipped tests, disabled gates, TODO anchors | 1 | integration tests skip without a DB by design (run-integration.sh runs them); no TODO/FIXME anchors in tools/ or runtime code |
| Unresolved product choices | 3 | listed under "Owner decisions" |

Candidates without a source: 0.

## Candidates

| # | Candidate | Source | Unblocks | Reversibility |
|---|---|---|---|---|
| C1 | Storage alpha: automatic WAL reclaim and whole-storage acceptance | runtime/storage/TAKEOVER-CONTRACT.md:4; release-manifest.json `alpha_acceptance` | storage leaving alpha | expensive (data path, retention) |
| C2 | Host acceptance: prove native skill discovery and invocation from a fresh agent session | release-manifest.json `host_acceptance` NOT_TESTED | the README claims about global skills | cheap (read-only check) |
| C3 | Make in-checkout test runs trustworthy: package-as-tree suites copy only manifest files (as tests/projects/test_clean_machine.py does) and session-size-docker resolves a symlinked TMPDIR | briefing §1, §6; tools/kit.py:120-134 | every future task's verification (today each needs a 10+ minute exported-package run and explaining false failures) | cheap (test-only) |
| C4 | Flaky `test_parallel_invocations_do_not_collide` under full-suite load | briefing §6 | a clean full-suite signal | cheap (test-only) |
| C5 | Check the metadata (archive-source-v2) capture path for the same outage gap fixed on the legacy path | a closed task record (outage recovery, "Not covered" section) | confidence that capture recovers on the current path | cheap to check; code fix moderate |
| C6 | Confirm or refute: capture and handoff registrations both pin the Claude settings file signature, so re-registering one makes the other report drift | briefing §6 (⚠️ unverified) | safe enrollment of native handoff beside capture | cheap (fixture test) |
| C7 | Old-version compatibility never exercised (old server / old operator) | runtime/storage/internal/control/archive_old_server_test.go:22; summary_consent_test.go:230; summary_projection_cancel_test.go:172 | safe storage upgrades with mixed versions | cheap to run if the old binaries are built; medium setup |
| C8 | Skill-routing evals ran once (n=1); results carry no repeat evidence | a closed task record (skill-routing eval, run n=1) | trust in routing claims | cheap, but costs model runs |
| C9 | First live archive install for a new project never exercised end to end | owner session notes (kept outside the repository): "first live archive install not yet exercised" | onboarding the next project with archive | expensive (external effect: grants, workers) |
| C10 | Codex hooks for some connected projects await owner trust in Codex | owner session notes (kept outside the repository, 2026-11-23) | Codex capture for those projects | owner action, not an agent move |
| C11 | review-diff turn-cap trial | owner session notes (kept outside the repository): "review-diff turn-cap trial" | ⚠️ scope not recorded beyond the name | unknown |

Filtered out (already done or decided): leftovers of earlier closed tasks (live kit update, dashboard rebuild → done);
a branch named in session notes (no such branch exists in this repository);
moving the live kit (owner 2026-11-24: capability only).

## Owner decisions

| Question | Options and cost | Recommendation |
|---|---|---|
| D1. Invest in taking storage out of alpha (C1)? | (a) start reclaim + acceptance now: large, data-path risk; (b) keep alpha, default off, revisit when archive volume grows | (b): nothing waits on it and it is the most expensive to undo |
| D2. Live operations now (C9, C10)? | (a) do a first live archive install and trust the Codex hooks: real external effects, owner time; (b) defer until a project needs it | (b) for C9; C10 is a one-minute owner step whenever convenient |
| D3. Commit the briefing and this agenda to the public repository? | (a) commit as is; (b) commit after rewriting references to records kept outside the repository; (c) keep them local only | decided 2026-11-24: (b) |

## Next move

**C3 — make in-checkout test runs trustworthy (with C4 folded in if its cause is the same load sensitivity).**
Small, test-only, cheap to undo, and it improves every later move: today a correct change shows false failures in
the checkout and needs a separate exported-package run to be verified.

Why not the others:
- **C6** is cheaper still and may reveal a real latent bug, but nothing uses handoff beside capture today, so it
  unblocks nothing until handoff is enrolled; it is the natural second move.
- **C2** is valuable evidence but changes no code path and does not make any later task easier.
- **C5** depends on running the storage suites, which C3 makes faster to trust; do it after C3.

Goes to: a small task record (below the spec-flow threshold), TDD on the test helpers, then the normal kit update.

## Done since the last agenda
First agenda in this repository; the earlier task queue closed before it (last: kit move → e7cdc70).
- done: C6 → 116c34a (confirmed real; capture and handoff now pin only own hooks + permissions; kit b7d9300e). 
- done: C3 → 9e82752 (checkout runs use a package view plus the exporter's check; TMPDIR resolved). D3 → fbd9747, cdea7a9.
