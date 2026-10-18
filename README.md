# AI Factory — 0.4.0 candidate

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

Чинні Cargo/Courses/Cassiopeia pins і readonly cache `626fd68` не змінено. Вони продовжують стару layout до окремого погодженого upgrade. [Повна карта всіх 350 старих файлів](provenance/layout-migration.json) фіксує moved/deduplicated/revised destinations; жоден original skill не втрачено.
