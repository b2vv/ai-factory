---
name: code-review
description: "Reviews changes since a fixed point (commit, branch, tag or merge-base) along two axes: Standards (does the code meet the repository's documented standards?) and Specification (does the code match what the original issue or spec requested?). Runs both reviews in parallel sub-agents and presents the results side by side. Use when the user wants to review a branch, PR or work-in-progress changes, or says \"review since X\"."
---

Two-axis review of the requested committed, staged, or working-tree changes:

- **Standards**: does the code conform to this repo's documented coding standards?
- **Spec**: does the code faithfully implement the originating issue / spec?

Both axes run as **parallel sub-agents** so they don't pollute each other's context, then this skill aggregates their findings.

## Process

### 1. Pin the fixed point

Pin the requested scope before launching reviewers:

- Branch/PR or review since a ref: resolve the user-supplied commit, branch or tag, capture `git diff <fixed-point>...HEAD` and `git log <fixed-point>..HEAD --oneline`. Ask for the base only if it is needed and cannot be inferred from the request.
- Uncommitted changes: use `git diff HEAD` for tracked staged plus unstaged changes, and `git ls-files --others --exclude-standard` for untracked files. Read relevant untracked files explicitly; they are absent from the diff. Do not stage them just to review them.
- Staged-only review: use `git diff --cached`; exclude unstaged/untracked work.

Record the selected scope and file list once for both reviewers. Validate any required ref and report an empty review only after checking all inputs in that scope. If the request explicitly includes both branch and local changes, include both and label their origin. Do not silently discard local changes because a committed diff is empty.

Also load, when present, the task record's acceptance criteria and the entity-e2e coverage matrix as an INPUT. Check the matrix for freshness (tested revision / diff fingerprint vs the reviewed HEAD) and gaps, and verify coverage independently — the matrix informs the review, it does NOT replace the reviewer's own check or authorize skipping it. Write findings (`file:line` + impact + verification, each marked BLOCKER or non-blocking, including UNRESOLVED) back into the task record's review-handoff package.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. Issue references in the commit messages (`#123`, `Closes #45`, GitLab `!67`, etc.), fetched via the workflow in `docs/agents/issue-tracker.md`. If issue references exist but that file is missing, tell the user to run `/setup-matt-pocock-skills` and continue with the sources below.
2. A path the user passed as an argument.
3. A spec file under `docs/`, `specs/`, or `.scratch/` matching the branch name or feature.
4. If nothing is found, ask the user where the spec is. If they say there isn't one, the **Spec** sub-agent will skip and report "no spec available".

### 3. Identify the standards sources

Read the [repository standards manifest](../../../rules/repo-standards-manifest.md) (`.claude/standards.md`) first when present: it names the repository's standards, constitution and review criteria. Then add anything else in the repo that documents how code should be written, such as `CODING_STANDARDS.md` or `CONTRIBUTING.md`. A missing manifest is not a finding; say which sources you used.

On top of whatever the repo documents, the Standards axis always carries the **smell baseline** below: a fixed set of Fowler code smells (_Refactoring_, ch.3) that applies even when a repo documents nothing. Two rules bind it:

- **The repo overrides.** A documented repo standard always wins; where it endorses something the baseline would flag, suppress the smell.
- **Always a judgement call.** Each smell is a labelled heuristic ("possible Feature Envy"), never a hard violation. Like any standard here, skip anything tooling already enforces.

Each smell reads *what it is* → *how to fix*; match it against the diff:

- **Mysterious Name**: a function, variable, or type whose name doesn't reveal what it does or holds. → rename it; if no honest name comes, the design's murky.
- **Duplicated Code**: the same logic shape appears in more than one hunk or file in the change. → extract the shared shape, call it from both.
- **Feature Envy**: a method that reaches into another object's data more than its own. → move the method onto the data it envies.
- **Data Clumps**: the same few fields or params keep travelling together (a type wanting to be born). → bundle them into one type, pass that.
- **Primitive Obsession**: a primitive or string standing in for a domain concept that deserves its own type. → give the concept its own small type.
- **Repeated Switches**: the same `switch`/`if`-cascade on the same type recurs across the change. → replace with polymorphism, or one map both sites share.
- **Shotgun Surgery**: one logical change forces scattered edits across many files in the diff. → gather what changes together into one module.
- **Divergent Change**: one file or module is edited for several unrelated reasons. → split so each module changes for one reason.
- **Speculative Generality**: abstraction, parameters, or hooks added for needs the spec doesn't have. → delete it; inline back until a real need shows.
- **Message Chains**: long `a.b().c().d()` navigation the caller shouldn't depend on. → hide the walk behind one method on the first object.
- **Middle Man**: a class or function that mostly just delegates onward. → cut it, call the real target direct.
- **Refused Bequest**: a subclass or implementer that ignores or overrides most of what it inherits. → drop the inheritance, use composition.

