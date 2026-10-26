---
title: Repo standards manifest — .claude/standards.md, format and purpose
---

> **Historical English translation — authored derivative.** Original: [rules/repo-standards-manifest.md](../../../../rules/repo-standards-manifest.md). Original SHA256: `fe4c59fa3705145be5d197e031a301274a0c00d1ad5d8d64cbba3c19d6b87b82`. Source base: `2c0960885926075502a319a19eafbed901690dde`. The original is unchanged. Historical assertions, statuses, examples, and limitations are retained; this translation does not establish current policy, execution evidence, or activation. Original-language compatibility anchors and literal protocol tokens remain where required.

# 📐 Repo standards manifest

Cross-project rule: **the process lives in the skill; the yardstick lives in the repository**.

Global skills (`code-review`, `spec-flow`) describe the sequence of steps that is the same everywhere.
What differs in each repository — which documents are standards, which commands are green, where code goes —
is collected in **one file at a predictable path**: `<repo>/.claude/standards.md`.

Without it, global `code-review` at step 3 **guesses** the yardstick (“something that documents how to write
code”). With it, guessing becomes an address lookup — and a copy of the skill in every repository is unnecessary.

---

<a id="0-мова--перше-що-читається"></a>
## 0. Language is read first

The yardstick **is bound to language and path**, and in a polyrepo this is not a formality.
`CODING_STANDARDS.md` describing Clean Code + SOLID + **Matt Pocock** applies to TypeScript;
it does **not apply at all** to the Rust, Python or Go portion of the same repository — Pocock idioms
(`satisfies` > `as`, branded types, discriminated unions, `z.infer` as SSOT) have no subject
outside TS.

Therefore every yardstick row carries an **“applies to”** column with paths. Without it, a reviewer
will apply the row to the entire repository — and report “does not use `satisfies`” on a `.rs` file.

---

<a id="1-фіксовані-заголовки"></a>
## 1. Fixed headings

The order and names are stable — skills use them to find their sections. The literal Ukrainian
heading keys below are retained as compatibility data; the explanations are English.

### `## Мірник`

Yardstick. Table: **document · what it decides · where its checklist is · applies to**.
Only what is actually used to judge. An empty “applies to” cell is not allowed.

### `## Не мірник`

Not a yardstick. What looks like a standard but is not: reports, plans, recorded debt, intentions.
Debt is not a violation; a recorded deviation is not a finding.

### `## Машинні гейти`

Machine gates. Command · exactly what it catches. Separately — **what they do NOT catch**, with a date
and measurement method (“measured by `tools/lint-contract/lint-contract.test.ts`, 2026-08-14”). A measured
list is more valuable than a declared one: review pays off precisely where machines cannot see.

### `## Конституція`

Constitution. Rules whose violation means stop, not a comment. Each links to its source (`AGENT.md §11`)
and notes whether a linter already enforces it — enforced rules are not repeated in review.

### `## Поріг пайплайна`

Pipeline threshold. A structural condition (not a judgment) that activates the full SDD cycle:
“does a new slice directory appear?”, “does a public API change?”. Also state what happens below the
threshold — a lightweight inline plan.

### `## Розміщення`

Placement. Where new code goes: “what → where”. Plus the reuse index, if the repository has one.

### `## Гілки й PR`

Branches and PRs. What to branch from, where PRs go, which remotes are canonical.

### `## Артефакти`

Artifacts. Home for spec/plan/tasks/reports — and the **task lifecycle**.

Agent tasks live in `work/`. Every repository has the directory, and its contents are split **by state**,
not by topic:

| Directory role | Contents | Next destination |
|---|---|---|
| tasks / plans | what has not yet started | started → “in progress” |
| in progress | accepted decisions and measured facts from an unfinished conversation | finished → archive |
| technical debt | debt register with addresses and costs | item closed → crossed out in place |
| bugs / others' problems | what breaks but cannot be fixed by this team | disappears when the fix arrives |
| archive | completed work | forever |

Exact directory names differ by repository — the manifest names them explicitly, because the agent must not guess.

Three rules keep this layout working:

- **Completed work moves to the archive rather than being deleted.** Otherwise the decision trail disappears.
- **The archive keeps pointers, not copies.** A copy diverges from its original, while a dead pointer is visible
  to the freshness gate.
- **Debt is not a violation.** The debt directory stays in `## Не мірник`: review does not report it
  as a finding.

**`work/` ≠ home for completed research.** If a repository has `reports/**` referenced by code, that is
the evidence base — it stays in place, because moving it breaks links. `work/` is what lies **ahead**.

---

<a id="2-що-в-маніфест-не-кладеться"></a>
## 2. What does not go into the manifest

The manifest is an **index and yardstick**, not a second copy of the standards. Rules stay in their
own documents; this file gets a row “document → what it decides → where the checklist is”. Standard
text copied into the manifest becomes a second truth that will diverge from the first.

The exception is **measured** facts that no document contains (the list of things gates do not catch;
measurement date). This is their home because they have no other one.

<a id="3-коли-маніфесту-немає"></a>
## 3. When the manifest is absent

The skill states this explicitly and proposes building one — then continues in guessing mode, declaring
that the yardstick is guessed. Silently switching to guessing is the worst option: the report looks
the same, but its basis differs.

<a id="-повязане"></a>
## 🔗 Related

- `~/.agents/skills/spec-flow/SKILL.md` — the process that reads this manifest
- `~/.agents/skills/code-review/SKILL.md` §3 — the step this manifest frees from guesswork
- `~/.agents/rules/typescript-pocock-idioms.md` — the TS idioms themselves (scope: TypeScript)
