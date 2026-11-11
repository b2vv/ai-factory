# AI Factory

AI Factory is a shared toolkit for developing software with AI coding agents. It
combines reusable skills, a task workflow and local helpers so an agent can take a
request from understanding and planning through implementation, testing and review,
then leave enough evidence and context for the next session to continue.

Use it with an existing agent such as Codex or Claude Code. Factory does not replace
the agent, supply a model, or build an application on its own. The agent follows the
workflow; scripts automate specific checks and operations. Your project's rules and
the task you approved remain in charge.

## What it helps you do

| Need | What Factory provides |
|---|---|
| Understand a repository before changing it | Read-only onboarding, project research and explicit routing to local instructions, architecture and tools |
| Keep tasks aligned with the product direction | A task-readiness checkpoint and continuation rules that reconcile the existing task index, roadmap, decisions and delivered work |
| Implement and verify a change | Planning, acceptance criteria, TDD and code-review skills, language-specific references, independent review and evidence-bound completion |
| Improve a web interface | `design-pass` coordinates existing design, UX, interface and measurement skills; it checks rendered states and interactions, not just a successful build |
| Continue after a session gets too large | File-based task records, plus optional native checkpoint/resume with an explicit ID and repository-state validation |
| Find earlier conversations and decisions | An optional local archive with project-scoped capture and search, source references and locally generated session excerpts |
| Keep several projects on one toolkit | A managed kit, shared global skill discovery, project-local connection files and guarded update/rollback tools |

The core workflow is useful without the archive, Docker or a graph server. Scanners,
archive storage, capture hooks and native handoff are optional components with
separate setup and verification.

## How a task moves through Factory

1. **Read the project context.** Load its instructions, existing task record,
   accepted decisions and relevant code. Use its own work protocol rather than
   adding a competing one.
2. **Agree on the change.** Identify scope, acceptance criteria, dependencies and
   what needs independent review. A small edit stays small; risky changes need a
   fuller plan. Record READY or the specific blocker before dependent work.
3. **Implement and check.** Select the relevant skills, make the change, run the
   applicable tests and inspect real UI behavior when the task affects UI.
4. **Review and finish.** Bind findings and test results to the actual changed
   files. Fix findings, recheck affected behavior and report what passed, failed or
   remains untested. Commit, publication and deployment follow the task's authority.
5. **Leave a usable continuation.** Update the existing task record with decisions,
   evidence and the next action. If the product direction changes, reconcile old
   tasks before resuming them; a new session does not automatically restart a queue.

For example, a request to improve a table should first identify its existing UI
contract and acceptance criteria. `design-pass` then covers empty and populated
states, disabled and enabled controls, interaction and measurements. The result is
a checked change and a report, not merely a new screenshot.

See the [workflow](ai-factory/workflow.md), [feature lifecycle](ai-factory/feature-lifecycle.md)
and [task continuation contract](ai-factory/task-continuation.md) for the full rules.

## How projects connect

The current shared setup has three distinct layers:

```text
Factory source repository
    -> verified release package -> one installed managed kit
                                      |
                                      +-> global agent skill discovery
                                      +-> project A: AGENTS.local.md + local adapter
                                      +-> project B: AGENTS.local.md + local adapter
```

- **Source repository:** where Factory itself is developed. A source edit or Git
  push does not update the installed kit or activate anything in a product.
- **Managed kit:** one dedicated installation containing the selected shared
  components. Global skill discovery points here, not at a development checkout.
- **Project connection:** `AGENTS.local.md` points to that kit and preserves local
  workflow, task navigation and search routing; `CLAUDE.local.md` may import it.
  Existing root `AGENTS.md` remains the project's own contract. Do not copy shared
  skills or add per-project shared-skill symlinks.

