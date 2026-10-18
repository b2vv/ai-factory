> Optional retained portable profile; the full canonical plan is in `ai-factory/`. This profile does not replace original skill contracts or authorize automatic activation.


[Вхід](../legacy/starter-readme.md) · [Workflow](workflow.md) · [CRG](crg.md)

# Helper / Coder / Escalation-reviewer

Це ручний розподіл ролей у наявному workflow, не встановлений router і не новий pipeline. Малі задачі не потребують трьох агентів. Локальний контракт визначає acceptance, гейти, власника коміту й потребу незалежного review. Чинний стек та користувацькі зміни зберігаються.

| Роль | Межі й результат | Ескалація |
|---|---|---|
| Helper | Швидкий дешевший read-only пошук, карта файлів, короткий підсумок із file:line; без source edits, остаточного verdict і важких перевірок | Неоднозначні вимоги/архітектура, суперечливі джерела або відсутня доказова база → Coder |
| Coder | Реалізація погодженого scope, acceptance, доречні детерміновані перевірки; журнал рішень/змін/результатів | Високий ризик або два невдалі обґрунтовані виправлення → Escalation |
| Escalation / reviewer | Складні причини, міжмодульні контракти, auth/доступ/дані/міграції/незворотність; review в новому незалежному контексті | Немає незалежного виконавця або бракує доступу/рішення → BLOCKED + конкретний handoff |

Високий ризик направляється одразу до Escalation, без обов'язкового невдалого дешевого проходу. Якщо Escalation сам писав рішення/код, для verdict потрібен інший reviewer; самоперевірка не стає незалежною через нову назву ролі. Модель не замінює compiler/lint/tests, browser interaction чи людське acceptance.

## Bindings і рівень підтвердження

Bindings визначаються заново для конкретного host/session, незалежно від провайдера. Назва ролі не задає model ID. Старі cache snapshots і configured defaults — історичні кандидати, не поточний каталог або entitlement. Каталог Codex app/dot/іншого executor не переноситься в локальний Codex CLI чи Claude Code.

| Поле session inventory | Необхідний доказ / дія за відсутності |
|---|---|
| Host, session, дата, роль | Назвати конкретний CLI/app та сесію; не виводити з назви репо |
| Available catalog і provenance | Вже доступний каталог саме цього host/session з reference; за відсутності отримати read-only inventory підтримуваним засобом або залишити UNBOUND |
| Candidate + effort | Candidate має бути в цьому каталозі; effort лише з підтверджених можливостей цього host, інакше unresolved |
| Entitlement | Окремо unknown / available / unavailable з доказом; присутність у каталозі не гарантує доступ акаунта |
| Budget | Окремо unknown / approved / denied; врахувати чинне доручення, не вмикати платний доступ |
| Actual binding | Лише вже підтверджений фактичний запуск/стан сесії; configured candidate не є runtime proof |

Для Helper, Coder, Escalation/reviewer запиши candidate status (catalog unknown / unselected / missing / listed), entitlement, budget та конкретний next step. Missing candidate → обрати з доступного same-host каталогу; unknown entitlement → перевірити доступ без платного probe; unknown budget → рішення власника перед витратним запуском. Непідтверджена комбінація — **UNBOUND**. Якщо вже відома поточна модель, її можна вказати як actual binding без припущення про дешевший tier; роль Helper сама не знижує вартість.

[Preflight schema](../onboarding-helper.md) перевіряє лише поданий inventory і session identity, не автентичність evidence або entitlement. `VALIDATED_DECLARATION` не означає виконаний model binding. Жодних model API probes, автоматичного перемикання, запису config або обходу permissions для заповнення таблиці. Наявний незалежний reviewer може виконати дозволену роботу; якщо required tier/reviewer недоступний — BLOCKED конкретного gate, не self-review PASS. Немає потреби призначати всі три ролі малій задачі.

## Ліміти роботи

- Helper: одна вузька задача; до 5 цільових пошукових/tool кроків і приблизно 800 токенів підсумку. Після одного уточненого повтору передати знайдене й блокер. Ці межі — стартовий бюджет, не критерій істинності.
- Coder: не більше двох виправлень однієї невдалої перевірки без нового доказу/гіпотези. Далі — короткий пакет Escalation; не повторювати той самий дорогий full gate без причини.
- Reviewer: один первинний прохід і один прохід по виправленнях; після зміни scope/рішення оновити контракт. Empty/null/timeout ≠ clean: один обґрунтований retry, потім BLOCKED.
- Контекст: передавати контракт, точні файли/рядки, diff і результати; не весь чат, архів репо або повний graph dump. Орієнтир handoff ≤1500 токенів плюс посилання; великий scope розбити до dispatch. Не скорочувати докази для формального потрапляння в ліміт.
- Після двох циклів без прогресу або перед compaction зафіксувати журнал і конкретний наступний крок. Гроші/квоти не вгадувати; автоматичного cost routing немає.

## CRG і мінімальний handoff

Перед graph-assisted роботою: [CRG freshness/coverage](crg.md). При stale/missing/untracked scope не робити висновків «немає callers», «dead code», «нуль impact»; перейти до `rg`, поточних файлів, language tools і тестів. Розмір/дорожнеча моделі не виправляє stale context.

У наявному plan/journal записати: роль + фактична модель/effort/host; ціль/acceptance та межі; repo/root/branch/HEAD + dirty/untracked scope; авторитетні інструкції; CRG status і точні запити/обмеження; змінені файли; команди/результати PASS/FAIL/BLOCKED/N/A; рішення/блокер; наступний виконавець і одна дія. Reviewer отримує ці артефакти без авторської історії чату. Нового обов'язкового журналу не потрібно.

## Докази доступності

Зберігай безсекретний reference на каталог/сесію та дату у чинному task record. Config/cache можна врахувати лише як відповідний тип джерела, без читання credentials та без називання старого кешу актуальним каталогом. Discovery, entitlement, budget і invocation мають окремі докази. Цим документальним оновленням model API та CLI probes не виконувалися, defaults не змінювалися.
