# Language review and testing references

These optional references refine a task's language-specific questions. They add no
new skill, approval authority, loader, tool installation or default framework.
The existing [TDD workflow](../../../tdd/SKILL.md), [code review](../../SKILL.md),
[behavior evidence](../behavior-coverage.md) and [Factory workflow](../../../../../ai-factory/workflow.md)
remain authoritative. Put selected paths, applicability, versions, observations and
unverified checks in the existing task record; do not create a parallel checklist.

## Select only relevant material

Use the requested task, touched files and actual project manifest/configuration.
An installed language elsewhere in a repository does not make it relevant here.
Unknown language means UNKNOWN; do not guess. A known language with an unknown
version permits generic review questions, but version-specific APIs and commands
remain UNKNOWN until verified. Inspect existing lockfiles, runner configuration
and accepted project conventions before choosing tooling. Do not install tools or
change lint/compiler settings merely to follow a reference.

Normally read this index, one language, and zero or one applicable framework.
For a cross-language boundary, justify the extra reads and test each side of the
same contract. Links are navigation, not instructions to load every document.
File budgets are 8 KiB for this index, 12 KiB per language and 10 KiB per framework;
these are byte limits, not measured host token or compliance guarantees.

| Task evidence | Reference | Optional framework / limitation |
|---|---|---|
| TypeScript or TSX | [TypeScript](typescript.md) | [React](frameworks/react.md) only with React + TS/TSX evidence |
| PHP | [PHP](php.md) | [Laravel](frameworks/laravel.md) only when confirmed; plain PHP/Symfony do not select it |
| Python | [Python](python.md) | [Django](frameworks/django.md) or [FastAPI](frameworks/fastapi.md) only when confirmed |
| Rust | [Rust](rust.md) | No artificial framework requirement |
| Go | [Go](go.md) | No artificial framework requirement |
| Unknown language | No language selection | Record UNKNOWN; resolve the missing evidence |

React alone does not imply TypeScript; React JS-only is outside this TS reference
scope. Unknown Python framework selects neither Django nor FastAPI. Mixed Go API
and TS consumer changes select Go and TS at the touched boundary. Other frameworks
are deferred; retain their accepted project rules instead of extrapolating Laravel,
Django or React conventions.

## Evidence and host limits

Claude and Codex may explicitly read these same files through their established
project workflow. Other agents may use explicit file reading when supported by
their local host. No new host configuration or native projection is supplied.
Native discovery/invocation and actual model selection behavior are NOT_TESTED;
local structural checks establish file closure and provenance only.

References specify test obligations, not executed language recipes. Map each
obligation to existing, version-compatible commands and record actual results.
Missing tools, compiler runs, browser or database checks stay NOT_TESTED. Formatting
alone is not linting, typechecking, contract verification or behavior evidence.
No automatic network access, model call, migration, cache rebuild, dependency
installation or global configuration change follows from selecting a reference.

## Sources and project precedence

These are owner-authored guidance informed by a pinned ECC source audit and the
user-designated Cassiopeia TypeScript rules. Exact conceptual sources and digests
are in [origins](../../../../../provenance/language-reference-origins.json).
No upstream executable recipes or product code were copied. Current accepted
project contracts decide project conventions. The TypeScript reference explicitly
documents the historical Factory Pocock rule conflict; opening the old rule alone
does not expose that correction.
