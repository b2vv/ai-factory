---
name: cto-agenda
description: Proposes what to do next — a ranked list of candidates collected from recorded repository sources, and one recommended next move with an explanation of why not the others. Use when P0 is closed and the queue is empty, when choosing between directions, when asked "що далі", "що брати в роботу", "склади беклог" (retained Ukrainian compatibility aliases), or on the trigger "cto agenda".
---

<a id="cto-agenda--що-робити-далі"></a>

# cto-agenda — what to do next

The bridge between “I understand the product” ([[cto-research]]) and “I execute the choice” (`spec-flow`, `to-tickets`).
Answers one question: **what is the next move**.

**Move** is the key concept. Not a “priority” or “task”, but a move: something that changes the position and makes
other moves available. A list without a selected move pushes the work back onto the person;
the skill ends with **one** move.

<a id="1-опертись-на-брифінг"></a>

## 1. Start from the briefing

Candidates come from the repository briefing, not impressions. If there is no briefing or it trails `HEAD`,
run `cto-research` first, then return here. State the commit underlying the agenda: when the briefing
was rewritten, the old choice of move may have expired with it.

<a id="2-зібрати-кандидатів-із-перелічених-джерел"></a>

## 2. Collect candidates from the listed sources

Visit **all** sources; state how many candidates each supplied (zero is also an answer):

| Source | What it supplies |
|---|---|
| **Open** tasks in `work/` (+ `gh issue list`) | declared but unfinished work |
| Recorded debt (`tech-debt/`, CRITIQUE files) | what is already recognized as a problem |
| The briefing's “Risks” section | the most fragile area |
| Unchecked boxes (`REQUIREMENTS`, `SPEC`, live tasks) | promised but unfinished work |
| Skipped tests, disabled gates, `TODO` anchors in code | debt absent from documents |
| Unresolved product choices | what blocks planning itself |

**Every candidate carries a source** — `path:line`, issue number, `doc §`. An agent-invented candidate
is allowed, but is marked `⚠️ no source` and must explain the observation from which it arose.
This is the main safeguard: without it the agenda fills with plausible tasks nobody requested.

**The archive is not a source.** `work/` is divided by state (the layout is given by the manifest's `## Артефакти`
heading, retained as a literal compatibility reference), and completed work is archived. Pulling a candidate from there means proposing work already
done — so read the archive only to **filter out**: a candidate already present there is removed from the agenda
with a note identifying what closed it.

<a id="3-розкласти-по-двох-осях"></a>

## 3. Classify on two axes

Instead of “high / medium / low”, use two dimensions that actually distinguish moves:

- **Unblocks** — how much other work awaits this move (name exactly what).
- **Reversibility** — the cost of discovering that the move was wrong: cheap (an edit) or expensive
  (data migration, public API, external effect).

Irreversible moves require more evidence **before** starting; reversible ones can be tried as an experiment.
A move that unblocks nothing and is expensive to undo is a candidate for “not now”; say so explicitly.

<a id="4-відокремити-рішення-людини"></a>

## 4. Separate human decisions

Product choices are **not** agent moves. List each separately as:
question · options · cost of each · **recommendation with a reason**.

The agent recommends; the person chooses. Disguising a choice as a task is making a decision silently.

<a id="5-назвати-хід"></a>

## 5. Name the move

Give one recommendation, followed by **why not the others**: for each of the 2–3 closest alternatives,
a line explaining what tipped the balance. Otherwise the recommendation cannot be checked or challenged.

The move then goes to `spec-flow` (for a substantial feature) or `to-tickets` (for a set of small items).
The agenda itself writes no code.

<a id="6-дім-агенди"></a>

## 6. Where the agenda lives

One file per repository: `work/AGENDA.md` (or a “Queue” section if the repository already keeps it in the briefing).
The agenda is **rebuilt**, not appended to — an ever-growing backlog stops being a choice.
Moves completed since the last agenda remain as “done: <move> → <commit/PR>”.

<a id="7-завершення"></a>

## 7. Completion

The skill is complete when **all** of the following hold:

- [ ] State the briefing commit underlying the agenda.
- [ ] Visit all six sources and state each candidate count.
- [ ] Every candidate has a source or a `⚠️ no source` label; state the number of those labels.
- [ ] Classify each candidate on both axes (unblocks / reversibility).
- [ ] List product choices separately, each with a recommendation.
- [ ] Name **one** next move and reasons for rejecting the 2–3 alternatives.
