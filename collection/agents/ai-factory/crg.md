---
title: "CRG: перевірка контексту й межі інтеграції"
reviewed: 2026-10-16
---

[Вхід](../ai-factory-plan.md) · [Workflow](workflow.md) · [Ролі](models.md)

# Code Review Graph

Локально встановлено `tirth8205/code-review-graph` 2.3.6 через pipx; executable `~/.local/bin/code-review-graph`. [Upstream](https://github.com/tirth8205/code-review-graph). Чотири скіли живуть у `~/.agents/skills/crg/*/SKILL.md`; Claude mirror не гарантує host discovery. CRG — структурний контекст, не compiler, runtime trace або незалежний reviewer.

## Перевірений transport і schema

2026-10-16 UTC: `code-review-graph serve --repo <absolute-root>` через стандартний MCP stdio успішно проходить initialize/tools/list; повертає 30 tools. Після повідомлення власника про оновлення повторно перевірено executable/package metadata і новий stdio subprocess: локальна версія все ще 2.3.6, schema та fixture-регресії незмінні. Пакет не оновлювався цією задачею. Без `--auto-watch`, HTTP, embeddings, інсталяцій і нових credentials. Host prefix може відрізнятися; використовуй фактичний tools/list, не короткі `next_tool_suggestions` із відповіді сервера.

Важливі аргументи 2.3.6:

| Tool | Що передавати |
|---|---|
| `get_minimal_context_tool` | `task`, `repo_root`, `base`, за потреби `changed_files`; **без** `detail_level` |
| `query_graph_tool` | `pattern`, `target`, `repo_root`, `detail_level` |
| `get_impact_radius_tool` | `changed_files`, `repo_root`, `base`, `max_depth`, `detail_level` |
| `detect_changes_tool` | `base`, `changed_files`, `repo_root`, `include_source=false`, `detail_level`; **не оновлює граф** |
| `list_graph_stats_tool` | `repo_root`; **без** `detail_level` |
| `get_affected_flows_tool` | `changed_files`, `base`, `repo_root`; **без** `detail_level` |
| `get_flow_tool` | `flow_id` або `flow_name`, `include_source=false`, `repo_root`; **без** `detail_level` |
| `refactor_tool` | `mode`; для rename — `old_name`, `new_name`; `repo_root`; **без** `detail_level` |

Негативний fixture-тест підтвердив: зайвий `detail_level` у minimal-context відхиляється validation error. Не додавати його механічно до всіх tools.

## Freshness перед довірою

1. Записати absolute root, branch, HEAD, scope diff і релевантні untracked. Передавати `repo_root` явно у кожен repo-scoped tool. Для dirty scope використовувати перевірений `base="HEAD"`; для PR — його реальну базу, не випадковий `HEAD~1`.
2. Звірити metadata graph (`git_branch`, `git_head_sha`, `last_updated`, `postprocess_level`) та hashes поточних scope-файлів. Сам збіг HEAD/дати не достатній: граф може містити старі/видалені файли й пропускати інші.
3. Звірити coverage: чи є потрібні файли/символи; окремо untracked, generated, ignored, unsupported languages, dynamic/framework entrypoints. Кількість файлів — лише сигнал, не відсоток семантичної коректності.
4. Підтвердити принаймні один релевантний import/caller і його file:line на диску. Graph edge/impact/flow — кандидат; порожній результат на неповному графі означає BLOCKED для висновку, не «безпечний код».

Fixture 2.3.6 показав: до update старий caller повертається без freshness warning; incremental update не включає новий untracked rename target; навіть full build на Git-репо пропускає untracked. Після staging **лише у синтетичному fixture** update знайшов нову функцію та її impact. Не stage користувацькі файли заради індексації. Для untracked scope — пряме читання/тести або окремо погоджений refresh, який явно включає ці файли.

## Відновлення без зміни source

Збережи узгоджену SQLite backup перед оновленням; для WAL використовуй SQLite backup API/узгоджений checkpoint, не копію одного `graph.db` під час запису. Не використовуй `immutable=1` при живому WAL/journal; read-only inventory без WAL потребує перевірки стабільності файла під час читання.

Оглянута реалізація `build_or_update_graph_tool` 2.3.6 виконує локальний parse, SQLite, FTS/flows/communities, не embeddings/API. `full_rebuild=true, postprocess="full", recurse_submodules=false` доречне лише після авторизації, backup і перевірки списку source-кандидатів. Не читати .env/credentials; не запускати install/init/watch/wiki/embed. Не змінювати `.gitignore`, git index, security controls або registry як побічний «ремонт».

Після refresh повторити root/revision/hash/coverage і релевантні query proofs; зберегти counts/errors/limitations. Один цільовий recovery і одна повторна перевірка; повторна невдача → BLOCKED + file-based fallback. Якщо робоче дерево активно змінюється іншою сесією, не називати перевірку стабільним snapshot.

## Host discovery: стан перевірки

- 2026-10-16, після явного дозволу власника: Codex user config має `crg-courses-read`, `crg-cassiopeia-read`, `crg-cargo-read`; CLI parser показує enabled для всіх трьох. Claude local config Cargo має `crg-cargo-read`, `claude mcp get` підтвердив Connected. Попередні Claude Courses/Cassiopeia registrations не змінювалися.
- Для кожного нового запису свіжий stdio subprocess із фактичних config args повернув **рівно 12** погоджених tools; прямий виклик видаленого `build_or_update_graph_tool` відхилено як Unknown tool. Enforcement серверний: `serve --tools` видаляє решту з FastMCP registry, а не лише приховує опис. Дозволено: `get_minimal_context_tool`, `list_graph_stats_tool`, `query_graph_tool`, `get_impact_radius_tool`, `detect_changes_tool`, `get_affected_flows_tool`, `list_flows_tool`, `get_flow_tool`, `list_communities_tool`, `get_community_tool`, `get_architecture_overview_tool`, `find_large_functions_tool`.
- Нові записи не запускають watch, build, embed чи refactor/apply. `--repo` задає default root, а не filesystem isolation: `repo_root` можна перевизначити. Codex записи user-level, доступні не тільки з відповідного cwd; назви фіксують призначення. Query tools можуть відкривати/мігрувати похідну SQLite БД — це не OS read-only sandbox. Перевірка registration виконала лише initialize/list і відхилений виклик на ізольованому fixture, без query/rebuild активних графів.
- Чинні host-сесії можуть потребувати нового запуску/перезавантаження MCP discovery; новий модельний turn із цими tools не тестувався. Докази: `crg-allowlist-preflight.json`, `crg-allowlist-postflight.json`, `crg-registration-applied.json` у робочій папці задачі. Config backups із режимом 0600: `mcp-config-backups/20261016T234627Z/`. Unrelated config values, credentials, model defaults і решта дозволів збережені.

## Історичні обмеження доказів (2026-10-16)

Поточний стислий стан ведеться у [status.md](status.md#capabilities). Під час роботи оригінальні HEAD/graphs змінювалися іншими сесіями, тому активні БД не підмінялися. Тодішній inventory (не поточний стан): Courses metadata вже оновлено зовнішньою роботою до c2970173, але current HEAD 8019b64d; graph лише 166 files, з них 124 hash mismatch. Cargo graph тоді був 2026-08-22/beta проти stage; 556 mismatch і 17 видалених entries. Cassiopeia зі збігом HEAD має 281 mismatch і 93 видалених entries. Час/HEAD самі не доводять freshness.

Після зняття approval-блокера створено валідні backups усіх трьох derived DB без WAL: SHA-256 source/copy збігається, metadata size/mtime стабільні, SQLite quick_check=ok. Початкова спроба SQLite backup API завершилася помилкою; її порожній файл не є backup. Для rebuild створено ізольовані source snapshots із перевіркою hashes/HEAD/status до/після копіювання, не копіюючи .env/credentials і не змінюючи user git index. Cargo snapshot включає 13 оригінально untracked source files. Snapshot graph roots навмисно інші; це тест відновлення, не deployed active graph.

На snapshots: full structural builds Courses 932, Cargo 1211, Cassiopeia 4888 parseable files; parse errors/warnings відсутні. TS samples Cargo (`appNavigate → getAppRouter`) і Cassiopeia (`AppBootstrapProvider → InitStatusMessage`) підтвердили callers/imports/impact. Courses Go `CanConsume`: callers_of знаходить 6 callers і imports_of показує access dependency, але impact повертає 0 додаткових файлів попри ці залежності. Це підтверджений false-negative конкретного impact query, який не виправляється самим rebuild; для Go impact потрібен прямий пошук і language/test evidence. Не переносити PASS TS-вибірки на всю семантику TS/Go.

Exact counts/revisions, backups і raw proofs: `~/Documents/Codex/2026-10-16/task/` (`crg-readonly-inventory.json`, `crg-stable-backups.json`, `crg-source-snapshots.json`, `snapshot-*-result.json`, `proof-*-result.json`, `crg-recheck-summary.json`, `crg-tools-schema.json`). Для активного графа потрібне окреме погоджене вікно без конкурентного writer і повторний freshness/query check; не копіювати snapshot DB поверх active DB, бо root paths відрізняються.

<a id="cargo-active-snapshot"></a>

## Cargo: завершений active refresh — snapshot 2026-10-17

Цей запис замінює попередній stale-статус **лише Cargo**. Root `~/projects/cargo/cargotrans-ui`, branch `stage`, HEAD `137e19df20b32f8a33f76c5a08090c2f8ef0c3bf`. Авторизований refresh завершено; source snapshot і git index лишилися незмінними. Persisted graph: **1212 files, 6882 nodes, 65619 edges**; 1212 hash matches, **0 mismatch, 0 deleted, 0 foreign roots**, SQLite integrity OK; parse errors/warnings відсутні. Consistent SQLite backup збережено до refresh.

Через чинну незмінену `crg-cargo-read` registration у свіжому stdio MCP процесі: initialize/tools/list — 12 tools; **live stats і callers_of PASS**. `appNavigate → getAppRouter` підтверджено також прямим читанням файла. Це більше за простий listing; водночас цей proof не підтверджує injected tools у кожній поточній Codex/Claude сесії. Не перезапускати refresh через відсутність native list/load у новому чаті.

Докази: [завершений звіт](~/Documents/Codex/2026-10-16/task/crg-cargo-active-refresh/report.md), [snapshot state](~/Documents/Codex/2026-10-16/task/crg-cargo-active-refresh/final-state.json), [MCP queries](~/Documents/Codex/2026-10-16/task/crg-cargo-active-refresh/mcp-query-proof.json). Це локальні історичні artifacts цього host, не залежності підключення іншого репо.

Межі: snapshot не гарантує freshness після змін; tracked/parser coverage не доводить dynamic calls або повноту семантики. На цьому snapshot parseable untracked exclusions не знайдено, але майбутні untracked потребують прямого читання. Інші графи цим refresh не змінювалися. Для іншого репо CRG необов’язковий: окремо registration → tool listing → live query → root/HEAD/hashes/coverage; missing/stale → files/rg. Refresh лише за окремою авторизацією й погодженим вікном без конкурентного writer.
