# Opt-in session guard

Python 3.9+ stdlib, POSIX/macOS and Git working trees with HEAD. Windows is unsupported (`fcntl`). No host hooks are activated by packaging or installing this component. Always pass an explicit canonical absolute `--store`; there is no default home directory write.

- Stat only the exact host-provided transcript path; never read transcripts or scan sessions.
- At 4,000,000 bytes prepare; at 5,000,000 bytes advise a new session. These are decimal-byte soft thresholds, not token limits or a hard cap.
- Threshold crossing saves an INCOMPLETE draft. Only an agent-supplied sanitized checkpoint becomes complete. No kill, restart, model invocation, permission change or replay of completed operations.
- Store must be owned by the current user, 0700; records are private. Atomic records and a bounded advisory lock serialize helper writers. Lock contention is DEFERRED; manual commands exit 75 and require retry of the same input. No background queue.
- An exact ID, complete summary, matching root/branch/HEAD/dirty metadata, 24-hour TTL and at most three hops are required. One pointer can be claimed by one target session; a post-claim delivery crash requires manual reconciliation, not replay.
- Dirty metadata uses status, size, mtime and inode, not content hashes; ignored files are outside this check. Revalidate relevant source evidence before acting. Git queries disable fsmonitor and hooks.

## Manual checkpoint and resume

Set KIT to the installed toolkit directory, STORE to a separately approved private state location and REPO to a canonical Git root. State should be outside REPO so recording a checkpoint does not dirty its own snapshot.

```sh
python3 "$KIT/session-size/session_guard.py" checkpoint --host claude \
  --session '<current-id>' --cwd "$REPO" --store "$STORE" <<'JSON'
{"goal":"Approved task", "done":"Completed operations; do not replay", "pending":"Next action", "evidence":"Exact revision and artifact references", "constraints":"Current scope; no new authority"}
JSON
python3 "$KIT/session-size/session_guard.py" resume --host claude \
  --session '<new-id>' --cwd "$REPO" --store "$STORE" --id '<returned-id>'
```

Use `--host codex` for Codex. The five fields are nonempty strings <=1600 characters; never supply secrets. Detection is defense in depth, not a guarantee. Keep detailed evidence in the existing task record.

## Optional future hook activation

The `hook --host <host> --store <absolute-store>` command consumes bounded JSON stdin for SessionStart/UserPromptSubmit/PostToolUse/Stop. An explicit `AI_FACTORY_HANDOFF` environment pointer may request resume. Stop is advisory. No registration file or live hook is written by this kit. Before separate activation, verify the installed host's current event schema, exact command, trust requirements and state permissions; test with synthetic payloads. Native activation and live transcript/CLI behavior remain NOT_TESTED. Without hooks, use the manual commands above.

Tests create disposable Git repositories and synthetic transcript-size files only. They do not launch an AI CLI or read a real transcript. No promise is made that a new host supports the same hook schema.
