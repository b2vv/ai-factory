#!/usr/bin/env python3
"""Validate explicit checkpoint declarations; never inspect Git, invoke tools or authorize work."""
import argparse
import json
from pathlib import Path
import re


def filled(value):
    return isinstance(value, str) and bool(value.strip())


def strings(value):
    return isinstance(value, list) and bool(value) and all(filled(x) for x in value)


def validate(record, current):
    issues = []
    def need(ok, message):
        if not ok:
            issues.append(message)
    if not isinstance(record, dict) or not isinstance(current, dict):
        return {'status': 'BLOCKED', 'issues': ['record and current snapshot must be objects']}
    need(filled(record.get('task_id')), 'task_id required')
    need(record.get('mode') in ('small', 'full', 'resume'), 'explicit small/full/resume route required')
    need(filled(record.get('owner')), 'readiness owner required')
    need(strings(record.get('acceptance')), 'acceptance/source references required')
    need(filled(record.get('scope')) and filled(record.get('non_goals')), 'scope and non-goals required')
    need(record.get('status') == 'READY', 'record is not explicitly READY')
    snapshot = record.get('snapshot', {})
    keys = ('root', 'head', 'dirty_scope')
    need(isinstance(snapshot, dict) and all(filled(snapshot.get(k)) and snapshot.get(k) == current.get(k) for k in keys), 'root/HEAD/dirty-scope snapshot mismatch or missing')
    for label in ('assumptions', 'alternatives'):
        need(strings(record.get(label)), label + ' disposition/evidence required (explicit reason if none)')
    grilling = record.get('grilling', {})
    if not isinstance(grilling, dict):
        grilling = {}
    need(grilling.get('status') in ('resolved', 'not-needed') and filled(grilling.get('reason')), 'grilling disposition and reason required')
    questions = grilling.get('questions')
    need(isinstance(questions, list), 'explicit questions list required')
    for q in questions if isinstance(questions, list) else []:
        if not isinstance(q, dict):
            need(False, 'invalid question'); continue
        need(type(q.get('required')) is bool and filled(q.get('question')), 'question and required flag required')
        need(q.get('status') in ('resolved', 'deferred'), 'question must be resolved or explicitly deferred')
        if q.get('required') is True:
            need(q.get('status') == 'resolved' and filled(q.get('decision')) and filled(q.get('source')), 'required question unresolved or lacks decision/source')
        else:
            need(filled(q.get('reason')) or (filled(q.get('decision')) and filled(q.get('source'))), 'optional question lacks disposition')
    dependencies = record.get('dependencies')
    need(isinstance(dependencies, list), 'explicit dependency list required')
    for dep in dependencies if isinstance(dependencies, list) else []:
        need(isinstance(dep, dict) and filled(dep.get('id')) and dep.get('status') == 'READY' and filled(dep.get('evidence')), 'dependency/shared-writer readiness missing')
    impact = record.get('impact', {})
    if not isinstance(impact, dict):
        impact = {}
    method = impact.get('method')
    need(method in ('files', 'crg', 'ttsc', 'graphify'), 'impact method required')
    need(impact.get('snapshot') == snapshot and bool(snapshot), 'impact snapshot must match checkpoint')
    need(strings(impact.get('callers')) and strings(impact.get('contracts')) and strings(impact.get('checks')), 'concrete callers/contracts/checks required; absence must cite bounded search')
    need(strings(impact.get('evidence')) and filled(impact.get('coverage')), 'impact evidence and coverage/limits required')
    if method == 'files':
        need(filled(impact.get('reason')), 'file fallback/direct-read reason required')
    elif method in ('crg', 'ttsc', 'graphify'):
        need(impact.get('fresh') is True and strings(impact.get('hash_evidence')) and filled(impact.get('untracked_coverage')), 'graph freshness/hashes/untracked coverage unproven')
    review = record.get('plan_review', {})
    if not isinstance(review, dict):
        review = {}
    need(type(review.get('required')) is bool, 'explicit local plan-review applicability required')
    if review.get('required') is True:
        need(review.get('status') == 'ACCEPTED' and filled(review.get('evidence')), 'mandatory planning review not accepted')
        need(review.get('route') in ('existing-session', 'subagent') and filled(review.get('reference')), 'independent reviewer route/reference required')
        need(filled(review.get('author')) and review.get('reference') != review.get('author'), 'author cannot accept own independent gate')
        need(strings(review.get('defense')), 'defense evidence or locally authorized equivalent required')
    else:
        need(review.get('status') == 'N/A' and filled(review.get('reason')), 'plan-review N/A requires local scope reason')
    if record.get('mode') == 'small':
        need(filled(record.get('small_reason')), 'small proportionality reason required')
    if record.get('mode') == 'resume':
        resume = record.get('resume', {})
        if not isinstance(resume, dict):
            resume = {}
        need(filled(resume.get('previous_record')) and filled(resume.get('delta')) and strings(resume.get('revalidated')), 'resume needs previous record, delta/no-change evidence and affected revalidation')
    return {'task_id': record.get('task_id'), 'status': 'BLOCKED' if issues else 'READY', 'issues': issues,
            'limitation': 'Declaration consistency only. Caller must verify sources, freshness, applicability and reviewer independence. Not agent/CI enforcement or permission.'}


