---
title: Obsidian + Claude Code + code-review-graph — Runbook
scope: multi-project local setup
розкладка: ~/vaults for notes, ~/dev for repositories
---

> **Historical English translation — authored derivative.** Original: [docs/guides/obsidian-cheatsheet.md](../../../../guides/obsidian-cheatsheet.md). Original SHA256: `c1a2eadb8611250b0bcaeac2fffa8f0cd0396fa4852af2f1886413e5e359ffc0`. Source base: `2c0960885926075502a319a19eafbed901690dde`. The sealed original remains unchanged; the in-repository historical document has a separately recorded local-project reference cleanup. Historical assertions, statuses, examples, and limitations are retained; this translation does not establish current policy, execution evidence, or activation. Original-language compatibility anchors and literal protocol tokens remain where required.

# Runbook: Obsidian (local) + Claude Code + code-review-graph

Multi-project local setup: a separate global vault + one vault per project,
with separate scope for Claude Code (per-vault MCP) and code-review-graph (per-repo).
The original frontmatter key `розкладка` means layout and is retained as metadata compatibility data.

---

<a id="0-ключові-принципи-чому-саме-так"></a>
## 0. Key principles (why this design)

- **Obsidian is local-first by default.** A vault is a directory of `.md` files; synchronization does not enable itself. Keep the vault outside iCloud/Dropbox/OneDrive/GDrive.
- **Vaults are isolated by design.** The graph, backlinks, search and `[[wikilinks]]` do NOT work across vaults. Cross-vault links are not natively available.
- **“Global is available everywhere” = a shared file on disk, NOT a link.** Solve this with a symlink to the global directory inside every project vault.
- **Three independent scope axes:**
    1. Notes — the vault boundary (directory).
    2. Claude Code ↔ vault — a per-vault MCP port + `-s local`.
    3. Code — a per-repo code-review-graph graph (`git ls-files`).

---

<a id="1-розкладка-на-диску"></a>
## 1. Disk layout

```
~/vaults/
├── global/                      # separate global vault
│   ├── .obsidian/               # its own configuration
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

<a id="2-створення-структури--symlink-глобальної-зони"></a>
## 2. Create the structure + symlink the global area

```bash
mkdir -p ~/vaults/global/{prompts,patterns,skills}
mkdir -p ~/vaults/cassiopeia/{ADR,domain,sessions}
mkdir -p ~/vaults/project-b

ln -s ~/vaults/global ~/vaults/cassiopeia/_global
ln -s ~/vaults/global ~/vaults/project-b/_global
```

Afterward, the graph, search and `[[_global/patterns/fsd]]` work natively in every project vault.

<a id="нюанс-з-obsidian"></a>
### The `.obsidian` detail

The symlink also brings `global/.obsidian` into the project vault. Functionally, Obsidian ignores it
(it only reads configuration at the vault root), but to prevent indexing it:

- **Settings → Files & Links → Excluded files → `_global/.obsidian`** (in each project vault).

If you do not want even the hidden directory included, symlink individual subdirectories instead of all of `_global`:

```bash
ln -s ~/vaults/global/prompts  ~/vaults/cassiopeia/_prompts
ln -s ~/vaults/global/patterns ~/vaults/cassiopeia/_patterns
```

<a id="бекап-без-хмари"></a>
### Backup without the cloud

```bash
cd ~/vaults/global && git init && git add -A && git commit -m "init global vault"
# likewise for each project vault; push to your own/private remote if needed
```

---

<a id="3-obsidian-mcp--по-порту-на-кожен-project-vault"></a>
## 3. Obsidian MCP — one port per project vault

In **each** project vault separately:

1. Settings → Community plugins → Browse → **Local REST API with MCP** → Install → Enable.
2. In the plugin settings, enable **Enable non-encrypted (HTTP) server**.
3. Copy the key (`Bearer XXXXXXX`).
4. Set a DIFFERENT HTTP port for each vault.

> Use HTTP specifically. HTTPS on 27124 uses a self-signed certificate and causes connection errors with Claude.

| Vault               | HTTP port | Repository                  |
|---------------------|-----------|-----------------------------|
| cassiopeia          | 27123     | `cassiopeia`   |
| cargotrans-ui       | 27133     | `cargotrans-ui` |
| diagram-hierarchy   | 27143     | `dg`             |

> 27124 is occupied by the cassiopeia vault plugin's HTTPS server — the next free grid increment is `+10`.

**The global vault does not need its own MCP** — its contents physically reside in each project's
`_global`, so the project MCP already serves them. This is the main benefit of the symlink arrangement.

---

<a id="4-привязка-до-claude-code-scope-на-репо"></a>
## 4. Bind to Claude Code (repository scope)

Run from the relevant repository directory so the configuration lands in this project's local scope
(and the token does not enter git):

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

Verification (should show `obsidian ... ✓ Connected`):

```bash
claude mcp list
```

`-s local` keeps the entry private to this project → in each repository, `obsidian` points only
to its own vault. No ProjectB in Cassiopeia's context.

Reconnect (for example, an incorrect token):

```bash
claude mcp remove obsidian
# then repeat claude mcp add ...
```

---

<a id="5-code-review-graph--окремий-граф-на-репо"></a>
## 5. code-review-graph — a separate graph per repository

An independent axis, per-repo. Requirements: Python 3.10+ (preferably `uv`).

```bash
pip install code-review-graph        # or: pipx install code-review-graph

