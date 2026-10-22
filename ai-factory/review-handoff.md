> Runtime examples below use `$KIT` as an explicitly selected absolute root of this release; `$PREVIOUS_RELEASE` is the immutable prior release when testing upgrades. This path update does not activate or change helper behavior.

# Startup routing та передача на незалежний review

Цей контракт доповнює чинний workflow, не створює ще одного tracker або оркестратора. Small зберігає один primary task record; поля нижче вставляються в нього. Evidence bundle — похідний snapshot для перевірки, не другий план. Локальні standards, gates та owner-рішення зберігаються.

## Перед початком роботи

У чинному primary record запиши мету review, `review_mode=existing_session` для вже призначеної додаткової сесії або `review_mode=independent_subagent`, якщо додаткової сесії немає; writer/reviewer reference (pending до дозволеного spawn), підставу вибору, чинний механізм зв’язку, delivery owner, authorization source та координацію shared-resource checks. Явний вибір власника має пріоритет. Не перепитуй вже визначений маршрут; справді невідомі необхідні дані познач BLOCKED із власником уточнення.

Вибір режиму не запускає review/security і не дозволяє нові зовнішні сесії. Existing-session використовує вже призначеного reviewer без дубля; independent-subagent — окремий контекст за чинною авторизацією, після запуску зберігається його reference. Self-review автора не незалежне review. Недоступний обраний runtime → BLOCKED, без тихого fallback або PASS. Після compaction/resume збережений режим і pending action відновлюються, а не вибираються заново. Підтверджений маршрут не означає завершений review; author checks звітуються окремо.

## Пакет передачі

Мінімальний self-contained package у наявному evidence-місці:

- task ID, author session ID, обраний маршрут/власник/reviewer reference та статус передачі `prepared/sent/acknowledged/verdict_received` у primary record;
- точний repo/root, branch, resolved base commit, HEAD; явний file scope із tracked dirty та relevant untracked, SHA-256 поточних і базових bytes, точний diff;
- acceptance та relevant contracts: точний шлях + SHA-256 + snapshot копія потрібного документа (або самодостатній витяг із provenance); не лише переказ автора;
- evidence: команда/сценарій, exit code, PASS/FAIL/BLOCKED/NOT_TESTED/N/A, scope/revision, сирий artifact/hash, limitation; непрогнане не стає PASS;
- constraints, non-goals, дозволи, ресурсні обмеження, unresolved decisions, наступний власник.

Не копіюй .env/credentials/config secrets, transcript або повні нерелевантні логи. За неможливості безпечно передати джерело — назви відсутній доказ і BLOCKED залежний gate. Для external shared документації використовуй явні paths; для коду scope не розширюється автоматично.

Одна пара `package ID + призначений reviewer reference` має один handoff у чинному record. Для вже переданого пакета повтор — NOOP, а не нове повідомлення чи spawn. Невідома доставка потребує звірки receipt; підтверджена недоставка може мати повтор за чинною авторизацією в тому самому handoff. Helper нічого не надсилає й не керує сесіями.


<a id="pending-next-action"></a>

## Наступна дія, яку не можна втратити

Після `/clear`, нового startup або resume валідний pending record — лише привід коротко показати task/checkpoint і запитати «Продовжити?». До поточної відповіді користувача не виконуй task/review/send; Stop не має примушувати продовження під час цього очікування. Явний новий запит користувача продовжити саме цю задачу може бути підтвердженням. Після підтвердження застосовні дозволені кроки йдуть без нового питання на кожному gate; permissions не розширюються. Згода іншої або попередньої сесії не переноситься.

Compaction усередині вже підтвердженої активної задачі зберігає continuity: віднови її конкретний next action без повторного питання. Якщо до compaction ще чекали відповіді — продовжуй чекати, не запускай цикл запитань. Unbound без задачі лишається тихим; schema/bind help доступний лише on-demand. Це scoped workflow UX, не нове правило security approval і не дозвіл запускати review.

На startup і після compaction/resume спочатку прочитай explicit primary task record. Фіксуй `review_mode=existing_session` для вже призначеної додаткової сесії або `review_mode=independent_subagent`, якщо додаткової сесії немає. Віднови цей вибір, writer/reviewer, чинний дозволений механізм зв’язку та pending action; не запитуй повторно відомі IDs/дозвіл, не створюй нову зовнішню сесію чи дубль review. Independent subagent має окремий контекст review; inline self-review автора не заміна. Якщо runtime не підтримує обраний режим або бракує дозволу, запиши BLOCKED і власника розблокування, без тихого перемикання чи PASS. Вибір режиму не запускає review, security або інші роботи сам собою.

