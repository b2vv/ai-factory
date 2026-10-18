# Підключення AI Factory до іншого репозиторію

[Головний вхід](../ai-factory-plan.md) · [Lifecycle](feature-lifecycle.md) · [Джерела істини](workflow.md#source-of-truth)

Мета — додати сумісний маршрут до наявного процесу та перевірити його на реальних для репо сценаріях. Це не гарантія відсутності всіх сюрпризів. Немає автоматичного rollout, installs, permissions, MCP registration/build, hooks, model defaults або зовнішнього запису. Зберігаються стек, архітектура й чинний tracker. Для нового репо відсутні contracts лишаються явно невизначеними; шаблон не вигадує їх.

## Один стартовий запит

> Підключи AI Factory до `<repo-root>` за `~/.agents/ai-factory/onboarding.md`: inventory → manifest → safe preflight → мінімальний additive adapter → acceptance report. Збережи наявні workflow, стек, ADR та required gates. Дозволено документаційний adapter і pointers у межах цього підключення; не змінюй продукт, config/hooks/permissions/models, не запускай installs/dev/CI/deploy/MCP refresh. Перед записом покажи diff, backup/hashguards; повторний запуск має бути NOOP для незміненого adapter. Неясні policy-рішення залиш BLOCKED із власником; заверши незалежним review та свіжим forward-test, відокремивши fixtures від runtime доказів.

Якщо доручено лише аудит, adaptation не виконується. Якщо мінімальні зміни вже явно дозволені, не запитуй повторно дозвіл лише через перехід між цими фазами. Питання власнику потрібне для нової політики, невизначеного scope або реального approval-блокера.

## Startup routing

Перед inventory запиши маршрут потрібних critique/review/verification за [review-handoff](review-handoff.md#перед-початком-роботи): новий субагент чи наявна окрема сесія, owner/reference, поточна підстава вибору та передача. Невизначений вибір уточни до spawn/надсилання, не до безпечної розвідки. Незалежний reviewer отримує pinned package; повторний handoff не створює нового reviewer.

## Швидкий початок

1. Обери точний root; read-only звір HEAD/status, ancestor/nested instructions у scope, чинні work/spec/ADR і власників. Не читай `.env`, credentials або config values. За кількох кандидатів з’ясуй root перед записом.
2. Прочитай [repo-bootstrap](../skills/utils/repo-bootstrap/SKILL.md) у check-only режимі: Codex `$repo-bootstrap`, Claude `/repo-bootstrap`; якщо discovery не підтверджено — прочитай точний файл і назви це fallback. Існування symlink не доводить invocation.
3. Підготуй manifest у робочій теці задачі з [прикладу](onboarding/manifest.example.json). Прибери неактуальні кандидати, вкажи фактичні відносні шляхи репо та лише потрібні скіли. Shared root передається аргументом, не зашитий у код. Запусти вже наявним Python 3.9+:

```sh
python3 /path/to/ai-factory/onboarding/preflight.py \
  --root /path/to/repository \
  --manifest /path/to/task/manifest.json \
  --shared-skill-root /path/to/shared/skills
```

Helper тільки читає явно перелічені файли; JSON результат — stdout. Він не запускає repo commands, MCP, hooks чи discovery. Без Python — ручний checklist, без автоматичної установки. Докладні обмеження й schema — [helper README](onboarding/README.md).

4. Доповни інвентар ручним читанням: повноваження джерел, scripts/prehooks/prerequisites, side effects, semantic conflicts, доступність потрібного незалежного reviewer. Не називай відсутність конфліктів результатом helper: він бачить лише явно внесені `conflicts`.
5. Заверши check-only фазу без записів у target repo; manifest/evidence лишаються у task workspace. В окремій, уже авторизованій adaptation-фазі підготуй additive adapter за [шаблоном](onboarding/adapter-template.md). Existing workflow не замінюється; prewrite hashes/backups і обмежений список файлів захищають конкурентні зміни. У старих входах заміни лише суперечливі твердження/додай pointers; не нашаровуй взаємовиключні правила. Нові обов’язкові gates або їх послаблення мають названого власника й рішення.
6. Незалежний reviewer читає diff і sources; свіжий контекст проходить сценарії нижче. Запиши scope, revision, результати/блокери й обмеження в наявний task record. Тільки тоді називай документальне підключення configured; runtime перевіряється окремо дозволеними діями.

7. Перед acceptance перевір Obsidian за [кроком синхронізації](#obsidian-sync): реальний shared target, актуальність і scope дозволу. Дозволена синхронізація або явно PENDING/fallback фіксується в тому самому report; symlink не є дозволом на запис.

## Checklist адаптації

- [ ] Root/HEAD/dirty scope; applicable instructions; архітектура/стек; місця tasks/spec/ADR/QA/archive визначені без міграції за замовчуванням.
- [ ] Доручення/permissions обмежують scope. Acceptance/contracts/ADR нормативні; код/scripts описують фактичну поведінку. Конфлікт має обидва джерела, рішення власника або BLOCKED залежної роботи. Код не легалізує баг. Уже доручене виправлення до однозначного контракту не потребує нового рішення; воно потрібне лише для неясної/суперечливої норми або її зміни.
- [ ] Один primary record для small: scope/acceptance, plan, append-only progress, verdict/evidence/next step. Незалежний review може бути окремим файлом. Для existing задач не зливати/видаляти артефакти автоматично. Full маршрут лише за ризиком/контрактом, resume — лише інвалідовані gates.
- [ ] Скіли: точний локальний/shared файл, availability/discovery окремо, `$skill` Codex / `/skill` Claude або explicit read fallback. Один оркестратор; не запускати весь inventory.
- [ ] Pattern applicability включає test helpers; entity E2E/scoped filters — matching/nonmatching і поверхні за acceptance; UI-copy оцінюється на layout/zoom/accessible names, open/active стани. Build не доводить UI.
- [ ] Commands знайдені статично; side effects/prehooks/transitive calls оглянуті вручну. Зокрема reset/delete volumes/seed/drain queues/generate/start/install не є read-only probe. Назва `check` не гарантує безпечності.
- [ ] Review справді незалежний; PASS має durable verdict. Helper/Coder/Reviewer — ролі, не автоматичні model bindings. Непідтверджені host/model/effort/budget лишаються unresolved; не міняти defaults.
- [ ] MCP registration, tool availability і graph freshness/coverage окремі. Missing/stale/unknown → файловий fallback; optional CRG не блокує незалежну роботу. Не rebuild/мігрувати graph автоматично.
- [ ] QA/landing/commit/push/deploy межі взято з репо; readiness не розширює доручення. Завершений ідентичний handoff не запускає роботу повторно.

<a id="checks"></a>

## Applicability перевірок

Ця матриця допомагає обґрунтувати набір, але не скасовує явних локальних required gates. Для кожного: джерело вимоги → impact → команда/сценарій та side effects → verdict/evidence. Скорочення required gate лишається BLOCKED до конкретного рішення його власника; пропозиція має назвати економію та втрачений захист.

| Impact | Доречні перевірки | Що не можна припускати |
|---|---|---|
| Docs/process/helper | Links, узгодженість контрактів, fixture/negative tests для helper, незалежний docs/behavior forward-review | Docs автоматично безризикові; fixtures доводять реальний host |
| Test helper/callback | Targeted regression, type/lint/format за контрактом, pattern applicability | Small скасовує mandatory repo gates; RED/GREEN дорівнює mutation |
| Product logic/API/dependency boundary | Affected tests/types, contract/schema/architecture checks; ширші builds/generations за залежностями або required gates | Локальний unit доводить всі backends/builds |
| UI-copy/layout/control | Зачеплені локалі, wrapping/overflow/zoom, keyboard/accessibility за scope, open/active/error стани; фактичний render | Text-only автоматично design N/A; screenshot без перегляду достатній |
| Entity flow/scoped filter | Приймальні сценарії для кожної заявленої surface/type, matching/nonmatching, persistence/read/update за scope | URL/controls/API самі доводять склад списку |
| Mutation потрібна контрактом/ризиком | Окремий mutant, killed/survived результат, чинний diff та команда; відновлення дозволеного scope | Перший RED перед fix — mutation; збій sandbox дає право його обходити |
| Resume без зміни inputs | Звірка completion/revision/evidence, повернути чинний результат | Новий handoff автоматично інвалідує все |

Execution failure: BLOCKED + точна причина або вже дозволений механізм виконання. Немає універсальної вимоги «поза sandbox». Старий PASS не переноситься на змінений scope; незмінний scope не потребує ритуального повтору всіх перевірок, якщо локальний contract не вимагає цього явно.

## Рівні підтвердження

| Рівень | Доказ |
|---|---|
| detected | Файл/команда/опис знайдені; це не runtime availability |
| configured | Adapter, pointers, ownership, paths і відсутність невирішених нормативних конфліктів перевірені; окремо позначити залишкові BLOCKED |
| behavior-tested | Конкретний сценарій виконано на названому host/revision з результатом; fixture, native forward-test і Claude CLI runtime — різні види доказу |
| BLOCKED | Потрібний компонент/рішення/доступ недоступний, названа залежна частина й наступний власник |
| N/A | Можливість не потрібна цьому scope, є причина; недоступний required gate не N/A |

Helper ніколи сам не підвищує detected до configured/behavior-tested. Manifest — input інвентарю, не сертифікат готовності; semantic conflicts, model bindings і actual diff impact потребують людини/агента.

## Перевірка перед повторним використанням

Ізольовані fixtures не змінюють репозиторії:

```sh
cd /path/to/ai-factory/onboarding
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_preflight.py
```

Обов’язкова вибірка для свіжого контексту: clean new repo; existing partial rules; missing shared skill; нормативний контракт проти коду; stale/unavailable CRG; small test-helper; UI-copy зі зміною layout; повтор завершеного handoff. Negative cases: path traversal/symlink/secret input, malformed manifest, config-file ≠ tool availability, empty side-effect indicators ≠ safe command. Forward reviewer отримує запит і raw artifacts, без підказки очікуваного verdict.

Міграція — мінімальний diff + список залишених правил/змінених правил/невирішених рішень, backups і hashguards за [протоколом повтору та restore](onboarding/change-protocol.md). Немає автоматичного rollout до інших проєктів. Реальні Claude/Codex discovery, hooks, MCP, model access, product gates і deploy не покриваються synthetic fixtures; їх перевіряють окремо за дорученням.

## Host-specific acceptance

Для кожного заявленого host/session збережи окремо: (1) readable exact skill file, (2) discovery evidence з датою/джерелом, (3) native tool inventory, (4) invocation result або NOT_TESTED. Відсутність native list/load tool не спростовує вже підтверджений discovery. Перелік із попередньої сесії не гарантує поточний, але зберігається як dated evidence; не замінюй його твердженням «не встановлено».

Required review має точний локальний/shared SKILL.md або задокументований локальний review-контракт і незалежного виконавця. Якщо native command не discovered — явно прочитати цей файл та його references; ті самі scope, pinned diff, acceptance і durable verdict. Відсутній незалежний виконавець/потрібний tool означає BLOCKED відповідного gate. Не створюй глобальний skill для repo-specific review. Helper підтримує SKILL.md route; інший локальний контракт перевіряється вручну й записується в acceptance, без вигаданого native invocation.

Моделі: [provider-independent inventory](models.md); catalog лише цього host/session, entitlement та budget окремо. Немає каталогів → UNBOUND + конкретний next step, не встановлення або платний probe. Optional CRG: config/listing/live query/freshness — різні докази; файли/rg достатні для дозволеної незалежної роботи. Вже завершені proofs використовуються лише в їхньому pinned scope.

Фінальний результат заповнюється за [acceptance template](onboarding/acceptance-template.md). Обов’язкові outputs: inventory+manifest, reviewed diff/receipt/backups, repeat NOOP або явно BLOCKED чужої зміни, незалежний verdict, свіжі сценарії, невирішені owner-рішення й наступна дія. Для partial repo не створюй відсутні tracker/ADR/CI, якщо вони не потрібні погодженому scope. Для нового minimal repo достатньо одного короткого входу/adapter і task record; стек не вигадується.

<a id="obsidian-sync"></a>

## Obsidian: перевірка та погоджена синхронізація

1. Якщо проєкт використовує Obsidian/Shared, знайди фактичний vault і resolved target його Shared-посилання. Перевір target кожного залученого vault; не виводь спільність із назви `4 - Shared`. Якщо target один, canonical нотатка теж одна. Без Obsidian у scope — N/A з причиною, без створення vault/інтеграції.
2. Прочитай лише релевантну workflow/report-нотатку; порівняй з canonical джерелами й поточними результатами. Зафіксуй path, source/revision/date та актуальна/застаріла/відсутня. Наявність symlink або вчорашній sync не доводять актуальності сьогодні, live MCP чи дозволу на запис.
3. Якщо поточне доручення вже дозволяє саме цю синхронізацію, виконай її без повторного запиту. Інакше залиш PENDING: точний target, запропонований мінімальний diff, причина й потрібний scope дозволу. За недоступного каналу — PENDING + repo/task fallback; незалежна дозволена робота триває. Не встановлюй tools/MCP, не змінюй permissions і не створюй automation.
4. За дозволеного запису: canonical target, backup/prewrite hashes, reviewed diff; збережи сторонній текст, не копіюй усі нормативні правила. Онови огляд, pointers, окремі результати проєктів і чесні runtime межі. Той самий shared target записується один раз. Немає змін змісту — NOOP, без штучного нового timestamp/report. Конкурентна правка → BLOCKED запису, не overwrite.
5. Перевір links і visibility через фактичні targets; запиши SYNCED/NOOP/PENDING/BLOCKED/N/A, evidence та fallback/наступну дію у [readiness](onboarding/acceptance-template.md). Filesystem visibility ≠ перевірений Obsidian UI/MCP. Дозвіл на один sync не створює постійного дозволу на наступні записи. Якщо sync required у цьому дорученні й лишився pending — не називай весь scope завершеним.

Це окремий контрольований крок після repository adaptation, а не обов’язкова копія звіту в кожний vault. Канонічні contracts/ADR/evidence залишаються у своїх джерелах; Obsidian — огляд і посилання. Локальний report без цього кроку не видається за повне виконання `ship-report`.
