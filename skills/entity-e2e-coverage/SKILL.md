---
name: entity-e2e-coverage
description: "Планує й перевіряє E2E покриття полів сутності та QA findings без підміни read-only view перевіркою edit. Використовуй для entity create/view/edit/update та scoped list-filter сценаріїв, їхніх тестів або аудиту покриття; не для загального візуального рев’ю."
---

# Entity E2E coverage

Мета — зберегти кожне потрібне QA-очікування і перевірити його на правильній поверхні. Це вузький контракт покриття, не тестовий runner і не гарантія відсутності багів.

## До тестування

1. Прочитай [testing-rules](references/testing-rules.md): загальні інваріанти та лише розділ поточного репо; звір оригінальні локальні правила, scope, acceptance і всі релевантні QA findings. Знайди реальні surfaces: read-only сторінка, drawer, preview, list cell, edit form. Одна URL може мати різні режими. Не вигадуй view-сторінку й не розширюй задачу до всього CRUD.
2. У наявному plan/test artifact створи матрицю: **QA requirement ID + source → entity field → deterministic expected value/format/permitted transform → surface + state → action → assertion → evidence**. Відокрем baseline вимог від результатів; звір перелік IDs з оригінальним QA джерелом, а не лише з наявними тестами.
3. Очікування бери зі spec/QA/незалежної fixture. Не з поточного UI або механічно з API-відповіді, яку цей самий тест має перевірити. Для неоднозначного формату потрібен контракт, не припущення.

## Окремі зобов’язання

Кожне застосовне зобов’язання має власний рядок та assertion:

- **Create persistence:** створена саме тестова сутність і збережені потрібні дані; успішний toast або local form state цього не доводить. Перевір повторне читання після завершення save, за потреби без client cache. API/DB може бути додатковим persistence-доказом.
- **Read-only view після create:** відкрий реальну read surface; перевір видимі значення/формати потрібних полів, зокрема дані з QA finding. Edit input, API/DB і screenshot без перевірки очікуваного не заміняють цей рядок.
- **Edit prefill:** окремо відкрий edit і перевір початкові значення, selected options та потрібні незмінені поля. Read-only view не доводить правильність prefill.
- **Save update:** змінюй поля на відмінні значення, що проходять контрактну нормалізацію як відмінні; перевір збереження, а не лише введений текст.
- **View після update/reload:** після save окремо перевір потрібні змінені й незмінені поля на read surface та після reload/reopen за контрактом. Старий create/view доказ не закриває новий стан.

Не всі рядки потрібні кожній задачі. Відсутня/непридатна surface або дія поза scope — **N/A з джерелом і причиною**. Якщо spec вимагає view, а доступ/реалізація відсутні — **BLOCKED** (або FAIL для доведеного дефекту), не N/A. List cell може бути read surface лише для тих полів/станів, які вона реально показує і які приймає контракт.

Для потрібних полів розрізняй label та ID, date-only й instant/timezone/locale, false й empty, null й порожній рядок, nested reference та його display label. Заданий дозволений transform перевіряється явно; не нормалізуй довільно, приховуючи дефект. Обирай fixture значення, на яких помилку видно.

## Умовні сценарії

Якщо acceptance охоплює фільтри або keyboard action, застосуй [scoped правила](references/testing-rules.md#scoped-перевірки-та-завершення): matching/nonmatching на кожному заявленому entity type × surface та browser key input з очікуваним UI-effect. Controls/URL/API не заміняють результати списку, submit dispatch — клавішу. Не додавай ці вимоги звичайному CRUD поза scope.

## Виконання та завершення

Працюй лише з тестовими даними в дозволеному середовищі. Перед mutation перевір чинний дозвіл і side effects команд; cleanup лише власних fixtures. Скіл не дозволяє reset спільних даних, deploy, установки чи нові MCP. Зокрема Courses `make check`/`make e2e-local` можуть видаляти dev volumes — не запускай як автоматичну передумову.

Доказ рядка: фактичний run ID, tested revision **і diff fingerprint** (включно з relevant dirty/untracked), test/assertion locator, artifact/trace або ручний запис із реально спостереженим результатом. Запиши fixture/entity identity, середовище й реалізовану перевірку; план або написаний, але не виконаний тест — не PASS. Після зміни коду повтори зачеплені assertions; старі докази не переносити мовчки.

Звіт зберігає кожен QA ID, field і required surface/state. PASS лише за власним виконаним assertion; FAIL/BLOCKED залишають gate відкритим. Skip/xfail — не PASS. Видалення/послаблення рядка, зміна requirement, snapshot update або тесту мають явний diff, причину та review за локальним процесом; зміна acceptance потребує рішення його власника. Не переписуй expected під отримане. Виправлений QA finding закривається повтором його конкретного сценарію.

Перед завершенням узгодь summary, plan checklist і evidence з фінальними revision/diff та фактично перевіреними entities/states/assertions. Неповне — PARTIAL/BLOCKED, незастосовне — N/A з причиною. Тимчасові корисні regression specs зберігай до переносу, звірки покриття й targeted run постійного suite; деталі — [testing-rules](references/testing-rules.md#scoped-перевірки-та-завершення). Завершену задачу не перевиконуй через ідентичний handoff без зміни inputs; спочатку звір статус та наявні докази. Не приписуй повтор автоматизації без доказів.

Ця матриця деталізує наявний acceptance/report, не дублює їх. [acceptance-spec](../plan/acceptance-spec/SKILL.md) визначає поведінку; цей скіл перевіряє field × surface × state; [interface-review](../interface-review/SKILL.md) оцінює UX/вигляд і не заміняє дані assertions. Виконання — чинним runner або дозволеним браузером, без прив’язки до чужого webdev-стеку.

За потреби машинної перевірки читай [формат і приклади](references/matrix.md), використовуй [validator](scripts/validate_matrix.py). Він перевіряє узгодженість baseline/report і evidence metadata, **не доводить, що браузер виконав assertions**, і не знаходить вимоги, не внесені в baseline. Незалежний reviewer звіряє джерела та фактичні artifacts.
