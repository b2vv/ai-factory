---
name: ui-audit
description: "Finds UI/UX problems on a rendered screen by looking at it the way a user does, and reports each as a numbered, located, plain-language problem the owner can confirm with one word. Use when the owner asks what is wrong with a screen, says something looks or feels off without naming it, points to a specific UI region and says it looks or feels wrong, or wants problems found before a review gate. Triggers: \"ui-audit\", \"find the problems on this screen\", \"what is wrong here\", \"something is off\"."
---

# ui-audit — find the problems, then name them

The owner should not have to explain what is wrong. This skill **finds** problems on a rendered screen and hands them back in a form the owner answers with a number and a word. It does not gate and does not fix: confirmed problems go to [interface-review](../interface-review/SKILL.md) for the gate and to [design-pass](../design-pass/SKILL.md) for the fix.

Two modes. **Sweep**: the agent looks first and reports. **Pointing**: the owner points at a place and says it is off; the agent names what it could be.

## 1. Fix the frame

Record the screen (route or screenshot), the user role and the **one task** this screen exists for. If the task is not given, infer it from the screen, mark it `inferred` and put it first in the report for the owner to confirm. Render the real screen in a browser at the project's main viewport and one narrow viewport (phone class of the [shared viewport contract](../design-pass/references/viewport-coverage.md)); a sweep from source code or memory is not a sweep. The full four-class coverage belongs to the interface-review gate, not to the sweep. Use authorized accounts and fixtures; the audit is read-only and changes no live data. Activating an action is part of the audit only where it is safe (§2, action inventory).

**Done when:** role, task and the inspected captures are written down.

## 2. Sweep: eight looks, one question each

Take the looks in order. Each look asks one question and ignores everything else; a single look "for everything" finds one problem and stops. Write down what you see before judging it.

| Look | Question | What a problem looks like |
| --- | --- | --- |
| **Glance** | In five seconds: what is this screen for, and what do I press? | no clear answer; two answers; the answer is not the task from §1 |
| **Squint** | Blurred, which three things are heaviest? | the heaviest things are not the most important for the task; the primary action is not among them |
| **Groups** | What belongs together, and what separates groups? Does each action's placement, group and label show what it acts on? | related things far apart; unrelated things close; a group with no visible edge; gaps that follow no rhythm; an action with no visible cue to its object or step |
| **Lines** | Which edges line up? | near-misses of a few pixels; a column that drifts; text baselines that disagree |
| **Twins** | Which elements do the same job? | same job, different look; different job, same look; one twin with a state the other lacks |
| **Words** | Read every word aloud. | a label that needs the context to make sense; two words for one thing; clipped or wrapped text; a button named by what it is, not what it does |
| **Task** | List every visible action (action inventory below), then do the task from §1 with the keyboard and with the pointer. | a step with no feedback; a dead end; an action that cannot be undone or cancelled; focus that disappears; an action whose object or step cannot be told from the screen |
| **Stress** | Empty, one item, many items, longest name, error, narrow. | layout breaks; actions vanish; a state that shows nothing at all |

**Action inventory (part of the Task look).** List every visible action on the inspected screen and state, whatever its apparent relevance to the task: buttons, links, menu items, icon controls, clickable rows or text. One line each:

```
action · object or task step it serves · visible association cue · observed result · keyboard
```

- The **association cue** is something read from the screen that names what the action acts on: its own label naming the target, the group or container it sits in, a heading over it, a count of selected items, the row or item it belongs to. Being on the same screen, or near something, is not by itself a cue. An action with no cue is a Groups finding whatever its label says; a weak label is a separate Words finding.
- If the object or step cannot be told from the screen, write `unknown`. Do not invent a purpose.
- The **observed result** comes from activating the action where that is safe: it changes no live or shared data and sends nothing outside the page (opening a menu, moving focus, filtering fixture data). Where activation could submit, save, delete, send or change data, or its effect cannot be known in advance, do not activate it: write `NOT_TESTED (unsafe)` or `NOT_TESTED (unknown effect)`.
- **Keyboard** comes from actual navigation: reach the action with Tab or Shift+Tab, record whether focus is visible on it, and activate it with Enter or Space where activation is safe. An action not reached or not tried that way is `NOT_TESTED`; reachability is never assumed from the markup.

