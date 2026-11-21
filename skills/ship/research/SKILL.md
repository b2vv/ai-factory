---
name: research
description: "Researches a question using reliable primary sources and records findings in a repository Markdown file. Use when the user wants to research a topic, gather facts from documentation or APIs, or delegate routine reading to a background agent."
---

Spin up a **background agent** to do the research, so you keep working while it reads. Give it a working file per [agent stream-to-file](../../../rules/agent-stream-to-file.md) §2, separate from the findings file; if it returns empty, read that file before retrying.

Its job:

1. Investigate the question against **primary sources** (official docs, source code, specs, first-party APIs), not a secondary write-up of them. Follow every claim back to the source that owns it.
2. Write the findings to a single Markdown file, citing each claim's source.
3. Save it where the repo already keeps such notes; match the existing convention, and if there is none, put it somewhere sensible and say where.
