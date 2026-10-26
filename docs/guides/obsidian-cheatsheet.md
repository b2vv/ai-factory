---
title: Obsidian + Claude Code + code-review-graph — Runbook
scope: багатопроєктний локальний setup
розкладка: ~/vaults для нотаток, ~/dev для репозиторіїв
---

# Runbook: Obsidian (local) + Claude Code + code-review-graph

Мультипроєктний локальний setup: окремий глобальний vault + по одному vault на проєкт,
з розведенням scope для Claude Code (per-vault MCP) і code-review-graph (per-repo).

---

## 0. Ключові принципи (чому саме так)

- **Obsidian local-first за замовчуванням.** Vault — це тека `.md`; синхронізація не вмикається сама. Тримати vault поза iCloud/Dropbox/OneDrive/GDrive.
- **Vault-и ізольовані за побудовою.** Граф, бэклінки, пошук і `[[wikilinks]]` НЕ працюють між vault-ами. Крос-vault лінки нативно відсутні.
- **«Глобальне доступне скрізь» = спільний файл на диску, НЕ лінк.** Розв'язується symlink-ом глобальної теки в кожен project-vault.
- **Три незалежні осі scope:**
    1. Нотатки — межа vault (тека).
    2. Claude Code ↔ vault — per-vault MCP порт + `-s local`.
    3. Код — per-repo граф code-review-graph (`git ls-files`).

---

## 1. Розкладка на диску

```
~/vaults/
├── global/                      # окремий глобальний vault
│   ├── .obsidian/               # свій конфіг
│   ├── prompts/                 # form-rules, agent-prompt, reverse-map-binding...
│   ├── patterns/                # FSD, XState, branded types, RTK Query
│   └── skills/
├── cassiopeia/                  # project vault
│   ├── .obsidian/
│   ├── _global  ->  ../global   # symlink
│   ├── ADR/                     # ADR-0021, 0022, 0026
│   ├── domain/
│   └── sessions/                # ClaudeSessions
└── project-b/
    ├── .obsidian/
    ├── _global  ->  ../global   # symlink
    └── ...
```

---

## 2. Створення структури + symlink глобальної зони

```bash
mkdir -p ~/vaults/global/{prompts,patterns,skills}
mkdir -p ~/vaults/cassiopeia/{ADR,domain,sessions}
mkdir -p ~/vaults/project-b

ln -s ~/vaults/global ~/vaults/cassiopeia/_global
ln -s ~/vaults/global ~/vaults/project-b/_global
```

Після цього в кожному project-vault граф, пошук і `[[_global/patterns/fsd]]` працюють нативно.

### Нюанс з `.obsidian`

Через symlink у project-vault потрапляє й `global/.obsidian`. Функціонально Obsidian його ігнорує
(читає лише конфіг з кореня vault), але щоб не індексувався:

- **Settings → Files & Links → Excluded files → `_global/.obsidian`** (у кожному project-vault).

Якщо не хочеш тягнути навіть приховану теку — symlink окремі підтеки замість усього `_global`:

```bash
ln -s ~/vaults/global/prompts  ~/vaults/cassiopeia/_prompts
ln -s ~/vaults/global/patterns ~/vaults/cassiopeia/_patterns
```

### Бекап без хмари

```bash
cd ~/vaults/global && git init && git add -A && git commit -m "init global vault"
# аналогічно для кожного project-vault; пуш на власний/приватний remote за потреби
```

---

## 3. Obsidian MCP — по порту на кожен project vault

У **кожному** project-vault окремо:

1. Settings → Community plugins → Browse → **Local REST API with MCP** → Install → Enable.
2. У налаштуваннях плагіна: увімкнути **Enable non-encrypted (HTTP) server**.
3. Скопіювати ключ (`Bearer XXXXXXX`).
4. Виставити РІЗНИЙ HTTP-порт на кожен vault.

> Використовувати саме HTTP. HTTPS на 27124 через self-signed сертифікат дає помилки підключення з Claude.

| Vault               | HTTP порт | Репо                        |
|---------------------|-----------|-----------------------------|
| cassiopeia          | 27123     | `cassiopeia`   |
| cargotrans-ui       | 27133     | `cargotrans-ui` |
| diagram-hierarchy   | 27143     | `dg`             |

> 27124 зайнятий HTTPS-сервером плагіна vault-а cassiopeia — наступний вільний крок сітки `+10`.

