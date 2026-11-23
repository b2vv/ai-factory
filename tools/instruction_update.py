"""Five exact legacy-instruction migrations, explicitly registered for normal update.

Public plans contain hashes only. Private durable preimages, lineage and delegated
receipt correlation support guarded rollback; the group is not an atomic transaction.
"""
import base64
from contextlib import contextmanager
import fcntl
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid

REG = 'instruction-registration.json'
PENDING = 'instruction-update-pending.json'
CURRENT = 'instruction-current.json'
RECEIPTS = 'instruction-updates'
HOME_STATE = '.agents/.ai-factory-instructions'
MAX_DOCUMENT = 128 * 1024
MAX_SPEC = 128 * 1024
MAX_RECEIPTS = 4096


def sibling(name):
    path = Path(__file__).absolute().with_name(name + '.py')
    spec = importlib.util.spec_from_file_location('_instruction_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture = sibling('capture_update')
KNOWN = {
    'empty-codex-entry': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'legacy-project-size-1': '3772859776cc3c688a5bc654bfbbfbbc00df06d3d72fa2e389347f02921cef52',
    'legacy-project-size-2': 'ae2a224321eea03fa5afbff98d45d8f2039a7794e71a26660ec66e602c1deb48',
    'legacy-agents-entry': 'a23de2cf90cca685bff8b9d10a5b6e2e8d9162bc58ebf6fa20b6fc6d258d5337',
    'legacy-claude-entry': 'c2f04a1c168518fa8df9d881a0d3423b23c8c5e41c0b29f00f0cfbf9354351f6',
}
# Earlier recipe ids that existing registrations may still name. Only their
# SHA256 is kept (no private names in the package); a registered spec is never
# rewritten, so its stored id stays byte-identical across updates.
RETIRED_RECIPES = {
    '1d0f44c0ec0a9b1ab02f6969f617108aef5fc40093705e19cd65c409fa9f0a73': 'legacy-project-size-1',
    '9f7cd2586db11535db30cb972a173cd59d9263ca54637f15504b1f8b5944b834': 'legacy-project-size-2',
}


def known_recipe(recipe):
    """Return the current KNOWN id for a recipe id, or None if unrecognized."""
    if recipe in KNOWN: return recipe
    return RETIRED_RECIPES.get(hashlib.sha256(recipe.encode('utf-8')).hexdigest())

# Conflict detection only, never broad regex rewriting of unrelated user prose.
# Exact codepoint-length/SHA256 commitments to reviewed legacy residues. This
# avoids bundling personal instruction text; it is not a language-gate exemption.
RESIDUES = (
    (22, '71ef1641123db6f877b91818ccbc1d4fb6ff9758beae6428ea444f6386d98e8f'),
    (16, '4abaad7e28de34f4ace0ea67c2a67440bf7e6ff526c5620229bbbdd5d9c40529'),
    (26, '47a7030a180cb209cb7bde62d10d698886322c1eeeadf12207c69b621d39180a'),
    (26, '1cefdb8b0e54fec74a51a57827a3c8ef7ccdc2e49a39f81d7177431dc6460f7a'),
)


def has_residue(text):
    # Documents are bounded by MAX_DOCUMENT; no unbounded regex or semantic match.
    return any(hashlib.sha256(text[start:start + length].encode('utf-8')).hexdigest() == digest
               for length, digest in RESIDUES for start in range(max(0, len(text) - length + 1)))


def replacement(root, recipe):
    entry = str(root / 'rules/agent-entry.md')
    if recipe.endswith('-entry'):
        text = ('# AI Factory shared instructions\n\n'
                f'Before work, skills or delegation, read `{entry}` and follow its current rules.\n'
                'The installed shared kit is the single source for cross-project rules and skills; '
                'project rules and current owner instructions keep their precedence.\n'
                'After identifying the verified repository root, read its AGENTS.local.md if present '
                'for scoped project routes and local rules; do not assume it is automatically discovered.\n'
                'Before nontrivial delegation, read its linked `agent-stream-to-file.md`: assign a '
                'separate progress file, consume bounded progress/results, never load full raw agent '
                'JSONL transcripts into context. Count launched versus returned agents; silence is '
                'not a clean result. If a progress file is empty, one authorized retry in a fresh '
                'context with a sufficiently strong reviewer is permitted; the same model may be used.\n'
                'Use the canonical task-resume and archive-search routes, not stale copied rules.\n')
        return text + (f'\n@{entry}\n' if recipe == 'legacy-claude-entry' else '')
    return (f'Session continuation follows the current shared rules at `{entry}`. '
            'Use the active task record and current host context-budget configuration; '
            'raw transcript bytes and compaction counts are not restart thresholds.')


def active(k, root, spec=None):
    return spec is not None or any((Path(root) / k.STATE / n).exists() for n in (REG, PENDING))


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_dir(k, path, create=False):
    path = k.absolute(path)
    if create and not path.exists():
        path.mkdir(mode=0o700)
        sync_dir(path.parent)
    if path.exists():
        s = path.stat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) & 0o077:
            raise ValueError('instruction state directory must be private and owned')


