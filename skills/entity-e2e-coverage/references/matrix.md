# Матриця й перевірка звіту

Людинозрозуміла таблиця у чинному plan достатня; JSON потрібен лише для валідатора. Baseline створюється до тестування, звіряється з оригінальними QA/spec і передається reviewer окремо від report. Видалений із самого baseline QA ID не може бути відновлений валідатором — джерело перевіряє reviewer.

## Формат

Зразки: [contract](example-contract.json), [report](example-report.json). Усі значення в них та [cases](cases.json) **синтетичні**, навіть `executed: true`: це fixtures валідатора, не докази браузерного тесту.

Contract: `revision`, `diff`, `qa` (повний scoped inventory ID/source) і `rows`. Рядок має унікальний `id`, `qa_id`, `field`, `expected`, `expected_source`, `surface`, `state`, `action`, `assertion`, `channel` (`ui/api/db`), `required`. Кілька полів одного QA finding — окремі rows. `expected` — детермінований текстовий опис значення/формату; для transform додай правило до нього та джерело. Не використовуй «правильно».

`required: false` означає саме N/A, потребує `na_reason` і `na_source`. Не змінюй required на false через недоступний браузер/роль/сервер. Для нового погодженого scope збережи diff старого baseline і рішення власника.

Report: поточні `revision`, `diff`, `run_id`, `environment`, `fixture_id`, `results`. Кожен result: `id`, `status`; для non-PASS — `reason` (крім N/A, чия причина в baseline). PASS має `evidence`: ті самі п’ять run-полів, `executed: true`, фактичні `surface/state/channel/assertion`, `artifact`, унікальний у цьому artifact `assertion_id`, `observed`. Один trace може містити багато незалежних assertions; один assertion не закриває різні зобов’язання. Для ручного тесту locator — конкретний крок запису, не загальний скриншот.

`diff` — fingerprint tested diff, включно з relevant untracked, а не просто branch або слово «dirty». Звір його з checkout і test deployment; report не може сам довести, що названа ревізія реально була відкрита. Для повторного прогону зафіксуй новий run та нові докази; baseline acceptance зберігається, його tested identity оновлюється явно.

Виклик (Python 3, без додаткових бібліотек):

```sh
python3 ~/.agents/skills/entity-e2e-coverage/scripts/validate_matrix.py contract.json report.json
python3 ~/.agents/skills/entity-e2e-coverage/scripts/test_validate_matrix.py
```

Exit 0: bookkeeping complete за переданим baseline. Exit 1: malformed/incomplete/FAIL/BLOCKED або підозріла невідповідність; причини в JSON. `browser_execution_proven` завжди false. Скрипт не відкриває artifacts, не порівнює DOM, не запускає browser, не виводить коректність expected/observed із текстів і не підтверджує правдивість metadata. Ідентичні, але вигадані metadata пройдуть; потрібен review фактичного test/trace і незалежного джерела.

## Реалістичний приклад

QA-41 вимагає назву Depot Cedar у detail та edit; після зміни — Depot Birch. QA-42 окремо вимагає display label `Kyiv region` для reference `r-17`, збереження region без зміни. Порівняння edit value з response `name` не доводить detail. Persistence API може очікувати `r-17`, UI має очікувати label з незалежної fixture.

Для дат окремо зафіксуй, чи `2026-10-17` є calendar date без timezone, чи timestamp з перетворенням у задану зону; не обрізай рядок до дня, якщо QA перевіряє час. Для boolean `false` перевір реальний контрактний label/unchecked, а не наявність truthy тексту. Для null/empty та nested references зафіксуй placeholder/відсутність/label, які справді обіцяє spec. Додавай лише поля й стани поточного scope.

Cases A–E містять різні звіти для depot workflow, придатні для незалежного review без доступу до живого середовища. Серед них є create→edit без view-доказу, повний цикл, edit-only UI із документованим N/A, недоступний required view та загублений QA field. Очікувані verdicts перевіряє test script; не видавай синтетичний complete за product PASS.

## Умовні поля для filters / keyboard / visual

Лише коли ці вимоги є в acceptance, додай row `kind`: `filter-matching`, `filter-nonmatching`, `keyboard` або `visual`, та `entity_type`. Evidence повторює обидва поля; channel — `ui`. Решта CRUD rows не змінюються.

Для заявленого filter scope додай contract `filter_scopes: [{"entity_type": "truck", "surface": "list", "source": "acceptance AF-1"}]`. Кожна пара потребує окремих required matching/nonmatching rows. Заявлені типи/поверхні звіряє reviewer з acceptance: parser не знаходить пропущеного scope у зовнішній прозі. Не включай до filter_scopes незастосовні фільтри; optional row з `required: false`, N/A/source/reason документує scoped виключення.

Required keyboard row також має `input_method` (`simulated-browser-key` або `manual-key`), `key` і `ui_effect`; evidence повторює їх. `dispatch-submit` не є keyboard input. Поля фіксують заявлений спосіб, а не доводять натискання.

Для scoped visual states створи окремі required `kind: visual` rows із конкретними `surface/state/assertion`; наприклад open-popover, active-trigger, chips. Default screenshot не може підмінити інший state. Реальний inventory і фактичне порівняння зображень перевіряє reviewer, не parser.

Необов’язкове report `claimed_pass_rows` — IDs рядків, для яких summary заявляє PASS; невідомі/non-PASS IDs відхиляються. Поле не аналізує текст summary чи зовнішній checklist. PARTIAL/BLOCKED із причиною дозволяють чесний звіт, але required row залишає coverage incomplete (exit 1). N/A з обґрунтуванням не закриває required scope.

[Scoped fixtures](scoped-cases.json) синтетично перевіряють missing entity coverage, keyboard substitution, uncovered active state, overclaim та scoped N/A. Вони не є результатом браузерного запуску.
