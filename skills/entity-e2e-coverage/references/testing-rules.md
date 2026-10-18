# Правила тестування сутностей

Звірено з локальними джерелами 2026-10-17. Це вузький довідник: прочитай загальні правила та лише свій repo-specific розділ; перед запуском перечитай застосовний оригінал. Чинний локальний контракт має пріоритет над переносом практики іншого репо. Команди у джерелах не є дозволом їх запускати. Зовнішні мануали не використані.

## Загальні інваріанти цього скілу

- **Спостережувана поведінка, не внутрішній стан.** Assertions мають розрізняти правильний і неправильний користувацький результат; відкрита сторінка/toast не доводять правильності даних. Unit перевіряє seam, E2E — потрібний користувацький шлях. Джерела: [acceptance-spec §1–2](../../plan/acceptance-spec/SKILL.md), [tdd: What a good test is / Anti-patterns](../../arch/tdd/SKILL.md). Не запускай увесь TDD-процес лише через це посилання.
- **Незалежне очікування.** QA IDs і field-level expected з QA/spec/fixture зберігаються у baseline; literal/known-good приклад або погоджений transform, а не повторення алгоритму реалізації. Джерело: [tdd: Tautological](../../arch/tdd/SKILL.md). Звір усі scoped QA IDs із першоджерелом; наявні тести не є повним inventory вимог.
- **Правильна surface і state.** Create persistence, created read-only view, edit prefill, update persistence та updated/reloaded view мають окремі assertions за застосовністю. Це новий цільовий контракт користувача, закріплений у [SKILL.md](../SKILL.md), а не твердження, що таке правило вже було у всіх репо. API/DB доказ може доповнювати persistence, але не доводить UI label/format. Для відсутньої непридатної surface — N/A з причиною; для недоступної required — BLOCKED.
- **Синхронізація з потрібним результатом.** Очікуй конкретний стан/завершення потрібного save та відображення даних; не довільний sleep і не сусідній сигнал. Bounded retry assertion має впасти, якщо очікуваного стану немає. Не маскуй race збільшенням timeout. Основа: [Cargo ADR-0008](~/projects/cargo/cargotrans-ui/docs/adr/0008-a-wait-must-watch-the-thing-that-varies.md) — його сувора вимога довести wait червоним є локальною, не автоматичним обов’язком кожного іншого репо.
- **Дані й незалежність.** Унікальна fixture identity для run, явні передумови, створення дозволеними засобами, cleanup тільки створених цим тестом сутностей. Не залежати від випадкового порядку тестів або чужих даних. Спільні auth/seed setup можуть бути локальним контрактом: не замінюй їх новими логінами «заради ізоляції». Джерела: Cassiopeia ADR-0071 і Cargo FIXTURES нижче. Немає дозволеного середовища — BLOCKED mutations; не перемикайся на production.
- **Негативні сценарії за ризиком.** Для зміненого контракту перевір застосовні invalid input, права, empty/null, відмову save/повтор і збереження незмінених полів. Не додавай всі можливі сценарії кожній правці. Відсутні групи поясни; джерело: [acceptance-spec §1](../../plan/acceptance-spec/SKILL.md).
- **Не послаблюй gate мовчки.** Skip/xfail/did-not-run, snapshot update, заміна assert, видалення QA row або зміна expected потребують видимого розбору. Зміна продуктового acceptance — рішення власника, а не адаптація до багу. Джерела: [ship-report §2](../../ship/ship-report/SKILL.md), Cargo FIXTURES «did not run» нижче. Snapshot — reviewed expectation, не автоматична нова істина після падіння.
- **Доказ виконання.** Потрібен фактичний run, revision/diff, entity/fixture, environment та конкретні assertions/artifacts. План тесту, успішний build або screenshot без перевірки не закривають рядок. Джерела: [design-pass §5](../../design-pass/SKILL.md), [ship-report §2, §5](../../ship/ship-report/SKILL.md). Валідатор перевіряє metadata, reviewer — правдивість evidence.

## Scoped перевірки та завершення