def private_json(k, path, limit=None):
    raw = k.regular(path)
    if raw is not None and limit is not None and len(raw) > limit:
        raise ValueError('instruction metadata too large')
    return capture.private_json(k, path)


def read_receipt(k, path):
    private_json(k, path)
    return k.read_tx(path)


def b64(raw):
    return base64.b64encode(raw).decode() if raw is not None else None


def decode(k, encoded, signature):
    if signature is None:
        if encoded is not None: raise ValueError('unexpected backup bytes')
        return None
    if not isinstance(encoded, str): raise ValueError('missing backup bytes')
    raw = base64.b64decode(encoded, validate=True)
    if k.digest(raw) != signature['sha256']: raise ValueError('corrupt instruction backup')
    return raw


def metadata(k, path):
    raw = k.regular(path)
    if raw is not None: private_json(k, path)
    return {'signature': k.signature(path), 'bytes': b64(raw)}


def disjoint(paths):
    """Reject aliases conservatively, including case-insensitive macOS volumes."""
    for index, path in enumerate(paths):
        a = str(path).casefold().rstrip('/')
        for other in paths[:index]:
            b = str(other).casefold().rstrip('/')
            if a == b or a.startswith(b + '/') or b.startswith(a + '/'):
                raise ValueError('overlapping instruction paths')
            if path.exists() and other.exists() and os.path.samefile(path, other):
                raise ValueError('aliased instruction paths')


def validate_spec(k, root, spec):
    if not isinstance(spec, dict) or set(spec) != {'schema', 'home', 'managed_root', 'targets'} or type(spec['schema']) is not int or spec['schema'] != 1:
        raise ValueError('invalid instruction specification')
    if spec['managed_root'] != str(root): raise ValueError('instruction root mismatch')
    home = k.absolute(spec['home'])
    if not home.is_dir(): raise ValueError('instruction home missing')
    targets = spec['targets']
    if not isinstance(targets, list) or not 1 <= len(targets) <= 5:
        raise ValueError('invalid instruction target count')
    seen = set(); result = []
    for target in targets:
        if not isinstance(target, dict) or set(target) != {'recipe', 'project', 'fragment'}:
            raise ValueError('invalid instruction target')
        fragment = target['fragment']
        recipe = known_recipe(target['recipe']) if isinstance(target['recipe'], str) else None
        if recipe is None or recipe in seen or not isinstance(fragment, str):
            raise ValueError('unknown instruction recipe')
        raw = fragment.encode('utf-8')
        if (not raw and recipe != 'empty-codex-entry') or len(raw) > 16384 or k.digest(raw) != KNOWN[recipe]:
            raise ValueError('unknown instruction fragment')
        seen.add(recipe)
        if recipe.endswith('-entry'):
            if target['project'] is not None: raise ValueError('global instruction has project')
            path = home / {'legacy-agents-entry': '.agents/AGENTS.md', 'legacy-claude-entry': '.claude/CLAUDE.md', 'empty-codex-entry': '.codex/AGENTS.md'}[recipe]
        else:
            project = k.absolute(target['project'])
            if project == home or home not in project.parents or not project.is_dir() or not (project / '.git').is_dir():
                raise ValueError('explicit canonical project checkout beneath home required')
            path = project / 'CLAUDE.local.md'
        result.append((target, k.absolute(path)))
    return home, result