У тому самому record тримай короткий блок (не новий tracker): `task/stage + snapshot/package ID; review_mode; writer; reviewer; contact mechanism + delivery owner + authorization source; action ID + next action + owner; transfer state + evidence pointer; required final verdict + evidence pointer; blocker/next check`. Адреса/маршрут береться з уже робочого зв’язку, а не з довільної схожої назви. Для independent_subagent reference лишається pending до дозволеного запуску; після нього збережи реальний reference та використовуй того самого reviewer. Не зберігай токени чи credentials.

Після кожного етапу онови блок і виконай лише applicable next action, уже дозволену поточним scope. Small/full і локальні gates визначають застосовність; не запускай усі skills або весь pipeline. Якщо дія залежить від іншого виконавця чи дозволу, зафіксуй очікування/блокер замість удаваного завершення.

| Стан | Наступна застосовна дія |
|---|---|
| Етап виконано, потрібні checks ще не виконані | Застосовні дозволені checks; без дозволу на side effects — BLOCKED |
| Checks достатні, required review ще не передано | Підготувати exact package і передати вже призначеному reviewer через чинний дозволений зв’язок |
| `prepared` | Файл готовий, але це не доставка; send належить delivery owner |
| `sent` | Зберегти фактичний transport result; чекати ACK/відповіді, не надсилати повторно через compaction |
| `acknowledged` | Reviewer підтвердив конкретний package; чекати verdict, ACK не є PASS |
| `verdict_received` | Звірити reviewer, package/snapshot, scope, findings і required evidence; FAIL → дозволене виправлення й зачеплене re-review; чинний final verdict → наступний локальний етап |
| Доставка невідома, held/refused, немає відповіді або доказ застарів | WAITING/BLOCKED із причиною та next check/owner; не трактувати таймаут як PASS і не дублювати delivery |

`sent` потребує фактичного результату надсилання; `acknowledged` — відповіді призначеного reviewer саме на цей package. Авторський файл результату, слова DONE/PASS або успішний hook не заміняють незалежного verdict. Повна валідна відповідь reviewer може одночасно підтвердити отримання та містити verdict — окремий ACK-пінг не потрібний. Для ручної передачі підтвердження власника є доказом send, але не reviewer ACK чи verdict.

Перед send познач намір/attempt для action ID, після — фактичний результат у тому самому record. Якщо між ними стався збій, delivery unknown: спочатку звір існуючу переписку/receipt, без автоматичного resend. Цей запис запобігає сліпим повторам, але не обіцяє exactly-once transport. Повтор за нового package ID або після підтвердженої недоставки — лише за чинною авторизацією; не створюй нового reviewer.

Resume починається з конкретного pending action та перевірки relevant snapshot. Незмінені прийняті етапи не повторюються; material delta відкриває лише зачеплені gates за локальним контрактом. До compaction/перед завершенням поточного turn збережи актуальний блок. WAITING/BLOCKED дозволяє завершити turn із чесним статусом і next check, але не оголосити задачу DONE. DONE можливий лише після всіх застосовних локальних gates і потрібного final verdict на фінальний snapshot; якщо review N/A, потрібна локальна підстава, а не новий waiver.

<a id="delivery-state"></a>
## Delivery state та security завершення

Єдиний transport contract — `prepared` → `sent` → `acknowledged` → `verdict_received` у наявному pending-action record вище. Для історичних security reports `PREPARED`, `SENT`, `VERDICT_RECEIVED` є aliases відповідних lowercase states; `AWAITING_DELIVERY` — причина WAITING із delivery owner/next action, а не окремий transport state. Legacy `delivered` означає `sent` лише за доказом доставки; `responded` означає `verdict_received` лише за валідною відповіддю потрібного reviewer на цей snapshot. ACK не є acceptance; повний валідний verdict може одночасно підтвердити ACK. Runtime schemas/helpers не змінюються цим documentation delta.

