# AI Factory — 0.7.0-rc.5

This prerelease strengthens code-review and TDD coverage guidance: individual
mutations of changed and deleted behavioral constructs, honest survivor
classification, and plain CI-running tests when service-only coverage skips in CI.
Evidenced real CI execution satisfies that specific gap; stronger local rules remain.
Reviewers recommend refactors; authorized authors implement and resubmit the delta.
Correlated test oracles are described as weak evidence rather than infallible matches.

The rc.4 four-viewport UI contract, separate text enlargement/reflow checks and
optional inactive rc.3 Docker session-guard package remain unchanged. Package
validation does not certify native skill/UI compliance or hook execution. Inherited
session-guard timing fixtures did not complete reliably in the tested Docker
harness; this release makes no new runtime acceptance claim.

- **[All 73 original skills](skills/)** — one canonical editable tree; groups, references, scripts, assets and synced variants are preserved.
- **[Full AI Factory plan](ai-factory/ai-factory-plan.md)** — workflow, lifecycle, status, roadmap and historical sources.
- [Shared rules](rules/) · [Runtime helpers](runtime/README.md) · [Explicit policy adapters](adapters/README.md)

Status: release candidate. The scanner milestone passed independent code/runtime review for Docker-only linux/amd64 execution on macOS; this does not constitute acceptance of the entire backlog, native agent discovery or persistent project activation. The final release package requires a separate hash-bound review before tagging/publication. This structure does not authorize installs, hooks, MCP, model changes or product actions. Local project contracts and the current task take precedence.

## What was adapted from ECC

