#!/usr/bin/env python3
"""Read one explicit task checkpoint. Read-only; no selection, binding, dispatch or hook installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

LIMITATION = ('Declaration consistency for the explicitly listed scope only; not authorization, '
              'readiness, authenticated independent review, evidence truth, whole-tree coverage, '
              'exactly-once delivery or native host enforcement. Recheck before acting.')


def need(ok):
    if not ok:
        raise ValueError('invalid, stale or unsupported explicit checkpoint')


def text(value, limit=300):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit and not any(ord(c) < 32 for c in value)


def identity(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value) is not None


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(path):
    p = Path(path)
    need(p.is_absolute() and '..' not in p.parts and p.resolve() == p)
    need(not any(x.is_symlink() for x in (p, *p.parents)))
    return p


def relative(root, value):
    need(isinstance(value, str) and bool(value) and not any(ord(c) < 32 for c in value))
    p = Path(value)
    need(not p.is_absolute() and '..' not in p.parts and str(p) == value)
    need(not any(re.search(r'(^\.env|credential|secret|token|^\.git$|^\.claude$|^\.codex$)', part, re.I)
                 for part in p.parts))
    return canonical(root / p)


def read(path, limit=1_048_576, absent=False):
    path = canonical(path)
    if absent and not path.exists():
        return None
    # lstat before open avoids blocking on FIFOs; O_NOFOLLOW and fstat recheck the opened file.
    st = path.lstat()
    need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_size <= limit)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        st = os.fstat(fd)
        need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_size <= limit)
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(limit + 1)
        need(len(data) <= limit)
        return data
    finally:
        os.close(fd)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result)
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique_pairs,
                      parse_constant=lambda _: need(False))


def load_record(raw):
    body = raw.decode('utf-8')
    if not body.lstrip().startswith('{'):
        blocks = re.findall(r'^```ai-factory-pending-action[ \t]*\n(.*?)^```[ \t]*$', body, re.M | re.S)
        need(len(blocks) == 1)
        body = blocks[0]
    need(len(body.encode()) <= 32768)
    data = decode(body)
    need(isinstance(data, dict) and data.get('schema') == 'ai-factory-pending/1')
    return data


def git_head(root):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_OPTIONAL_LOCKS='0')
    cmd = ['git', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', '-C', str(root)]
    def run(*args):
        return subprocess.check_output(cmd + list(args), env=env, stderr=subprocess.DEVNULL, timeout=5).decode().strip()
    need(run('rev-parse', '--show-toplevel') == str(root))
    return run('rev-parse', '--verify', 'HEAD')


def snapshot_id(data):
    value = {k: data[k] for k in ('root', 'head', 'scope')}
    if data.get('ordering') is not None:
        value['ordering'] = data['ordering']
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())


def reconcile_order(ordering, data, evidence, required=False):
    """Check supplied claims and source bindings, not semantic truth or omitted contradictions."""
    if ordering is None:
        return {'status': 'NEEDS_RECONCILIATION' if required else 'NOT_CHECKED',
                'reasons': ['ordering evidence not supplied'], 'completed_dependencies': []}
    need(isinstance(ordering, dict))
    observations = ordering.get('observations')
    dependencies = ordering.get('dependencies')
    topics = ordering.get('decision_topics')
    need(isinstance(observations, list) and 1 <= len(observations) <= 64)
    need(isinstance(dependencies, list) and len(dependencies) <= 32)
    need(isinstance(topics, list) and len(topics) <= 32 and all(identity(x) for x in topics))
    need(len(set(topics)) == len(topics))
    claims = {}
    task_states = ('planned', 'pending', 'in_progress', 'waiting', 'blocked', 'paused', 'completed', 'superseded', 'unknown')
    for row in observations:
        need(isinstance(row, dict) and identity(row.get('id')) and row['id'] not in claims)
        need(row.get('kind') in ('task', 'decision') and identity(row.get('subject')))
        need(row.get('value') in (task_states if row['kind'] == 'task' else ('allow', 'block', 'defer', 'unknown')))
        evidence(row.get('source'))
        if row['value'] == 'superseded':
            need(identity(row.get('replacement')) and row['replacement'] != row['subject'])
        claims[row['id']] = row
    retired = set()
    for row in observations:
        targets = row.get('supersedes', [])
        need(isinstance(targets, list) and len(targets) <= 64 and all(identity(x) for x in targets))
        need(len(set(targets)) == len(targets))
        if targets:
            evidence(row.get('resolution'))
        for target in targets:
            need(target in claims and target != row['id'])
            need(all(claims[target][k] == row[k] for k in ('kind', 'subject')))
            retired.add(target)
    visiting, visited = set(), set()
    def visit(key):
        need(key not in visiting)
        if key in visited:
            return
        visiting.add(key)
        for target in claims[key].get('supersedes', []):
            visit(target)
        visiting.remove(key); visited.add(key)
    for key in claims:
        visit(key)
    unresolved, blockers, completed = [], [], []
    def current(kind, subject):
        rows = [r for k, r in claims.items() if k not in retired and r['kind'] == kind and r['subject'] == subject]
        values = {(r['value'], r.get('replacement') if r['value'] == 'superseded' else None) for r in rows}
        if len(values) != 1:
            unresolved.append('missing or conflicting current ' + kind + ' observations: ' + subject)
            return None
        value = next(iter(values))
        if value[0] == 'unknown':
            unresolved.append('unknown current ' + kind + ' state: ' + subject)
        return value
    selected = current('task', data['task_id'])
    dep_ids = set()
    for dep in dependencies:
        need(isinstance(dep, dict) and identity(dep.get('task_id')))
        name = dep['task_id']; need(name != data['task_id'] and name not in dep_ids); dep_ids.add(name)
        outputs = dep.get('outputs')
        need(isinstance(outputs, list) and len(outputs) <= 32)
        for output in outputs:
            evidence(output)
        status = current('task', name)
        if status and status[0] == 'completed' and outputs:
            completed.append(name)
        elif status and status[0] != 'unknown':
            blockers.append('predecessor lacks completed status and current output evidence: ' + name)
    for topic in topics:
        decision = current('decision', topic)
        if decision and decision[0] in ('block', 'defer'):
            blockers.append('owner constraint does not permit candidate: ' + topic)
    direction = ordering.get('direction')
    if direction is None:
        unresolved.append('current task/roadmap/completed-work assessment missing')
    else:
        need(isinstance(direction, dict) and text(direction.get('rationale'), 1000))
        for key in ('task', 'roadmap', 'approval', 'coverage'):
            evidence(direction.get(key))
        assessment = direction.get('assessment')
        need(assessment in ('aligned', 'conflict', 'duplicate', 'partial', 'unknown'))
        if assessment == 'unknown':
            unresolved.append('task alignment with current direction is unknown')
        elif assessment != 'aligned':
            blockers.append('task alignment requires reconciliation: ' + assessment)
        delivered = direction.get('completed')
        need(isinstance(delivered, list) and len(delivered) <= 32)
        delivered_ids = set()
        for item in delivered:
            need(isinstance(item, dict) and identity(item.get('task_id')) and item['task_id'] not in delivered_ids)
            delivered_ids.add(item['task_id'])
            need(item.get('relation') in ('distinct', 'overlap', 'duplicate', 'unknown'))
            evidence(item.get('evidence'))
            if item['relation'] == 'unknown':
                unresolved.append('completed-work overlap is unknown: ' + item['task_id'])
            elif item['relation'] != 'distinct':
                blockers.append('completed-work overlap needs task reconciliation: ' + item['task_id'])
    replacement = None
    if selected:
        if selected[0] in ('completed', 'superseded'):
            if data['state'] != selected[0]:
                unresolved.append('primary pending state disagrees with completed/superseded task evidence')
            if selected[0] == 'superseded':
                replacement = selected[1]
        elif data['state'] in ('completed', 'superseded'):
            unresolved.append('terminal primary state lacks matching task evidence')
        elif selected[0] in ('waiting', 'blocked', 'paused'):
            blockers.append('selected task is not active: ' + selected[0])
    status = 'NEEDS_RECONCILIATION' if unresolved else 'BLOCKED' if blockers else 'RECONCILED'
    if not unresolved and selected and selected[0] in ('completed', 'superseded'):
        status = 'DO_NOT_RESUME'
    result = {'status': status, 'reasons': unresolved + blockers, 'completed_dependencies': completed,
              'limitation': 'Only supplied claims and cited bytes/quotes were checked; omitted contradictions, semantic alignment, source authority and execution permission are not established.'}
    if replacement:
        result['replacement'] = replacement
    return result


def inspect(root, record, task, require_ordering=False):
    root, record = canonical(root), canonical(record)
    need(root.is_dir() and identity(task))
    raw = read(record, 524288); data = load_record(raw)
    need(data.get('root') == str(root) and data.get('task_id') == task)
    for name in ('task_id', 'revision', 'stage', 'writer', 'action_id', 'action_owner'):
        need(identity(data.get(name)))
    for name in ('next_action', 'contact_mechanism', 'delivery_owner', 'authorization_source'):
        need(text(data.get(name)))
    need(data.get('review_mode') in ('existing_session', 'independent_subagent'))
    reviewer = data.get('reviewer')
    need(reviewer is None or (identity(reviewer) and reviewer != data['writer']))
    need(data['review_mode'] != 'existing_session' or reviewer is not None)
    need(type(data.get('runtime_available')) is bool and type(data.get('required_final_verdict')) is bool)
    state, transfer = data.get('state'), data.get('transfer')
    need(state in ('pending', 'waiting', 'blocked', 'paused', 'completed', 'superseded'))
    need(transfer in ('none', 'prepared', 'attempted', 'sent', 'acknowledged', 'verdict_received'))
    if state in ('waiting', 'blocked', 'paused'):
        need(text(data.get('next_check')))
    need(data['runtime_available'] or state == 'blocked')
    need(data.get('head') == git_head(root))
    scope = data.get('scope')
    need(isinstance(scope, dict) and 1 <= len(scope) <= 100)
    observed = {record: raw}; total = len(raw)
    for name, expected in scope.items():
        path = relative(root, name)
        need(path != record and (expected is None or (isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected))))
        body = read(path, absent=True)
        need((None if body is None else digest(body)) == expected)
        total += len(body or b''); need(total <= 8_388_608)
        observed[path] = body
    checks = data.get('checks')
    need(isinstance(checks, list) and len(checks) <= 100)
    ids = set()
    for check in checks:
        need(isinstance(check, dict) and identity(check.get('id')) and check['id'] not in ids)
        ids.add(check['id'])
        need(type(check.get('required')) is bool and check.get('status') in ('PASS', 'FAIL', 'BLOCKED', 'NOT_TESTED', 'N/A'))
        if state == 'completed':
            need(not check['required'] or check['status'] == 'PASS')
            if check['status'] == 'PASS':
                need(check.get('snapshot_id') == snapshot_id(data))
                path = relative(record.parent, check.get('path'))
                need(path != record)
                body = read(path); need(digest(body) == check.get('sha256'))
                total += len(body); need(total <= 8_388_608); observed[path] = body
            else:
                need(text(check.get('reason')))
    if state == 'completed':
        need(bool(checks))
        if data['required_final_verdict']:
            need(reviewer is not None and identity(data.get('package_id')) and transfer == 'verdict_received')
            path = relative(record.parent, data.get('verdict_path')); need(path != record)
            body = read(path, 524288); need(digest(body) == data.get('verdict_sha256'))
            verdict = decode(body); need(isinstance(verdict, dict))
            need(all(verdict.get(k) == data.get(k) for k in ('task_id', 'revision', 'root', 'head', 'scope', 'package_id', 'reviewer')))
            if data.get('ordering') is not None:
                need(verdict.get('ordering_snapshot_id') == snapshot_id(data))
            need(verdict.get('outcome') == 'ACCEPTED' and verdict.get('blocking_findings') == [])
            need(isinstance(verdict.get('evidence'), list) and bool(verdict['evidence']) and all(text(x) for x in verdict['evidence']))
            total += len(body); need(total <= 8_388_608); observed[path] = body
        else:
            need(text(data.get('review_na_basis')))
    def evidence(source):
        nonlocal total
        need(isinstance(source, dict) and source.get('base', 'record') in ('record', 'repository', 'primary'))
        quote = source.get('quote')
        need(isinstance(quote, str) and 8 <= len(quote.strip()) <= 4096)
        need(all(ord(c) >= 32 or c in '\n\t' for c in quote))
        if source.get('base') == 'primary':
            # No self-referential full-file hash or duplicate task document. The full primary
            # bytes are already observed; bind an exact prose excerpt outside the JSON block.
            need('path' not in source and digest(quote.encode('utf-8')) == source.get('sha256'))
            primary = raw.decode('utf-8')
            need(not primary.lstrip().startswith('{'))
            prose = re.sub(r'^```ai-factory-pending-action[ \t]*\n.*?^```[ \t]*$', '', primary, flags=re.M | re.S)
            need(quote in prose)
            return
        path = relative(root if source.get('base') == 'repository' else record.parent, source.get('path'))
        need(path != record)
        body = read(path)
        need(digest(body) == source.get('sha256') and quote in body.decode('utf-8'))
        if path in observed:
            need(observed[path] == body)
        else:
            total += len(body); need(total <= 8_388_608)
            observed[path] = body
    ordering = reconcile_order(data.get('ordering'), data, evidence,
                               required=require_ordering or state == 'superseded')
    # Detect observed concurrent edits; no locking or claim of an atomic Git/filesystem snapshot.
    need(data['head'] == git_head(root))
    for path, before in observed.items():
        need(read(path, absent=True) == before)
    continuation = 'REVALIDATE_AUTHORIZATION'
    if state in ('completed', 'paused'):
        continuation = 'DO_NOT_RESUME'
    elif state == 'blocked':
        continuation = 'BLOCKED'
    elif transfer == 'attempted':
        continuation = 'RECONCILE_DELIVERY'
    elif state == 'waiting' or transfer in ('sent', 'acknowledged'):
        continuation = 'WAIT'
    status, next_action = 'CONSISTENT', data['next_action']
    if ordering['status'] in ('NEEDS_RECONCILIATION', 'BLOCKED'):
        status, continuation = ordering['status'], 'BLOCKED'
        next_action = 'Reconcile the cited task, current direction, completed work and decisions before implementation; preserve task history and status.'
    elif ordering['status'] == 'DO_NOT_RESUME':
        continuation = 'DO_NOT_RESUME'
        next_action = 'Do not resume this completed or superseded task; a replacement requires its own scope, readiness and current authorization.'
    return {'status': status, 'task_id': task, 'stage': data['stage'], 'state': state,
            'transfer': transfer, 'next_action': next_action, 'recorded_next_action': data['next_action'],
            'ordering': ordering, 'action_owner': data['action_owner'],
            'review_mode': data['review_mode'], 'reviewer': reviewer, 'snapshot_id': snapshot_id(data),
            'continuation': continuation, 'limitation': LIMITATION}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--require-ordering', action='store_true', help='require explicit evidence for candidate/roadmap/dependency reconciliation; no implicit task selection')
    args = parser.parse_args()
    try:
        result = inspect(args.root, args.record, args.task, args.require_ordering)
    except (ValueError, OSError, TypeError, KeyError, RecursionError, subprocess.SubprocessError):
        result = {'status': 'BLOCKED', 'reason': 'Invalid, stale, unsafe or unreadable explicit checkpoint; reconcile the primary record.',
                  'limitation': LIMITATION}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result['status'] == 'CONSISTENT' else 1


if __name__ == '__main__':
    raise SystemExit(main())
