---
name: ponytail-audit
description: >
  Те саме, що ponytail-review, але по всьому дереву репозиторію, а не по дифу:
  ранжований список того, що видалити, спростити чи замінити на stdlib/нативне —
  найбільший різ першим, у кінці `net: -N lines, -M deps possible`.
  Використовуйте, коли треба разовий аудит кодової бази на роздутість, коли питають
  "що можна викинути з цього репо", "де тут bloat", "чи не переускладнено", або на
  тригери "audit for over-engineering", /ponytail-audit. Лише перелічує, правок не
  вносить; коректність, безпека й продуктивність — поза скоупом.
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
