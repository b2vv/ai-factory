"""Container-only identity selector. Does not authorize or inspect any path."""
import hashlib
import json
import sys

def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate')
        result[key] = value
    return result

def select(host, raw):
    if host not in ('codex', 'claude') or len(raw) > 8_000_000:
        raise ValueError('input')
    payload = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(payload, dict) or payload.get('hook_event_name') not in ('SessionStart', 'UserPromptSubmit', 'PostToolUse', 'Stop'):
        raise ValueError('event')
    sid = payload.get('session_id')
    if not isinstance(sid, str) or not sid or len(sid.encode()) > 256 or any(ord(c) < 32 or ord(c) == 127 for c in sid):
        raise ValueError('identity')
    result = {}
    for field in ('hook_event_name', 'session_id', 'cwd', 'transcript_path'):
        value = payload.get(field)
        if field == 'transcript_path' and value is None:
            result[field] = None
            continue
        if not isinstance(value, str) or not value or len(value.encode()) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('field')
        result[field] = value
    return hashlib.sha256((host + '\n' + sid + '\n').encode()).hexdigest()

def project(host, raw):
    key = select(host, raw)
    payload = json.loads(raw, object_pairs_hook=pairs)
    result = {k: payload.get(k) for k in ('hook_event_name', 'session_id', 'cwd', 'transcript_path')}
    output = key + '\n' + json.dumps(result, ensure_ascii=True, separators=(',', ':')) + '\n'
    if len(output.encode()) > 16384:
        raise ValueError('projection bound')
    return output

if __name__ == '__main__':
    try:
        sys.stdout.write(project(sys.argv[1], sys.stdin.buffer.read(8_000_001)))
    except Exception:
        sys.exit(2)