For **Twins** and **Lines**, read the real values instead of estimating them: use [ui-measurements](../ui-measurements/SKILL.md) `style` rows and compare by role per [semantic-consistency](../ux-review/references/semantic-consistency.md). `style` rows are observed values, not a verdict; they do not establish contrast. For contrast use the ui-measurements `contrast` kind with a declared threshold and its source; where it returns `NOT_TESTED` (unsupported paint, opacity, background outside the text box), the entry says `NOT_TESTED` and is never reported as fine. A contrast or keyboard statement without that evidence (helper rows for contrast, actual navigation for keyboard) is reported as `NOT_TESTED` with what was observed, never as a violation or a pass; a ratio calculated by hand from source colours is not evidence.

**Done when:** every look has either problems written down or one line saying what was looked at and found fine; the action inventory has a line for every visible action, each with its cue and an observed result or `NOT_TESTED` with the reason; and every contrast or keyboard statement cites its evidence or says `NOT_TESTED`. A look that could not be done (no keyboard access, no fixture for the empty state) is `not looked`, never `fine`. Missing coverage is listed as `not looked` or `NOT_TESTED` and never counts as fine or as a pass.

## 3. Write each problem so it can be confirmed in one word

One problem, one entry:

```
#4 · Twins · profile card, contact rows
sees:   the phone row has a pencil icon to edit it; the email row has the word "Change"
costs:  the user cannot tell that both rows are edited the same way
proof:  phone edit control 16x16 icon, no text; email edit control text link 13px (style rows 3, 5)
rule:   [consistency] Same role, same treatment
fix:    give both rows the same edit control
sure:   yes
```

- **sees** is what is on the screen, in the owner's words, with no design jargon.
- **costs** is the consequence for the task. An entry with no cost is a preference; move it to the end under "taste" or drop it.
- **rule** names the matching rule in the [ux-review rules](../ux-review/references/rules.md) when one exists; a problem with no rule is still reported, marked `no rule`.
- **sure** is `yes` or `suspect`. A suspect is something that looks wrong but may be intended; the owner decides, unless it fails an applicable requirement (§4).

Mark every entry's place so the owner sees where before reading what: give its selector and its box on the capture (x, y, width, height in CSS px). If the environment can annotate an image, number the marks on a copy of the capture; otherwise the plain capture with each entry's number, selector and box is sufficient. Never inject an overlay or any other change into the audited page.

**Done when:** each problem has all seven lines and a located mark: a number on an annotated capture, or its number, selector and box listed against a plain capture.

## 4. Report for a one-word answer

Order: the inferred task (if any), then problems by cost to the task, then suspects, then taste, then the action inventory. End with the looks marked `not looked` and every `NOT_TESTED` line, each with its reason.

Ask the owner to answer by number: `4 yes`, `6 no`, `7 intended`, `9 worse than you say`. Record the answers beside the entries. A `no` or `intended` on a preference, suspect or taste entry becomes a recorded owner decision, so the next sweep does not raise it again. An entry that fails an applicable accessibility, keyboard or functional requirement (an in-scope WCAG criterion, a broken task step, an unreachable control) stays in the report and is passed to the interface-review gate whatever the answer; record the answer beside it, and only a dated limitation the owner explicitly accepts, with its impact, changes its gate status. Keep the report and the answers in the task record when one exists; otherwise in the project's existing review-evidence location. With neither, say so and leave the report in the conversation only. Before a sweep, read earlier recorded decisions for this screen and do not raise those preference entries again unless the screen changed; requirement failures are rechecked every sweep.

**Done when:** the owner has the list and its located marks (an annotated capture, or a plain capture with each entry's number, selector and box), and the answers are recorded.

## 5. Pointing: the owner says "this is off"

When the owner points at a place without naming the problem, do not ask them to explain. Run the eight looks, including the action inventory, on that region only and answer with **two to four candidate diagnoses**, each one line in the `sees` form and each naming its look:

```
You pointed at the card header. It could be:
a) Groups — the "Archive" icon sits in the header but nothing shows which card items it archives
b) Lines — the title baseline is 3px below the badge beside it
c) Squint — the badge is heavier than the title it labels
Which is it, or is it something else?
```

Each candidate must rest on something read from the screen. If the owner says "something else", ask for one word about the feeling (crowded, lost, loud, cheap, slow, unsure) and map it: crowded → Groups; lost → Glance or Task; loud → Squint; cheap → Lines or Twins; slow → Task; unsure → Words. Then offer new candidates.

**Done when:** the owner has picked a candidate or the mapped looks are exhausted and reported as such.

## Shared words

The eight look names are the vocabulary. Use them in the report, in the owner's answers and in later tasks ("fix the two Twins problems"), so a problem can be named in one word by either side.
