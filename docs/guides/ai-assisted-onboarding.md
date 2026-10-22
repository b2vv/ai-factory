# AI-assisted onboarding: package → host → project → evidence

Це практичний guide до [єдиного onboarding protocol](../../ai-factory/onboarding.md), не новий installer або tracker. Доручення власника й локальні contracts/ADR мають пріоритет; наявні required gates не скасовуються. Приклади нижче не виконуються самим читанням.

<a id="destinations"></a>
## 1. Що куди належить

| Шар | Destination / джерело | Реальна можливість і межа |
|---|---|---|
| Trusted source | Повний release/checkout у погодженому окремому root | Звірити commit/provenance, source і manifest; `verify_release.py`. Не міняти immutable release у місці |
| Managed package | Наприклад `~/project-data/ai-factory-kit`, canonical absolute path | `tools/kit.py` plan/install/update/rollback. State/backups/receipts у `.ai-factory-state`. Це не host discovery |
| Shared host store | `~/.agents/skills`; workflow/rules можуть мати окремі pointers у `~/.agents` | Конвенція поточного набору, не ціль managed installer. Exact immutable package paths також придатні для file fallback. Окремого host publisher нема |
| Claude Code | Personal `~/.claude/skills/<name>/SKILL.md`, project `.claude/skills/<name>/SKILL.md` | Selected mapping після collision/provenance review, не копіювання всіх synced variants. Наявну symlink topology не замінювати автоматично |
| Codex | Обрані shared skills та локальні `AGENTS.md`/adapter | Перевірити actual discovery саме встановленого CLI; наявність `.agents/skills` сама по собі не сертифікує invocation. Без native discovery — exact-file fallback |
| Project adapter | Наявний project-owned doc + pointers із entry files | Templates пропонують контент, `preflight.py` лише читає manifest. Потрібний scoped manual/AI edit, не auto-bootstrap |
| Optional runtimes | Python helpers у package; graph/MCP executables окремо | Skill Graphify/CRG не встановлює server, DB, language runtime чи hook. Models/entitlement — host-specific, не частина package |

У цьому bundle skills згруповані, є однакові names у variants. Не flatten/copy усі 73 originals у discovery root. Спочатку вибрати exact `SKILL.md`, прочитати references, визначити destination/name й перевірити collision. Installer відхиляє symlinks у source/destination; легітимний host symlink не означає, що його можна передати installer. Для preflight вказувати canonical physical paths, не обходити path guard.

