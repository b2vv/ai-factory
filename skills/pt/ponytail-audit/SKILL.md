---
name: ponytail-audit
description: "The same as ponytail-review, but across the entire repository tree rather than the diff: a ranked list of what to delete, simplify or replace with stdlib/native capabilities — largest cut first, ending with `net: -N lines, -M deps possible`. Use for a one-off codebase bloat audit, when asked what can be removed from the repository, where the bloat is or whether it is overcomplicated, or on triggers \"audit for over-engineering\", /ponytail-audit. Lists findings only; makes no edits. Correctness, security and performance are out of scope. Ukrainian compatibility trigger aliases: \"що можна викинути з цього репо\", \"де тут bloat\", \"чи не переускладнено\"."
---

ponytail-review, repo-wide. Scan the whole tree instead of a diff. Rank
findings biggest cut first.

## Tags

Same as ponytail-review:

- `delete:` dead code, unused flexibility, speculative feature. Replacement: nothing.
- `stdlib:` hand-rolled thing the standard library ships. Name the function.
- `native:` dependency or code doing what the platform already does. Name the feature.
- `yagni:` abstraction with one implementation, config nobody sets, layer with one caller.
- `shrink:` same logic, fewer lines. Show the shorter form.

## Hunt

Deps the stdlib or platform already ships, single-implementation interfaces,
factories with one product, wrappers that only delegate, files exporting one
thing, dead flags and config, hand-rolled stdlib.

## Output

One line per finding, ranked: `<tag> <what to cut>. <replacement>. [path]`.
End with `net: -<N> lines, -<M> deps possible.` Nothing to cut: `Lean already. Ship.`

## Boundaries

Scope: over-engineering and complexity only. Correctness bugs, security holes,
and performance are explicitly out of scope. Route them to a normal review
pass. Lists findings, applies nothing. One-shot.
"stop ponytail-audit" or "normal mode" to revert.