def discovery_guard(k, home, targets):
    if not any(target['recipe'] == 'empty-codex-entry' for target, _ in targets): return None
    default = k.absolute(home/'.codex')
    override = os.environ.get('CODEX_HOME')
    if override is not None and override != str(default):
        raise ValueError('unexpected CODEX_HOME; default discovery not verified')
    if os.path.lexists(default/'AGENTS.override.md'):
        raise ValueError('Codex instruction override exists; preserve and reconcile explicitly')
    return {'CODEX_HOME': override, 'override_absent': True}


def classify(raw, root, target):
    text = raw.decode('utf-8')
    if text.startswith('\ufeff') or '\r' in text:
        raise ValueError('unknown instruction encoding or line endings')
    old = target['fragment']; new = replacement(root, target['recipe'])
    if target['recipe'] == 'empty-codex-entry':
        if raw == b'': return new.encode('utf-8')
        if raw == new.encode('utf-8'): return raw
        raise ValueError('unknown nonempty Codex entry; preserved')
    if text.count(old) == 1 and new not in text:
        start = text.index(old)
        if target['recipe'].endswith('-entry') and start != 0:
            raise ValueError('unknown global instruction prefix')
        tail = text[:start] + text[start + len(old):]
        if has_residue(tail):
            raise ValueError('unrecognized legacy continuation instruction remains')
        return (text[:start] + new + text[start + len(old):]).encode('utf-8')
    if old not in text and text.count(new) == 1:
        if target['recipe'].endswith('-entry') and not text.startswith(new):
            raise ValueError('unknown canonical instruction placement')
        tail = text.replace(new, '', 1)
        if has_residue(tail):
            raise ValueError('unrecognized legacy continuation instruction remains')
        return raw
    raise ValueError('unknown or ambiguous instruction content; preserved')


def host_plan(k, root, targets):
    entries = []
    for target, path in targets:
        before = k.signature(path); raw = k.regular(path)
        if raw is None or before is None or len(raw) > MAX_DOCUMENT or k.digest(raw) != before['sha256']:
            raise ValueError('missing, oversized or changing instruction target')
        if path.stat().st_uid != os.getuid() or not before['mode'] & 0o444 or not os.access(path, os.R_OK):
            raise ValueError('instruction target must be readable and owned')
        desired = classify(raw, root, target)
        if len(desired) > MAX_DOCUMENT: raise ValueError('instruction result too large')
        if k.signature(path) != before: raise ValueError('instruction changed while planning')
        entries.append({'path': str(path), 'recipe': target['recipe'], 'before': before,
                        'after': {'sha256': k.digest(desired), 'mode': before['mode']},
                        'old': b64(raw), 'new': b64(desired)})
    return entries


def inventory(k, root, combined):
    directory = root / k.STATE / (capture.RECEIPTS if combined else 'receipts')
    names = sorted(p.stem for p in directory.glob('*.json'))
    if len(names) > MAX_RECEIPTS or any(not re.fullmatch('[a-f0-9]{32}', n) for n in names):
        raise ValueError('delegated receipt inventory out of bounds')
    return names


def fingerprint(k, root, spec=None):
    files = [root/k.STATE/n for n in ('installed.json', 'pending.json', capture.REG, capture.PENDING)]
    if spec is not None:
        registration = k.absolute(Path(spec['registration_root']) / k.STATE)
        files.extend([registration/'current.json', registration/'pending.json'])
        current_path = registration/'current.json'
        if current_path.exists():
            current = read_receipt(k, current_path)
            ident = current.get('id')
            if not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{32}', ident):
                raise ValueError('invalid capture current receipt')
            receipt = registration/'receipts'/(ident+'.json')
            read_receipt(k, receipt)
            files.append(receipt)
            declared = current.get('files')
            if not isinstance(declared, dict) or len(declared) > 256:
                raise ValueError('invalid capture file inventory')
            files.extend(k.absolute(name) for name in declared)
    return {str(path): k.signature(path) for path in files}


def capture_context(bp, combined):
    return bp['_capture']['binding']['spec'] if combined else None


def check_home(k, home, root):
    directory = k.absolute(home/HOME_STATE)
    private_dir(k, directory)
    owner = private_json(k, directory/'owner.json')
    if owner is not None and owner != {'schema': 1, 'root': str(root)}:
        raise ValueError('home already bound to another managed root')
    return directory