**Update the kit once, then verify its consumers.** Use the normal reviewed
`kit.py` update with the complete desired component set, backup and rollback.
Reconcile project identity metadata where needed, preserving local adapters and
rules. Projects use the stable installed path; hashes and receipts verify the bytes
rather than requiring a separate checkout per project. This is not an automatic
pull of remote `main`. Already-open sessions may need to reread instructions or
restart at a safe boundary.

Start with [managed kit connections](docs/managed-kit-connections.md) for the current
installation/update contract. It supersedes historical per-project snapshot layout
recommendations. The installer does not clean old project wiring, register hooks or
prove that the agent actually invoked a skill.

## Optional archive and session continuity

These solve different problems:

- **Task record:** the project's existing plan/journal holds decisions, progress,
  checks and the next action. It is the normal continuation route.
- **Native handoff:** the [non-Docker runtime](docs/managed-native-handoff.md) stores
  a bounded checkpoint and validates the exact ID and repository snapshot on resume.
  It requires explicit registration; it does not launch a new model session.
- **Conversation archive:** the [storage service](runtime/storage/TAKEOVER-CONTRACT.md)
  stores original records in MongoDB. PostgreSQL supplies a derived search index;
  it is not the authority for archived conversation text. Capture and search use
  separate project-scoped access. The optional
  [search client](runtime/storage/deploy/search-client/README.md) handles bounded
  cursor traversal; an empty page is not necessarily the end of results.
- **Session excerpts:** the [summary worker](runtime/storage/SESSION-SUMMARIES.md)
  can create derived records in MongoDB and index them for search. Its default
  scheduling is 30 minutes from the first uncovered message or 15 minutes of idle
  time, whichever occurs first. It selects local excerpts, not LLM-written semantic
  summaries, and retains source provenance. Activation is separate from installation;
  a summary does not prove that capture contains the complete original conversation.

See [runtime helpers](runtime/README.md) for exact entry points and limits.

## Where to start

| Goal | Read this |
|---|---|
| Connect an existing project or set up another machine | [AI-assisted onboarding](docs/guides/ai-assisted-onboarding.md), then [managed kit connections](docs/managed-kit-connections.md) |
| Choose the workflow for a task | [Factory entry point](ai-factory/ai-factory-plan.md) and [workflow](ai-factory/workflow.md) |
| Find a skill | [Canonical skills tree](skills/) and [skill routing map](ai-factory/workflow.md#skill-map) |
| Understand checks before implementation | [Pre-code readiness](ai-factory/pre-code-checkpoint.md) |
| Set up independent review | [Review handoff](ai-factory/review-handoff.md) |
| Install, update or roll back the kit | [Installer contract](docs/portability-design.md) and [managed connections](docs/managed-kit-connections.md) |
| Run optional security checks | [Scanner contract and limits](runtime/scanners/README.md) |
| Check recorded capability evidence | [Dated capability registry](ai-factory/status.md#capabilities); source presence, installation and live verification are different |
| Trace history and licensing | [Provenance and notices](PROVENANCE.md), [release notes](docs/release-0.8.0-alpha.1.md) and [layout migration](docs/migration-0.4.md) |

## Scope and requirements

Factory is experimental. The storage alpha still has incomplete whole-system
acceptance and operational limits, including no automatic WAL reclaim; see its
[contract](runtime/storage/TAKEOVER-CONTRACT.md). Tests and reviews of a particular
feature do not certify every component or every consumer project.

Offline kit helpers require Python 3.9+ and a POSIX filesystem; some helpers also
require Git. macOS is the documented verification environment; Windows is
unsupported. Storage uses Go, MongoDB and PostgreSQL; optional scanner/container
work has its own requirements. Factory does not install model access, project
language toolchains or MCP servers. Native discovery, hook delivery and actual
model behavior need verification in the intended host.

The [release manifest](release-manifest.json) identifies the package contents and
components. Preserve source notices and review provenance before reuse. Checksums
verify integrity, not authorship or permission to redistribute. Never place local
credentials, host routes, private task evidence or session data in a portable
release.
