# Startup routing та передача на незалежний review

Цей контракт доповнює чинний workflow, не створює ще одного tracker або оркестратора. Small зберігає один primary task record; поля нижче вставляються в нього. Evidence bundle — похідний snapshot для перевірки, не другий план. Локальні standards, gates та owner-рішення зберігаються.

## Перед початком роботи

Сесія записує й показує користувачу для кожної потрібної критики/review/verification:

> Перевірки/критика/review: `<мета>` → `<новий субагент | наявна окрема сесія | НЕ ВИЗНАЧЕНО>`; власник `<ім’я/роль>`; session/agent reference `<точний ID або pending>`; підстава вибору `<поточне доручення/відповідь користувача>`; хто передає пакет `<власник>`; доступ до спільного стенда `<не потрібен | узгоджений слот/власник | BLOCKED>`.

Явний вибір користувача має пріоритет. Якщо маршрут однозначно заданий поточним дорученням — зафіксуй його без повторного питання. Інакше запитай **до spawn або надсилання**: «Для `<мета>` запускати нового субагента чи використати окрему наявну сесію? Якщо наявну — яка точна назва/ID і хто передає пакет?» Без відповіді маршрут лишається НЕ ВИЗНАЧЕНО; незалежні safe inventory/planning можуть тривати. Не підставляй субагента за таймаутом. Наявність сесії не є виконаним review.

Для `новий субагент` після дозволеного spawn допиши отриманий ID у той самий record; для `наявна сесія` не вгадуй ID за схожою назвою. Дозвіл вибрати спосіб не означає автоматичний дозвіл надсилати повідомлення іншій сесії: потрібне явне доручення на передачу або її виконує користувач. Не створюй дубль reviewer, якщо він уже призначений; не дублюй handoff через повторний запит. Звичайні авторські перевірки позначай окремо як author checks, не як незалежний review.

## Пакет передачі

Мінімальний self-contained package у наявному evidence-місці:

- task ID, author session ID, обраний маршрут/власник/reviewer reference та статус передачі `prepared/delivered/responded` у primary record;
- точний repo/root, branch, resolved base commit, HEAD; явний file scope із tracked dirty та relevant untracked, SHA-256 поточних і базових bytes, точний diff;
- acceptance та relevant contracts: точний шлях + SHA-256 + snapshot копія потрібного документа (або самодостатній витяг із provenance); не лише переказ автора;
- evidence: команда/сценарій, exit code, PASS/FAIL/BLOCKED/NOT_TESTED/N/A, scope/revision, сирий artifact/hash, limitation; непрогнане не стає PASS;
- constraints, non-goals, дозволи, ресурсні обмеження, unresolved decisions, наступний власник.

Не копіюй .env/credentials/config secrets, transcript або повні нерелевантні логи. За неможливості безпечно передати джерело — назви відсутній доказ і BLOCKED залежний gate. Для external shared документації використовуй явні paths; для коду scope не розширюється автоматично.

Одна пара `package ID + призначений reviewer reference` має один handoff у чинному record. Повтор того самого пакета — NOOP, а не нове повідомлення чи spawn. Helper нічого не надсилає й не керує сесіями.

## Контракт reviewer

Reviewer працює незалежно: сам читає pinned acceptance/contracts, diff і source snapshots, звіряє живий root/snapshot до та після перевірки, оцінює достатність scope й relevant untracked. Summary автора — лише навігація. Read-only за замовчуванням: source/config/index не змінює. Локальний дозволений review artifact можна записати лише у визначене evidence-місце. Потреба тесту не дозволяє reset/seed/install або доступ до спільного стенда; спочатку узгодити операцію, власника, слот і side effects. Окремо позначити власні checks та прийняті pinned raw evidence автора.

Кожен finding: `file:line`, конкретний наслідок, доказ/спосіб відтворення чи перевірки, blocking/nonblocking, confidence. Verdict: reviewer reference, package/snapshot ID, checked scope/axes, findings, checks/evidence й limitation. Відсутня/порожня/незавершена відповідь означає **review NOT_TESTED, required gate BLOCKED**. Автор не видає self-review за незалежний PASS. Структурна валідація helper не доводить незалежності людини/агента чи істинності її декларацій.

## Зміни після review

PASS стосується тільки перевіреного snapshot/scope. Після виправлень сформуй final delta до reviewed snapshot; reviewer визначає зачеплені criteria/checks та дає verdict на фінальний package ID. Unchanged evidence можна явно прийняти, якщо inputs не змінилися. Не повторюй весь gate для нерелевантної правки, якщо локальний контракт цього не вимагає. Не перенось старий PASS на змінені acceptance/diff/untracked. Зміна base/HEAD потребує звірки provenance, а не автоматичного повтору всіх тестів. Розширений/звужений scope reviewer підтверджує окремо; нові релевантні файли мають бути включені.

## Опційний stdlib helper

[review_package.py](../review/review_package.py) працює на Git repo з HEAD, UTF-8 текстовими файлами: максимум 100 scope files, 1 MB/file, 8 MB унікальних blobs. Не запускає repo commands/tests/CLI/MCP; лише read-only Git queries. Немає install, network, dispatch, hooks або permission changes. Symlink paths, секретоподібні назви/вміст і конфігурації відхиляються; це defense in depth, не універсальний secret scanner. Використовуй canonical paths (на macOS `/private/...` замість symlink `/tmp` для fixture).

```sh
python3 "$KIT"/review/review_package.py route manifest.json
python3 "$KIT"/review/review_package.py capture manifest.json /absolute/existing-evidence/review
python3 "$KIT"/review/review_package.py assess /absolute/package-ID --response response.json
python3 "$KIT"/review/review_package.py delta /absolute/old-ID /absolute/new-ID
```

[Manifest приклад](../review/manifest.example.json) і [response приклад](../review/response.example.json) — форми, не готові approvals чи PASS. Заміни paths/IDs і declarations фактичними. Пакет містить `package.json` та `objects/<SHA256>`; відкрий diff blob і source/reference blobs за manifest. Metadata/package ID й кожен blob перевіряються при load; повтор capture незміненого scope — той самий ID/NOOP. Два проходи collection відхиляють спостережені конкурентні правки; вони не блокують writer після capture, тому freshness перевіряється повторно перед verdict/застосуванням. Snapshot — explicit file scope, не повний repo audit; ignored/out-of-scope файли не охоплено автоматично. Нерелевантні зміни поза scope не інвалідують його.

`assess` перевіряє цілісність, current scope/reference/evidence hashes, маршрут, response identity/coverage та required check declarations. Це **структурний статус**, не створений інструментом review. Порожній response, missing evidence, чужий reviewer або stale package блокуються. Непідтримуваний формат — ручний еквівалент з тими самими полями й чесним NOT_TESTED, не встановлення нових tools.

Тести: `python3 -B "$KIT"/review/test_review_package.py`; усі Git fixtures disposable. Живі чужі сесії/CLI/стенд не використовуються для симуляції.