**Глобальному vault свій MCP не потрібен** — його вміст фізично лежить у `_global` кожного
проєкту, тож project-MCP уже його віддає. Це головний бонус symlink-схеми.

---

## 4. Прив'язка до Claude Code (scope на репо)

Запускати з теки відповідного репо, щоб конфіг ліг у local-scope цього проєкту
(і токен не потрапив у git):

```bash
cd ~/dev/cassiopeia
claude mcp add -s local --transport http obsidian \
  http://127.0.0.1:27123/mcp/ \
  --header "Authorization: Bearer TOKEN_CASS"

cd ~/dev/project-b
claude mcp add -s local --transport http obsidian \
  http://127.0.0.1:27133/mcp/ \
  --header "Authorization: Bearer TOKEN_PB"
```

Перевірка (має показати `obsidian ... ✓ Connected`):

```bash
claude mcp list
```

`-s local` тримає запис приватним до цього проєкту → у кожному репо `obsidian` вказує лише
на свій vault. Ніякого ProjectB у контексті Cassiopeia.

Перепідключення (напр. неправильний токен):

```bash
claude mcp remove obsidian
# далі повторити claude mcp add ...
```

---

## 5. code-review-graph — окремий граф на репо

Незалежна вісь, per-repo. Вимоги: Python 3.10+ (бажано `uv`).

```bash
pip install code-review-graph        # або: pipx install code-review-graph

cd ~/dev/cassiopeia
code-review-graph install            # авто-конфіг MCP для знайдених інструментів
code-review-graph build              # парсинг кодової бази
```

Фоновий демон на кілька репо (тримає граф свіжим без ручного build):

```bash
crg-daemon add ~/dev/cassiopeia --alias cass
crg-daemon add ~/dev/project-b  --alias pb
crg-daemon start
crg-daemon status
crg-daemon logs --repo cass -f
```

- `install` визначає встановлені AI-інструменти й пише коректну MCP-конфігурацію для кожного.
- Демон стежить за репо і автоматично перебудовує граф; health-check кожні 30 с перезапускає мертві watcher-и.
- Індексуються лише `git ls-files` → gitignored пропускаються; винятки — `.code-review-graphignore`.
- MCP-prompts: `review_changes`, `architecture_map`, `debug_issue`, `onboard_developer`, `pre_merge_check`.

> Порада по scope: Obsidian тримати в `-s local` (через токен), а crg лишати в `-s project`
> (`.mcp.json`) — граф і так ізольований через git.

---

## 6. Підсумкова карта

| Компонент          | cassiopeia                | project-b                | scope        |
|--------------------|---------------------------|--------------------------|--------------|
| Obsidian vault     | `~/vaults/cassiopeia`     | `~/vaults/project-b`     | тека         |
| `_global` symlink  | → `~/vaults/global`       | → `~/vaults/global`      | спільний файл|
| Obsidian MCP порт  | 27123                     | 27133                    | `-s local`   |
| code-review-graph  | граф репо cass            | граф репо pb             | per-repo     |

**Результат:** глобальні промпти/патерни спільні й зв'язані всередині кожного vault;
проєкти ізольовані; Claude Code у кожному репо бачить рівно свій vault + свій код-граф.

---

## 7. Чек-ліст запуску нового проєкту

1. `mkdir -p ~/vaults/<proj>` → `ln -s ~/vaults/global ~/vaults/<proj>/_global`
2. Відкрити vault в Obsidian → Excluded files: `_global/.obsidian`
3. Local REST API with MCP → HTTP on → унікальний порт → скопіювати токен
4. `cd ~/dev/<proj>` → `claude mcp add -s local --transport http obsidian http://127.0.0.1:<port>/mcp/ --header "Authorization: Bearer <token>"`
5. `claude mcp list` → перевірити `✓ Connected`
6. `code-review-graph install && code-review-graph build` (або `crg-daemon add ... && crg-daemon start`)
7. `git init` у vault для локального бекапу

---

## 8. Відкриті опції (не реалізовано)

- Hook, що детерміністично валить сесію Claude Code, якщо стартує в репо без відповідного Obsidian-MCP (у дусі PreToolUse exit code 2).
- Винесення prompt-бібліотеки в `global/prompts/` з підтягуванням через Obsidian MCP на тригер.