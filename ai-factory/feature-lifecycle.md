---
title: "Feature lifecycle — маршрут через наявні скіли"
reviewed: 2026-10-16
---

# Від запиту до готовності фічі

[Вхід](../docs/legacy/ai-factory-plan-entry.md) · [Workflow](workflow.md) · [Ролі й ліміти](models.md) · [CRG](crg.md)

Це навігація по чинному процесу, не новий скіл чи оркестратор. Спочатку доручення користувача й застосовні локальні інструкції, потім обраний SKILL.md. Зберігай поточний стек, архітектуру та місце plan/journal. Один артефакт має одного власника; не створюй другий task tracker. Якщо обрано spec-flow, саме він делегує свої етапи: наведені нижче кроки не запускаються вдруге.

Переносиме підключення та manifest — [onboarding.md](onboarding.md). Нормативне acceptance/contracts/ADR відокремлюй від фактичного коду/scripts за [правилом джерел](workflow.md#source-of-truth): код не виправдовує порушення контракту.

## Startup: хто виконує критику, review та перевірки

До роботи запиши у чинний primary record і покажи користувачу: мета → **новий субагент / наявна окрема сесія / НЕ ВИЗНАЧЕНО**, owner, точний session/agent reference якщо відомий, підстава поточного вибору, хто передає пакет, координація shared-resource checks. Явне доручення має пріоритет. Якщо вибір не задано й не можна однозначно вивести з поточного доручення — запитай до spawn/надсилання; незалежні safe inventory/planning дозволені. Не створюй дубль reviewer і не контактуй з іншою сесією без авторизації. Наявна сесія ≠ виконаний review. Авторські checks позначай окремо.

Пакет і verdict — за [review handoff](review-handoff.md): task/session IDs, root/base/HEAD, scoped dirty/untracked hashes та diff, pinned acceptance/contracts, raw evidence/commands/exits, constraints. Reviewer read-only, перевіряє джерела незалежно; тести зі shared side effects потребують координації. Findings: file:line + impact + verification. PASS прив'язаний до snapshot; після змін — пропорційний final-delta review. Missing response/evidence → NOT_TESTED/BLOCKED. Small лишає один primary record, без другого tracker.

## Вибір маршруту

- **Малий:** зрозумілий локальний scope → короткі acceptance → потрібний контекст → один завершений зріз → доречні перевірки → локальне незалежне рев’ю → короткий report/наступний стан. Для small один основний task record містить scope/acceptance, план, append-only перебіг і підсумок; окремі незалежний review та raw evidence — лише за потрібними gates. Не дублюй це в чотирьох документах. План може бути в наявній задачі або повідомленні, якщо репо дозволяє; чинні задачі не мігруй автоматично. Немає обов’язкових нового каталогу, ADR, grilling чи fan-out.
- **Повний:** невизначена поведінка, міжмодульна зміна, дані/міграція, авторизація, зовнішній контракт або складний UI → дослідження → spec/acceptance/plan → потрібний ADR та незалежний плановий gate → реалізація → перевірки → незалежний review → виправлення → report/QA. Спочатку локальний процес; spec-flow лише якщо він обраний і сумісний із ним.
- **Частково налаштований проєкт:** [repo-bootstrap](../skills/utils/repo-bootstrap/SKILL.md), Codex `$repo-bootstrap`, Claude `/repo-bootstrap`, тільки check-only. Результат — прогалини й мінімальна пропозиція. Наявність bootstrap-команд не дозволяє установок або переписування конфігурації.

Ролі — [Helper, Coder, Escalation/reviewer](models.md). Helper збирає докази read-only; Coder веде дозволені зміни й артефакти; reviewer працює в незалежному свіжому контексті. Модельні candidates не означають перевірений runtime-доступ; Claude binding залишається **UNBOUND** до окремої перевірки. Людина-власник приймає продуктові рішення та визначені локальні QA/landing-рішення.

## Як викликати

Нижче пари **Codex CLI / Claude Code**. Спочатку перевір discovery та точний SKILL.md за посиланням; у Codex є також `/skills`. Symlink або файл на диску не доводить discovery. За колізії локальної й глобальної назви явно вкажи шлях і прочитай потрібний файл; це fallback інструкцій, а не доказ успішної slash-команди. Не вигадуй MCP/Agent API; фактична схема й дозволені засоби визначають виконання.

Обраний скіл виконується з його власними gates, а не лише з назвою в журналі. `cto-research` може записувати briefing, `spec-flow` — створювати workflow-артефакти, `ship-report` — дублювати звіт у доступний Obsidian; це не read-only дії Helper і не автоматичний дозвіл на зовнішній запис. Якщо потрібна лише локальна дія, використай чинний локальний контракт і чесно назви це локальним звітом, не повним виконанням іншого скілу.

## Етапи

### 1. Scope й acceptance

- **Вхід / коли:** запит і чинна задача; завжди, глибина за ризиком.
- **Скіли:** за суттєвої невизначеності [grilling](../skills/plan/grilling/SKILL.md) — `$grilling` / `/grilling`; для поведінкової фічі [acceptance-spec](../skills/plan/acceptance-spec/SKILL.md) — `$acceptance-spec` / `/acceptance-spec`. Для очевидної правки достатньо коротких локальних критеріїв.
- **Власник:** Coder формулює, користувач вирішує невідомі продуктові питання.
- **Результат:** межі й non-goals; спостережувані happy/boundary/failure сценарії, спосіб перевірки; причина незастосовності групи. Не вигадуй вимоги з реалізації.
- **Gate → далі:** поведінка достатньо визначена; якщо обрано grilling, його підтвердження спільного розуміння потрібне до дій. Далі 2; невідоме, що змінює результат, — BLOCKED для залежної частини.

### 2. Дослідження та свіжість контексту

- **Вхід / коли:** scope, root/branch/base/HEAD, dirty й untracked; щоразу перевір актуальність, глибоке дослідження лише для невідомого.
- **Скіли:** [cto-research](../skills/plan/cto-research/SKILL.md) — `$cto-research` / `/cto-research`; [crg-explore-codebase](../skills/crg/crg-explore-codebase/SKILL.md) — `$crg-explore-codebase` / `/crg-explore-codebase`, коли граф допоможе. Для багу замість широкої розвідки [crg-debug-issue](../skills/crg/crg-debug-issue/SKILL.md) — `$crg-debug-issue` / `/crg-debug-issue`.
- **Власник:** Helper збирає файли/докази; Coder записує потрібний briefing у чинне місце.
- **Результат:** зачеплені межі, реалізація, ADR, повторне використання, ризики й невідоме з посиланнями.
- **Gate → далі:** за [CRG-контрактом](crg.md) перевір hashes/coverage, а не лише HEAD/час; untracked не гарантовано індексується. За stale/missing graph — файловий пошук і явна межа доказів; нуль impact, особливо Go, не доводить відсутності впливу. Refresh потребує окремого права запису й координації writer; цей маршрут його не запускає автоматично. Далі 3 або малий зріз 6.

### 3. Spec і план

- **Вхід / коли:** acceptance і докази; повний маршрут або локальна вимога. Малий — компактний план у чинному артефакті.
- **Скіли:** [spec-flow](../skills/deliver/spec-flow/SKILL.md) — `$spec-flow` / `/spec-flow`, лише як обраний оркестратор. Він делегує acceptance-spec, [plan-critique](../skills/plan/plan-critique/SKILL.md) — `$plan-critique` / `/plan-critique`, [plan-defense](../skills/plan/plan-defense/SKILL.md) — `$plan-defense` / `/plan-defense`. У локальному процесі окремі лінзи додаються за потребою.
- **Власник:** Coder/локальний власник плану; незалежний reviewer дає gate verdict.
- **Результат:** що/чому, задачі з файлами, залежностями й acceptance IDs, перевірки, side effects, міграція/rollback або обґрунтоване N/A.
- **Gate → далі:** вимоги локального плану; для spec-flow GATE 1 і GATE 2 (critique + defense + конституція) обов’язкові. plan-critique означає всі чотири незалежні лінзи; одна самоперевірка — не його PASS. plan-defense покриває invalid input, dependency failure, race/repeat, boundaries, rollback з доказами в плані. Немає reviewer/mandatory manifest — BLOCKED для відповідного процесу, не прихований bootstrap. Далі 4/5/6 за застосовністю.

### 4. Умовний ADR

- **Вхід / коли:** архітектурне рішення, нова залежність/межа/конвенція, зміна прийнятого рішення; за локальним порогом, не на кожну фічу.
- **Скіли:** окремий ADR-скіл не потрібен; використовуй локальний шаблон і правила. Якщо порогу немає, запропонуй [four-gate критерії](repo-evidence.md#adr-gates), не встановлюй їх мовчки.
- **Власник:** визначений репо автор і reviewer/operator рішення.
- **Результат:** ADR у репо з альтернативами, наслідками, статусом; plan/task посилається на нього. Виправлення факту відділяється від supersession рішення.
- **Gate → далі:** потрібне рішення прийняте за локальними правилами; інакше BLOCKED залежна реалізація. За відсутності тригера N/A з короткою причиною. Далі 5 або 6.

### 5. UI/design

- **Вхід / коли:** змінений екран/контрол/сценарій, референс і локальна система. UI-copy теж оцінюється: довжина/локалізація, wrapping, overflow, zoom, accessible name, open/active стани. Text-only не означає автоматичного design N/A; обсяг proof пропорційний впливу. Без відповідного UI-впливу — N/A з причиною.
- **Скіли:** спершу локальний дизайн-скіл; за потребою [design-pass](../skills/design-pass/SKILL.md) — `$design-pass` / `/design-pass`. Для аудиту [interface-review](../skills/interface-review/SKILL.md) — `$interface-review` / `/interface-review`; у вибраному design-pass це обов’язковий фінальний прохід.
- **Власник:** Coder; reviewer оцінює зібрані фактичні докази.
- **Результат:** план композиції/станів, повторне використання компонентів, критерії desktop/mobile, keyboard/focus, error/recovery, zoom/reflow й reduced motion де застосовно.
- **Gate → далі:** перед кодом визначені локальні обмеження; реалізація й browser proof завершуються через 6–7. Не імпортуй generic стек/тему/шрифт. Без фактичного рендеру/взаємодії UI-gate BLOCKED; build не закриває його.

### 6. Реалізація

- **Вхід / коли:** погоджений scope/план, потрібні рішення, acceptance; для дозволеної реалізації.
- **Скіли:** [tdd](../skills/arch/tdd/SKILL.md) — `$tdd` / `/tdd`, коли обрано TDD або цього вимагає процес. Для ризикового refactor [crg-refactor-safely](../skills/crg/crg-refactor-safely/SKILL.md) — `$crg-refactor-safely` / `/crg-refactor-safely`, лише в дозволеному scope; назва не надає write-MCP permission.
- **Власник:** Coder, з узгодженими межами запису між виконавцями.
- **Результат:** один завершений вертикальний зріз, поведінкові тести й оновлений journal.
- **Gate → далі:** глобальний tdd вимагає погоджених з користувачем seams до написання тестів; не перепитуй те, що вже погоджено. Його цикл — один red → minimal green за раз; refactoring віднесено до review, не масова пачка уявних тестів наперед. Локальний однойменний скіл може мати інший контракт — фіксуй точний шлях. Далі 7.

### 7. Перевірки й browser QA

- **Вхід / коли:** актуальний diff та acceptance; вибери набір за [матрицею applicability](onboarding.md#checks) і явними локальними gates. Зниження обов’язкового gate потребує рішення його власника; small сам по собі не waiver. RED→GREEN доводить відтворення/виправлення дефекту; mutation окремо вносить контрольовану зміну та перевіряє її виявлення тестами, зі своїм evidence. Sandbox failure — BLOCKED або явно дозволений механізм виконання, не універсальний наказ запускати поза sandbox.
- **Скіли:** окремого універсального test-скілу немає; фактичні package scripts/Makefile/CI і локальні правила. UI — завершити design-pass/interface-review, якщо обрано. Для E2E сутностей/QA field findings застосуй [entity-e2e-coverage](../skills/entity-e2e-coverage/SKILL.md) — `$entity-e2e-coverage` / `/entity-e2e-coverage`: baseline QA ID × field × surface/state до тестів; окремі persistence/view/edit/update assertions, без підміни required view через edit. Правила й локальні джерела — у [testing-rules](../skills/entity-e2e-coverage/references/testing-rules.md). Це доповнення чинного acceptance/report, не новий pipeline. Для scoped filters — matching/nonmatching на кожному заявленому entity type × surface; для keyboard acceptance — simulated browser key із UI-effect, не submit dispatch. У design-pass окремо покрий змінені open/active/chips states. Тимчасові корисні regressions зберігай до еквівалентного переносу й targeted run постійного suite за testing-rules.
- **Власник:** Coder запускає дозволені команди; окрема людська QA-роль там, де вимагає репо.
- **Результат:** команда/сценарій, SHA+dirty scope, exit/verdict, доказ; UI — реально переглянуті кадри із viewport та виконані взаємодії, повтор після виправлення.
- **Gate → далі:** всі обов’язкові застосовні перевірки PASS. FAIL → 6; недоступність/недозволена побічна дія → BLOCKED із точним потрібним кроком. Не замінюй skipped CI/E2E зеленим загальним статусом. Далі 8.

### 8. Незалежне рев’ю

- **Вхід / коли:** pin diff/base/HEAD, relevant untracked, контракт і докази; перед готовністю за локальним gate, для ризикової фічі обов’язково.
- **Скіли:** локальне review першим. За обраного глобального [code-review](../skills/arch/code-review/SKILL.md) — `$code-review` / `/code-review` — дві незалежні осі Standards і Spec. [crg-review-changes](../skills/crg/crg-review-changes/SKILL.md) — `$crg-review-changes` / `/crg-review-changes` може дати контекст впливу, не незалежний verdict сам собою.
- **Applicability:** для змін абстракцій, відповідальностей, залежностей або дублювання (включно з test helpers) явно оціни [pattern-architecture-review](../skills/pattern-architecture-review/SKILL.md) — `$pattern-architecture-review` / `/pattern-architecture-review`. У чинному plan/report запиши коротке `applied` з посиланням на доказ або `N/A` з причиною; звичайний docs/typo без такої зміни не потребує цього проходу. Локальне review не є повним еквівалентом спеціалізованих лінз. Збережи локальний precedence; сумісти потрібну оцінку з незалежним review того самого pinned diff або додай лише відсутні лінзи окремим supplement, без повтору вже підтверджених checks/циклу.
- **Власник:** незалежний reviewer у свіжому контексті; автор дає джерела, не підміняє review самоперевіркою.
- **Результат:** сирі findings із file:line, доказом, рівнем впевненості й блокувальністю; окремий verdict за потрібними осями.
- **Gate → далі:** немає відкритих blocking findings; відсутній/порожній reviewer — BLOCKED, не clean review. Spec не вигадувати; відсутність позначити як skipped/BLOCKED залежно від контракту. Далі 9 при findings, інакше 10.

### 9. Виправлення й повторний gate

- **Вхід / коли:** findings; лише коли вони є.
- **Скіли:** [receiving-code-review](../skills/arch/receiving-code-review/SKILL.md) — `$receiving-code-review` / `/receiving-code-review`.
- **Власник:** Coder верифікує й виправляє; reviewer перевіряє закриття.
- **Результат:** кожен finding → виправлення+перевірка або доказова незгода/прийняте рішення власника; без безумовного виконання порад.
- **Gate → далі:** неясні пов’язані findings спершу уточнити за контрактом скілу. Повторити зачеплені 7–8 на новому diff. За [лімітами](models.md): не більше двох безрезультатних fixes одного check без нових доказів; reviewer initial + один fixes pass; null — один повтор. Далі escalation/BLOCKED, а не автоматичний PASS. Зміна scope повертає до 1–3 через власника контракту. Закрито → 10.

### 10. Документація, handoff і readiness for landing

- **Вхід / коли:** перевірений diff або чесний блокер; завершення/пауза сесії.
- **Скіли:** локальний report; за відповідності scope [ship-report](../skills/ship/ship-report/SKILL.md) — `$ship-report` / `/ship-report`. Додатковий [handoff](../skills/ship/handoff/SKILL.md) — `$handoff` / `/handoff` лише за явним запитом: він створює тимчасовий файл поза repo, не замінює durable journal; Claude має `disable-model-invocation: true`.
- **Власник:** Coder веде report; локальний owner/operator/QA приймає наступний стан.
- **Результат:** що змінилося, acceptance verdicts, фактичні checks, відкриті ризики/блокери, рішення/ADR, root/branch/SHA/dirty, наступна дія й власник за [handoff-контрактом](workflow.md#handoff). Не вигадуй acceptance-таблицю заднім числом як нібито попередньо погоджену.
- **Gate → далі:** ready for review/QA/landing названо точно. Це не дозвіл на commit, push, merge чи deploy. Людська QA pending не є done; перенос/архів — лише за локальним порядком. Після landing/post-deploy перевірки виконуються лише за окремим застосовним дорученням.

## Адаптація до трьох репозиторіїв

| Репозиторій | Що зберігати | Особливі gates |
|---|---|---|
| Cassiopeia | [work/README](~/projects/cassiopeia/cassiopeia-admin-ui/work/README.md), локальний UI/ADR і наявні задачі | `qa-test` перед merge; окремий тестувальник-людина, потім merge/deploy й archive. Рев’ю та UI-fit не заміняють QA. Стару суперечливу інструкцію direct archive не використовувати для обходу нового gate; конфлікт, що впливає на задачу, показати власнику. |
| Cargo | [task-workflow](~/projects/cargo/cargotrans-ui/work/rules/task-workflow.md): власник плану, worker journal, read-only reviewer, operator | [локальний review](~/projects/cargo/cargotrans-ui/.claude/skills/review/SKILL.md), `$review` / `/review` лише якщо саме цей скіл discovered; інакше точний файл. Один прохід без fan-out за замовчуванням. [QA-конвенція](~/projects/cargo/cargotrans-ui/work/qa/README.md): tasks → qa після merge → archive після QA. Старий маршрут без QA не закриває цей gate. |
| Courses | [work/tasks.md](~/projects/courses/work/tasks.md), чинні phase plans/reports і незалежні review briefs | Зберегти Go modular monolith і TanStack Start/Rsbuild/React Aria. spec-flow тільки opt-in, без другої системи задач. Pending user QA не перетворюється на done. Важкі команди — за умовами нижче. |

**Courses:** [Makefile](~/projects/courses/Makefile) `make check` (рядок 165) і `make e2e-local` (106) включають `e2e-reset`: зупинка compose та видалення postgres/redis/media volumes, включно з dev-даними того самого compose project (107–128). `drain-queue` (151–156) видаляє media/asr queue keys і вимагає ексклюзивної сесії важких gates. `check-generated` (159–164) спершу генерує файли. Це не read-only smoke test. Перед запуском потрібні чинна явна авторизація з розумінням втрати даних, перевірений compose project і відсутність конкуруючих writers; без цього потрібний gate BLOCKED. Не обходь обов’язковий gate меншою командою й не називай її повним check. У Cassiopeia також перевір side effects pretest:E2E перед запуском; у Cargo skipped E2E не підтверджує browser QA.

## Відновлення з середини

0. Ідентичний handoff за незмінених inputs не відкриває завершену задачу повторно: звір статус і поверни наявний результат. Не приписуй повтор автоматизації без доказів.
1. Прочитай наявний task/plan/journal, останній handoff та сирий review. Знайди власника й точний останній gate; не запускай весь маршрут заново.
2. Звір checkout/root/branch/base/HEAD, staged/unstaged/untracked та зміни після доказів. Не чіпай чужі зміни; узгодь межі запису.
3. Познач інвалідовані gates. Змінився контракт → 1–3; лише fix → 6–9; лише handoff → 10. Застарілий граф → fallback 2, без несанкціонованого rebuild.
4. Запиши одну наступну дію, відповідальну роль і критерій завершення. Збережи застосовні попередні докази; після зміни коду повтори зачеплені checks.

**PASS** — фактично виконаний застосовний gate із доказом. **FAIL** — виконаний, критерій порушено. **BLOCKED** — потрібний gate неможливо виконати через конкретну залежність/доступ/рішення. **N/A** — критерій не застосовується зі зрозумілою причиною; відсутній браузер, reviewer або дозвіл на destructive test не є N/A. Інші незалежні дозволені кроки можна продовжувати, але залежний landing gate залишається відкритим.

Цей документ не свідчить, що фічу, skills, runtime-моделі або gates вже перевірено. Поточний стан можливостей ведеться в [status.md](status.md#capabilities); реальний пілот потребує конкретної задачі.
