# CTO research — pre-implementation briefing

**Date:** 2026-11-24 · **Base commit:** e7cdc70 · **Local state:** clean apart from an untracked local evidence directory
(not part of the release). Freshness gate: compare `git log --oneline e7cdc70..HEAD` and `git status --short`.

This file is a cache of primary sources. When it disagrees with a cited source, the source governs; rewrite this file.

## 1. One-screen verdict

AI Factory is a portable toolkit for working with AI coding agents (Claude Code, Codex): skills, a task workflow and
local helper tools, distributed as a verified release package and installed once per machine as a *managed kit*
that projects connect to (README.md "How projects connect"). Release 0.9.0, status
`ALPHA_EXPERIMENTAL_UNTAGGED_CODEX_EVENT_SUBSET`, 16 components, 927 manifest files (release-manifest.json).
The core workflow needs only Python 3.9+; the conversation archive (Go storage server, MongoDB + PostgreSQL),
capture hooks, dashboard and native handoff are optional components (README.md "Scope and requirements").
No live P0: the task queue is empty after the kit-move task (e7cdc70; see section 6).

**Architectural fact #1 — the checkout is not what agents run.** Agents and connected projects use the *installed
kit* at its stable root, never this repository. A source change reaches them only through: commit → `git archive` →
`tools/export_release.py` → `tools/verify_release.py` → `kit.py update --package P --root K` with the **complete**
component list (a partial list is a removal) → re-plan NOOP (docs/managed-kit-connections.md; README.md "Update the kit
once"). Corollary: several test suites treat their own tree as a release package (every file must be listed in the
manifest, no symlinks), so they fail in a working checkout that holds untracked files or `node_modules` symlinks and
pass only inside an exported package (tools/kit.py:120-134 `payload`; tests/collection/test_collection.py:7-9).
Run the full suite inside the exported package.

## 2. Product

| Question | Answer | Source |
|---|---|---|
| What is it | Skills + task workflow + local helpers for agent-driven development; does not supply a model or build apps | README.md:1-11 |
| Who uses it | One owner running several projects on one machine through one kit | README.md "Keep several projects on one toolkit" |
| Delivery | Release package (manifest + checksums) installed by `tools/kit.py install/update/rollback` into a managed root | docs/managed-kit-connections.md; tools/kit.py |
| Project connection | Managed block in the project's gitignored `AGENTS.local.md` (+ `CLAUDE.local.md` import), one project list in the kit | tools/connect-project.py; tools/projects.py |
| Skills | 78 SKILL.md files in a grouped tree (plan/deliver/arch/git/crg/ship/utils/pt + top-level) | `find skills -name SKILL.md` |
| Optional archive | Storage server keeps original records in MongoDB; PostgreSQL is a derived search index; capture and search use separate project-scoped access | README.md "Optional archive"; runtime/storage/TAKEOVER-CONTRACT.md |
| Platform | POSIX/macOS documented; Windows unsupported | release-manifest.json `platform` |

## 3. Codebase and seams

| Area | What lives there | Source |
|---|---|---|
| `tools/` | Installer and kit operations: kit.py (install/update/rollback/move dispatch), projects.py (one project list), connect-project/capture/handoff, instruction_update/capture_update (registrations), kit_move.py, export/verify, run_tests.py — ~5.8k lines Python, stdlib only | `wc -l tools/*.py` |
| `skills/`, `rules/`, `ai-factory/` | Skill bodies, cross-project rules, workflow docs; delivered as kit components, discovered globally through skill symlinks | README.md; tools/connect-skills.sh |
| `runtime/storage` | Go archive server: wal, ingest, budget ledger, control, archive, search, summary, api … (~20k non-test lines) | `ls runtime/storage/internal` |
| `runtime/dashboard` | Go server + React UI bundled with esbuild; reads a private feed and a generated projects file | runtime/dashboard/package.json; tools/project_dashboard.py |
| `runtime/web-to-md`, `runtime/session-size*`, `runtime/scanners` | HTML→Markdown helper (Go); native handoff/session-size guard; optional scanners | runtime/README.md |

Seams and what crosses them:

