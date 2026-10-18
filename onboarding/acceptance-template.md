# Acceptance підключення AI Factory

[Вхід](../docs/onboarding.md) · [Change protocol](change-protocol.md)

Встав у наявний task record; не створюй дубль report заради шаблону. Усі поля заповнюються фактами або UNKNOWN/BLOCKED/N/A з причиною.

- Root / branch / HEAD / relevant dirty scope / дата:
- Авторизація та exact files; збережені stack/workflow/contracts; owner:
- Startup routing: purpose → new subagent / named existing session / unresolved; owner/reference, current selection evidence, delivery owner, resource coordination; no duplicate spawn/message.
- Review package ID: task/author/reviewer IDs, pinned scope/diff/acceptance/contracts, raw checks/exits/results; response status; final-delta scope and accepted unchanged evidence. Missing response/evidence → NOT_TESTED/BLOCKED. See [contract](../docs/review-handoff.md).
- Manifest/preflight evidence; ручний огляд semantic conflicts і side effects:
- Canonical adapter/entry; baseline/applied hashes, backup/receipt, diff:
- Obsidian: vault/Shared paths → resolved canonical target; note/report path; перевірена актуальність/source/date; поточний scope дозволу; SYNCED/NOOP/PENDING/BLOCKED/N/A + evidence або причина/fallback/наступна дія. Shared target записується один раз; visibility не є runtime чи майбутнім дозволом.
- Repeat: NOOP або conflict BLOCKED; restore rehearsal evidence (лише fixture), фактичний restore якщо доручений:

| Host/session | Exact skill file | Discovery + source/date | Native tools | Invocation | Required review route/executor |
|---|---|---|---|---|---|
| ... | ... | UNKNOWN або dated evidence | UNKNOWN/перелік | NOT_TESTED або proof | exact fallback + references, independent verdict або BLOCKED |

| Роль | Host/session catalog provenance | Candidate status | Entitlement | Budget | Binding / next step |
|---|---|---|---|---|---|
| Потрібні ролі лише | ... | unknown/missing/listed | unknown/available/unavailable | unknown/approved/denied | UNBOUND до підтвердження; без model probes |

| Capability/check | detected | configured | behavior-tested | Evidence/revision + limitation |
|---|---|---|---|---|
| Adapter/pointers | ... | ... | ... | ... |
| Required independent review | ... | ... | ... | raw verdict і pinned diff; author self-review не заміна |
| Obsidian/shared note | ... | ... | ... | actual targets, sync verdict, source/revision; pending не дорівнює synced |
| Optional CRG | ... | ... | ... | registration/list/live query/root/HEAD/hash/coverage окремо; files/rg fallback |
| Docs/helper fixtures | ... | ... | ... | synthetic scope, не CLI/runtime |
| Product/UI/hook/MCP/model runtime | ... | ... | ... | NOT_TESTED без дозволеного запуску |

Для checks: PASS/FAIL/BLOCKED/N/A з причиною. Forward-test свіжого контексту: new minimal, existing own workflow, partial, missing skill/CRG, stale CRG, unavailable model, hosts differ, normative conflict, повтор onboarding. Зберегти raw prompt/result; не давати очікуваного verdict reviewer наперед.

Невирішені owner decisions: джерела конфлікту → impact → залежна BLOCKED частина → власник/одна наступна дія. Інші дозволені частини можуть бути configured; не називай усе підключення повністю завершеним, якщо required gate лишився BLOCKED. За відсутності невирішених required decisions — documentary acceptance; runtime статус окремо.

Підсумок: фактичні changed files, виконані перевірки, незалежний review, що не запускалось, залишкові рішення, короткий startup prompt. Немає гарантії, що довільний репозиторій не потребуватиме людських policy-рішень.