- **Фільтри лише в scope:** окремі positive matching і negative nonmatching assertions для кожного заявленого entity type × list surface. PASS для trucks не доводить trailers, навіть зі shared component. Відокрем controls/URL/API від фактичного складу списку. Для AND, Clear, reload, chip removal та no-results перевір саме потрібний результат за acceptance; зникнення одного fixture рядка саме по собі не доводить порожній список. Не додавай фільтри звичайному CRUD.
- **Keyboard лише за acceptance:** подай потрібну клавішу через browser input на реальний focused control і перевір очікуваний UI-effect. Unit dispatch submit/callback не заміняє Enter. Автоматизацію називай «simulated browser key», не фізичною ручною QA. Запиши key, input method і effect; ручну QA називай виконаною лише за фактичним ручним спостереженням.
- **Тимчасові regressions:** не видаляй корисні acceptance/regression specs до переносу сценаріїв у постійний підтримуваний suite, звірки еквівалентності assertions/entities/states та успішного targeted run цього suite. Збережи mapping старих і нових сценаріїв у чинному report. Це не дозвіл видаляти чужі файли, commit або push.
- **Точність PASS:** звір заяву з реально виконаними assertions, entity types, surfaces/states та фінальними revision/diff. Summary, plan checklist й evidence мають узгоджуватися. Неповне познач PARTIAL або BLOCKED з причиною, поза scope — N/A з джерелом і причиною. Старий PASS не переноситься на нову UI delta. Завершену задачу не повторюй лише через ідентичний handoff за незмінених inputs; звір наявний статус. Походження повтору невідоме, доки немає доказу тригера.

## Cassiopeia

Канонічні джерела:

- [docs/agent/22-testing-strategy.md](~/projects/cassiopeia/cassiopeia-admin-ui/docs/agent/22-testing-strategy.md), §22.0–22.5: межа unit/Storybook/E2E, live save semantics, локальні selectors/session patterns. Читати потрібний розділ, не переносити історичні числа у новий звіт.
- [ADR-0071](~/projects/cassiopeia/cassiopeia-admin-ui/docs/adr/0071-e2e-shared-session-and-new-spec-construction-rules.md): вибери застосовний session pattern; у shared storageState сценарії не додавай власний login, який може відкликати чужу сесію. Dependencies — для справжньої залежності даних, не лише бажаного порядку.
- [work/README.md](~/projects/cassiopeia/cassiopeia-admin-ui/work/README.md): людська QA окрема від code review; qa-test не дорівнює archive.

Практичні наслідки: після create чекай відповідь відповідного POST, ідентичність створеної сутності береться за локальним helper/контрактом. Sequential edit може мати кілька write-команд — перша успішна відповідь не доводить завершення save. Це лише синхронізація: після неї потрібні окремі UI view assertions. Для stateful компонентної проби no-op onChange не доводить збереження вибору (§22.1). Pretest/reset має side effects — перевір перед запуском.

## Cargo

- [ADR-0008](~/projects/cargo/cargotrans-ui/docs/adr/0008-a-wait-must-watch-the-thing-that-varies.md): wait дивиться на змінну, що визначає готовність; локально вимагається показати падіння без wait/зі зламаною умовою. Мок замість live rights-read змінює предмет доказу.
- [ADR-0014](~/projects/cargo/cargotrans-ui/docs/adr/0014-running-tests-gates-stands-live-telemetry.md): fast/unit не доводять browser behavior; backend generation і stand мають відповідати run. Його вимога двох стендів застосовується до локального E2E gate; один цільовий repro не називай повним gate. Live telemetry сценарії мають власні залежності й coordination, не запускай їх для довільної entity-форми.
- [tests/FIXTURES.md](~/projects/cargo/cargotrans-ui/tests/FIXTURES.md): local/testing fixtures, seed відділений від destructive rebuild; visual snapshots залежать від завершення writers. `did not run` — невідомо, не PASS. Звідси брати потрібну роль/fixture, не копіювати credential-приклади у звіт.
- [work/qa/README.md](~/projects/cargo/cargotrans-ui/work/qa/README.md): tasks → qa після merge → archive після QA; це відрізняється від Cassiopeia.

## Courses

- [docs/development/testing.md](~/projects/courses/docs/development/testing.md): ordered gates; Go public seams, Rstest і Playwright із Compose, disposable PostgreSQL для integration. Відсутній Docker не перетворюється на skip-success. Migration-down не виконують проти developer DB. Recovery tests відновлюють локальні сервіси в finally; це спеціалізований scoped сценарій, не передумова будь-якого entity test.
- [Makefile](~/projects/courses/Makefile), `e2e-local`, `e2e-reset`, `drain-queue`, `check-generated`, `check`: `make check` і `make e2e-local` включають видалення postgres/redis/media volumes того самого compose project, включно з dev-даними. Drain видаляє queue keys і потребує ексклюзивної сесії. `check-generated` пише generated файли. Потрібні чинний дозвіл з розумінням цих наслідків і координація; цей скіл не запускає їх автоматично.

Не копіюй shared-session правила Cassiopeia чи два Cargo стенди у Courses. Повний gate, точковий regression і ручна перевірка — різні обсяги доказів, називай фактичний.
