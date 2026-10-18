# AI Factory — адаптер наявного workflow

Цей шаблон заповнюється фактами репо, не встановлює їх за замовчуванням. Невідоме позначити unresolved із власником; видалити неактуальні кандидати. Не копіювати Cargo/персональні шляхи.

| Поле | Фактичний шлях / правило / джерело |
|---|---|
| Root, HEAD, relevant dirty scope | ... |
| Instructions і precedence | ... |
| Нормативні acceptance/contracts/ADR | ... |
| Stack/architecture — зберегти | ... |
| Primary task record; append-only progress | ... |
| Small/full/resume triggers | ... |
| Startup critique/review/verification routing | mode: subagent / existing-session / unresolved; owner; exact reference/pending; current authorization; delivery owner; shared-resource coordination |
| Independent review / evidence / QA / archive | ...; package ID, root/base/HEAD, scoped diff/untracked hashes, pinned acceptance/contracts/evidence; raw reviewer response and final-delta verdict |
| Required gates; applicability source; side effects | ... |
| Local/shared skill paths; invocation/fallback | ... |
| Optional MCP availability/freshness/file fallback | ... |
| Obsidian/Shared canonical target і релевантна note/report | ...; актуальність, поточна авторизація, SYNCED/NOOP/PENDING/BLOCKED/N/A, fallback; без копій на vault |
| Host/session discovery; native tools; invocation | Окремі evidence/status, відсутній list/load не заперечує discovery |
| Required review exact file + references / independent executor | ...; file fallback з тим самим evidence або BLOCKED |
| Helper/Coder/Reviewer actual bindings | UNBOUND; same-host/session catalog, entitlement, budget і next step окремо |
| Canonical adapter path; receipt/backup; repeat | ...; NOOP за точного hash match, conflict → BLOCKED |
| Commit/push/deploy owner й доручення | ... |

Код/scripts показують поточний факт; acceptance/contracts/ADR визначають потрібну поведінку. Конфлікт записується, не вирішується автоматично на користь коду. Scope/permissions користувача мають пріоритет.

Small має один основний record із scope/acceptance, планом, журналом і результатом; окремий незалежний review/evidence лише за потрібними gates. Якщо чинний contract вимагає більше — спочатку конкретне рішення власника. Existing задачі не мігруються автоматично.

Перед викликом потрібного скілу перевір точний файл і discovery: Codex `$name`, Claude `/name`; читання файла — fallback, не invocation proof. Pattern — за structural impact, включно test helpers; entity/scoped-filter proof і UI-copy layout — за acceptance. Один оркестратор, без запуску всіх skills.

## Migration / рішення

| Суперечність або прогалина | Мінімальна additive зміна | Власник/рішення | Перевірка та статус |
|---|---|---|---|
| ... | ... | unresolved | BLOCKED залежна частина |

Зниження required gate: назвати зекономлений час і втрачений захист, посилання на рішення; без нього gate зберігається. RED/GREEN — bug proof, mutation має окремий evidence. Заблоковане виконання — BLOCKED або дозволений механізм, без обходу sandbox.

## Приймання підключення

Record містить detected/configured/behavior-tested окремо, source/revision/result для перевірок; N/A із причиною; незалежний review, forward scenarios і наступну дію. Config/symlink не доводять runtime. Немає автоматичних installs/registrations/hooks/permissions/models або rollout.

Перед записом і відновленням застосуй [change protocol](../ai-factory/onboarding/change-protocol.md) у shared onboarding; у скопійованому adapter заміни це посилання фактичним shared path або виклади необхідні правила тут. Підсумок — за [acceptance template](acceptance-full.md), у наявному task record. Власник adapter не стає власником source contracts; не копіюй нормативні таблиці без потреби, посилайся на них.
