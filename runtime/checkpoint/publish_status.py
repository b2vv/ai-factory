#!/usr/bin/env python3
"""Publish a neutral local dashboard observation from an explicitly selected primary record."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from pending_action import canonical, decode, digest, git_head, inspect, read, relative


# Project IDs come from the owner's dashboard projects config, never from the kit.
PROJECT_ID = re.compile('[a-z0-9][a-z0-9-]{0,62}')
EVENTS = ('start', 'stage', 'handoff', 'closeout')
WORKFLOW_STAGES = ('plan', 'implementation', 'verification', 'review', 'qa', 'push', 'update')
LIMIT = 524288


class Uncertain(Exception):
    """The external writer may have acted; inspect the destination before retrying."""


def need(ok, message):
    if not ok:
        raise ValueError(message)


def private(path, is_dir=False):
    st = path.lstat()
    need(st.st_uid == os.getuid() and not st.st_mode & 0o077, 'binding/feed must be owned and private')
    need(stat.S_ISDIR(st.st_mode) if is_dir else stat.S_ISREG(st.st_mode), 'binding/feed has wrong type')


def registered_root(path, project):
    """The dashboard projects config must register the project; the writer re-validates it fully."""
    info = path.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o022,
         'dashboard projects config must be an owned regular file, not group/world writable')
    entries = decode(read(path, 65536))
    need(isinstance(entries, list), 'dashboard projects config must be a JSON array')
    found = [x for x in entries if isinstance(x, dict) and x.get('id') == project]
    need(len(found) == 1 and isinstance(found[0].get('root'), str), 'project is not in the dashboard projects config')
    return found[0]['root']


def binding(path, project, root):
    path = canonical(path)
    private(path)
    raw = decode(read(path, 16384))
    need(isinstance(raw, dict) and set(raw) == {'schema', 'projects', 'feed', 'publisher', 'dashboard_projects'}
         and raw.get('schema') == 'ai-factory-dashboard-bindings/2', 'invalid binding schema')
    projects = raw.get('projects')
    need(isinstance(projects, dict) and project in projects
         and all(isinstance(x, str) and PROJECT_ID.fullmatch(x) for x in projects), 'project is not bound')
    project_binding = projects[project]
    need(isinstance(project_binding, dict) and set(project_binding) <= {'root', 'record_roots'}
         and project_binding.get('root') == str(root), 'bound and requested project roots differ')
    roots = project_binding.get('record_roots', [])
    need(isinstance(roots, list) and len(roots) <= 4, 'invalid additional record roots')
    roots = [root] + [canonical(x) for x in roots]
    need(all(x.is_dir() for x in roots), 'record roots must be directories')
    for base in roots[1:]:
        need(not base.is_relative_to(root) and not root.is_relative_to(base),
             'additional records root cannot contain the project or mirror its internal paths')
    feed = canonical(raw['feed'])
    private(feed, is_dir=True)
    need(all(not feed.is_relative_to(x) and not x.is_relative_to(feed) for x in roots),
         'feed must be separate from project and record roots')
    publisher = canonical(raw['publisher'])
    info = publisher.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o022
         and info.st_nlink == 1 and os.access(publisher, os.X_OK) and not publisher.is_relative_to(feed)
         and all(not publisher.is_relative_to(x) for x in roots),
         'publisher must be an owned executable outside project and record roots')
    registry = canonical(raw['dashboard_projects'])
    need(not registry.is_relative_to(feed) and all(not registry.is_relative_to(x) for x in roots),
         'dashboard projects config must be outside the feed, project and record roots')
    need(registered_root(registry, project) == str(root), 'dashboard projects config registers another root')
    return roots, feed, publisher, registry


def selected_record(path, roots):
    path = canonical(path)
    need(path.suffix.lower() in ('.md', '.json'), 'only a selected Markdown/JSON primary record is supported')
    for base in roots:
        if path.is_relative_to(base):
            return relative(base, str(path.relative_to(base)))
    raise ValueError('primary record is not inside an explicitly bound record root')


def read_snapshot(root, record):
    head = git_head(root)
    need(re.fullmatch('[a-f0-9]{40}', head) is not None, 'unsupported current Git HEAD')
    first = record.lstat()
    contents = read(record, LIMIT)
    last = record.lstat()
    fingerprint = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    need(fingerprint(first) == fingerprint(last) and bool(contents) and head == git_head(root),
         'primary record or HEAD changed during read')
    return head, digest(contents), last.st_mtime_ns


def payload(project, task, event, stage, snap, observation, scope_id, scope_digest):
    head, _, mtime = snap
    recorded = datetime.fromtimestamp(mtime / 1_000_000_000, timezone.utc)
    need(recorded <= observation, 'record timestamp is ahead of the observation')
    data = {
        'schema': 'factory-dashboard/transition/1',
        'project': project,
        'revision': head,
        'taskId': task.lower(),
        'event': event,
        'updatedAt': observation.isoformat(),
        'recordedAt': recorded.isoformat(),
    }
    if stage is not None:
        data['stage'] = stage
    if scope_id is not None:
        data.update(scopeId=scope_id, scopeSnapshot=scope_digest)
    return data


def writer_command(publisher, registry, feed, apply):
    command = [str(publisher), '-projects', str(registry), '-feed', str(feed), '-publish-transition']
    return command + (['-apply'] if apply else [])


def call_writer(command, data, may_write):
    try:
        result = subprocess.run(command, input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                cwd=Path(command[0]).parent, timeout=8, check=False,
                                env={'PATH': os.defpath, 'LC_ALL': 'C', 'HOME': str(Path(command[0]).parent)})
    except subprocess.TimeoutExpired:
        if may_write:
            raise Uncertain('publisher timed out after apply; inspect the feed before retrying') from None
        raise ValueError('publisher validation timed out') from None
    need(result.returncode == 0, 'dashboard publisher rejected the record')


def publish(project, root, record, task, event, config, apply=False, expected_head=None, expected_record=None, stage=None, scope_id=None):
    need(isinstance(project, str) and PROJECT_ID.fullmatch(project) and event in EVENTS and re.fullmatch('[A-Za-z0-9][A-Za-z0-9-]{0,47}', task),
         'unknown project, transition, or unsafe task identifier')
    need((event == 'stage' and stage in WORKFLOW_STAGES) or (event != 'stage' and stage is None),
         'stage must be given only for the stage event')
    root = canonical(root)
    allowed, feed, publisher, registry = binding(config, project, root)
    record = selected_record(record, allowed)
    snap = read_snapshot(root, record)
    need(expected_head is None or expected_head == snap[0], 'selected HEAD no longer matches')
    need(expected_record is None or expected_record == snap[1], 'selected primary record no longer matches')
    def scope():
        if scope_id is None:
            return None
        need(re.fullmatch('[a-z0-9][a-z0-9-]{0,47}', scope_id), 'scope ID must be a canonical lowercase slug')
        checked = inspect(root, record, task)
        value = checked.get('snapshot_id')
        need(checked.get('status') == 'CONSISTENT' and isinstance(value, str)
             and re.fullmatch('[a-f0-9]{64}', value), 'exact pending-action scope is not consistent')
        return value

    scope_snapshot = scope()
    event_data = payload(project, task, event, stage, snap, datetime.now(timezone.utc), scope_id, scope_snapshot)
    data = json.dumps(event_data, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode()

    def unchanged():
        return scope_snapshot == scope() and snap == read_snapshot(root, record)

    call_writer(writer_command(publisher, registry, feed, False), data, False)
    need(unchanged(), 'primary record, HEAD or scope changed after validation')
    if apply:
        call_writer(writer_command(publisher, registry, feed, True), data, True)
        try:
            ok = read(feed / f'{project}.transition.json', 16384) == data and unchanged()
        except (ValueError, OSError, subprocess.SubprocessError):
            ok = False
        if not ok:
            raise Uncertain('transition receipt or source moved after apply; reconcile before retrying')
    return 'PUBLISHED' if apply else 'VALIDATED'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bindings', default=os.environ.get('AI_FACTORY_DASHBOARD_BINDINGS'),
                        help='owner-authorized local binding; default AI_FACTORY_DASHBOARD_BINDINGS')
    parser.add_argument('--project', required=True, help='project ID from the dashboard projects config')
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--event', required=True, choices=EVENTS)
    parser.add_argument('--stage', choices=WORKFLOW_STAGES, help='required only for the stage event; never a verdict')
    parser.add_argument('--scope-id', help='optional lowercase slice ID; requires an existing consistent pending-action block')
    parser.add_argument('--expect-head')
    parser.add_argument('--expect-record-sha256')
    parser.add_argument('--apply', action='store_true', help='write only to the bound local dashboard feed')
    args = parser.parse_args()
    if not args.bindings:
        print('UNBOUND: local dashboard publication is not configured')
        return 2
    try:
        outcome = publish(args.project, args.root, args.record, args.task, args.event, args.bindings,
                          args.apply, args.expect_head, args.expect_record_sha256, args.stage, args.scope_id)
    except Uncertain:
        print('OUTCOME_UNCERTAIN: inspect the bound dashboard feed before retrying')
        return 3
    except (ValueError, OSError, KeyError, TypeError, RecursionError, subprocess.SubprocessError):
        print('BLOCKED: invalid/stale source, binding, or publisher; no published outcome is confirmed')
        return 1
    print(f'{outcome}: {args.project} / {args.task} / {args.event}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
