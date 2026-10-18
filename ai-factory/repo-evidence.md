---
title: "ADR і workflow: джерела QnA та generic-ui"
reviewed: 2026-10-16
---

[До точки входу](../docs/legacy/ai-factory-plan-entry.md) · [Статус](status.md#capabilities) · [Маршрути](workflow.md#routing) · [Задачі](roadmap.md#tasks) · [Практики репо](repo-evidence.md#repo-evidence) · [Історія](history.md#history)

<a id="repo-evidence"></a>

# ADR і workflow: джерела QnA та generic-ui

### 7.1 Джерела й межі висновку

Досліджено папки `work/` усередині двох репозиторіїв:

- **QnA backend:** `~/projects/b2bsoft/genericui/openai-qna` — фактична назва каталогу `openai-qna`, не `qna-ai`; ідентифікація за [README.md:1](../../projects/b2bsoft/genericui/openai-qna/README.md) та [AGENTS.md:6](../../projects/b2bsoft/genericui/openai-qna/AGENTS.md).
- **generic-ui:** `~/projects/b2bsoft/genericui/generic-ui`.

В обох `CLAUDE.md` посилається на `AGENTS.md`. Нижче розділено **правило**, **наявний приклад** і **пропозицію**. Читання review/journal підтверджує наявність запису про перевірку, а не повторне виконання тестів цим аудитом. Репозиторії, їхні скіли й ADR не змінювалися.

<a id="adr-gates"></a>

### 7.2 Коли потрібен ADR, а коли достатньо іншого запису

**Підтверджене спільне правило цих двох проєктів:** кандидат має пройти всі чотири критерії — важко скасувати; рішення неочевидне без контексту; є реальна відхилена альтернатива з причиною; запис змінює майбутні дії читача/агента. Джерела: QnA [PRINCIPLES.md:44](../../projects/b2bsoft/genericui/openai-qna/PRINCIPLES.md), generic-ui [constitution.md:89](../../projects/b2bsoft/genericui/generic-ui/specs/constitution.md). Це опис локальних контрактів, не вже встановлена глобальна вимога для всіх репо.

Практичні кандидати з джерел:

- **Контракт між споживачами/репозиторіями:** зміна вимагає узгодження реалізацій, а локальний рефактор виглядає безпечним. Приклад QnA: [ADR 0026:3](../../projects/b2bsoft/genericui/openai-qna/lib/chat/docs/adr/0026-citation-replay-fold-is-a-cross-repo-contract.md) — спільна семантика citation replay fold, відхилене незалежне дублювання.
- **Неочевидний інваріант із реальною альтернативою:** QnA [ADR 0032:3](../../projects/b2bsoft/genericui/openai-qna/lib/chat/docs/adr/0032-rewind-surviving-events.md) — збереження Events після rewind, альтернатива amend-in-place й наслідки для кількох реалізацій.
- **Deletion-blocker:** «залишити X, доки споживач Y не мігрує». generic-ui прямо вимагає назвати що зберігається, що блокує видалення і що його дозволить: [constitution.md:105](../../projects/b2bsoft/genericui/generic-ui/specs/constitution.md). Це кандидат лише за виконання всіх чотирьох критеріїв.

**ADR не потрібен автоматично** для кожної задачі, TODO, відкладеного cleanup, очевидної правки або переказу реалізації. Якщо хоча б один критерій не пройдено — коротке «чому» в документі-власнику/коментарі або відмова від запису. Виправлення застарілого факту в чинному ADR не є новим рішенням: у QnA це окрема обов’язкова перевірка актуальності, яка не проходить чотири критерії заново ([PRINCIPLES.md:116](../../projects/b2bsoft/genericui/openai-qna/PRINCIPLES.md)). Зміна самого рішення чи причини відхилення альтернативи потребує нового рішення, а не тихого переписування старого.

### 7.3 Хто запускає етапи і як пов’язані артефакти

| Питання | QnA backend | generic-ui |
|---|---|---|
| Авторитет процесу | `PRINCIPLES.md` → `work/README.md` → локальний work-скіл | Конституція й specs; `work/README.md` — опційний execution-протокол |
| План і реалізація | Developer володіє планом та оркеструє; свіжий Worker реалізує й веде journal | Reviewer володіє plan/review; окремий Worker — кодом і journal; Operator передає роботу між сесіями |
| Критика | Design critic перед планом на основі design; plan critic, коли план специфікує поведінку; очевидна послідовність правок може обійтись без нього | Додатковий Critic опційний для складної/ризикової роботи, після approval Reviewer і до commit; це окрема лінза якості коду |
| Кандидати ADR | Reviewer складає promote list; відсутність майбутньої чернетки до codify сама по собі не finding | Reviewer формує promote-on-commit list; Operator переносить довготривале знання в specs/ADRs/wiki |
| Фіксація й прийняття | Після approval Developer замовляє codify; Maintainer читає сирі review/journal і приймає, уточнює або відхиляє ADR | Operator відповідає за promotion і commit; не переносити сюди автоматично окрему роль Maintainer з QnA |
| Зв’язки | Plan називає ticket/base/design; journal і review зберігають перебіг. Постійний ADR має самодостатню аргументацію, без залежності від work/design | Plan містить Constraints із посиланнями на specs/ADRs; work зберігає audit trail; знання між задачами виноситься в постійні docs |
| Архів | Work-гілка заморожується; артефакти work не потрапляють у base при landing | Папка переміщується до `work/archive/<NNN>-<slug>/` разом із додатковими артефактами |

Джерела таблиці: QnA [work/README.md:9](../../projects/b2bsoft/genericui/openai-qna/work/README.md), [work-reviewer.md:32](../../projects/b2bsoft/genericui/openai-qna/.claude/agents/work-reviewer.md), [design/README.md:12](../../projects/b2bsoft/genericui/openai-qna/docs/design/README.md), [adr-format.md:67](../../projects/b2bsoft/genericui/openai-qna/docs/adr-format.md); generic-ui [work/README.md:3](../../projects/b2bsoft/genericui/generic-ui/work/README.md), розділи Roles, Lifecycle, Files та Optional role — Critic.

**Важлива локальна відмінність:** обидва процеси залишають commit оператору; QnA також віддає оператору branch/push/rebase/tag. Це не привід змінювати глобальні дозволи, а правило, яке треба прочитати й виконати при роботі саме в цих репо. Архівування, видалення superseded ADR та ephemeral design — теж локальні політики, не автоматична дія для інших проєктів.

<a id="repo-skills"></a>

### 7.4 Які скіли справді підключені

**QnA — наявний локальний файл** [.claude/skills/work/SKILL.md:1](../../projects/b2bsoft/genericui/openai-qna/.claude/skills/work/SKILL.md). Він виконує `work/README.md`, а не замінює його:

`design critic за потребою design-документа → work plan-critique за змістом плану → work run → work review → work codify → work land`.

`plan-critic`, `work-worker`, `work-reviewer`, `design-critic` — версіоновані prompt-файли в `.claude/agents/`, не назви глобальних скілів. Свіжі контексти читають саме ці файли; автор не переписує prompt свого рецензента. Конкретні Claude-моделі та механізми spawn з локального опису не можна вважати доступними в Codex. Якщо інший агент не виявляє локальний work-скіл, прочитай файл явно; саме перейменування `/work` на `$work` не доводить discovery. Без незалежного контексту відповідний gate лишається BLOCKED.

**generic-ui — файловий протокол без обов’язкового skill-runner.** `role-reviewer`, `role-worker`, `role-critic`, `mode-careful`, `mode-ralph` згадані як опційні в [work/README.md:11](../../projects/b2bsoft/genericui/generic-ui/work/README.md), але їхні виконувані SKILL.md у перевірених локальних/global місцях не підтверджені. Не оголошувати їх виконаними чи встановленими.

Натомість існують prompt-скіли, прямо підключені через [specs/README.md:22](../../projects/b2bsoft/genericui/generic-ui/specs/README.md):

- [validate-spec.md](../../projects/b2bsoft/genericui/generic-ui/specs/prompts/validate-spec.md) — один spec проти живого коду;
- [analyze-specs.md](../../projects/b2bsoft/genericui/generic-ui/specs/prompts/analyze-specs.md) — узгодженість кількох specs; перед bundle або після змін конституції/структури; після його фіксів повторити validate для зачепленого spec;
- [pre-qa-review.md](../../projects/b2bsoft/genericui/generic-ui/specs/prompts/pre-qa-review.md) — pre-QA рев’ю, передача QA та аналіз результатів після QA.

Викликати їх явним проханням прочитати файл; сама наявність frontmatter не підтверджує slash-команду. Глобальні `spec-flow`, `plan-critique` або `design-pass` тут можна запропонувати як допоміжні лінзи, але не стверджувати, що вони вже автоматично вбудовані в ці локальні процеси.

### 7.5 Приклади й виявлені розбіжності

- **QnA, спостережуваний приклад:** [work/038-message-feedback/plan.md:3](../../projects/b2bsoft/genericui/openai-qna/work/038-message-feedback/plan.md) пов’язує ticket, base й design, а відмінну назву гілки явно пояснює рішенням оператора. [review.md:119](../../projects/b2bsoft/genericui/openai-qna/work/038-message-feedback/review.md) відокремлює fact corrections у ADR 0002/0013 від [promote list:158](../../projects/b2bsoft/genericui/openai-qna/work/038-message-feedback/review.md) для нового rewind-інваріанта; ADR 0032 на диску існує. Це доказ зв’язку артефактів, не підтвердження landing або повторний прогін gate.
- **generic-ui, наявні приклади:** [work/002-keda-scaling/review.md:27](../../projects/b2bsoft/genericui/generic-ui/work/002-keda-scaling/review.md) фіксує ADR 0020 разом із spec-оновленнями, а рядки 43–45 — перевірку four gates і supersede-посилань. [work/003-jobs-heartbeat-research/plan.md:84](../../projects/b2bsoft/genericui/generic-ui/work/003-jobs-heartbeat-research/plan.md) залишає рішення в per-job записі/коментарях і створює ADR лише за four gates. Це підтверджує, що журнал рішення та ADR — різні речі.
- **generic-ui, локальна адаптація:** [work/004-navigate-message-feedback/plan.md:9](../../projects/b2bsoft/genericui/generic-ui/work/004-navigate-message-feedback/plan.md) використовує design як план без дублювання; рядок 35 вимагає amendment ADR 0002, а рядки 43–50 віддають browser/live verification і review людині, без reviewer-агента. Отже загальну схему work не застосовувати механічно поверх контракту конкретної задачі. Передача перевірки людині не є доказом, що її вже виконано.
- **QnA, суперечність у шаблоні:** [adr-format.md:45](../../projects/b2bsoft/genericui/openai-qna/docs/adr-format.md) радить посилання ADR на design, тоді як рядки 67–72 забороняють такі посилання, а design видаляється при landing. Не переносити цю суперечність у глобальний шаблон; винести власнику як окреме виправлення. У цьому аудиті джерело не змінене.
- **Приклад не дорівнює поточному правилу:** QnA work/038 review описує перевірку HEAD із незакоміченими змінами ([review.md:3](../../projects/b2bsoft/genericui/openai-qna/work/038-message-feedback/review.md)), тоді як чинний work-скіл перед review вимагає committed state ([SKILL.md:59](../../projects/b2bsoft/genericui/openai-qna/.claude/skills/work/SKILL.md)). Дата/причина цієї різниці не встановлена; не трактувати старий приклад як дозвіл обійти чинний контракт.

Практична маршрутизація та погоджений handoff — у [workflow.md](workflow.md#routing). Приклади тут не оновлюють поточний статус автоматично.
