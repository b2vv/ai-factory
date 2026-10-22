# AI Factory — 0.7.0-rc.1

- **[Усі 73 оригінальні скіли](skills/)** — один canonical editable tree; групи, references, scripts, assets і synced variants збережені.
- **[Повний AI Factory plan](ai-factory/ai-factory-plan.md)** — workflow, lifecycle, status, roadmap та історичні джерела.
- [Спільні правила](rules/) · [Runtime helpers](runtime/README.md) · [Явні policy adapters](adapters/README.md)

Статус: release candidate. Scanner milestone пройшов незалежне code/runtime review для Docker-only linux/amd64 запуску на macOS; це не прийняття всього backlog, native agent discovery чи постійної активації проєктів. Фінальний release-пакет потребує окремого hash-bound review перед tag/publication. Структура не надає дозволу на installs, hooks, MCP, model changes чи product actions. Локальні project contracts і поточне доручення мають пріоритет.

## Почати через AI: три сценарії

Цей repository містить workflow, skills, templates та offline helpers; він не встановлює сам Codex/Claude, мову проєкту, MCP/graph servers чи моделі. Локальні helpers не потребують додаткового SaaS; доступ до AI залишається вашим чинним account/ліцензією, не обіцянкою безкоштовних model calls.

| Ситуація | Маршрут і готовий prompt |
|---|---|
| Наявний проєкт | [AI-assisted onboarding](docs/guides/ai-assisted-onboarding.md#existing-project): read-only inventory → scoped adapter diff → погоджений apply → окремий host proof |
| Порожній проєкт | [Empty project](docs/guides/ai-assisted-onboarding.md#empty-project): спочатку продукт/стек/acceptance, потім мінімальні instructions; автоматичного app bootstrap немає |
| Інший developer / машина | [New machine](docs/guides/ai-assisted-onboarding.md#new-machine): trusted private source → dedicated package root → selected host exposure → project adapter; без копіювання credentials |

**Що куди ставити.** Повний перевірений package — в окремий керований каталог, наприклад `~/project-data/ai-factory-kit`. `~/.agents/skills` — канонічний спільний host-facing store за конвенцією цього набору; `~/.claude/skills` може використовувати те саме джерело лише після перевірки конфліктів і підтримки host. `kit.py` НЕ публікує skills туди й навмисно відхиляє `~/.agents`, `~/.claude` або каталог `skills` як install root. Немає безпечної команди «встановити все в home». [Карта шарів і discovery](docs/guides/ai-assisted-onboarding.md#destinations) пояснює exact-file fallback, варіанти/колізії та межі автоматизації.

**Перед будь-яким запуском:** прочитати source/provenance і effects scripts; checksum не є підписом або sandbox. Не передавати агенту токени, `.env`, keychain чи сесійні логи. [Security adoption](docs/guides/ai-assisted-onboarding.md#security-proposed) поки **PROPOSED**, не installed/enforced.

Технічний мінімум helpers: Python **3.9+**, POSIX filesystem; Git потрібний review helpers/fixtures. macOS — поточне середовище перевірки; Linux — **NOT_TESTED**, Windows — **UNSUPPORTED** (`fcntl`). Інструменти продукту визначає його стек; Node/npm/Docker не потрібні для offline install. Точні CLI versions/discovery/runtime capabilities перевіряються на цільовій машині, не успадковуються з цього README.

Задачі виконуються на [task branch головного repo](ai-factory/workflow.md#task-branches), один writer, без автоматичного worktree/clone для задач. Чужий/невідомий dirty WIP → STOP і координація; без stash/reset/commit для очищення. Runtime/test isolation — окремо. Початкове отримання trusted AI Factory source для нової машини не є створенням per-task clone продукту.

## AI Factory як локальний tooling агента в проєкті

Factory можна організувати як локальний інструмент: pinned workflow/skills окремо від
налаштувань конкретного проєкту. **Рекомендована схема**, якщо вона не конфліктує з
наявним підключенням:

```text
<project>/
  .ai/
    factory/   # керований snapshot обраної ревізії Factory; не редагувати вручну
    project/   # локальні paths, adapter/config та pin; зберігати під час update
    README.md  # як агенту почати/resume, де правила, задачі та докази
```

Ці destinations можна залишити локальними й ignored. Спочатку перевірити, що вже
tracked і що містить `.ai/`: **gitignore не прибирає вже tracked файли**. Не ігнорувати
всю `.ai/` навмання, не виконувати автоматичний untrack і не мігрувати наявні
AGENTS/adapter/pin/symlinks. Для нового setup обрати лише точні погоджені ignore paths.
Не зберігати тут secrets, tokens, `.env`, auth/session stores; ignored не означає захищене.

**Агенту потрібен явний entrypoint.** Довільна `.ai/` не гарантує discovery чи виконання
workflow. Користувач може додати короткий tracked pointer з root README/AGENTS,
налаштувати підтримуваний саме його агентом entrypoint або кожного разу починати з
«Прочитай `.ai/README.md` і застосуй указаний там workflow до моєї задачі». README для
людини не обов'язково автоматично читається агентом. Native skill invocation та явне
читання файла — різні докази; жоден pointer не гарантує дотримання правил.

### Що реалізовано, а що потрібно перевірити

[Чинний installer](docs/portability-design.md) `tools/kit.py` працює з явним dedicated
absolute target: plan/install/update/rollback, selected components, hashes, backups,
receipts і guarded NOOP. Він **не має окремого `.ai` mode**, не генерує project config,
не змінює gitignore/AGENTS і не реєструє skills у host. Ця layout-рекомендація сама
по собі не є підтвердженим installer/runtime acceptance.

До встановлення агент має прочитати source/provenance та контракт **обраної ревізії**,
перевірити підтримку target `.ai/factory/`, canonical paths без symlink components,
відсутність перетину source/target і unmanaged collisions, потрібні components та
writer window. Target — тільки dedicated subtree, не корінь продуктового repository
і не вся `.ai/`. Якщо обрана версія не підтримує такий target, залишити залежний setup
BLOCKED або погодити вже підтримуваний зовнішній dedicated root; не обходити guards.
Не створювати другий installer. [Onboarding guide](docs/guides/ai-assisted-onboarding.md)
і [read-only preflight](docs/onboarding-helper.md) лишаються чинним маршрутом.

Для project-local declarations повторно використати наявні adapter,
`ai-factory-manifest.json` і `ai-factory-package.json`, якщо вони вже є. Для нового
setup погодити їхні paths у `.ai/project/` на основі [manifest example](examples/onboarding/manifest.json)
та [adapter template](templates/adapter-full.md), без другого джерела тих самих правил.
Не переносити локальні overrides у `.ai/factory/`: update має змінювати лише managed
package target і залишати project config, task history та required gates незмінними.

Pin — точний commit обраного trusted source, release manifest/hash і component set,
а не floating branch або `latest`. Приклад наявного exact pin:
`1e5411f12677c45fd67b0900c77eb418a214d065` (merged scanner milestone до release); статус candidate не є
незалежним прийняттям усіх можливостей. Перед використанням перевірити конкретний
release, потрібні hashes і [provenance](PROVENANCE.md). Hash із того самого невідомого
архіву не автентифікує автора. Незакомічений checkout, зокрема scanner additions,
не підміняє pinned workflow release й не активується локальним setup.

**Нова машина:** ignored files не приходять із clone. Зберегти окремо несекретний
bootstrap record із trusted source/commit, manifest hash, components, layout і backup
локального config — у погодженому приватному backup або як мінімальний tracked manifest
за вибором команди. Відновити той самий pin через перевірений setup; custom config не
можна відтворити лише з Factory core. Повний trusted source зберігається окремо від
встановленого subset; metadata subset не робить його повним release. Новий release
отримується й застосовується лише явним update із review diff, backup та preservation
checks, без автоматичного переписування локальних налаштувань.

### Промпт 1 — перевірити й безпечно підключити локально

```text
Підготуй AI Factory як локальний tooling для <PROJECT_ROOT>.
Trusted source: <SOURCE + EXACT COMMIT + MANIFEST HASH>.
Спочатку лише read-only: прочитай локальні AGENTS/CLAUDE, чинний adapter/pin,
README, git tracked/ignored state, relevant WIP і ownership. Не читай secrets.
Не припускай, що підключення відсутнє, і не мігруй existing setup автоматично.
Прочитай root README, onboarding guide, installer contract і source обраного
Factory release; перевір hashes/provenance та підтримку рекомендованих
.ai/factory/, .ai/project/, .ai/README.md. Не вигадуй .ai installer mode.
Використай наявні kit plan, preflight та change protocol, де вони застосовні.
До записів покажи точні paths/components/entrypoint, ignore changes за потреби,
conflicts, diff, backup/rollback і що залишиться локальним. Немає підтримки
або writer window — BLOCKED залежний setup, без обходу guards.
Лише після погодження конкретного plan застосуй цей setup і перевір hashes,
local preservation та repeat NOOP. Не запускай product tools/scanners,
installs залежностей, hooks/MCP, не міняй permissions або model defaults.
```

### Промпт 2 — почати або продовжити задачу

```text
Прочитай <PROJECT_ROOT>/.ai/README.md або чинний погоджений entrypoint,
локальні instructions/config та pinned Factory workflow. Перевір pin і paths.
Задача: <МЕТА або ID + ЧИННИЙ PLAN/REPORT>.
Покажи scope/acceptance, root/branch/HEAD/relevant WIP, writer, small/full/resume,
review route і pre-code READY/BLOCKED. Збережи локальні contracts та gates.
На resume звір поточні inputs і докази; не відкривай незмінене завершене заново.
Виконуй лише доручений scope; evidence і handoff — у наявних task artifacts.
Відсутній shared файл/required review — конкретний BLOCKED, не вигаданий PASS.
Не оновлюй core/pin/config і не запускай scanner лише через читання workflow.
```

### Промпт 3 — перевірено оновити package

```text
Підготуй update локального AI Factory до <NEW EXACT COMMIT + MANIFEST HASH>.
Спочатку read-only звір чинний pin, managed state, повний бажаний component set,
новий trusted source/provenance, relevant WIP і writer window.
Перевір підтримку update у цій версії; використай чинний kit plan/update,
не новий installer. Покажи diff/additions/removals/conflicts, backup і rollback.
Зафіксуй baseline hashes project-local config/README/entrypoints; не переписуй
їх із core template. Несумісність локального adapter — окрема явна пропозиція.
Лише після погодження exact plan онови managed package target і погоджену
pin metadata; збережи решту .ai/project/ та чинні локальні правила/task history.
Перевір final hashes, local preservation і повторний NOOP. Concurrent changes
або unmanaged collision — BLOCKED, без force/reset/untrack. Поверни receipt,
перевірки, limitations і next action; без product rollout/scans/commit/push.
```

## Один файл — одна роль

`skills/` містить originals, не скорочені portable заміни. `ai-factory/` — повний source plan. `docs/portable/` та `adapters/legacy-planning/` — явно окремі успадковані portable profiles; їхні поведінкові відмінності не злиті мовчки. `runtime/legacy/` зберігає original helper behavior, тоді як portable review/session helpers мають hardened Git reads та explicit store. Тести обох варіантів лежать у `tests/`.

84 внутрішні source definitions accounted: 73 включені, 11 synced-наборів мають явну outside-Service copy restriction і залишаються лише в [provenance inventory](provenance/source-map.json). Зовнішні symlink targets і `b2b*` не додаються. [Походження й notices](PROVENANCE.md).

## Безпечне використання та оновлення

[Migration guide](docs/migration-0.4.md) пояснює exact paths, component selection, variants і перехід зі старої layout. [Installer contract](docs/portability-design.md) зберігає explicit plan, hash guards, backups і guarded rollback.

```sh
# Source checkout includes an exact, inert research archive; export only release files.
# Choose a new destination outside this checkout. No archive scripts are executed.
EXPORT_DIR="$(python3 -c 'from pathlib import Path; print(Path.cwd().parent / "ai-factory-release-export")')"
python3 -B tools/export_release.py --root "$PWD" --destination "$EXPORT_DIR"
python3 -B "$EXPORT_DIR/tools/verify_release.py" --root "$EXPORT_DIR"
TOOLKIT_DIR="$(python3 -c 'from pathlib import Path; print(Path.cwd().parent / "ai-factory-toolkit-plan-only")')"
python3 -B "$EXPORT_DIR/tools/kit.py" plan --package "$EXPORT_DIR" --root "$TOOLKIT_DIR" --component collection --component planning --component review --component session-guard
```

Цей приклад виконує export, перевірку та read-only installer plan; не install. Destination export має бути новим, toolkit root — окремим dedicated каталогом. Для повного regression suite використайте `python3 -B "$EXPORT_DIR/tools/run_tests.py" --previous-release /absolute/path/to/verified-previous-release` лише після вибору реального immutable previous release. Placeholder не є готовою командою; archive scripts не запускати.

`collection` — compatibility component, що включає повні skills та explicit legacy helpers; `skills` можна вибрати окремо. `graphify` містить єдиний canonical graphify skill, а `skills` залежить від нього. `planning` додає чотири **не-discovered adapter documents**, не новий SKILL tree. Installer розв’язує оголошені component dependencies, відхиляє cycles/unknown components; no network/tool installs/host registration.

Нові інсталяції та upgrades — лише у dedicated root, не поверх `~/.agents`, `~/.claude` або product repo. Передавайте повний бажаний component set. Native discovery не доведена exact-file читанням; вибирайте qualified skill paths. `docs`, `import-memory`, `morning`, `skill-creator` мають по дві збережені synced-версії; не активувати однойменні variants одночасно без явного mapping.

Product pins і immutable caches оновлюються окремим погодженим rollout; публікація shared release сама їх не перемикає. [Повна карта всіх 350 старих файлів](provenance/layout-migration.json) фіксує moved/deduplicated/revised destinations; жоден original skill не втрачено.

## Pre-code readiness

[One checkpoint per task](ai-factory/pre-code-checkpoint.md): acceptance, proportional grilling, dependencies, scoped impact and READY/BLOCKED. Small/resume remain proportional. Optional offline declaration/index validation and regression fixtures are included; no automatic CI or agent enforcement is claimed.

Versioned [plan critic prompt](prompts/plan-critic.md), exact plan/snapshot binding and material-change rules extend that same checkpoint. No extra tracker, native registration or automatic reviewer dispatch.

[Documentation hygiene](ai-factory/documentation-hygiene.md) уточнює чинний onboarding: factual drift, symlink routing, hook/CI coverage та scope provenance. Це документаційне доповнення; originals і runtime behavior незмінені.

[Selective constraint adoption](ai-factory/constraint-adoption.md) adds one skill and offline evidence checks, preserving existing Storybook/E2E and reviewer routes. Live model behavior and native discovery remain NOT_TESTED.

## Offline scanner candidate

[Product-neutral scanner baseline](runtime/scanners/README.md) adds an explicit runner, isolated Compose template, original direct-eval rules and a separate DB snapshot updater. Shipped image/DB pins are unresolved and block execution. Author unit/mock checks do not establish real scanner, read-only cache or Yarn dev-dependency acceptance; independent review remains pending. No product rollout or automatic activation.
