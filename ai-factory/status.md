---
title: "Поточний статус можливостей і джерела"
reviewed: 2026-10-16
---

[До точки входу](../docs/legacy/ai-factory-plan-entry.md) · [Статус](status.md#capabilities) · [Маршрути](workflow.md#routing) · [Задачі](roadmap.md#tasks) · [Практики репо](repo-evidence.md#repo-evidence) · [Історія](history.md#history)

<a id="capabilities"></a>

# Поточний статус можливостей і джерела

Початковий статус стосується доказів, зібраних 2026-10-14 та 2026-10-16; уточнення Cargo snapshot і onboarding від 2026-10-17 наведено окремо; цей рефакторинг не є новим runtime-аудитом. «Є джерело» ≠ «підключено у конкретному репо» ≠ «перевірено на задачі». «Не перевірено» не означає «відсутнє». Після нового пілоту оновлюй відповідний рядок тут, не створюй другу таблицю в roadmap чи Shared.

Перевірено локальні скіли, їхні ресурси та Shared-довідники. Репозиторії dg/cargotrans-ui, CI, живі MCP, порти, секрети й деплої в початковому аудиті **не перевірялися**; пізніший Cargo live MCP proof нижче має окремі дату й scope. Старі результати нижче — історичні свідчення, не поточний PASS.

| Шар | Чинне джерело / стан |
|---|---|
| Виконувані скіли | `~/.agents/skills/`: 60 SKILL.md поза synced, ще 22 у synced; числа — знімок аудиту, не число унікальних команд |
| Спільний доступ | `~/.claude/skills` і `~/.cursor/skills` — симлінки на `~/.agents/skills` |
| Shared | `~/vaults/global/skills` і `~/vaults/global/prompts` — окремі Markdown-довідники, **не** симлінки на виконувані скіли; автоматичну синхронізацію не підтверджено |
| Vault-підключення | `4 - Shared` у cassiopeia, cargotrans-ui, courses і diagram-hierarchy веде до `~/vaults/global`; це підтверджує шлях, а не роботу MCP |
| Правила | `~/vaults/global/rules` → `~/.agents/rules`; конфігурації й правила цим редагуванням не змінюються |
| Шпаргалка | [skills-cheatsheet.md](../docs/guides/skills-cheatsheet.md); оновлена разом із Shared, але поведінку задає відповідний SKILL.md |
Окремий вузький CRG-прохід 2026-10-16 UTC доповнив цей початковий аудит: live stdio/schema, host discovery, fixture та ізольовані source snapshots перевірено; source/active graph replacement, CI/deploy й model API не запускалися. Деталі — [CRG](crg.md), ручні кандидати моделей — [models.md](models.md).

## Переносиме підключення

[Onboarding](onboarding.md) містить checklist, manifest і read-only helper. Його локальні fixtures та незалежне forward-review перевіряють обмежений контракт підключення, не runtime Claude/Codex discovery, hooks, MCP або model access. Файл/симлінк — лише detected; configured і behavior-tested потребують окремих доказів. Неперевірені bindings лишаються unresolved.

## Єдиний реєстр

| Можливість / ID | Джерело існує | Інтегровано в репо | Перевірено на задачі | Доказ і дата / межа |
|---|---|---|---|---|
| CRG 2.3.6 | Встановлений пакет і 4 виправлені скіли | Codex: 3 read registrations enabled; Claude Cargo: crg-cargo-read Connected; попередні Claude Courses/Cassiopeia збережено | Нові 4 registrations: рівно 12 tools, прямий build dispatch denied; попередні fixture/snapshot proofs збережено; Go impact false-negative | [CRG proofs і межі](crg.md): Cargo active snapshot 2026-10-17 / stage / 137e19df: 1212 files, 0 mismatch/deleted; live MCP stats/callers PASS. Інші графи — лише історичні виміри; backups валідні |
| Три ролі моделей | [models.md](models.md), ручний контракт | Автоматичного routing немає; defaults не змінено | Model API/benchmark не запускалися | Bindings — per-host/session inventory; candidate/catalog, entitlement і budget окремо; непідтверджені UNBOUND |
| E1.1 [cto-research](../skills/plan/cto-research/SKILL.md) | Так, глобальний SKILL.md | dg/cargotrans-ui: не перевірено; для spec-flow підтверджено лише глобальні зв’язки | Новий пілот не проводився | Аудит 2026-10-14. Свіжість: базовий коміт, HEAD, staged/unstaged і релевантні untracked; без валідної бази — повторне збирання. Інструкції проєкту не перезаписуються. |
| E1.2 [plan-critique](../skills/plan/plan-critique/SKILL.md) | Так, глобальний SKILL.md | dg/cargotrans-ui: не перевірено; для spec-flow підтверджено лише глобальні зв’язки | Новий пілот не проводився | Аудит 2026-10-14. Скіл існує; новий прогін на проєкті не проводився. |
| E1.3 [plan-defense](../skills/plan/plan-defense/SKILL.md) | Так, глобальний SKILL.md | dg/cargotrans-ui: не перевірено; для spec-flow підтверджено лише глобальні зв’язки | Новий пілот не проводився | Аудит 2026-10-14. Скіл існує; новий прогін на проєкті не проводився. |
| E1.4 [acceptance-spec](../skills/plan/acceptance-spec/SKILL.md) | Так, глобальний SKILL.md | dg/cargotrans-ui: не перевірено; для spec-flow підтверджено лише глобальні зв’язки | Новий пілот не проводився | Аудит 2026-10-14. Скіл існує; застосування в конкретному репо не перевірялося. |
| E1.5 [ship-report](../skills/ship/ship-report/SKILL.md) | Так, глобальний SKILL.md | dg/cargotrans-ui: не перевірено; для spec-flow підтверджено лише глобальні зв’язки | Новий пілот не проводився | Аудит 2026-10-14. Скіл існує; старе «немає» в історії більше не описує global. |
| E1.6 [post-deploy-check](../skills/ship/post-deploy-check/SKILL.md) | Так, глобальний SKILL.md | dg/cargotrans-ui: не перевірено; для spec-flow підтверджено лише глобальні зв’язки | Новий пілот не проводився | Аудит 2026-10-14. Скіл існує; живий деплой не перевірявся. |
| E1.9 [cto-agenda](../skills/plan/cto-agenda/SKILL.md) | Так, глобальний SKILL.md | dg/cargotrans-ui: не перевірено; для spec-flow підтверджено лише глобальні зв’язки | Новий пілот не проводився | Аудит 2026-10-14. Скіл існує; поточну продуктову чергу треба визначати в репо. |
| E1.10 [repo-bootstrap](../skills/utils/repo-bootstrap/SKILL.md) | Так, глобальний SKILL.md | dg/cargotrans-ui: не перевірено; для spec-flow підтверджено лише глобальні зв’язки | Новий пілот не проводився | Аудит 2026-10-14. 11 позицій інвентарю, включно з 5а: задачі/борг/архів; перевірка за замовчуванням, ініціалізація окремо. |
| E2.1/E2.2/E2.6 (global) [spec-flow](../skills/deliver/spec-flow/SKILL.md) | Так, глобальний SKILL.md | dg/cargotrans-ui: не перевірено; для spec-flow підтверджено лише глобальні зв’язки | Новий пілот не проводився | Аудит 2026-10-14. Є сайд-ефекти/міграція/rollback, acceptance-spec, GATE 2 critique+defense+конституція, незалежний рецензент і звіт. Це не підтверджує стан локальних копій у репо. |
| UI: design-pass та допоміжні лінзи | Так, [design-pass](../skills/design-pass/SKILL.md), frontend-design, anti-slop-design, ux-review, interface-review | Глобальні посилання є; автоматичну інтеграцію в репо не підтверджено | Реальний UI-пілот не проводився | Аудит 2026-10-14; метод і критерії — [workflow](workflow.md#ui) |
| E1.7: multi-model-roles | Є історичний запис про rule; повторно не перевірено цим проходом | Не підтверджено, що правило застосовується в цільових репо | Новий поведінковий прогін не проводився | [Історія 2026-08-25](history.md#history); поведінковий DoD — roadmap |
| E1.8: eval | Доступний під час аудиту [Codex skill-creator](../../.codex/skills/.system/skill-creator/SKILL.md); Claude-плагін не підтверджено | Не перевірено | Eval не виконувався в цих проходах | 2026-10-14; завдання E1.8 |
| QnA: локальний work | Так, [work/SKILL.md](../../projects/b2bsoft/genericui/openai-qna/.claude/skills/work/SKILL.md) | Так, документований зв’язок із work/README і agent prompts | Є записаний приклад work/038; незалежного повторного прогону не було | Read-only огляд 2026-10-16, [докази](repo-evidence.md#repo-evidence) |
| generic-ui: файловий work і prompt-скіли | Так, work/README та validate-spec/analyze-specs/pre-qa-review | Так, документовані посилання зі specs/README; work опційний | Є записані приклади work/002–004; повторного прогону не було | Read-only огляд 2026-10-16, [докази](repo-evidence.md#repo-evidence) |
| generic-ui: role-*/mode-* | SKILL.md не підтверджені у перевірених місцях | Згадані як опційні; виконуваність не підтверджена | Не перевірено | Read-only огляд 2026-10-16; не оголошувати встановленими |
| E0: Obsidian dg | Vault і Shared-лінк є; інші компоненти повторно не перевірено | Живий MCP/порти не перевірено | Не перевірено | Аудит шляхів 2026-10-14; [старі записи](history.md#history) |
| E2/E3: інтеграція конвеєра в cargotrans-ui/dg | Cargo має локальний adapter, review і task workflow; dg тут не перевірено | Cargo документально інтегровано; discovery/runtime окремо | Cargo052 має pinned test-only review + pattern supplement; не повторювався цим onboarding | Читання наявних evidence, не новий product/QA/landing PASS; [snapshot CRG](crg.md#cargo-active-snapshot) |
| E4: PR-рев’ю в CI | Є історичний запис про workflow; тепер не перевірено | Не перевірено; історично job пропускався без секрету | Новий PR-прогін не проводився | [Історичні записи E4](history.md#ci-history) |
| E5: post-deploy | Є історичні записи про scripts/workflow; тепер не перевірено | Не перевірено | Історичний dg smoke; cargo flow тоді не пройдені; нових запусків немає | [Історичні записи E5](history.md#ci-history) |

## Оновлення доказів

Фіксуй репозиторій, шлях/ревізію та dirty state, дату, фактично виконану команду або переглянутий артефакт. Зміна коду/контракту після перевірки може вимагати повторної перевірки; старий PASS не переноситься автоматично. Для перевірок використовуй PASS / FAIL / BLOCKED / N/A із підставою; стани наявності/інтеграції не підміняй цими verdict.

## Session-size helper — 2026-10-17

Реалізація й disposable fixtures: [контракт](../docs/legacy/session-size.md). Глобальні command hooks підготовлено для Claude 2.1.302 та Codex 0.156.1: SessionStart/UserPromptSubmit/PostToolUse/Stop. Факт запису registration не означає execution: Codex потребує review/trust у /hooks; trust і security permissions автоматично не змінюються. Live CLI/model sessions не запускалися. 5 000 000 bytes — soft threshold; complete semantic checkpoint залежить від агента, автоматичного restart немає.
