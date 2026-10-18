---
name: resolving-merge-conflicts
description: "Використовуйте, коли потрібно вирішити поточний конфлікт git merge/rebase."
---

1. **See the current state** of the merge/rebase. Record the initial working-tree and staged status, then check git history and the conflicting files so unrelated local work remains identifiable.

2. **Find the primary sources** for each conflict. Understand deeply why each change was made, and what the original intent was. Read the commit messages, check the PRs, check original issues/tickets.

3. **Resolve each hunk.** Preserve both intents where possible. Where incompatible, pick the one matching the merge's stated goal and note the trade-off. Do **not** invent new behaviour. Always resolve; never `--abort`.

4. Discover the project's **automated checks** and run them — typically typecheck, then tests, then format. Fix anything the merge broke.

5. **Finish the merge/rebase.** Stage only resolved conflict files and necessary merge fixes. Inspect the full staged diff before committing; if unrelated pre-existing staged work would enter the commit, stop and ask how to preserve it rather than silently including or unstaging it. For a merge, commit the resolution. For a rebase, use the rebase continuation flow until all commits are rebased.
