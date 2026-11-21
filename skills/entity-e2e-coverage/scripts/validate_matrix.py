#!/usr/bin/env python3
"""Validate coverage bookkeeping, not browser execution. Python stdlib only."""
import argparse
import json
from pathlib import Path


def validate(contract, report):
    errors = []
    def check(condition, message):
        if not condition:
            errors.append(message)
    def text(value):
        return isinstance(value, str) and bool(value.strip())
    def indexed(items, label):
        check(isinstance(items, list) and bool(items), label + ': nonempty list required')
        result = {}
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or not text(item.get('id')):
                errors.append(label + ': invalid row/id')
                continue
            check(item['id'] not in result, label + ': duplicate ' + item['id'])
            result[item['id']] = item
        return result
    if not isinstance(contract, dict) or not isinstance(report, dict):
        return ['contract and report must be objects']
    qa = indexed(contract.get('qa'), 'qa')
    rows = indexed(contract.get('rows'), 'contract')
    results = indexed(report.get('results'), 'results')
    for q in qa.values():
        check(text(q.get('source')), q['id'] + ': QA source missing')
    seen = set()
    for key in ('revision', 'diff', 'run_id', 'environment', 'fixture_id'):
        check(text(report.get(key)), 'report: missing ' + key)
    for key in ('revision', 'diff'):
        check(text(contract.get(key)), 'contract: missing ' + key)
        check(report.get(key) == contract.get(key), 'report: stale ' + key)
    check(set(results) <= set(rows), 'results: unknown row IDs')
    # Optional inventories are declared from acceptance, never inferred from prose.
    scopes = contract.get('filter_scopes', [])
    check(isinstance(scopes, list), 'filter_scopes: list required')
    for scope in scopes if isinstance(scopes, list) else []:
        if not isinstance(scope, dict):
            errors.append('filter_scopes: invalid scope')
            continue
        check(all(text(scope.get(k)) for k in ('entity_type', 'surface', 'source')),
              'filter_scopes: entity_type/surface/source required')
        for kind in ('filter-matching', 'filter-nonmatching'):
            check(any(row.get('kind') == kind and row.get('required') is True
                      and row.get('entity_type') == scope.get('entity_type')
                      and row.get('surface') == scope.get('surface')
                      and row.get('channel') == 'ui' for row in rows.values()),
                  'filter_scopes: missing ' + kind + ' for ' + str(scope.get('entity_type')) + '/' + str(scope.get('surface')))
    claims = report.get('claimed_pass_rows', [])
    check(isinstance(claims, list), 'claimed_pass_rows: list required')
    for rid in claims if isinstance(claims, list) else []:
        check(isinstance(rid, str) and rid in rows and results.get(rid, {}).get('status') == 'PASS',
              'report: unsupported PASS claim ' + str(rid))
    assertion_keys = set()
    for rid, row in rows.items():
        for key in ('qa_id', 'field', 'expected', 'expected_source', 'surface', 'state', 'action', 'assertion', 'channel'):
            check(text(row.get(key)), rid + ': missing ' + key)
        check(row.get('qa_id') in qa, rid + ': unknown QA ID')
        seen.add(row.get('qa_id'))
        check(type(row.get('required')) is bool, rid + ': required must be boolean')
        check(row.get('channel') in ('ui', 'api', 'db'), rid + ': invalid channel')
        if row.get('required') is False:
            check(text(row.get('na_reason')) and text(row.get('na_source')), rid + ': N/A needs reason and source')
        kind = row.get('kind')
        if kind is not None:
            check(kind in ('filter-matching', 'filter-nonmatching', 'keyboard', 'visual'), rid + ': invalid kind')
            check(text(row.get('entity_type')), rid + ': missing entity_type')
            check(row.get('channel') == 'ui', rid + ': scoped behavior requires ui channel')
        if kind == 'keyboard' and row.get('required') is True:
            check(row.get('input_method') in ('simulated-browser-key', 'manual-key'), rid + ': keyboard needs browser/manual key input')
            check(text(row.get('key')) and text(row.get('ui_effect')), rid + ': keyboard needs key and UI effect')
        result = results.get(rid)
        if result is None:
            errors.append(rid + ': missing coverage row')
            continue
        if row.get('required') is False:
            check(result.get('status') == 'N/A', rid + ': non-applicable row must be N/A')
            continue
        check(result.get('status') == 'PASS', rid + ': required row not PASS (' + str(result.get('status')) + ')')
        if result.get('status') != 'PASS':
            check(text(result.get('reason')), rid + ': non-PASS needs reason')
            continue
        ev = result.get('evidence')
        if not isinstance(ev, dict):
            errors.append(rid + ': missing evidence')
            continue
        check(ev.get('executed') is True, rid + ': unexecuted evidence')
        for key in ('revision', 'diff', 'run_id', 'environment', 'fixture_id'):
            check(ev.get(key) == report.get(key), rid + ': stale/mismatched ' + key)
        for key in ('surface', 'state', 'channel', 'assertion'):
            check(ev.get(key) == row.get(key), rid + ': substitution ' + key)
        scoped_keys = ('kind', 'entity_type') if kind is not None else ()
        if kind == 'keyboard':
            scoped_keys += ('input_method', 'key', 'ui_effect')
        for key in scoped_keys:
            check(ev.get(key) == row.get(key), rid + ': substitution ' + key)
        for key in ('artifact', 'assertion_id', 'observed'):
            check(text(ev.get(key)), rid + ': missing evidence ' + key)
        pair = (ev.get('artifact'), ev.get('assertion_id'))
        check(pair not in assertion_keys, rid + ': reused assertion for distinct obligation')
        assertion_keys.add(pair)
    check(set(qa) <= seen, 'contract: QA IDs without coverage rows: ' + ', '.join(sorted(set(qa) - seen)))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contract', type=Path)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    try:
        errors = validate(json.loads(args.contract.read_text()), json.loads(args.report.read_text()))
    except (ValueError, OSError, TypeError) as exc:
        errors = ['Invalid input: ' + str(exc)]
    print(json.dumps({'coverage_complete': not errors, 'errors': errors, 'browser_execution_proven': False}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