def plan(k, package, root, components=(), spec_path=None, capture_spec=None):
    root = k.safe_root(root); package = k.absolute(package)
    state = root/k.STATE
    for directory in (state, state/RECEIPTS): private_dir(k, directory)
    if (state/PENDING).exists(): raise ValueError('unfinished instruction update: explicit rollback required')
    combined = capture.active(k, root, capture_spec)
    bp = capture.plan(k, package, root, components, capture_spec) if combined else k.plan(package, root, components)
    # This authorization does not permit hook/consent/credential reconciliation.
    if combined and (bp['capture']['changes'] or bp['capture']['registration_changed']):
        raise ValueError('instruction update cannot change capture configuration')
    _, selected, _ = k.payload(package, components)
    required = {'rules/agent-entry.md', 'tools/kit.py', 'tools/capture_update.py', 'tools/instruction_update.py'}
    if not required <= set(selected): raise ValueError('canonical entry or instruction updater not selected')
    selected['rules/agent-entry.md'].decode('utf-8')
    previous = private_json(k, state/REG)
    if previous and previous.get('spec_sha256') != k.digest(k.encode(previous['spec'])):
        raise ValueError('instruction registration integrity mismatch')
    spec = private_json(k, k.absolute(spec_path), MAX_SPEC) if spec_path is not None else (previous or {}).get('spec')
    if spec is None: raise ValueError('explicit instruction specification required')
    if previous and previous['spec'] != spec: raise ValueError('instruction registration scope changed')
    home, targets = validate_spec(k, root, spec)
    discovery = discovery_guard(k, home, targets)
    homedir = check_home(k, home, root)
    extra = [package, root, homedir]
    if spec_path is not None: extra.append(k.absolute(spec_path))
    context = capture_context(bp, combined)
    if combined:
        extra.extend(k.absolute(p) for p in bp['_capture']['connector']['files'])
        extra.extend([k.absolute(context['registration_root']), k.absolute(context['mapping_path'])])
    # Extra resources may overlap each other (e.g. capture mapping inside registration);
    # only target-v-target and target-v-resource overlap is forbidden here.
    paths = [p for _, p in targets]; disjoint(paths)
    for path in paths:
        for other in extra: disjoint([path, other])
    files = host_plan(k, root, targets)
    registration = {'schema': 1, 'spec': spec, 'spec_sha256': k.digest(k.encode(spec))}
    baseline = {name: metadata(k, state/name) for name in (REG, CURRENT)}
    current = private_json(k, state/CURRENT)
    if current and (current.get('root') != str(root) or not re.fullmatch('[a-f0-9]{32}', current.get('id', ''))):
        raise ValueError('invalid instruction lineage')
    binding = {'base_plan_id': bp['plan_id'], 'capture': combined, 'files': files,
               'registration': registration, 'baseline': baseline, 'parent': current,
               'dependencies': fingerprint(k, root, context), 'inventory': inventory(k, root, combined),
               'home': str(home), 'discovery': discovery}
    rawreg = k.encode(registration)
    regafter = {'sha256': k.digest(rawreg), 'mode': 0o600}
    binding['registration_after'] = regafter
    noop = bp['status'] == 'NOOP' and all(e['before'] == e['after'] for e in files) and baseline[REG]['signature'] == regafter
    result = {'status': 'NOOP' if noop else 'PLANNED', 'plan_id': k.digest(k.encode(binding)),
              'root': str(root), 'package': str(package), 'components': list(components), 'base': bp, '_instructions': binding}
    if len(k.encode(result)) > k.MAX - 65536: raise ValueError('instruction receipt preflight too large')
    return result


def public(p):
    if '_instructions' not in p:
        return {key: value for key, value in p.items() if not key.startswith('_')}
    b = p['_instructions']
    return {'status': p['status'], 'plan_id': p['plan_id'], 'root': p['root'],
            'base': capture.public(p['base']),
            'instructions': [{'path': e['path'], 'recipe': e['recipe'], 'before': e['before'], 'after': e['after']} for e in b['files']],
            'registration_changed': b['baseline'][REG]['signature'] != b['registration_after']}