cd ~/dev/cassiopeia
code-review-graph install            # automatic MCP configuration for detected tools
code-review-graph build              # parse the codebase
```

A background daemon for multiple repositories (keeps the graph fresh without manual builds):

```bash
crg-daemon add ~/dev/cassiopeia --alias cass
crg-daemon add ~/dev/project-b  --alias pb
crg-daemon start
crg-daemon status
crg-daemon logs --repo cass -f
```

- `install` detects installed AI tools and writes the correct MCP configuration for each.
- The daemon watches repositories and automatically rebuilds the graph; a health check every 30 seconds restarts dead watchers.
- Only `git ls-files` entries are indexed → gitignored files are skipped; exclusions use `.code-review-graphignore`.
- MCP prompts: `review_changes`, `architecture_map`, `debug_issue`, `onboard_developer`, `pre_merge_check`.

> Scope advice: keep Obsidian in `-s local` (because of the token), and leave crg in `-s project`
> (`.mcp.json`) — the graph is already isolated through git.

---

<a id="6-підсумкова-карта"></a>
## 6. Summary map

| Component          | cassiopeia                | project-b                | scope        |
|--------------------|---------------------------|--------------------------|--------------|
| Obsidian vault     | `~/vaults/cassiopeia`     | `~/vaults/project-b`     | directory    |
| `_global` symlink  | → `~/vaults/global`       | → `~/vaults/global`      | shared file  |
| Obsidian MCP port  | 27123                     | 27133                    | `-s local`   |
| code-review-graph  | cass repository graph    | pb repository graph      | per-repo     |

**Result:** global prompts/patterns are shared and linked within each vault;
projects are isolated; Claude Code in each repository sees exactly its own vault + its own code graph.

---

<a id="7-чек-ліст-запуску-нового-проєкту"></a>
## 7. New-project startup checklist

1. `mkdir -p ~/vaults/<proj>` → `ln -s ~/vaults/global ~/vaults/<proj>/_global`
2. Open the vault in Obsidian → Excluded files: `_global/.obsidian`
3. Local REST API with MCP → HTTP on → unique port → copy token
4. `cd ~/dev/<proj>` → `claude mcp add -s local --transport http obsidian http://127.0.0.1:<port>/mcp/ --header "Authorization: Bearer <token>"`
5. `claude mcp list` → verify `✓ Connected`
6. `code-review-graph install && code-review-graph build` (or `crg-daemon add ... && crg-daemon start`)
7. `git init` in the vault for local backup

---

<a id="8-відкриті-опції-не-реалізовано"></a>
## 8. Open options (not implemented)

- A hook that deterministically fails a Claude Code session if it starts in a repository without the matching Obsidian MCP (in the spirit of PreToolUse exit code 2).
- Moving the prompt library into `global/prompts/` and pulling it through Obsidian MCP on a trigger.
