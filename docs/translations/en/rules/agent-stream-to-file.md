---
title: Agent stream-to-file — every agent writes its progress to its own file so a failure does not erase its work
---

> **Historical English translation — authored derivative.** Original: [rules/agent-stream-to-file.md](../../../../rules/agent-stream-to-file.md). Original SHA256: `4b35270e78dc9bfdf2ff849cfeca28266649e40dc380c0e2ef2aaa0c6110a7e0`. Source base: `2c0960885926075502a319a19eafbed901690dde`. The original is unchanged. Historical assertions, statuses, examples, and limitations are retained; this translation does not establish current policy, execution evidence, or activation. Literal protocol tokens remain where required. Section navigation uses English heading anchors; old original-language fragment URLs are not retained.

# 🧵 Agent stream-to-file

Cross-project rule: **a subagent that crashes must leave something from which work can resume.**
Applies to the `Agent` tool, `Workflow` `agent()` and any manual orchestration.

---

## 1. Why — and why the existing transcript is not enough

Claude Code **already** writes each subagent's full JSONL transcript to
`<session-tmp>/tasks/<agentId>.output`. But it does not save the work for two reasons:

- **it cannot be read** — it is the entire event stream; reading it overflows the orchestrator's
  context (the harness itself warns about this);
- **it is not structured around results** — findings are mixed with tool calls.

When an agent dies on an API error, the notification contains `result` — a truncated tail such as
“Now let me append the final section”. Work the agent **has already done in its head** disappears.
One day's empirical evidence: three subagent deaths (two critique lenses + one plan defense), and
in each case `result` carried no findings.

**Second series, 2026-09-04/05** — it adds what the first did not show. Again three deaths
(the “logical gaps” lens, then the Standards axis in code review **twice in succession**), again no trail:
`result` carried “I'll read the plan…” and “I'll review the diff…”. New observations:

- **the same role died twice** — so “retry once on another tier” is not a guarantee, and without
  a working file the second retry starts from zero just like the first;
- **failure can be transport-related rather than model-related** (“Connection lost mid-response”),
  so it correlates with neither tier nor task complexity — planning on “a strong model will not fail” is not viable;
- 🔴 **the rule existed all this time and did not work**, because nothing brought it to the
  dispatch point: it lives in `~/.agents/rules/`, skills reference it, but a direct `Agent` tool
  call bypassed it. A separate link fixed this — `~/.claude/CLAUDE.md`, loaded in **every** session
  before any skill.

**The lesson is broader than this rule:** a rule with no path to its point of application is equivalent
to no rule. If it only works when someone remembers to read it, it does not work.

---

## 2. The rule

**Every dispatch carries the path to a working file and requires writing to it during the work, not at the end.**

The agent prompt contains the following. The record labels `ФАКТ:`, `РІШЕННЯ:`, `ДАЛІ:` and
`ПИТАННЯ:` are retained compatibility labels meaning FACT, DECISION, NEXT and QUESTION.

```
WORKING FILE: <path>
Append to it AFTER EVERY STEP — do not accumulate everything for the final answer, and do not rewrite
the entire file (append, not rewrite). If you are interrupted, this file will remain the only work trail.
Final answer = a concise summary of the file.

**First entry immediately, before the first tool:** a `ДАЛІ:` line with what you intend to check.
Then record what is expensive to reconstruct:
- ФАКТ: verified in code <exactly what, path:line> — before it becomes a conclusion;
- РІШЕННЯ: <what was chosen>, because <reason> — before writing the section that carries it;
- ДАЛІ: <what you intended to do next> — the most useful line if the agent dies;
- ПИТАННЯ: <what remains unresolved>.
```

**Why these four.** The harness transcript records **tool calls** — it cannot reconstruct the work.
What is expensive to reproduce is not commands but verified facts and accepted decisions; the “NEXT”
line turns an interruption from “start over” into “continue here”.

**Where the file lives**

| Context | Path |
|---|---|
| Pipeline step (`spec-flow`, waves) | `<дім артефактів>/_agent-<роль>-<n>.md` |
| Ad-hoc subagent | session scratchpad, `agent-<роль>.md` |
| Multiple lenses for one step | a separate file per lens — a shared file will collide in a race |

The path placeholders above retain their original spellings: `<дім артефактів>` means artifact home
and `<роль>` means role.

**Parallel agents write to different files.** One file for two agents = a corrupted file; this is not
a recommendation but a consequence of having no locking.

---

## 3. What the orchestrator does

1. **Creates the path before dispatch** (the directory must exist) and puts it in the prompt.
2. **After `null` / a crash — reads the working file first**, rather than restarting blindly:
   - file empty → the agent accomplished nothing; retry according to
     [[multi-model-roles]] §3 (once, on another tier);
   - file has partial findings → retry with an **addition to the prompt**: “here is what you already
     found (path); continue from here, do not repeat it”.
3. **Does not confuse this with the ledger.** The ledger ([[subagent-orchestration-ledger]]) answers
   “which task is complete”; the working file answers “what the agent had time to think through”.
   Different questions, different files.
4. **Cleans up afterward**: ad-hoc agents' working files are disposable after successful completion;
   pipeline-step files stay beside the artifacts as a trail.

---

## 4. Who needs this most

Roles that keep their result **in their head until the final message** lose the most:
plan critique, plan defense, review, research. An observed case: an agent delivered everything in one
message after ~870 seconds of work — a transport interruption at second 860 would have destroyed a
fully developed finding, and nobody would have known it ever existed.

Roles that write files as they work (implementation — it commits code) face less risk:
their intermediate state is already on disk.

---

## 5. Limits

- **The guarantee begins with the first flush, not with launch.** Observed: an agent died on an API error
  **before** the first write — no file was created at all, no trail. That is why the first entry
  (`ДАЛІ:` with the verification plan) is made before the first tool: it costs one line and avoids
  “it died — and we do not even know what it intended to do”.
- For the orchestrator, this has a simple implication: **missing or empty file = agent did not run**
  ([[multi-model-roles]] §3, retry once on another tier). Do not try to guess what it accomplished.
- The rule does **not** apply to trivial single-step agents (one answer to one question without
  research): the file costs more than the work it saves.
- The file is **not** a replacement for the final answer. The orchestrator reads the answer; the file
  is needed only when there will be no answer.
- Do not try to read `<session-tmp>/tasks/<agentId>.output` instead — its size is the very reason
  this rule exists.

## 🔗 Related

- [[multi-model-roles]] §3 — `null` = lens did not run; retry once on another tier.
- [[subagent-orchestration-ledger]] §1 — durable task ledger; §3 — brief-file handoff (input),
  whereas this rule concerns output.