@contextmanager
def locks(k, root, home):
    # A home binding survives rollback intentionally: one writer-root owns these targets.
    agents = k.absolute(home/'.agents')
    if not agents.exists():
        agents.mkdir(mode=0o700); sync_dir(home)
    directory = check_home(k, home, root)
    private_dir(k, directory, create=True)
    state = root/k.STATE; private_dir(k, state, create=True)
    handles = []
    try:
        for path in (directory/'lock', state/'instruction-lock'):
            if path.exists(): private_json_lock(k, path)
            fd = os.open(k.absolute(path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            handles.append(fd); fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_home(k, home, root)
        yield directory
    finally:
        for fd in reversed(handles): os.close(fd)


def private_json_lock(k, path):
    k.regular(path)
    s = path.stat()
    if s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) & 0o077:
        raise ValueError('instruction lock must be private and owned')


@contextmanager
def delegate(k, root, ident):
    # Internal in-process ownership, not an environment variable or CLI bypass flag.
    previous = getattr(k, '_instruction_context', None)
    k._instruction_context = (str(root), ident)
    try: yield
    finally: k._instruction_context = previous


def save(k, root, tx):
    directory = root/k.STATE/RECEIPTS; private_dir(k, directory, create=True)
    if len(k.encode({**tx, 'integrity': '0'*64})) > k.MAX: raise ValueError('instruction receipt too large')
    k.write_tx(directory/(tx['id']+'.json'), tx)


def clear_pending(k, root, ident):
    path = root/k.STATE/PENDING
    if path.exists():
        if private_json(k, path) != {'id': ident}: raise ValueError('different pending instruction update')
        path.unlink(); sync_dir(path.parent)


def apply(k, package, root, components, spec_path, capture_spec, expected, exclusive):
    if not exclusive: raise ValueError('exclusive writer window required')
    root = k.safe_root(root)
    pre = plan(k, package, root, components, spec_path, capture_spec)
    if pre['plan_id'] != expected: raise ValueError('stale instruction update plan')
    if pre['status'] == 'NOOP': return {'status': 'NOOP', 'plan_id': expected}
    with locks(k, root, Path(pre['_instructions']['home'])) as homedir:
        p = plan(k, package, root, components, spec_path, capture_spec)
        if p['plan_id'] != expected: raise ValueError('instruction update changed')
        b = p['_instructions']; ident = uuid.uuid4().hex
        for entry in b['files']:
            decode(k, entry['old'], entry['before']); decode(k, entry['new'], entry['after'])
        tx = {'id': ident, 'root': str(root), 'status': 'PREPARED', 'plan': p,
              'base_result': None, 'post_dependencies': None}
        save(k, root, tx)  # durable complete preimages BEFORE child mutation
        k.atomic(root/k.STATE/PENDING, k.encode({'id': ident}))
        if not (homedir/'owner.json').exists():
            data = k.encode({'schema': 1, 'root': str(root)})
            k.guarded_write(homedir/'owner.json', None, {'sha256': k.digest(data), 'mode': 0o600}, data)
        try:
            tx['status'] = 'DELEGATING'; save(k, root, tx)
            with delegate(k, root, ident):
                result = (capture.apply(k, package, root, components, capture_spec, b['base_plan_id'], True)
                          if b['capture'] else k.apply(package, root, components, b['base_plan_id']))
            tx['base_result'] = result; save(k, root, tx)
            if result.get('status') not in ('APPLIED', 'NOOP'):
                raise ValueError('delegated update incomplete')
            if result['status'] == 'NOOP' and p['base']['status'] != 'NOOP':
                raise ValueError('unexpected delegated NOOP')
            tx['post_dependencies'] = fingerprint(k, root, capture_context(p['base'], b['capture']))
            tx['status'] = 'BASE_APPLIED'; save(k, root, tx)
            home, targets = validate_spec(k, root, b['registration']['spec'])
            if discovery_guard(k, home, targets) != b['discovery']: raise ValueError('discovery changed during update')
            for entry in b['files']:
                if k.signature(Path(entry['path'])) != entry['before']: raise ValueError('instruction concurrent edit')
            tx['status'] = 'INSTRUCTIONS_APPLYING'; save(k, root, tx)
            for entry in b['files']:
                if entry['before'] != entry['after']:
                    k.guarded_write(Path(entry['path']), entry['before'], entry['after'], decode(k, entry['new'], entry['after']))
            k.guarded_write(root/k.STATE/REG, b['baseline'][REG]['signature'], b['registration_after'], k.encode(b['registration']))
            current = {'id': ident, 'root': str(root), 'parent': (b['parent'] or {}).get('id'), 'dependencies': tx['post_dependencies']}
            raw = k.encode(current)
            k.guarded_write(root/k.STATE/CURRENT, b['baseline'][CURRENT]['signature'], {'sha256': k.digest(raw), 'mode': 0o600}, raw)
            tx['current_after'] = metadata(k, root/k.STATE/CURRENT)
            for entry in b['files']:
                if k.signature(Path(entry['path'])) != entry['after']:
                    raise ValueError('instruction changed before completion')
            if k.signature(root/k.STATE/REG) != b['registration_after'] or tx['current_after']['signature']['sha256'] != k.digest(raw):
                raise ValueError('instruction metadata changed before completion')
            if fingerprint(k, root, capture_context(p['base'], b['capture'])) != tx['post_dependencies']:
                raise ValueError('dependency changed before completion')
            tx['status'] = 'APPLIED'; save(k, root, tx); clear_pending(k, root, ident)
            return {'status': 'APPLIED', 'transaction': ident, 'base_transaction': result.get('transaction'), 'plan_id': expected}
        except Exception:
            return {'status': 'BLOCKED', 'phase': tx['status'], 'transaction': ident,
                    'reason': 'Instruction update incomplete; explicit guarded rollback required. No automatic replay.'}


def is_transaction(k, root, ident):
    return bool(ident and re.fullmatch('[a-f0-9]{32}', ident) and (Path(root)/k.STATE/RECEIPTS/(ident+'.json')).exists())


def recover_base(k, root, tx):
    b = tx['plan']['_instructions']; bp = tx['plan']['base']; result = tx.get('base_result') or {}
    if result.get('transaction'):
        ident = result['transaction']
        if ident in b['inventory']: raise ValueError('delegated result references historical transaction')
        candidates = [ident]
    elif bp['status'] == 'NOOP':
        if fingerprint(k, root, capture_context(bp, b['capture'])) != b['dependencies']:
            raise ValueError('NOOP dependency changed')
        return None
    else:
        candidates = sorted(set(inventory(k, root, b['capture'])) - set(b['inventory']))
        if not candidates and tx['status'] == 'PREPARED' and fingerprint(k, root, capture_context(bp, b['capture'])) == b['dependencies']:
            return None
        if len(candidates) != 1: raise ValueError('uncertain delegated transaction; manual reconciliation required')
    directory = capture.RECEIPTS if b['capture'] else 'receipts'
    if len(candidates) != 1: raise ValueError('ambiguous delegated receipt')
    child = k.read_tx(root/k.STATE/directory/(candidates[0]+'.json'))
    if child['id'] != candidates[0] or child['plan']['plan_id'] != b['base_plan_id'] or child['plan']['root'] != str(root):
        raise ValueError('delegated receipt ownership mismatch')
    return candidates[0]


def expected_current(k, root, tx):
    b = tx['plan']['_instructions']
    if tx.get('post_dependencies') is None: return None
    raw = k.encode({'id': tx['id'], 'root': str(root), 'parent': (b['parent'] or {}).get('id'), 'dependencies': tx['post_dependencies']})
    return {'signature': {'sha256': k.digest(raw), 'mode': 0o600}, 'bytes': b64(raw)}


def validate_backups(k, tx):
    b = tx['plan']['_instructions']
    for entry in b['files']:
        decode(k, entry['old'], entry['before']); decode(k, entry['new'], entry['after'])
    for entry in b['baseline'].values(): decode(k, entry['bytes'], entry['signature'])


def terminal_cleanup_allowed(k, root, tx, baseid, actual):
    """A child terminal receipt can precede its own pending-marker cleanup.

    Only that exact owned child marker is tolerated; its rollback primitive does
    the cleanup after its normal restored-state verification. No marker is cleared
    here and no different dependency drift is normalized.
    """
    binding = tx['plan']['_instructions']
    directory = capture.RECEIPTS if binding['capture'] else 'receipts'
    child = read_receipt(k, root/k.STATE/directory/(baseid+'.json'))
    if child.get('status') != 'ROLLED_BACK': return False
    pending_path = root/k.STATE/(capture.PENDING if binding['capture'] else 'pending.json')
    if private_json(k, pending_path) != {'id': baseid}: return False
    key = str(pending_path)
    if binding['dependencies'].get(key) is not None: return False
    normalized = dict(actual); normalized[key] = None
    if normalized != binding['dependencies']: return False
    installed = k.current(root)
    for name, signature in installed['files'].items():
        if k.signature(root/k.relative(name)) != signature: return False
    if not binding['capture']:
        if installed != child['before']: return False
        for entry in child['plan']['changes']:
            if k.signature(root/k.relative(entry['path'])) != entry['before']: return False
    return True


def recipe_name(entry):
    """The current known recipe id (a retired id maps to its successor); never the raw registered text."""
    recipe = entry.get('recipe')
    return (known_recipe(recipe) if isinstance(recipe, str) else None) or 'unknown'


def edited_target(n, entry, now, permitted):
    """Name a hand-edited target by position and recipe, never by path; list only the states the plan accepts."""
    short = lambda sig: (sig or {}).get('sha256', 'none')[:12] if sig else 'none'
    expected = ' or '.join(dict.fromkeys(short(sig) for sig in permitted))
    return f"instruction user edit blocks rollback: target {n} recipe {recipe_name(entry)} sha256 {short(now)} expected {expected}"


def verify_restored(k, root, b):
    """After a rollback, every target, the registration and the current metadata must be back at their recorded baseline."""
    for n, entry in enumerate(b['files'], 1):
        if k.signature(Path(entry['path'])) != entry['before']:
            raise ValueError(f'instruction rollback did not restore target {n}')
    if k.signature(root/k.STATE/REG) != b['baseline'][REG]['signature']:
        raise ValueError('instruction rollback did not restore the registration')
    if metadata(k, root/k.STATE/CURRENT) != b['baseline'][CURRENT]:
        raise ValueError('instruction rollback did not restore the current metadata')


def rollback_plan(k, root, ident):
    root = k.safe_root(root)
    if not re.fullmatch('[a-f0-9]{32}', ident): raise ValueError('invalid instruction transaction')
    tx = read_receipt(k, root/k.STATE/RECEIPTS/(ident+'.json'))
    if tx['id'] != ident or tx['root'] != str(root): raise ValueError('instruction receipt mismatch')
    b = tx['plan']['_instructions']; validate_backups(k, tx)
    pending = private_json(k, root/k.STATE/PENDING); current = private_json(k, root/k.STATE/CURRENT)
    if pending and pending != {'id': ident}: raise ValueError('different pending instruction update')
    terminal = tx['status'] == 'ROLLED_BACK'
    if terminal:
        if current != b['parent']: raise ValueError('rolled-back instruction lineage changed')
    elif not pending and (current or {}).get('id') != ident:
        raise ValueError('rollback must target current instruction transaction')
    elif pending and current not in (b['parent'], None) and current.get('id') != ident:
        raise ValueError('instruction lineage changed during pending transaction')
    files = []
    for n, entry in enumerate(b['files'], 1):
        now = k.signature(Path(entry['path']))
        permitted = (entry['before'],) if terminal else (entry['before'], entry['after'])
        if now not in permitted: raise ValueError(edited_target(n, entry, now, permitted))
        files.append({'path': entry['path'], 'current': now})
    regnow = k.signature(root/k.STATE/REG)
    allowedreg = (b['baseline'][REG]['signature'],) if terminal else (b['baseline'][REG]['signature'], b['registration_after'])
    if regnow not in allowedreg: raise ValueError('instruction registration changed')
    curmeta = metadata(k, root/k.STATE/CURRENT); wantedcurrent = expected_current(k, root, tx)
    allowedcur = [b['baseline'][CURRENT]] + ([] if terminal or wantedcurrent is None else [wantedcurrent])
    if curmeta not in allowedcur: raise ValueError('instruction current metadata changed')
    context = capture_context(tx['plan']['base'], b['capture'])
    actual = fingerprint(k, root, context)
    if terminal or tx['status'] == 'BASE_ROLLED_BACK':
        if actual != b['dependencies']: raise ValueError('restored dependency fingerprint changed')
        baseid = None; bp = None
    else:
        baseid = recover_base(k, root, tx)
        if tx.get('post_dependencies') and tx['status'] not in ('ROLLING_BACK', 'RESTORED') and actual != tx['post_dependencies']:
            raise ValueError('newer dependency update blocks rollback')
        if baseid:
            with delegate(k, root, ident):
                bp = capture.rollback_plan(k, root, baseid) if b['capture'] else k.rollback_plan(root, baseid)
            if bp['status'] == 'NOOP' and actual != b['dependencies']:
                if not terminal_cleanup_allowed(k, root, tx, baseid, actual):
                    raise ValueError('delegated rollback NOOP with changed dependencies')
        else:
            bp = None
            if actual != b['dependencies']: raise ValueError('unowned dependency state')
    result = {'status': 'NOOP' if terminal else 'PLANNED', 'transaction': ident, 'files': files,
              'registration_current': regnow, '_current': curmeta, 'base_transaction': baseid, '_base_rollback': bp}
    result['plan_id'] = k.digest(k.encode(result)); return result


def rollback(k, root, ident, expected, exclusive):
    if not exclusive: raise ValueError('exclusive writer window required')
    root = k.safe_root(root)
    tx = read_receipt(k, root/k.STATE/RECEIPTS/(ident+'.json'))
    with locks(k, root, Path(tx['plan']['_instructions']['home'])):
        p = rollback_plan(k, root, ident)
        if p['plan_id'] != expected: raise ValueError('stale instruction rollback')
        if p['status'] == 'NOOP': clear_pending(k, root, ident); return public(p)
        b = tx['plan']['_instructions']
        tx['status'] = 'ROLLING_BACK'; save(k, root, tx)
        k.atomic(root/k.STATE/PENDING, k.encode({'id': ident}))
        pinned_files = {entry['path']: entry['current'] for entry in p['files']}
        for path, pinned in pinned_files.items():
            if k.signature(Path(path)) != pinned:
                raise ValueError('instruction changed after rollback plan')
        if (k.signature(root/k.STATE/REG) != p['registration_current']
                or k.signature(root/k.STATE/CURRENT) != p['_current']['signature']):
            raise ValueError('instruction metadata changed after rollback plan')
        # Never adopt a newly observed value as the CAS baseline after planning.
        for entry in b['files']:
            expected_before_restore = pinned_files[entry['path']]
            if k.signature(Path(entry['path'])) != expected_before_restore:
                raise ValueError('instruction changed after rollback plan')
            if expected_before_restore != entry['before']:
                k.guarded_write(Path(entry['path']), expected_before_restore, entry['before'], decode(k, entry['old'], entry['before']))
        for name, pinned in ((REG, p['registration_current']), (CURRENT, p['_current']['signature'])):
            old = b['baseline'][name]
            if k.signature(root/k.STATE/name) != pinned:
                raise ValueError('instruction metadata changed after rollback plan')
            if pinned != old['signature']:
                k.guarded_write(root/k.STATE/name, pinned, old['signature'], decode(k, old['bytes'], old['signature']))
        tx['status'] = 'RESTORED'; save(k, root, tx)
        if p['base_transaction']:
            with delegate(k, root, ident):
                if b['capture']:
                    result = capture.rollback(k, root, p['base_transaction'], p['_base_rollback'].get('plan_id'), True)
                else:
                    result = k.rollback(root, p['base_transaction'], p['_base_rollback'].get('plan_id'))
            if result['status'] not in ('ROLLED_BACK', 'NOOP'): raise ValueError('delegated rollback incomplete')
        tx['status'] = 'BASE_ROLLED_BACK'; save(k, root, tx)
        rollback_plan(k, root, ident)  # Verify every restored output before completion.
        verify_restored(k, root, b)     # Strictly: the plan above still accepts the `after` states.
        tx['status'] = 'ROLLED_BACK'; save(k, root, tx)
        clear_pending(k, root, ident)
        return {'status': 'ROLLED_BACK', 'transaction': ident}
