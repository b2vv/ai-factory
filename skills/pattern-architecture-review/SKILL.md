---
name: pattern-architecture-review
description: Analyzes code for appropriate GoF patterns and KISS, DRY, SOLID, Clean Code and Clean Architecture principles. Use this skill for architectural review, finding a design pattern, or checking simplicity, duplication, responsibilities and dependencies. Support findings with code and assess GoF candidate fit; do not impose a pattern when a simpler solution is better.
---

# Pattern & Architecture Review

Perform an evidence-based review of selected code or a codebase for appropriate GoF patterns and KISS, DRY, SOLID, Clean Code and Clean Architecture principles. By default, review only reads code and produces recommendations; change nothing until the user separately requests implementation.


## 1. Establish boundaries and context

- Clarify the review target from the request: files, module, diff or repository. If unspecified, begin with the relevant area rather than scanning everything unnecessarily.
- Identify languages, framework and local conventions. Check repository instructions, existing architecture documents, `GLOSSARY.md` and ADRs if present.
- Inspect calls, dependencies and tests around the suspect area. Do not infer a need for a pattern from one class or name.
- If context is insufficient for a firm recommendation, state that and lower confidence.

**Done when:** the review area is bounded and important project constraints are known.


## 2. Find a real reason to change

Look for concrete pressure on code: repeated logic, growing conditionals, unstable dependencies, scattered side effects, changes in many places for one behavior, difficulty testing, or reversed dependency direction.

For every finding, record:

- the exact code location (file and lines);
- the observed problem and its consequence for changes, tests or understanding;
- the recurring scenario or variation, when that justifies the abstraction;
- context that could not be verified.

Do not call ordinary complexity a “smell” without explaining its cost. Do not treat matching syntax as proof of shared responsibility: combine code only when it expresses one changing concept.

**Done when:** every subsequent recommendation rests on a concrete code finding.


## 3. Assess appropriate GoF patterns

Use the catalog of 23 classic GoF patterns as candidates, not a mandatory refactoring list. Consider only patterns whose purpose matches the observed pressure. For each problem, compare the best few options, a simple pattern-free solution and leaving the current code unchanged.


### Fit assessment

Give each named pattern four scores from 0 to 5 and compute the weighted percentage:

| Criterion | Weight | What is assessed |
|---|---:|---|
| Problem fit | 35% | How precisely the pattern's intent matches the demonstrated problem |
| Reality of variation | 25% | Whether the pattern isolates a change already occurring or directly expected |
| Boundary and testability gains | 20% | Whether it simplifies dependencies, change locality or testing |
| Cost and complexity | 20% | Whether the gain justifies extra types, relationships and entry points |

Formula: `Σ (criterion score / 5 × weight)`; round to a whole percentage. This is an explainable fit estimate, not a statistical probability. Pattern scores are independent and need not sum to 100%.

- Give every score a short justification linked to the evidence found.
- Separately state analysis confidence (`high`, `medium`, `low`), based on context completeness. Do not substitute it for the fit percentage.
- Score the pattern-free alternative on the same scale when realistic. If simple and sufficient, recommend it.
- Interpretation guide: `80–100%` — strong candidate; `60–79%` — conditional candidate requiring an explicit applicability condition; `<60%` — do not recommend implementation. If every pattern scores low, state plainly that no GoF pattern is needed here.
- Do not promise future flexibility without a concrete change scenario. Do not invent future requirements to raise the score.

Explain differences between patterns easily confused in this situation. For example, `Strategy` isolates an interchangeable algorithm, `State` models behavior according to state, and `Factory Method` delegates product creation. Name a GoF pattern only when its structure and intent actually match the code; do not relabel an ordinary function or dependency.

**Done when:** relevant options are compared for every problem and the winning pattern or simple solution is explained.


## 4. Apply a separate KISS, DRY and SOLID lens

Evaluate each principle independently and name it in the report. A principle is a question about concrete code, not a label for any stylistic preference.

- **KISS:** is there a simpler option that covers the real requirements equally well? Compare it with the current solution and show the cost of extra abstractions, layers or configuration.
- **DRY:** is one rule or piece of knowledge duplicated whose changes must remain consistent? Do not automatically combine identical code with different reasons to change.
- **SRP:** does a module have more than one independent reason to change? Do not interpret this as “one method per class”.
- **OCP:** does a real recurring scenario force adding a variant by editing many stable branches? Do not require extension through inheritance by default.
- **LSP:** can an implementation substitute for its contract without violating expected behavior, preconditions, postconditions or invariants?
- **ISP:** must a particular client depend on operations it does not use? Split the interface only when such a client exists.
- **DIP:** do high-level rules depend on a concrete external detail where a genuine change or testing seam is needed? Do not create an interface just to satisfy the principle formally.

For each violation, cite a code location and concrete cost: extra changes, fragile tests, hidden behavior, repeated fixes or harder reading. If a principle holds or the question has no practical consequence, add no finding. Do not duplicate a related recommendation under several principles: name the main principle and mention the others as overlap.

**Done when:** every KISS/DRY/SOLID signal has evidence, a consequence and a minimal useful next step.


## 5. Check Clean Code and Clean Architecture separately

### Clean Code

Record violations only where they create noticeable cost. In particular, check:

- names that hide intent or responsibility;
- mixing computation, orchestration and side effects;
- implicit dependencies, unclear error handling and unreadable control flow;
- missing tests for important behavior or overly fragile tests.

Do not repeat SRP-lens conclusions here. Record distinct readability and maintainability problems that lens does not cover.

### Clean Architecture

Check dependency direction and real boundaries, not folder names:

- whether domain rules or use cases depend on a framework, database, network or UI;
- whether dependencies point from external details toward internal rules;
- whether policies and mechanisms are separated where changes must be independent;
- whether data crossing boundaries suits the inner layer without leaking framework types;
- whether an interface/port is a useful seam for real variation or testing.

Do not demand layers, interfaces, DI containers or ports for every call. Propose a boundary only when it isolates independent policy, change or an external detail. Check the project's already documented decisions.

**Done when:** Clean Code and Clean Architecture recommendations are separate from GoF and KISS/DRY/SOLID and have local evidence.


## 6. Deliver a concise report

Lead with the conclusion and count of significant findings. Then use this format:


### Finding: <short name>
- **Evidence:** `path/to/file.ext:line` — a concrete observation.
- **Problem:** what this makes harder.
- **GoF candidates:** name and fit percentage for each relevant option; criterion scores and brief explanations.
- **Principles:** KISS / DRY / SOLID if relevant evidence exists; otherwise omit this row.
- **Simpler alternative:** score and explanation when appropriate.
- **Recommendation:** best next step and the condition under which it is worthwhile.
- **Confidence:** high / medium / low, with a reason.

Give **KISS / DRY / SOLID**, **Clean Code** and **Clean Architecture** separate sections. Each contains only substantiated findings or a brief statement that no significant problems were found. Rank next steps by impact and effort. Do not overwhelm the user with all 23 patterns.


## Boundaries and related skills

- Review changes no code and adds no dependencies without a separate request.
- For a deeper audit of module-deepening opportunities, hand off to `$improve-codebase-architecture`.
- For designing a module interface's shape, use `$codebase-design` terminology.
- For reviewing a diff against requirements or standards, use `$code-review`.
