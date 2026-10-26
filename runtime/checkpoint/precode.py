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


MATERIAL_FIELDS = ('acceptance', 'scope', 'contracts', 'dependencies', 'architecture', 'risk', 'test_strategy')


def identity(value):
    return isinstance(value, dict) and filled(value.get('version')) and isinstance(value.get('sha256'), str) and bool(re.fullmatch(r'[a-f0-9]{64}', value['sha256']))


def classify_change(before, after):
    """Compare declared decision surfaces, not the semantics of plan text."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return {'status': 'BLOCKED', 'reason': 'explicit before/after records required'}
    a, b = before.get('decision_surface'), after.get('decision_surface')
    if not all(isinstance(x, dict) and all(filled(x.get(k)) for k in MATERIAL_FIELDS) for x in (a, b)):
        return {'status': 'BLOCKED', 'reason': 'complete decision surfaces required; reason when not applicable'}
    if not identity(before.get('plan')) or not identity(after.get('plan')):
        return {'status': 'BLOCKED', 'reason': 'plan version and sha256 required'}
    if not all(isinstance(x.get('snapshot'), dict) and all(filled(x['snapshot'].get(k)) for k in ('root', 'head', 'dirty_scope')) for x in (before, after)):
        return {'status': 'BLOCKED', 'reason': 'before/after target snapshots required'}
    changed = [k for k in MATERIAL_FIELDS if a[k] != b[k]]
    if changed:
        return {'status': 'RECRITIQUE', 'material_fields': changed}
    if before['plan'] != after['plan']:
        return {'status': 'REAFFIRM', 'material_fields': [], 'reason': 'verify wording-only delta and bind retained verdict to new plan'}
    if before.get('snapshot') != after.get('snapshot'):
        return {'status': 'REVALIDATE', 'material_fields': [], 'reason': 'verify affected evidence against new target snapshot'}
    return {'status': 'UNCHANGED', 'material_fields': []}


def review_binding(review, record):
    if review.get('plan') == record.get('plan') and review.get('snapshot') == record.get('snapshot'):
        return True
    carry = review.get('carry_forward')
    if not isinstance(carry, dict):
        return False
    before = carry.get('before')
    after = {'plan': record.get('plan'), 'snapshot': record.get('snapshot'), 'decision_surface': record.get('decision_surface')}
    change = classify_change(before, after)
    return (change['status'] in ('REAFFIRM', 'REVALIDATE') and
            isinstance(before, dict) and before.get('plan') == review.get('plan') and before.get('snapshot') == review.get('snapshot') and
            carry.get('target_plan') == record.get('plan') and carry.get('target_snapshot') == record.get('snapshot') and
            filled(carry.get('owner')) and filled(carry.get('reason')) and strings(carry.get('evidence')))


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
    need(identity(record.get('plan')) and record.get('plan') == current.get('plan'), 'plan version/hash missing or not current')
    surface = record.get('decision_surface')
    need(isinstance(surface, dict) and all(filled(surface.get(k)) for k in MATERIAL_FIELDS), 'explicit decision surface required')
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
    findings = review.get('findings')
    need(isinstance(findings, list), 'explicit plan findings list required')
    for finding in findings if isinstance(findings, list) else []:
        if not isinstance(finding, dict):
            need(False, 'invalid plan finding'); continue
        need(filled(finding.get('id')) and finding.get('severity') in ('blocker', 'nonblocking') and finding.get('status') in ('open', 'resolved'), 'finding identity/severity/status required')
        if finding.get('severity') == 'blocker':
            need(finding.get('status') == 'resolved', 'open blocker finding prevents READY even with accepted verdict')
        need(filled(finding.get('disposition')) and filled(finding.get('evidence')), 'finding disposition/evidence required')
    if review.get('required') is True:
        need(review.get('stage') == 'plan', 'implementation review does not accept a plan')
        prompt = review.get('prompt')
        need(isinstance(prompt, dict) and filled(prompt.get('path')) and identity(prompt) and prompt == current.get('review_prompt'), 'versioned prompt path/hash missing or not current')
        need(review_binding(review, record), 'critique must bind exact plan and target snapshot; material delta cannot carry verdict')
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
    measurements = record.get('measurements')
    need(isinstance(measurements, list), 'explicit measurement evidence list required (empty when no commands claimed)')
    for e in measurements if isinstance(measurements, list) else []:
        if not isinstance(e, dict):
            need(False, 'invalid measurement'); continue
        status = e.get('status')
        need(status in ('PASS', 'FAIL', 'BLOCKED', 'NOT_TESTED', 'N/A'), 'measurement status required')
        need(filled(e.get('command')) and filled(e.get('artifact')) and e.get('snapshot') == snapshot, 'measurement command/artifact/exact snapshot required')
        need(type(e.get('required')) is bool, 'measurement applicability required')
        if status == 'PASS':
            need(type(e.get('exit_code')) is int and e['exit_code'] == 0, 'PASS needs actual exit 0')
        elif status == 'FAIL':
            need(type(e.get('exit_code')) is int and e['exit_code'] != 0, 'FAIL needs actual nonzero exit')
        else:
            need(e.get('exit_code') is None and filled(e.get('reason')), 'unrun measurement needs null exit and reason')
        if e.get('required') is True:
            need(status == 'PASS', 'required pre-code measurement not passed')
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
    if re.search(r'Next available number\s*[—:-]\s*\*\*\d+', text):
        issues.append({'kind': 'hardcoded-next-number'})
    return {'status': 'FAIL' if issues else 'PASS', 'issues': issues,
            'limitation': 'Checks explicit links and directory coverage, not truth of task status, semantic decisions or agent compliance.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    c = sub.add_parser('record'); c.add_argument('record', type=Path); c.add_argument('snapshot', type=Path)
    c = sub.add_parser('batch'); c.add_argument('record', type=Path); c.add_argument('snapshot', type=Path)
    c = sub.add_parser('change'); c.add_argument('before', type=Path); c.add_argument('after', type=Path)
    c = sub.add_parser('index'); c.add_argument('--root', type=Path, required=True); c.add_argument('--index', required=True); c.add_argument('--task-root', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'index': result = check_index(args.root, args.index, args.task_root)
        elif args.command == 'change': result = classify_change(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
        else:
            record = json.loads(args.record.read_text()); current = json.loads(args.snapshot.read_text())
            result = (validate_batch if args.command == 'batch' else validate)(record, current)
    except (ValueError, OSError, TypeError, KeyError):
        result = {'status': 'BLOCKED', 'issues': ['invalid/unreadable explicit input']}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] in ('PASS', 'READY', 'UNCHANGED', 'REAFFIRM', 'REVALIDATE') else 1


if __name__ == '__main__':
    raise SystemExit(main())