DONE блокується за будь-якого незакритого applicable required check або required independent final verdict. Missing runtime proof лишає VERIFICATION_INCOMPLETE; missing verdict — REVIEW_PENDING: це reporting outcomes, не transport states. N/A потребує причини застосовності, а зміна required requirement — явного owner-рішення. Aggregate build/fixture/merge не заміняє required row. Це instruction contract, не автоматичне CI enforcement. Для scoped security work — [proposed adapter](../adapters/security/review.md).

## Контракт reviewer

Reviewer працює незалежно: сам читає pinned acceptance/contracts, diff і source snapshots, звіряє живий root/snapshot до та після перевірки, оцінює достатність scope й relevant untracked. Summary автора — лише навігація. Read-only за замовчуванням: source/config/index не змінює. Локальний дозволений review artifact можна записати лише у визначене evidence-місце. Потреба тесту не дозволяє reset/seed/install або доступ до спільного стенда; спочатку узгодити операцію, власника, слот і side effects. Окремо позначити власні checks та прийняті pinned raw evidence автора.

Кожен finding: `file:line`, конкретний наслідок, доказ/спосіб відтворення чи перевірки, blocking/nonblocking, confidence. Verdict: reviewer reference, package/snapshot ID, checked scope/axes, findings, checks/evidence й limitation. Відсутня/порожня/незавершена відповідь означає **review NOT_TESTED, required gate BLOCKED**. Автор не видає self-review за незалежний PASS. Структурна валідація helper не доводить незалежності людини/агента чи істинності її декларацій.

## Зміни після review

PASS стосується тільки перевіреного snapshot/scope. Після виправлень сформуй final delta до reviewed snapshot; reviewer визначає зачеплені criteria/checks та дає verdict на фінальний package ID. Unchanged evidence можна явно прийняти, якщо inputs не змінилися. Не повторюй весь gate для нерелевантної правки, якщо локальний контракт цього не вимагає. Не перенось старий PASS на змінені acceptance/diff/untracked. Зміна base/HEAD потребує звірки provenance, а не автоматичного повтору всіх тестів. Розширений/звужений scope reviewer підтверджує окремо; нові релевантні файли мають бути включені.

## Опційний stdlib helper

[review_package.py](../runtime/legacy/review/review_package.py) працює на Git repo з HEAD, UTF-8 текстовими файлами: максимум 100 scope files, 1 MB/file, 8 MB унікальних blobs. Не запускає repo commands/tests/CLI/MCP; лише read-only Git queries. Немає install, network, dispatch, hooks або permission changes. Symlink paths, секретоподібні назви/вміст і конфігурації відхиляються; це defense in depth, не універсальний secret scanner. Використовуй canonical paths (на macOS `/private/...` замість symlink `/tmp` для fixture).

```sh
python3 "$KIT/runtime/legacy/review/review_package.py" route manifest.json
python3 "$KIT/runtime/legacy/review/review_package.py" capture manifest.json /absolute/existing-evidence/review
python3 "$KIT/runtime/legacy/review/review_package.py" assess /absolute/package-ID --response response.json
python3 "$KIT/runtime/legacy/review/review_package.py" delta /absolute/old-ID /absolute/new-ID
```

[Manifest приклад](../examples/review/manifest.json) і [response приклад](../examples/review/response.json) — форми, не готові approvals чи PASS. Заміни paths/IDs і declarations фактичними. Пакет містить `package.json` та `objects/<SHA256>`; відкрий diff blob і source/reference blobs за manifest. Metadata/package ID й кожен blob перевіряються при load; повтор capture незміненого scope — той самий ID/NOOP. Два проходи collection відхиляють спостережені конкурентні правки; вони не блокують writer після capture, тому freshness перевіряється повторно перед verdict/застосуванням. Snapshot — explicit file scope, не повний repo audit; ignored/out-of-scope файли не охоплено автоматично. Нерелевантні зміни поза scope не інвалідують його.

`assess` перевіряє цілісність, current scope/reference/evidence hashes, маршрут, response identity/coverage та required check declarations. Це **структурний статус**, не створений інструментом review. Порожній response, missing evidence, чужий reviewer або stale package блокуються. Непідтримуваний формат — ручний еквівалент з тими самими полями й чесним NOT_TESTED, не встановлення нових tools.

Тести: `python3 -B "$KIT/tests/legacy-tests/review/test_review_package.py"`; усі Git fixtures disposable. Живі чужі сесії/CLI/стенд не використовуються для симуляції.
