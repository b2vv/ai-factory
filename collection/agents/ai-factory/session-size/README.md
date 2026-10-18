# Session-size guard / explicit handoff

2026-10-17. Python standard library, POSIX/macOS. Scope: Git working trees with a HEAD.

## Contract

- 4,000,000 bytes: early preparation. 5,000,000 bytes: soft limit. Decimal bytes, not MiB and not token context.
- Hooks stat only the exact host-provided transcript_path. They never read transcripts, scan sessions, copy prompts/tool outputs, or bypass denied access. Missing/denied size is UNKNOWN.
- A first threshold crossing atomically saves an INCOMPLETE draft with root, branch, HEAD, dirty metadata fingerprint and explicit generation ID. It preserves any previous sanitized summary but does not pretend it is current. The current agent supplies goal/done/pending/evidence/constraints through checkpoint at a safe boundary.
- No hard cap: a single output can overshoot; hooks run after events. A hook payload above 8 MB is rejected with BLOCKED before parsing, and the next supported smaller event can measure size. Stop is advisory and never forces another model turn.
- No kill, commit, reset, automatic restart, model invocation, unbounded retry loop, permission/trust expansion, or replay of completed operations.
- State is owner-only under `~/.agents/session-handoffs` (0700; files 0600). Atomic replace, nonblocking advisory lock, unique immutable records, per-session generation, one notification per threshold, one claimed target per pointer. Lock acquisition retries for at most 1 second (25 ms intervals), then reports DEFERRED without reading or advancing protected state. Threshold work remains pending in unchanged session state; the next supported event retries it. An explicit launch handoff ID is retried on later supported events if SessionStart was deferred. There is no background queue: if no later event arrives, retry manually before leaving. Manual checkpoint/resume commands return exit 75 on contention and require the same input/ID to be retried; no success ID is emitted. Permission, IO and invalid-state errors remain BLOCKED. The lockfile is never deleted: OS locks release when the holder exits, including crashes. The global lock serializes cross-session pointer claims; it is not reentrant (nested acquisition also times out). A complete handoff has 24-hour TTL and maximum three handoff hops; further continuation requires manual reconciliation. Checkpoint duplicates with unchanged summary/snapshot are NOOP.
- Snapshot compares canonical root/branch/HEAD and status plus dirty file metadata (size/mtime/inode), without reading file contents or secrets. This detects normal edits but is not a cryptographic content proof and does not cover ignored files. Follow repository freshness rules before acting. Non-Git/no-HEAD roots are BLOCKED.
- Only explicit IDs are accepted, never latest/mtime. Summary is context, not authority. Read current repository instructions, verify authorization, and do not repeat completed side effects.

## Checkpoint in the current session

The SessionStart hook tells the agent its host/session/root and helper path. At meaningful progress and before switching, pass sanitized JSON on stdin:

```sh
python3 ~/.agents/ai-factory/session-size/session_guard.py checkpoint \
  --host claude --session '<current-session-id>' --cwd '/absolute/repo' <<'JSON'
{"goal":"Approved task and scope", "done":"Completed operations; do not repeat", "pending":"Next action and blockers", "evidence":"Commands/results and exact revision or artifact paths; not output dumps", "constraints":"Current permissions, boundaries, decisions; no new authority"}
JSON
```

Use `--host codex` in Codex. Each field is nonempty and at most 1600 characters. Credentials must never be supplied; a conservative detector rejects common patterns but is not a guarantee of secret detection. Keep existing repo journals as primary detailed evidence. If sandbox denies writing shared state, do not change permissions: retain the sanitized summary in the already-authorized task journal and report BLOCKED for this helper.

The command returns an exact ID. Incomplete drafts cannot resume. After checkpoint, avoid additional changes: changed root/branch/HEAD/dirty metadata invalidates it and requires a new checkpoint.

## Fresh session and actual reading

At a safe boundary, the USER closes/leaves the old session and starts a fresh one in the same working tree:

```sh
cd '/absolute/repo'
AI_FACTORY_HANDOFF='<exact-id>' claude
# or:
AI_FACTORY_HANDOFF='<exact-id>' codex
```

No `--resume`, `--continue`, `--last` or fork of the oversized transcript. No shell profile export: the pointer is scoped to one launch. SessionStart loads the exact complete record, validates freshness/root/snapshot/chain, durably records depth and claim, then injects the actual five-field summary. A repeated event for the same target is a no-op; another session cannot consume that pointer. A post-claim delivery crash does not replay automatically: manually inspect/reconcile the exact record. A state/claim inconsistency is BLOCKED.

For hosts that do not execute hooks, explicitly run `resume --host <host> --session <new-session-id> --cwd <repo> --id <id>` using this helper. It validates and prints the actual summary for the agent to read. This is a fallback command, not native automatic resume. If shared state access is unavailable, use the normal authorized journal handoff instead.

## Registration and capabilities

Observed installed versions: Codex CLI 0.156.1 (`hooks stable true`), Claude Code 2.1.302. Official sources inspected:

- [Codex hooks](https://learn.chatgpt.com/docs/hooks)
- [Claude hooks](https://code.claude.com/docs/en/hooks)

Both support SessionStart, UserPromptSubmit and PostToolUse context injection. Stop uses only a systemMessage here: `decision:block` would continue the old session. No documented hook API safely launches a fresh model session.

Global registration appends those four command handlers in `~/.claude/settings.json` and `~/.codex/hooks.json`. Existing hooks, permissions, models, MCP and trust remain unchanged. Codex requires the user to inspect/trust exact definitions via `/hooks`; until then it skips new hooks. No trust bypass is used. Claude applies its normal trust/config reload lifecycle. Existing running sessions are not controlled or restarted.

Courses' existing personal hook at `~/.claude/hooks/courses/session_hooks.py` delegates size/handoff to the same shared handler, preserving gotchas and local note-writing prompts. The shared lock and threshold/intro state deduplicate global+local calls. It no longer chooses latest notes or issues its old size/compaction restart reminders. Product repository registrations and instructions are untouched.

## Evidence / operational status

Disposable tests cover byte boundaries, overshoot, duplicates, concurrent sessions, partial writes, stale/root/branch/HEAD/dirty mismatch, denied stat/write, actual resume content, consumed pointer, same-session refusal, chain limit, credentials and symlinks. Run with `python3 -B -m unittest discover -s ~/.agents/ai-factory/session-size -p 'test_*.py' -v`; tests create only temporary Git fixtures and do not launch either AI CLI.

Registration is configuration evidence, not live execution proof. No paid/model session, active transcript, product gate, or live restart was used in validation. Review and applied hashes are in the task deliverables `~/Documents/Codex/2026-10-16/task/session-size/`.
