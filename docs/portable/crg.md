> Optional retained portable profile; the full canonical plan is in `ai-factory/`. This profile does not replace original skill contracts or authorize automatic activation.

# Optional CRG freshness and recovery

CRG is not required by this kit. No server, graph, registration or binary is bundled. The behavior notes below originated from local CRG 2.3.6 fixtures; they are version-specific limitations, not new-machine PASS. Verify the installed tool schema before querying. Graph queries may write derived database metadata; use an authorized location.

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