def validate_batch(batch, snapshots):
    if not isinstance(batch, dict) or not isinstance(batch.get('tasks'), list) or not batch['tasks'] or not isinstance(snapshots, dict):
        return {'status': 'BLOCKED', 'issues': ['nonempty task records and current snapshots required']}
    tasks = batch['tasks']
    ids = [t.get('task_id') if isinstance(t, dict) else None for t in tasks]
    if not all(filled(i) for i in ids) or len(set(ids)) != len(ids):
        return {'status': 'BLOCKED', 'issues': ['unique task IDs required']}
    results = [validate(t, snapshots.get(t['task_id'], {})) for t in tasks]
    return {'status': 'READY' if all(t['status'] == 'READY' for t in results) else 'BLOCKED', 'tasks': results,
            'limitation': 'Batch approval never supplies missing per-task readiness; independent READY tasks may proceed only within their authorization/dependencies.'}


def check_index(root, index, task_root):
    """Explicit Cargo-style directory index check, not universal project lifecycle inference."""
    root = Path(root).resolve()
    index = (root / index).resolve()
    tasks = (root / task_root).resolve()
    if not index.is_relative_to(root) or not tasks.is_relative_to(root):
        raise ValueError('index inputs must remain within explicit root')
    text = index.read_text()
    issues = []
    linked = set()
    for line_no, line in enumerate(text.splitlines(), 1):
        for link in re.findall(r'\]\(([^)]+)\)', line):
            path = link.partition('#')[0]
            if not path or '://' in path or path.startswith('mailto:'):
                continue
            target = (index.parent / path).resolve()
            if not target.is_relative_to(root) or not target.exists():
                issues.append({'kind': 'missing-or-outside-link', 'line': line_no, 'target': path})
            if target.is_relative_to(tasks):
                relative = target.relative_to(tasks)
                if relative.parts:
                    linked.add(relative.parts[0])
    for directory in sorted(tasks.iterdir()):
        if directory.is_dir() and re.match(r'^\d{3}-', directory.name) and directory.name not in linked:
            issues.append({'kind': 'unindexed-task', 'task': directory.name})
    if re.search(r'Наступний вільний номер\s*[—:-]\s*\*\*\d+', text):
        issues.append({'kind': 'hardcoded-next-number'})
    return {'status': 'FAIL' if issues else 'PASS', 'issues': issues,
            'limitation': 'Checks explicit links and directory coverage, not truth of task status, semantic decisions or agent compliance.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    c = sub.add_parser('record'); c.add_argument('record', type=Path); c.add_argument('snapshot', type=Path)
    c = sub.add_parser('batch'); c.add_argument('record', type=Path); c.add_argument('snapshot', type=Path)
    c = sub.add_parser('index'); c.add_argument('--root', type=Path, required=True); c.add_argument('--index', required=True); c.add_argument('--task-root', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'index': result = check_index(args.root, args.index, args.task_root)
        else:
            record = json.loads(args.record.read_text()); current = json.loads(args.snapshot.read_text())
            result = (validate_batch if args.command == 'batch' else validate)(record, current)
    except (ValueError, OSError, TypeError, KeyError):
        result = {'status': 'BLOCKED', 'issues': ['invalid/unreadable explicit input']}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] in ('PASS', 'READY') else 1


if __name__ == '__main__':
    raise SystemExit(main())