| Seam | Crossing | Source |
|---|---|---|
| source repo → installed kit | only a verified package via `kit.py update` | docs/managed-kit-connections.md |
| kit → home | `~/.agents/.ai-factory-instructions/owner.json` (one kit per home), instruction targets, hook commands, skills links | tools/instruction_update.py `check_home`; tools/connect-capture.py; tools/connect-handoff.py |
| kit → project | managed block (kit path, entry rules, routes, work/ layout, dashboard pointer) | tools/connect-project.py `build_block` |
| registration records | capture/handoff/instruction records bind host files by sha256 and the kit by `kit_identity`; drift blocks | tools/connect-capture.py `current`; tools/instruction_update.py `fingerprint` |
| agent → storage server | loopback HTTP, per-project grants; capture writes the WAL, the budget ledger reserves before writes | runtime/storage/internal/api/api.go; internal/budget/ledger.go |

## 4. Infrastructure and delivery

| Question | Answer | Source |
|---|---|---|
| CI | None in the repository (no `.github/`); all checks are local | `ls .github` |
| Test entry | `python3 tools/run_tests.py [--suite all|storage|dashboard|web-to-md]`: Python suites per directory, Go suites, dashboard node tests | tools/run_tests.py:12, :80 |
| Release integrity | `tools/verify_collection.py` (provenance/source-map hashes), `tools/verify_release.py` (package), manifest + checksums must match bytes | AGENTS.md; tools/verify_*.py |
| Storage image | Digest-pinned OCI build (`deploy/oci/build-and-verify.sh`); integration (`deploy/test/run-integration.sh`) and process e2e (`deploy/test/e2e-process.sh`) need Docker | runtime/storage/deploy/oci/Dockerfile:1-12 |
| Kit live state | `kit.py update` prints a per-project report (OK / NEEDS_REPAIR / PROBLEM) | tools/kit.py `project_report`; tools/projects.py `check_projects` |
| Publication | Plain `git push` of `main` to a public repository after a privacy scan; tag `release-0.9.0` exists | `git tag`; local push practice ⚠️ unverified as a written repository rule |

## 5. Dependencies

| Module | Key dependencies | Source |
|---|---|---|
| tools/ (Python) | stdlib only; Python ≥3.9; `/usr/bin/git` for project roots | release-manifest.json `platform`; tools/projects.py `git` |
| runtime/storage | go 1.27.0; pgx/v5 5.9.2, mongo-driver 1.17.7, x/text 0.41.0, compress 1.20.2 | runtime/storage/go.mod |
| runtime/web-to-md | go 1.27.0; html-to-markdown/v2 2.5.2, x/net 0.62.0 | runtime/web-to-md/go.mod |
| runtime/dashboard | go 1.27.4; react/react-dom 19.2.7, react-markdown 10.1.0, esbuild 0.28.2 | runtime/dashboard/go.mod; package.json |

## 6. Risks

| Risk | State | Source |
|---|---|---|
| Storage alpha | Whole-storage independent review BLOCKED; no automatic WAL reclaim | runtime/storage/TAKEOVER-CONTRACT.md:4; release-manifest.json `alpha_acceptance` |
| Host acceptance | Native discovery/invocation and global activation NOT_TESTED / NOT_RUN | release-manifest.json `host_acceptance`, `independent_review` |
| Checkout vs package tests | Package-as-tree suites fail in a dirty checkout (untracked files, `runtime/dashboard/node_modules` symlinks); session-size-docker tests fail when TMPDIR is under a symlinked path | section 1; tools/kit.py:126 |
| Known flaky test | `test_parallel_invocations_do_not_collide` (session-size-docker) fails under full-suite load, passes alone | ⚠️ unverified as a recorded debt item; observed in recent full runs |
| Outage recovery scope | Capture recovers after a Mongo outage on the legacy ingest path; the metadata (archive-source-v2) path was not exercised by the e2e | commit 2775134; runtime/storage/internal/ingest/ingest.go |
| Kit move | `kit.py move` proven on fixtures and in a closed sandbox; never run against a live kit; Codex hook trust and dashboard restarts stay manual | commit e7cdc70; docs/managed-kit-connections.md |
| Shared settings file | Capture and handoff registrations both record the signature of the same Claude settings file; re-registering one may make the other report drift | ⚠️ unverified (code reading of tools/connect-capture.py `current` and tools/connect-handoff.py `current`) |
| Translation provenance | Full source-bound verification of translated skills needs an external, hash-authenticated history baseline; a package hash check alone is not semantic equivalence (`REQUIRED_EXTERNAL_REVIEW` is an enduring requirement) | PROVENANCE.md:104 |

Unverified claims: 3 (labelled ⚠️).
