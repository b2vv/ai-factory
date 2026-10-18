#!/bin/bash
# Static guard, not a shell sandbox. Never evaluates the submitted command.
# Requires Python 3; unavailable runtime, invalid input or unsupported syntax
# fail closed. Existing Git hooks/configuration/executables remain trusted.
if ! command -v python3 >/dev/null 2>&1; then
  echo 'BLOCKED: Python 3 is required to inspect this command; nothing was approved.' >&2
  exit 2
fi
read -r -d '' GUARD_PROGRAM <<'PY' || :
import json
import os
import sys

class Blocked(Exception):
    pass

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Blocked('duplicate JSON fields')
        result[key] = value
    return result

def tokenize(command):
    # Retain shell quoting semantics: quoted echo arguments are data, not code.
    # Expansions, redirects, globbing and compound shell syntax are unsupported.
    words, word, started, quote, i = [], [], False, None, 0
    def flush():
        nonlocal word, started
        if started:
            words.append(('word', ''.join(word)))
            word, started = [], False
    while i < len(command):
        c = command[i]
        if c == '\x00':
            raise Blocked('NUL in command')
        if quote == "'":
            if c == "'": quote = None
            else: word.append(c)
        elif c == '\\':
            i += 1
            if i == len(command): raise Blocked('unfinished escape')
            next_char = command[i]
            if quote == '"' and next_char not in '$`"\\\n':
                word.append('\\')
            if next_char != '\n': word.append(next_char)
            started = True
        elif c == quote and quote is not None:
            quote = None
        elif c in '$`':
            raise Blocked('dynamic shell expansion cannot be inspected safely')
        elif quote == '"':
            word.append(c)
        elif c in "'\"":
            quote, started = c, True
        elif c in ' \t\r':
            flush()
        elif c == '#' and not started:
            while i < len(command) and command[i] != '\n': i += 1
            if i < len(command):
                flush(); words.append(('op', ';'))
        elif c in ';\n&|':
            flush()
            op = ';' if c == '\n' else c
            if c in '&|' and i + 1 < len(command) and command[i+1] == c:
                op += c; i += 1
            if op == '&': raise Blocked('background execution is unsupported')
            words.append(('op', op))
        elif c == '~' and not started:
            raise Blocked('tilde expansion is unsupported')
        elif c in '(){}<>*?[]':
            raise Blocked('compound syntax, redirection or expansion is unsupported')
        else:
            word.append(c); started = True
        i += 1
    if quote is not None: raise Blocked('unclosed quote')
    flush()
    return words

# Only commands whose arguments are data are accepted outside Git. In
# particular shells, eval, interpreters, xargs and executable wrappers are not.
DATA_COMMANDS = {'echo', 'printf', 'pwd', 'true', 'false', 'ls', 'cat', 'head', 'tail', 'wc'}
GIT_COMMANDS = {
    'status', 'diff', 'log', 'show', 'add', 'commit', 'switch', 'checkout',
    'restore', 'reset', 'branch', 'fetch', 'pull', 'merge', 'rebase',
    'cherry-pick', 'revert', 'stash', 'tag', 'init', 'clone', 'remote',
    'config', 'ls-files', 'ls-tree', 'rev-parse', 'rev-list', 'describe',
    'blame', 'shortlog', 'show-ref', 'merge-base', 'reflog', 'check-ignore',
    'check-attr', 'check-ref-format', 'diff-files', 'diff-index', 'diff-tree',
    'name-rev', 'count-objects', 'fsck', 'version', 'help', 'push', 'clean'
}