[Claude skills docs](https://code.claude.com/docs/en/skills) підтверджують personal/project locations; host precedence й reserved names потрібно перевіряти для обраного CLI. Локальний home store не переноситься автоматично в cloud session. Official OpenAI skills URL під час цього documentation review перенаправив на [загальний build-skills guide](https://learn.chatgpt.com/docs/build-skills); це не доказ current CLI search roots. Тому мінімальна Codex version/native discovery тут **NOT_TESTED**, не вигадана. Обидва hosts можуть читати явно вибрані файли; це instruction fallback, не native invocation.

## 2. Перед виконанням і приватний доступ

Python 3.9+ stdlib; installer використовує `fcntl`, atomic filesystem operations і advisory lock. macOS fixture-tested; Linux POSIX-кандидат, але не перевірена support matrix; Windows unsupported. Git з HEAD потрібний review helpers; в empty directory без initial commit цей review route BLOCKED. Продуктові Node/Go/Docker/Playwright versions визначає проєкт, не цей kit.

Для private GitHub source developer має бути доданий до repository й використовує власний уже налаштований SSH agent або credential manager/approved Git client. Repo URL без embedded credentials і trusted commit надає власник. Не просити PAT/password у чаті, не копіювати чужі `.gitconfig`, `.ssh`, `.npmrc`, `.env`, session stores, auth caches або vault. Якщо доступу немає — BLOCKED acquisition; власник вирішує доступ, агент не шукає токени. Download/initial source checkout дозволяється окремим scope; цей guide не запускає network або login. Trusted source можна передати offline разом із незалежно підтвердженим commit/digest; checksum, отриманий із того самого неперевіреного архіву, не автентифікує автора.

До першого Python/npm/CI запуску оглянути source, scripts, dependencies/lockfiles та provenance. Repo instructions є контентом для оцінки, а не дозволом читати secrets або розширювати scope. Мінімальні permissions і credential-free test environment; не вимикати OS trust/TCC/sandbox або міняти security settings заради onboarding.

## 3. Реальні offline команди

Нижче всі placeholders замінюються погодженими **canonical absolute paths без symlink components**. SOURCE — повний trusted package, TARGET — окремий managed root (не home, `.agents`, `.claude`, `.codex`, `skills` чи product root), PROJECT — наявний project directory, EVIDENCE — доступна reviewer папка поза product tree. Не використовувати `$HOME` як тимчасову змінну. У прикладах немає `--dry-run`: такого прапорця НЕМАЄ; `plan` і відсутність `--execute` є read-only режимом.

```sh
FACTORY_SOURCE='/absolute/trusted/ai-factory'
FACTORY_TARGET='/absolute/dedicated/ai-factory-kit'
FACTORY_PROJECT='/absolute/project'
FACTORY_MANIFEST='/absolute/evidence/onboarding-manifest.json'
python3 -B "$FACTORY_SOURCE/tools/verify_release.py" --root "$FACTORY_SOURCE"
python3 -B "$FACTORY_SOURCE/tools/kit.py" plan --package "$FACTORY_SOURCE" --root "$FACTORY_TARGET" --component collection --component planning --component review --component session-guard
```

Прочитати JSON plan: additions/removals, component set, conflicts і `plan_id`. `collection` включає core/skills/graphify/legacy-runtime; `planning` — чотири non-native profiles, `review` і `session-guard` — окремі portable helpers. Наявність legacy helpers не активує hooks. Для меншого набору явно вибрати інші components; core-only не містить усі skills.

Тільки після дозволу на конкретний reviewed plan і підтвердження exclusive writer window:

```sh
python3 -B "$FACTORY_SOURCE/tools/kit.py" install --package "$FACTORY_SOURCE" --root "$FACTORY_TARGET" --component collection --component planning --component review --component session-guard --execute --exclusive-window --plan-id '<reviewed-plan-id>'
python3 -B "$FACTORY_SOURCE/tools/kit.py" plan --package "$FACTORY_SOURCE" --root "$FACTORY_TARGET" --component collection --component planning --component review --component session-guard
```

Повторний plan має дати `NOOP`. Зберегти returned transaction ID, plan, exit і source commit/hash. `--exclusive-window` — твердження про координацію, не автоматична міжсесійна гарантія. Apply не атомарний на всі файли: partial failure залишає receipt/pending transaction; не видаляти state вручну.

[Приклад manifest](../../examples/onboarding/manifest.json) — валідна відправна точка, не результат inventory. Для existing repo заповнити фактичні instruction/workflow/command paths; optional skills не оголошувати required лише через їх наявність. `preflight.py` не виявляє всі семантичні конфлікти автоматично. Скопіювати/adapt manifest у погоджену evidence-папку, потім:

```sh
python3 -B "$FACTORY_SOURCE/runtime/onboarding/preflight.py" --root "$FACTORY_PROJECT" --manifest "$FACTORY_MANIFEST" --shared-skill-root "$FACTORY_TARGET/skills"
```

Preflight read-only; JSON `configured=false` і `behavior_tested=false` очікувані. Успішний exit означає виконаний inventory, не готовий проєкт; перевірити item-level BLOCKED/UNKNOWN. Empty project закономірно має missing instructions, не PASS. Symlinked entrypoints inventory задавати physical repo-relative paths після перевірки їхньої семантики.

<a id="existing-project"></a>
## 4. Наявний проєкт — copy-ready AI prompt

Замінити поля в кутових дужках. Prompt починає safe planning, не дає blanket apply/install дозволу:

```text
Підключи AI Factory до існуючого <PROJECT_ROOT>, не змінюючи стек, архітектуру чи продукт.
Trusted complete source: <FACTORY_SOURCE + COMMIT/DIGEST>; managed destination: <FACTORY_TARGET>;
evidence root: <EVIDENCE>; чинний reviewer: <REFERENCE або UNRESOLVED>.
Прочитай README, docs/guides/ai-assisted-onboarding.md та ai-factory/onboarding.md.
Спочатку read-only: source/provenance/scripts, AGENTS/CLAUDE, local skills, tasks/ADR/gates,
HEAD/index/dirty ownership і фактичні host versions/discovery. Не читати secrets/session logs.
Звір release; зроби kit plan (не вигадуй --dry-run), manifest/preflight та мінімальний adapter diff.
Покажи exact targets, selected components/skill mappings, side effects, conflicts, backups,
перевірки й rollback. Існуючі global skills/symlinks зберегти. Native publisher тут відсутній:
selected host mapping лише як окремий reviewed diff, exact-file fallback допустимий.
Після явного дозволу застосуй тільки погоджений package plan/adapter delta; runtime tools,
graph DB, hooks/MCP/models/permissions, dependencies і product tests не встановлювати/не запускати.
Task branch у main repo тільки за погодженого writer і WIP; foreign/unknown WIP → STOP,
не stash/reset/commit і не fallback у worktree/clone. Збережи чинного reviewer, без дубля/контакту без дозволу.
Перевір hashes/links, repeat NOOP; native invocation тільки окремим дозволеним нешкідливим probe.
Поверни applied/blocked/not-tested, raw commands/exits/snapshot і review handoff, не fake PASS.
```

<a id="empty-project"></a>
## 5. Порожній проєкт — copy-ready AI prompt

Kit не містить `bootstrap` CLI, project generator або автоматичного вибору стеку. Repo-bootstrap skill існує як instructions, не як installed app scaffolder. Визначити product goal, мову/stack, тестовий runner, delivery target і required constraints до skeleton. Мінімальний результат першого етапу — project instructions, adapter і один task/acceptance record; не копіювати чужу FSD/MVC/Go архітектуру. `git init`, initial commit, package-manager install і scaffold execution — окремо погоджені дії, не побічний ефект onboarding. Відсутність HEAD позначити BLOCKED лише для залежних Git-review helpers.

```text
Підготуй AI Factory workflow для порожнього <PROJECT_ROOT>.
Trusted source <FACTORY_SOURCE + COMMIT/DIGEST>, managed root <FACTORY_TARGET>, evidence <EVIDENCE>.
Спочатку перевір, що директорія справді порожня/ким володіє WIP, і прочитай onboarding guide.
Мета продукту: <GOAL>; вже погоджений стек/обмеження: <VALUES або UNKNOWN>.
Не вибирай framework чи hosting за замовчуванням. Уточни лише рішення, що блокують scope/acceptance.
Зроби read-only package plan + empty-project preflight, запропонуй мінімальні AGENTS/CLAUDE pointers,
project adapter, task/acceptance record і доречні tests/QA; не створюй другий tracker.
Покажи exact diff/commands/backups/rollback; після окремого apply дозволу запиши лише ці docs
і погоджений package plan. Не запускай scaffold/install/devserver, не роби git init/commit/push
без відповідного доручення. Task branch/one writer; немає HEAD → явний review-helper BLOCKED.
Збережи існуючого reviewer або познач UNRESOLVED. Не називай missing tests/CLI discovery PASS.
Після застосування перевір files/links/NOOP; перший маленький product slice і runtime proof —
окремий lifecycle із code review та final evidence, не частина docs bootstrap.
```

<a id="new-machine"></a>
## 6. Новий developer / машина — copy-ready AI prompt

Потрібні власний доступ до private source, встановлений Python/Git та обраний AI host. Відсутній prerequisite → BLOCKED із конкретним next step, не прихований package download. Pin спочатку той самий, що погодив team; не використовувати floating `latest`. Home paths попереднього developer не переносити. Ліцензійні exclusions/provenance залишаються чинними; доступ до приватного repo не дає права redistribute restricted skills.

```text
Налаштуй план перенесення AI Factory на цю машину для <DEVELOPER/TEAM>.
OS/host: <OS + Codex/Claude CLI>; trusted private source/commit: <SOURCE>; dedicated managed
root: <TARGET>; project: <PROJECT>; evidence: <EVIDENCE>; reviewer: <REFERENCE або UNRESOLVED>.
Спочатку read-only перевір Python/Git/host versions, platform limits і наявні ~/.agents/skills,
~/.claude/skills mappings, не читаючи credentials. Auth налаштовує сам developer через власний
approved client; не проси токени в чаті й не копіюй чужі home/settings/session stores.
Якщо source ще недоступний, BLOCKED acquisition; не запускай network/auth без дозволу.
Після source inspection/commit/hash verification зроби kit plan для dedicated root та inventory
project adapter. Не install прямо в ~/.agents: native host publisher відсутній; запропонуй
selected skill mapping або exact-file fallback, покажи collisions і backup/restore boundaries.
Після дозволу застосуй тільки reviewed plan/diff, перевір repeat NOOP і збережи transaction.
Не міняй system permissions, hooks/MCP/models і не встановлюй graph/scanners/marketplace/SaaS.
Linux познач NOT_TESTED, Windows UNSUPPORTED для kit; не обіцяй parity без окремого proof.
Запиши per-host detected/configured/discovered/invoked окремо. Перший task branch у main repo —
лише за визначеного writer і без foreign/unknown WIP; жодного автоматичного per-task clone/worktree.
Поверни evidence + наявному reviewer handoff; installation ≠ product/runtime/workflow acceptance.
```

## 7. Update, backups, rollback і межі uninstall

Для нового trusted release — спочатку новий SOURCE + повний бажаний component set у `plan`. Пропущений component на update означає видалення його managed files; це не «залишити як було». Зберегти current source та `.ai-factory-state`; unmanaged file collision або чужа правка → BLOCKED, без force/adopt/reset.

```sh
python3 -B "$FACTORY_SOURCE/tools/kit.py" update --package "$FACTORY_SOURCE" --root "$FACTORY_TARGET" --component collection --component planning --component review --component session-guard
python3 -B "$FACTORY_SOURCE/tools/kit.py" update --package "$FACTORY_SOURCE" --root "$FACTORY_TARGET" --component collection --component planning --component review --component session-guard --execute --exclusive-window --plan-id '<new-reviewed-plan-id>'
python3 -B "$FACTORY_SOURCE/tools/kit.py" rollback --root "$FACTORY_TARGET" --transaction '<transaction-id>'
python3 -B "$FACTORY_SOURCE/tools/kit.py" rollback --root "$FACTORY_TARGET" --transaction '<transaction-id>' --execute --exclusive-window --plan-id '<rollback-plan-id>'
```

Rollback перевіряє latest/pending receipt і applied hashes, відновлює лише власні bytes, не чужі edits. Для initial install може прибрати owned files, але не чужі файли/директорії. Окремої `uninstall` команди немає. Видалення optional component — reviewed update; повне очищення state, host links, adapters, hooks чи caches не покривається rollback пакета. Не радити `rm -rf ~/.agents` чи видалення callback store. Потрібний окремий exact ownership inventory/дозвіл; до цього зберігати artifacts.

## 8. Як перевірити готовність

Один existing task record: source/commit/digest, selected components, exact source→destination mapping, baseline/applied hashes, branch/base/writer, plan/receipt IDs, commands/exits/artifacts/snapshot, limitations. Стан кожного host: DETECTED → CONFIGURED → DISCOVERED → INVOKED із окремим доказом; file reading не invocation. Для перевірок PASS/FAIL/BLOCKED/NOT_TESTED/N/A з причиною. Fixtures доводять helpers, не native agent behavior. Не встановлений optional graph → явний file fallback; потрібний unavailable tool блокує лише залежний scope.

Чинний [lifecycle](../../ai-factory/feature-lifecycle.md): proportional grilling → scoped impact/checkpoint → required bound critique/defense → implementation → observable verification → independent final review → durable handoff. Агрегатний build або merge не заміняє acceptance rows. Один task branch/one writer; незалежний reviewer отримує snapshot і не дублюється. Delivery state відділяти від verdict: `prepared` / `sent` / `acknowledged` / `verdict_received` за [єдиним контрактом](../../ai-factory/review-handoff.md#delivery-state); ACK не є PASS, `AWAITING_DELIVERY` — лише історична назва причини очікування. Не чекати випадкового нагадування власника: автор готує фінальний пакет і використовує вже дозволений reviewer route; коли manual relay — явно називає його next action. `sent` або exit 0 не є отриманим ACCEPTED. За незакритих required proofs звіт лишається VERIFICATION_INCOMPLETE/REVIEW_PENDING, навіть якщо продукт merged.

Безпечна перевірка самого trusted package (тільки disposable fixtures, не user projects):

```sh
python3 -B "$FACTORY_SOURCE/tools/verify_release.py" --root "$FACTORY_SOURCE"
python3 -B "$FACTORY_SOURCE/tools/run_tests.py" --previous-release '/absolute/trusted/previous-release'
```

Без `--previous-release` конкретний migration fixture буде skipped, не PASS. Зберегти output/exit. Гарантія portable support потребує окремого OS/CLI proof; цей запуск не installs/graphs/models/browser QA.

<a id="security-proposed"></a>
## 9. Security adoption — PROPOSED, не installed

Небезпечний код може виконатися **до scanner**: dependency lifecycle scripts, явно викликані npm test/run, CI Actions або інструкції з чужого repository. Спочатку provenance/source review, reviewed lockfile, exact vetted tool/action versions/digests, permissions і secretless test environment; потім окремо дозволене виконання. Install-script policy має назвати дозволені lifecycle scripts та причину; default inspection може використати `--ignore-scripts`, але це **не sandbox** і не блокує явно викликані `npm test`/`npm run`. Джерела: [npm ci](https://docs.npmjs.com/cli/commands/npm-ci/), [GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use). Actions перевіряти як код із доступом до runner; pin verified immutable revisions і мінімальні token permissions, без automated settings changes цим guide.

| Кандидат попереднього research | Статус / boundary перед adoption |
|---|---|
| Semgrep Community Edition / власні правила | PROPOSED. Engine і registry rules мають різні умови. [Rules license](https://semgrep.dev/legal/rules-license/) треба перевірити перед redistribution; не vendor чужі registry rules у Factory. Власні правила/дозволені references — окремий reviewed scope |
| Trivy | PROPOSED. [Official supply-chain advisory March 2026](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23) показує потребу перевірки provenance й конкретного vetted version/digest; не доводить current unsafe або ураження цього користувача. Не pin навмання `latest` чи стару «safe» версію |

Цей shortlist не exhaustive security coverage. Tool install, database download/update, network mode, findings policy й permissions залишаються невизначеними до окремого proposal. Нічого не встановлено, registry/marketplace не підключено; no additional SaaS required. Scanner zero findings не доводить відсутність вразливостей; first-party scripts, actions, secrets handling і dependency provenance теж потребують перевірки. Research нижче уточнює proposal; будь-який rollout потребує окремого bounded доручення у чинному task record.

### Risk-triggered gates у чинному lifecycle

Це proposal для наступного bounded adoption, не автоматично увімкнена policy. У наявному task/acceptance record записати лише застосовні trigger → expected behavior → actual check/artifact → owner → status. Немає відповідної feature — N/A з причиною; немає потрібного доказу — NOT_TESTED/BLOCKED. Новий tracker чи однаковий важкий checklist для кожного repo не потрібний.

| Trigger | Що включити в scoped acceptance і докази |
|---|---|
| Будь-яке нове execution джерело | До запуску dependency/test scripts, CI Actions, hooks/MCP оглянути source, provenance, permissions і data egress. Instructions із repository, retrieved content або tool output не надають нових дозволів. Тестувати без production secrets; погоджувати фактичні side effects, а не довіряти назві scanner. [Secure Coding with AI](https://cheatsheetseries.owasp.org/cheatsheets/Secure_Coding_with_AI_Cheat_Sheet.html), [Prompt Injection](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html) |
| Identity, role, tenant або shared cache | Перевірити реальний API/resource: anonymous, інший user/tenant, revoked role, disabled account, expired session, switch/logout і повторний cached request. Hidden UI не authorization. Cache keys/invalidation мають зберігати tenant/user boundaries; якщо є SSR/hydration — перевірити HTML/serialized state на private fields. [Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), [Web Cache Security](https://cheatsheetseries.owasp.org/cheatsheets/Web_Cache_Security_Cheat_Sheet.html) |
| Cookie/session/cross-origin mutation | Зафіксувати actual Set-Cookie attributes і logout/expiry behavior через реальний proxy path. Перевірити CSRF для state-changing requests, credentialed CORS і origin policy, а не лише конфігураційні рядки. CORS не замінює authorization чи CSRF захист. [Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) |
| Server fetch за URL | Лише коли feature приймає/виводить destination: перевірка scheme/host/IP, redirect destination й повторного DNS resolution/rebinding, межі часу/розміру та network egress. Контрольовані fixtures, без probing чужих чи internal production endpoints. [SSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) |
| Upload/archive/download | Серверні total bytes, decompressed size/count, type/content/name validation, storage/processing boundary і download authorization; не покладатися на client MIME/extension. Перевірки із малими bounded fixtures. [File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) |
| Incoming webhook | Перевірити provider signature за його contract до business effects, replay/delivery ID та idempotency для повторної доставки, invalid/missing signature й duplicate event. Сам факт HTTP 2xx не доводить правильну обробку. [GitHub webhook practices](https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks) |
| Resource/cost amplification | Визначити request bytes, batch/array/page limits, queues/concurrency/timeouts і downstream cost budget за feature. Для Go `ParseMultipartForm(maxMemory)` обмежує memory file parts, решту пише на disk; це НЕ total upload cap. Потрібний окремий total-body limit, наприклад reviewed `MaxBytesReader` placement. Без навантаження production. [OWASP API4](https://api-security.owasp.org/editions/2023/en/0xa4-unrestricted-resource-consumption/), [Go net/http](https://pkg.go.dev/net/http) |
| Errors/logs/traces та incident recovery | Перевірити redaction credentials, session IDs і sensitive payloads у actual error/log/trace outputs; визначити owner для patch, revoke й rollback, межі доступу/зберігання evidence. У review передавати sanitized artifacts без secrets. [Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) |

### Scanner gate потребує власної перевірки

Перед adoption у CI/local gate потрібні три harmless fixtures: відомий позитивний detection із очікуваним policy failure, clean case із PASS, та tool/config/DB error із ERROR/BLOCKED, не «чисто». Записувати version/digest, rule-set/version/license, DB timestamp, target snapshot, enabled scanners, coverage/exclusions, output format, findings policy й commands/exits. Перевірити, що саме wrapper/CI зберігає і трактує findings; exit 0 сам по собі не PASS. [Trivy default exit](https://www.trivy.dev/docs/dev/guide/configuration/others/) може бути 0 навіть за findings. Для Go лише як stack-specific кандидат: [govulncheck](https://pkg.go.dev/golang.org/x/vuln/cmd/govulncheck) також має output modes із success exit за findings та documented static-analysis limits. Це не дозвіл встановити/запустити ще один scanner.

### Final evidence та межі заяв про завершення

Перевіряти actual built artifact/handler/runtime на фінальному snapshot; copied-handler harness може підтвердити вузьку логіку, але не підміняє реальний production route. Для потрібних CSP/browser interaction, throw path, SSR cancellation/abort, auth/proxy/cache boundaries — окремі observable acceptance rows із raw sanitized evidence. Unit/build/merge не закривають неперевірені runtime rows. Після delta визначити invalidated checks і передати чинному independent reviewer final snapshot; `prepared`/`sent`/`acknowledged` не є `verdict_received`/ACCEPTED. Пропущені required rows залишають VERIFICATION_INCOMPLETE навіть після merge.

Adoption sequence: у чинному плані погодити лише застосовні gates та власника → окремим bounded scope перевірити scanner provenance/policy/fixtures → отримати actual runtime evidence для першого малого slice → independent final-delta verdict. Destructive DAST, нові permissions, paid tools, network integrations або rollout не дозволяються цим документом.

Review-only adoption proposal: [thin security adapter](../../adapters/security/review.md), [pinned upstream sources](../../provenance/security-sources.json), [declarative scanner profile](../../examples/security/scanner-profile.json). These references do not imply installation, native invocation or a working security gate.
