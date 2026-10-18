---
name: ponytail-debt
description: >
  Збирає всі коментарі `ponytail:` у репозиторії в один реєстр свідомих спрощень —
  що спрощено, яка в нього стеля і за яким тригером повертатись — щоб відкладене не
  стало вічним. Маркери без тригера позначає `no-trigger`: саме вони тихо гниють.
  Використовуйте, коли треба побачити, що саме відклали й де, перед плануванням чи
  релізом, або на тригери "ponytail debt", "list the shortcuts", "що ми лишили на
  потім", /ponytail-debt. Лише читає й звітує; за запитом кладе реєстр у файл.
---

Every deliberate ponytail shortcut is marked with a `ponytail:` comment naming
its ceiling and upgrade path. This collects them into one ledger so a deferral
can't quietly become permanent.

## Scan

Grep the repo for comment markers, skipping `node_modules`, `.git`, and build
output:

`rg -n --hidden -g '!**/node_modules/**' -g '!**/.git/**' -g '!**/dist/**' -g '!**/build/**' '(#|//) ?ponytail:' .`  (add other comment prefixes if your stack uses them)

Respect repository ignore rules and add exclusions for its other generated output directories. If `rg` is unavailable, use a search tool with the same exclusions.

Each hit is one ledger row. The comment prefix keeps prose that merely mentions
the convention out of the ledger.

## Output

One row per marker, grouped by file:

`<file>:<line>, <what was simplified>. ceiling: <the limit named>. upgrade: <the trigger to revisit>.`

The convention is `ponytail: <ceiling>, <upgrade path>`, so pull the ceiling
and the trigger straight from the comment. Want an owner per row too? add
`git blame -L<line>,<line>`.

Flag the rot risk: any `ponytail:` comment that names no upgrade path or
trigger gets a `no-trigger` tag, those are the ones that silently rot.

End with `<N> markers, <M> with no trigger.` Nothing found: `No ponytail: debt. Clean ledger.`

## Boundaries

Reads and reports only, changes nothing. To persist it, ask and it writes the
ledger to a file (e.g. `PONYTAIL-DEBT.md`). One-shot. "stop ponytail-debt" or
"normal mode" to revert.
