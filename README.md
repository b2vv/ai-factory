# AI Factory — 0.7.0 candidate

- **[Усі 73 оригінальні скіли](skills/)** — один canonical editable tree; групи, references, scripts, assets і synced variants збережені.
- **[Повний AI Factory plan](ai-factory/ai-factory-plan.md)** — workflow, lifecycle, status, roadmap та історичні джерела.
- [Спільні правила](rules/) · [Runtime helpers](runtime/README.md) · [Явні policy adapters](adapters/README.md)

Статус: author-validated candidate; незалежне review і native CLI discovery/activation не підтверджені. Структура не надає дозволу на installs, hooks, MCP, model changes чи product actions. Локальні project contracts і поточне доручення мають пріоритет.

## Один файл — одна роль

`skills/` містить originals, не скорочені portable заміни. `ai-factory/` — повний source plan. `docs/portable/` та `adapters/legacy-planning/` — явно окремі успадковані portable profiles; їхні поведінкові відмінності не злиті мовчки. `runtime/legacy/` зберігає original helper behavior, тоді як portable review/session helpers мають hardened Git reads та explicit store. Тести обох варіантів лежать у `tests/`.

84 внутрішні source definitions accounted: 73 включені, 11 synced-наборів мають явну outside-Service copy restriction і залишаються лише в [provenance inventory](provenance/source-map.json). Зовнішні symlink targets і `b2b*` не додаються. [Походження й notices](PROVENANCE.md).

## Безпечне використання та оновлення

[Migration guide](docs/migration-0.4.md) пояснює exact paths, component selection, variants і перехід зі старої layout. [Installer contract](docs/portability-design.md) зберігає explicit plan, hash guards, backups і guarded rollback.

```sh
python3 -B tools/verify_release.py --root "$PWD"
python3 -B tools/run_tests.py --previous-release '/absolute/immutable/626fd68-release'
python3 -B tools/kit.py plan --package "$PWD" --root '/absolute/dedicated/toolkit' --component collection --component planning --component review --component session-guard
```

`collection` — compatibility component, що включає повні skills та explicit legacy helpers; `skills` можна вибрати окремо. `graphify` містить єдиний canonical graphify skill, а `skills` залежить від нього. `planning` додає чотири **не-discovered adapter documents**, не новий SKILL tree. Installer розв’язує оголошені component dependencies, відхиляє cycles/unknown components; no network/tool installs/host registration.

Нові інсталяції та upgrades — лише у dedicated root, не поверх `~/.agents`, `~/.claude` або product repo. Передавайте повний бажаний component set. Native discovery не доведена exact-file читанням; вибирайте qualified skill paths. `docs`, `import-memory`, `morning`, `skill-creator` мають по дві збережені synced-версії; не активувати однойменні variants одночасно без явного mapping.

Product pins і immutable caches оновлюються окремим погодженим rollout; публікація shared release сама їх не перемикає. [Повна карта всіх 350 старих файлів](provenance/layout-migration.json) фіксує moved/deduplicated/revised destinations; жоден original skill не втрачено.

## Pre-code readiness

[One checkpoint per task](ai-factory/pre-code-checkpoint.md): acceptance, proportional grilling, dependencies, scoped impact and READY/BLOCKED. Small/resume remain proportional. Optional offline declaration/index validation and regression fixtures are included; no automatic CI or agent enforcement is claimed.

Versioned [plan critic prompt](prompts/plan-critic.md), exact plan/snapshot binding and material-change rules extend that same checkpoint. No extra tracker, native registration or automatic reviewer dispatch.

[Documentation hygiene](ai-factory/documentation-hygiene.md) уточнює чинний onboarding: factual drift, symlink routing, hook/CI coverage та scope provenance. Це документаційне доповнення; originals і runtime behavior незмінені.

[Selective constraint adoption](ai-factory/constraint-adoption.md) adds one skill and offline evidence checks, preserving existing Storybook/E2E and reviewer routes. Live model behavior and native discovery remain NOT_TESTED.