These are selective, independently authored adaptations of ideas following a source audit of
[ECC `90606c8315ee09cafc303515c5f33024db6b9882`](https://github.com/affaan-m/ECC/tree/90606c8315ee09cafc303515c5f33024db6b9882),
not an ECC installation or an import of its skill/hook pack. The implementation below is included in
Factory commit `17a9527421e8fac3e43a16c287c404118699833c`; it is an unreleased
commit-pinned candidate, not a new publication of the rc.5 tag. This description is a separate docs-only
delta; it does not move consumer pins or replace immutable caches.

| Implemented capability | What the user gets | Evidence limits |
|---|---|---|
| [Offline discovery-response checker](docs/onboarding-helper.md) | Shared comparison of selected skills by name/path/enabled; declared inventory for Claude and Codex; a separate parser for a supplied Codex `skills/list` result | `RESPONSE_MATCH`: each selected skill appears exactly once at the expected enabled path; additional unselected skills are allowed. Digests bind bytes, not capture authenticity. There is no native Claude parser; capture authenticity, native discovery/invocation and model behavior are NOT_TESTED. The checker does not launch the host |
| [Five language review/testing references](skills/arch/code-review/references/languages/index.md) | TypeScript: runtime boundary validation and wire contracts; PHP: DTO/ports and unit/integration; Python: fixture ownership, autospec/await and cleanup; Rust: ownership/unsafe contracts, properties/doctests; Go: bounded concurrency, cancellation, race/fuzz/golden obligations | Guidance for the existing TDD/review gates, not installed toolchains, compiled recipes or evidence that product tests were executed |
| Optional framework references in the same index | React for confirmed TS/TSX; Laravel only for Laravel; Django/DRF or FastAPI only when supported by the actual stack | Normally the index + one language + zero/one framework. An unknown stack is UNKNOWN; no automatic loading of all references or framework installation |

TypeScript primarily preserves the user-authorized portable intent of the
Cassiopeia rules. MVC layout, service/naming conventions, libraries and versions are not
imposed on other projects. The [TypeScript reference](skills/arch/code-review/references/languages/typescript.md)
explicitly explains the conflict with the old forced-interface Pocock rule: the historical file
is unchanged, and the current project convention takes precedence. Exact conceptual
sources, per-file digests and exclusions are in
[language provenance](provenance/language-reference-origins.json); the checker's
origins and rights/limitations are in [PROVENANCE](PROVENANCE.md).

Unsafe examples were not copied verbatim. Go guidance requires cancellation to reach
the actual blocking operation and bounded fan-out; Rust rejects fabricated lifetimes
from raw pointers and notes the `Debug` requirement for `unwrap_err`; FastAPI distinguishes transport from
lifespan; Django does not call an external side effect idempotent without an appropriate
contract. PHP cache/Composer commands are not described as read-only. Formatting does not
replace lint/typecheck. Execution evidence is required separately for each recipe.

**What Factory already had.** Core TDD, mutation/behavior coverage, snapshot-bound
independent review, durable handoff, guarded installer/update/rollback and four
viewport classes were not adopted anew or replaced with ECC. The existing
[workflow](ai-factory/workflow.md), [behavior coverage](skills/arch/code-review/references/behavior-coverage.md)
and [review handoff](ai-factory/review-handoff.md) remain the sole authority.

**What was not adopted.** Wholesale skills/hooks installation, worktree orchestration,
transcript learning/LLM summaries, auto-promotion, broad MCP defaults and claims of
universal native parity. Budgeted context routing, matched behavioral eval and
additional recipes for parked/rejected/validated ideas before they become tasks are only possible future
work, **NOT_IMPLEMENTED in this delta**; the existing
[lifecycle](ai-factory/feature-lifecycle.md) is unchanged. The presence of an upstream
README or test fixtures is not evidence of productivity or safe runtime behavior.

**Separate rollout checkpoint (2026-10-26).** Candidate `17a9527` was applied through
approved tooling adapters in Cargo, Courses, Cassiopeia and dg; hash/path checks and
repeat reconciliation/installer NOOP passed. The independent technical review was
accepted; external final applied-snapshot reviews are still PENDING. In dg, after apply,
unrelated work changed the product HEAD: tooling bytes were verified, but overall
HEAD/WIP preservation is not reported as PASS. This is a dated report, not a live status service,
native activation proof or permission to repeat the rollout. This docs delta does not
change any of those pins or review verdicts.

## Getting started with AI: three scenarios

This repository contains workflow, skills, templates and offline helpers; it does not install Codex/Claude itself, the project's language, MCP/graph servers or models. Local helpers need no additional SaaS; AI access remains subject to your existing account/license, not a promise of free model calls.

| Situation | Route and ready-to-use prompt |
|---|---|
| Existing project | [AI-assisted onboarding](docs/guides/ai-assisted-onboarding.md#existing-project): read-only inventory → scoped adapter diff → approved apply → separate host proof |
| Empty project | [Empty project](docs/guides/ai-assisted-onboarding.md#empty-project): first define the product/stack/acceptance, then minimal instructions; no automatic app bootstrap |
| Another developer / machine | [New machine](docs/guides/ai-assisted-onboarding.md#new-machine): trusted private source → dedicated package root → selected host exposure → project adapter; no copying credentials |

**What goes where.** Place the full verified package in a separate managed directory, for example `~/project-data/ai-factory-kit`. `~/.agents/skills` is the canonical shared host-facing store by this kit's convention; `~/.claude/skills` may use the same source only after checking conflicts and host support. `kit.py` does NOT publish skills there and deliberately rejects `~/.agents`, `~/.claude` or a directory named `skills` as an install root. There is no safe "install everything into home" command. The [layer and discovery map](docs/guides/ai-assisted-onboarding.md#destinations) explains exact-file fallback, variants/collisions and automation limits.

**Before any execution:** read the source/provenance and the scripts' effects; a checksum is not a signature or sandbox. Do not give the agent tokens, `.env`, keychain contents or session logs. [Security adoption](docs/guides/ai-assisted-onboarding.md#security-proposed) is still **PROPOSED**, not installed/enforced.

Minimum requirements for helpers: Python **3.9+**, a POSIX filesystem; Git is required by review helpers/fixtures. macOS is the current verification environment; Linux is **NOT_TESTED**, Windows is **UNSUPPORTED** (`fcntl`). Product tools depend on its stack; Node/npm/Docker are not required for offline installation. Exact CLI versions/discovery/runtime capabilities must be verified on the target machine, not inherited from this README.

Tasks use a [task branch in the main repo](ai-factory/workflow.md#task-branches), with one writer and no automatic per-task worktree/clone. Foreign/unknown dirty WIP → STOP and coordinate; no stash/reset/commit to clear the tree. Runtime/test isolation is separate. Obtaining trusted AI Factory source for a new machine for the first time is not creating a per-task product clone.

## AI Factory as project-local agent tooling

Factory can be organized as local tooling: pinned workflow/skills separate from
project-specific settings. **Recommended layout**, provided it does not conflict with
the existing integration:

```text
<project>/
  .ai/
    factory/   # managed snapshot of the selected Factory revision; do not edit manually
    project/   # local paths, adapter/config and pin; preserve during update
    README.md  # how the agent starts/resumes; where rules, tasks and evidence live
```

These destinations may remain local and ignored. First check what is already
tracked and what `.ai/` contains: **gitignore does not remove already tracked files**. Do not blindly ignore
all of `.ai/`, automatically untrack files or migrate existing
AGENTS/adapter/pin/symlinks. For a new setup, select only the exact approved ignore paths.
Do not store secrets, tokens, `.env`, auth/session stores here; ignored does not mean protected.

**The agent needs an explicit entrypoint.** An arbitrary `.ai/` does not guarantee discovery or execution of
the workflow. The user may add a short tracked pointer from root README/AGENTS,
configure an entrypoint supported by their particular agent, or start each time with
"Read `.ai/README.md` and apply its specified workflow to my task." A README for
humans is not necessarily read automatically by an agent. Native skill invocation and explicit
file reading are different evidence; neither pointer guarantees compliance with the rules.

### What is implemented and what needs verification

The [current installer](docs/portability-design.md), `tools/kit.py`, uses an explicit dedicated
absolute target: plan/install/update/rollback, selected components, hashes, backups,
receipts and guarded NOOP. It **has no separate `.ai` mode**, does not generate project config,
change gitignore/AGENTS or register skills with the host. This layout recommendation alone
does not establish installer/runtime acceptance.

Before installation, the agent must read the source/provenance and the contract of the **selected revision**,
verify support for target `.ai/factory/`, canonical paths without symlink components,
no source/target overlap or unmanaged collisions, the required components and
the writer window. The target must be a dedicated subtree, not the product repository root
or all of `.ai/`. If the selected version does not support that target, leave the dependent setup
BLOCKED or agree on an already supported external dedicated root; do not bypass guards.
Do not create a second installer. The [onboarding guide](docs/guides/ai-assisted-onboarding.md)
and [read-only preflight](docs/onboarding-helper.md) remain the established route.

For project-local declarations, reuse the existing adapter,
`ai-factory-manifest.json` and `ai-factory-package.json`, if present. For a new
setup, agree on their paths in `.ai/project/` using the [manifest example](examples/onboarding/manifest.json)
and [adapter template](templates/adapter-full.md), without a second source for the same rules.
Do not move local overrides into `.ai/factory/`: an update must change only the managed
package target and leave project config, task history and required gates unchanged.

A pin is the exact commit of the selected trusted source, release manifest/hash and component set,
not a floating branch or `latest`. An example of an existing exact pin:
`1e5411f12677c45fd67b0900c77eb418a214d065` (merged scanner milestone before release); candidate status does not
constitute independent acceptance of all capabilities. Before use, verify the specific
release, required hashes and [provenance](PROVENANCE.md). A hash from the same unknown
archive does not authenticate its author. An uncommitted checkout, including scanner additions,
does not substitute for a pinned workflow release and is not activated by local setup.

**New machine:** ignored files do not arrive with a clone. Separately preserve a non-secret
bootstrap record containing trusted source/commit, manifest hash, components, layout and a backup of
local config — in an approved private backup or as a minimal tracked manifest,
as the team chooses. Restore the same pin through verified setup; custom config cannot
be reconstructed from Factory core alone. Full trusted source is kept separately from
the installed subset; subset metadata does not make it a full release. A new release
is obtained and applied only through an explicit update with diff review, backup and preservation
checks, without automatically overwriting local settings.

### Prompt 1 — inspect and safely connect local tooling

```text
Prepare AI Factory as local tooling for <PROJECT_ROOT>.
Trusted source: <SOURCE + EXACT COMMIT + MANIFEST HASH>.
Start read-only: read local AGENTS/CLAUDE, the current adapter/pin,
README, git tracked/ignored state, relevant WIP and ownership. Do not read secrets.
Do not assume integration is absent or migrate the existing setup automatically.
Read root README, the onboarding guide, the installer contract and the source of the selected
Factory release; verify hashes/provenance and support for the recommended
.ai/factory/, .ai/project/, .ai/README.md. Do not invent an .ai installer mode.
Use existing kit plan, preflight and change protocol where applicable.
Before writing, show exact paths/components/entrypoint, ignore changes if needed,
conflicts, diff, backup/rollback and what will remain local. Missing support
or writer window means BLOCKED for the dependent setup; do not bypass guards.
Only after the specific plan is approved, apply this setup and verify hashes,
local preservation and repeat NOOP. Do not run product tools/scanners,
dependency installs or hooks/MCP, or change permissions or model defaults.
```

### Prompt 2 — start or resume a task

```text
Read <PROJECT_ROOT>/.ai/README.md or the current approved entrypoint,
local instructions/config and the pinned Factory workflow. Verify the pin and paths.
Task: <GOAL or ID + CURRENT PLAN/REPORT>.
Show scope/acceptance, root/branch/HEAD/relevant WIP, writer, small/full/resume,
review route and pre-code READY/BLOCKED. Preserve local contracts and gates.
On resume, reconcile current inputs and evidence; do not reopen unchanged completed work.
Perform only the assigned scope; keep evidence and handoff in existing task artifacts.
A missing shared file/required review means a specific BLOCKED, not an invented PASS.
Do not update core/pin/config or run a scanner merely because you read the workflow.
```

### Prompt 3 — perform a verified package update

```text
Prepare a local AI Factory update to <NEW EXACT COMMIT + MANIFEST HASH>.
First, read-only, reconcile the current pin, managed state, full desired component set,
new trusted source/provenance, relevant WIP and writer window.
Verify update support in this version; use the existing kit plan/update,
not a new installer. Show the diff/additions/removals/conflicts, backup and rollback.
Record baseline hashes of project-local config/README/entrypoints; do not overwrite
them from a core template. Local adapter incompatibility requires a separate explicit proposal.
Only after the exact plan is approved, update the managed package target and approved
pin metadata; preserve the rest of .ai/project/ and existing local rules/task history.
Verify final hashes, local preservation and repeat NOOP. Concurrent changes
or an unmanaged collision mean BLOCKED; no force/reset/untrack. Return the receipt,
checks, limitations and next action; no product rollout/scans/commit/push.
```

## One file — one role

`skills/` contains originals, not abbreviated portable replacements. `ai-factory/` is the full source plan. `docs/portable/` and `adapters/legacy-planning/` are explicitly separate inherited portable profiles; their behavioral differences are not silently merged. `runtime/legacy/` preserves original helper behavior, while portable review/session helpers have hardened Git reads and an explicit store. Tests for both variants live in `tests/`.

84 internal source definitions accounted for: 73 included, 11 synced sets have an explicit outside-Service copy restriction and remain only in the [provenance inventory](provenance/source-map.json). External symlink targets and `b2b*` are not added. [Origins and notices](PROVENANCE.md).

## Safe use and updates

The [migration guide](docs/migration-0.4.md) explains exact paths, component selection, variants and migration from the old layout. The [installer contract](docs/portability-design.md) retains explicit planning, hash guards, backups and guarded rollback.

```sh
# Source checkout includes an exact, inert research archive; export only release files.
# Choose a new destination outside this checkout. No archive scripts are executed.
EXPORT_DIR="$(python3 -c 'from pathlib import Path; print(Path.cwd().parent / "ai-factory-release-export")')"
python3 -B tools/export_release.py --root "$PWD" --destination "$EXPORT_DIR"
python3 -B "$EXPORT_DIR/tools/verify_release.py" --root "$EXPORT_DIR"
TOOLKIT_DIR="$(python3 -c 'from pathlib import Path; print(Path.cwd().parent / "ai-factory-toolkit-plan-only")')"
python3 -B "$EXPORT_DIR/tools/kit.py" plan --package "$EXPORT_DIR" --root "$TOOLKIT_DIR" --component collection --component planning --component review --component session-guard
```

This example exports, verifies and performs a read-only installer plan; it does not install. The export destination must be new, and the toolkit root must be a separate dedicated directory. For the full regression suite, use `python3 -B "$EXPORT_DIR/tools/run_tests.py" --previous-release /absolute/path/to/verified-previous-release` only after selecting an actual immutable previous release. The placeholder is not a ready-to-run command; do not execute archive scripts.

`collection` is a compatibility component that includes the full skills and explicit legacy helpers; `skills` can be selected separately. `graphify` contains the sole canonical graphify skill, and `skills` depends on it. `planning` adds four **non-discovered adapter documents**, not a new SKILL tree. The installer resolves declared component dependencies and rejects cycles/unknown components; no network/tool installs/host registration.

New installations and upgrades must use a dedicated root, not overlay `~/.agents`, `~/.claude` or a product repo. Supply the full desired component set. Exact-file reading does not prove native discovery; select qualified skill paths. `docs`, `import-memory`, `morning`, `skill-creator` each have two preserved synced versions; do not activate same-name variants simultaneously without explicit mapping.

Product pins and immutable caches are updated through a separate approved rollout; publishing a shared release does not switch them automatically. The [full map of all 350 old files](provenance/layout-migration.json) records moved/deduplicated/revised destinations; no original skill was lost.

## Pre-code readiness

[One checkpoint per task](ai-factory/pre-code-checkpoint.md): acceptance, proportional grilling, dependencies, scoped impact and READY/BLOCKED. Small/resume remain proportional. Optional offline declaration/index validation and regression fixtures are included; no automatic CI or agent enforcement is claimed.

Versioned [plan critic prompt](prompts/plan-critic.md), exact plan/snapshot binding and material-change rules extend that same checkpoint. No extra tracker, native registration or automatic reviewer dispatch.

[Documentation hygiene](ai-factory/documentation-hygiene.md) clarifies the existing onboarding: factual drift, symlink routing, hook/CI coverage and scope provenance. This is a documentation addition; originals and runtime behavior are unchanged.

[Selective constraint adoption](ai-factory/constraint-adoption.md) adds one skill and offline evidence checks, preserving existing Storybook/E2E and reviewer routes. Live model behavior and native discovery remain NOT_TESTED.

## Offline scanner candidate

[Product-neutral scanner baseline](runtime/scanners/README.md) adds an explicit runner, isolated Compose template, original direct-eval rules and a separate DB snapshot updater. Shipped image/DB pins are unresolved and block execution. Author unit/mock checks do not establish real scanner, read-only cache or Yarn dev-dependency acceptance; independent review remains pending. No product rollout or automatic activation.
