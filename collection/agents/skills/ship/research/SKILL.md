---
name: research
description: Досліджує питання за надійними першоджерелами і фіксує висновки у Markdown-файлі репозиторію. Використовуйте, коли користувач хоче дослідити тему, зібрати факти з документації чи API, або делегувати рутинне читання фоновому агенту.
---

Spin up a **background agent** to do the research, so you keep working while it reads.

Its job:

1. Investigate the question against **primary sources** (official docs, source code, specs, first-party APIs), not a secondary write-up of them. Follow every claim back to the source that owns it.
2. Write the findings to a single Markdown file, citing each claim's source.
3. Save it where the repo already keeps such notes; match the existing convention, and if there is none, put it somewhere sensible and say where.