def check(argv):
    # Support only transparent wrappers, never arbitrary env assignments.
    while argv and argv[0] in ('command', 'env'):
        argv = argv[1:]
        if argv and argv[0] == '--': argv = argv[1:]
    if not argv: raise Blocked('missing executable')
    exe = os.path.basename(argv[0])
    if exe in DATA_COMMANDS:
        # printf -v mutates shell state; the ordinary data-only form suffices.
        if exe == 'printf' and len(argv) > 1 and argv[1] == '-v':
            raise Blocked('printf variable assignment is unsupported')
        return
    if exe != 'git':
        raise Blocked('unrecognized executable or wrapper; use a directly inspectable command')
    args = argv[1:]
    i = 0
    while i < len(args) and args[i].startswith('-'):
        arg = args[i]
        if arg in ('--version', '--help') and i == len(args)-1: return
        if arg in ('-C', '--git-dir', '--work-tree', '--namespace'):
            i += 2
            if i > len(args): raise Blocked('missing Git global-option value')
        elif arg.startswith('-C') and len(arg) > 2:
            i += 1
        elif any(arg.startswith(k+'=') for k in ('--git-dir', '--work-tree', '--namespace')):
            i += 1
        elif arg in ('--no-pager', '-P', '--bare', '--literal-pathspecs', '--no-optional-locks'):
            i += 1
        else:
            raise Blocked('unsupported Git global option (including inline configuration)')
    if i == len(args): raise Blocked('missing Git subcommand')
    sub, rest = args[i], args[i+1:]
    if sub not in GIT_COMMANDS:
        raise Blocked('unknown Git subcommand or alias')
    options = rest[:rest.index('--')] if '--' in rest else rest
    def long_option(name):
        return any(a.startswith('--') and name.startswith(a.split('=',1)[0]) for a in options)
    def short_flag(flag):
        return any(a.startswith('-') and not a.startswith('--') and flag in a[1:] for a in options)
    if sub == 'push': raise Blocked('git push is prohibited')
    if sub == 'reset' and long_option('--hard'):
        raise Blocked('git reset --hard is prohibited')
    if sub == 'clean' and (short_flag('f') or long_option('--force')):
        raise Blocked('forced git clean is prohibited')
    if sub == 'branch' and (short_flag('D') or ((short_flag('d') or long_option('--delete')) and (short_flag('f') or long_option('--force')))):
        raise Blocked('forced branch deletion is prohibited')
    if sub in ('checkout', 'restore'):
        for arg in rest:
            if arg.startswith(':') or any(c in arg for c in '*?['):
                raise Blocked('ambiguous checkout/restore pathspec is unsupported')
            if not arg.startswith('-') and os.path.normpath(arg) == '.':
                raise Blocked('whole-tree checkout/restore is prohibited')
    # These modes execute additional commands, which this static guard cannot inspect.
    if sub in ('clone', 'fetch', 'pull') and long_option('--upload-pack'):
        raise Blocked('inline upload-pack command execution is unsupported')
    if sub == 'clone' and (short_flag('u') or short_flag('c') or long_option('--config')):
        raise Blocked('clone inline execution/configuration is unsupported')
    if sub == 'rebase' and (short_flag('x') or long_option('--exec')):
        raise Blocked('rebase command execution is unsupported')

def main():
    data = json.load(sys.stdin, object_pairs_hook=unique_object)
    if not isinstance(data, dict) or not isinstance(data.get('tool_input'), dict):
        raise Blocked('invalid hook input; expected tool_input.command')
    command = data['tool_input'].get('command')
    if not isinstance(command, str) or not command.strip():
        raise Blocked('command must be a nonempty string')
    tokens = tokenize(command)
    argv, checked, last = [], 0, None
    for kind, value in tokens:
        if kind == 'word':
            argv.append(value); last = 'word'
        else:
            if argv:
                check(argv); checked += 1; argv = []
            elif value != ';' or last not in (None, ';'):
                raise Blocked('malformed command separator')
            last = value
    if argv: check(argv); checked += 1
    elif last not in (None, ';'): raise Blocked('unfinished pipeline or conditional')
    if not checked: raise Blocked('no inspectable command')

try:
    main()
except (Blocked, ValueError, OSError, TypeError) as exc:
    # Never echo submitted command text, which may contain credentials.
    reason = str(exc) if isinstance(exc, Blocked) else 'invalid input or inspection failure'
    print('BLOCKED: ' + reason + '. No command was approved.', file=sys.stderr)
    sys.exit(2)
except Exception:
    print('BLOCKED: unexpected inspection failure. No command was approved.', file=sys.stderr)
    sys.exit(2)
PY
if python3 -c "$GUARD_PROGRAM"; then
  exit 0
else
  echo 'BLOCKED: command inspection did not succeed.' >&2
  exit 2
fi