### 3a. Behavior coverage

Before dispatch, read [behavior coverage](references/behavior-coverage.md) in full, including its **Anti-patterns** section, and the shared [reference anti-patterns](../../../ai-factory/reference-anti-patterns.md) (4-field template + cross-cutting rules). A coverage matrix or green aggregate never substitutes for independent verification at the reviewed HEAD.
For changed guards, filters, serializers and invariants, apply its individual
mutation and CI-running coverage requirements to the pinned scope. Assign one
coordinated runner in an authorized disposable copy; give both reviewers this
reference and the pinned evidence, with Standards assessing test requirements and
Spec assessing whether tests discriminate the requested behavior. Reviewer source
remains read-only. Missing execution evidence stays BLOCKED/NOT_TESTED.

### 3b. Final-review coverage and decisions

Read [final-review coverage and ADR decisions](../../../ai-factory/review-handoff.md#final-review-coverage-and-adr-decisions) before dispatch. Include that contract and the relevant decision sources in both pinned reviewer packages. Standards reports existing-ADR compliance/freshness and new decision-material disposition; Spec checks those decisions against requested behavior and acceptance. Preserve eight coverage questions within these two independent axes, not eight new reviewers. Require explicit evidence or justified N/A for both ADR checks; preserve local drafting/approval timing and do not manufacture an ADR for a trivial change. Aggregation must retain these results and unresolved owners, not hide them behind an overall PASS.

### 4. Spawn both sub-agents in parallel

Give each sub-agent its own working file per [agent stream-to-file](../../../rules/agent-stream-to-file.md) §2 (`agent-review-standards.md`, `agent-review-spec.md`; in a pipeline, the artifact home). Both briefs carry the pinned scope from step 1, the step 3a reference and evidence, and the step 3b contract and decision sources. Every finding uses one line: `file:line` — finding — impact — evidence — `BLOCKER` | `non-blocking` (`UNRESOLVED` when evidence is missing).

**Standards sub-agent prompt** should include:

- The full diff command and commit list.
- The list of standards-source files you found in step 3, **plus the smell baseline from step 3** pasted in full (the sub-agent has no other access to it).
- The brief: "Report, per file/hunk where relevant, (a) every place the diff violates a documented standard: cite the standard (file + the rule); and (b) any baseline smell you spot: name it and quote the hunk. Distinguish hard violations from judgement calls: documented-standard breaches can be hard, but baseline smells are always judgement calls, and a documented repo standard overrides the baseline. Skip anything tooling enforces. Assess test requirements per the behavior-coverage reference and report existing-ADR compliance and new decision-material disposition. One line per finding; no narrative."

**Spec sub-agent prompt** should include:

- The diff command and commit list.
- The path or fetched contents of the spec.
- The brief: "Report: (a) requirements the spec asked for that are missing or partial; (b) behaviour in the diff that wasn't asked for (scope creep); (c) requirements that look implemented but where the implementation looks wrong. (d) whether the tests discriminate the requested behavior, per the behavior-coverage reference, and whether recorded decisions match the requested behavior. Quote the spec line for each finding. One line per finding; no narrative."

If the spec is missing, skip the Spec sub-agent and note this in the final report.

### 5. Aggregate

Count launched against returned axes numerically (`2 launched / N returned`) before aggregating. An axis that returned `null`, empty or a crash is NOT_TESTED, not clean: read its working file first, retry once in a fresh context (same model allowed; tell it to continue from the file when it holds partial findings), and if it is still empty report that axis BLOCKED.

Present the two reports under `## Standards` and `## Spec` headings, verbatim or lightly cleaned. Do **not** merge or rerank findings, because the two axes are deliberately separate (see _Why two axes_).

Include the behavior-coverage inventory/evidence and remaining gaps without merging the two axes.

End with a one-line summary: total findings per axis, and the worst issue _within each axis_ (if any). Don't pick a single winner across axes: that's the reranking the separation exists to prevent.

## Why two axes

A change can pass one axis and fail the other:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the issue asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.

## Dashboard status (only when the project has one)

If the project's managed block (AGENTS.local.md) contains "Dashboard status for this project",
publish the primary task's status after the review verdict is recorded and after your own commit, with the
command named there: first without `--apply`, then with it. Build the status only from the task
record's recorded evidence (stages without evidence stay `Unknown`), with no paths, URLs or secrets.
Report a refusal; do not work around it or retry in a loop.
See [publishing a project's status](../../../docs/dashboard-status.md).
