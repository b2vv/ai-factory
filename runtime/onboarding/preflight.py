#!/usr/bin/env python3
"""Read-only, dependency-free onboarding inventory. Never executes repo commands."""
import argparse
import hashlib
import json
import re
from pathlib import Path

MAX_BYTES = 1024 * 1024
SECRET = re.compile(r"(^\.env|^\.(aws|ssh|git)$|credential|secret|token|^id_(rsa|ed25519)|\.pem$|\.key$)", re.I)
EFFECTS = {
    'deletion': r'\b(rm|rmdir|unlink)\b|\b(reset|clean|drop|truncate)\b',
    'services_or_containers': r'\b(docker|compose|serve|start|dev)\b',
    'installation_or_network': r'\b(install|curl|wget|fetch|publish|push|deploy)\b',
    'data_mutation': r'\b(seed|migrate|migration|flush|prune)\b',
}

def safe_path(root, relative):
    """Resolve only explicit relative paths, rejecting all symlinks and sensitive names."""
    if not isinstance(relative, str) or not relative:
        raise ValueError('path must be a nonempty relative string')
    part = Path(relative)
    if part.is_absolute() or '..' in part.parts or any(SECRET.search(p) for p in part.parts):
        raise ValueError('unsafe or sensitive path')
    current = root
    for component in part.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError('symlink paths are not inspected')
        if current != root / part and current.exists() and not current.is_dir():
            raise ValueError('parent component is not a directory')
    result = current.resolve()
    if not result.is_relative_to(root):
        raise ValueError('path escapes selected root')
    return result

def read_text(path):
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('not a regular file or exceeds size limit')
    return path.read_text(encoding='utf-8')

def load_manifest(root, supplied_path):
    """An explicit external manifest grants access only to that one regular file."""
    path = Path(supplied_path)
    if path.is_absolute():
        # Check the complete spelling before resolving: no symlink traversal or
        # sensitive parent directories. This grants no external inventory root.
        path = safe_path(Path(path.anchor), str(path.relative_to(path.anchor)))
    else:
        path = safe_path(root, supplied_path)
    return json.loads(read_text(path))

def state(detected=False, configured=False, status='UNKNOWN', reason='Runtime not tested'):
    return dict(detected=detected, configured=configured, behavior_tested=False,
                status=status, reason=reason)

def inspect_paths(root, paths):
    result = []
    for relative in paths:
        try:
            path = safe_path(root, relative)
            exists = path.is_file() or path.is_dir()
            result.append(dict(path=relative, **state(exists, False,
                'DETECTED' if exists else 'BLOCKED',
                'File exists; contents and runtime not validated' if exists else 'Missing path')))
        except ValueError:
            result.append(dict(path='[rejected]', **state(status='BLOCKED', reason='Unsafe path rejected')))
    return result

def route(scope):
    """Conservative applicability only; never waives declared required gates."""
    if not isinstance(scope, dict):
        raise ValueError('scope must be an object')
    flags = {'abstraction', 'responsibility', 'dependencies', 'duplication', 'test_helper', 'ui_change', 'ui_copy', 'entity_flow', 'completed_handoff'}
    if set(scope) - flags - {'mode'} or any(not isinstance(scope[k], bool) for k in flags & set(scope)):
        raise ValueError('unknown scope key or non-boolean impact flag')
    pattern = any(scope.get(k, False) for k in ('abstraction', 'responsibility', 'dependencies', 'duplication', 'test_helper'))
    ui = bool(scope.get('ui_change') or scope.get('ui_copy'))
    if scope.get('completed_handoff'):
        mode = 'resume_verify_completion'
    else:
        mode = scope.get('mode', 'small')
    if mode not in ('small', 'full', 'resume', 'resume_verify_completion'):
        raise ValueError('unsupported mode')
    return {
        'mode': mode,
        'primary_task_records': 1,
        'pattern_review': 'ASSESS' if pattern else 'N/A: no declared structural impact',
        'ui_design': 'ASSESS layout, wrapping, active/open states and accessibility' if ui else 'N/A: no declared UI impact',
        'entity_e2e': 'ASSESS affected entity/scoped filters' if scope.get('entity_flow') else 'N/A: no declared entity flow impact',
        'independent_review': 'ASSESS required repo contract and risk; reuse same pinned-diff review',
        'checks': 'Select by actual impact plus explicit required repo gates; unresolved gate reduction is BLOCKED',
        'bug_proof': 'RED/GREEN is regression evidence, not mutation testing',
        'execution_blocked': 'BLOCKED; use only an explicitly permitted execution mechanism',
        'resume': 'Validate existing completion evidence; do not duplicate completed work',
    }

def validate_manifest(manifest):
    fields = {'instructions', 'workflow', 'dependency_files', 'skills', 'command_files', 'integrations', 'conflicts', 'scope', 'hosts', 'models', 'adapter_files'}
    if not isinstance(manifest, dict) or set(manifest) - fields:
        raise ValueError('invalid manifest fields')
    for field in fields - {'scope'}:
        if field in manifest and not isinstance(manifest[field], list):
            raise ValueError('manifest collections must be arrays')
    for field in ('instructions', 'workflow', 'dependency_files', 'command_files'):
        if any(not isinstance(p, str) for p in manifest.get(field, [])):
            raise ValueError('path entries must be strings')
    for skill in manifest.get('skills', []):
        if not isinstance(skill, dict) or set(skill) - {'name', 'source', 'path'} or not all(isinstance(skill.get(k), str) for k in ('name', 'path')) or skill.get('source', 'local') not in ('local', 'shared'):
            raise ValueError('invalid skill declaration')
    for item in manifest.get('integrations', []):
        if not isinstance(item, dict) or set(item) - {'name', 'config_paths', 'declared_availability', 'declared_freshness'} or not isinstance(item.get('name'), str):
            raise ValueError('invalid integration declaration')
        if not isinstance(item.get('config_paths', []), list) or any(not isinstance(p, str) for p in item.get('config_paths', [])):
            raise ValueError('integration paths must be strings')
        if item.get('declared_availability', 'unknown') not in ('unknown', 'available', 'unavailable') or item.get('declared_freshness', 'unknown') not in ('unknown', 'fresh', 'stale'):
            raise ValueError('invalid integration state')
    for item in manifest.get('conflicts', []):
        if not isinstance(item, dict) or set(item) != {'id'} or not isinstance(item['id'], str):
            raise ValueError('conflicts require only an identifier')
    validate_extensions(manifest)
    route(manifest.get('scope', {}))

def validate_extensions(manifest):
    def strings(item, keys):
        return all(isinstance(item.get(k), str) and item[k] for k in keys)
    seen = set()
    for host in manifest.get('hosts', []):
        if not isinstance(host, dict) or set(host) - {'host', 'session', 'discovered_skills', 'native_tools', 'discovery_evidence', 'review'} or not strings(host, ('host', 'session')):
            raise ValueError('invalid host session')
        key = (host['host'], host['session'])
        if key in seen:
            raise ValueError('duplicate host session')
        seen.add(key)
        for field in ('discovered_skills', 'native_tools'):
            if not isinstance(host.get(field, []), list) or any(not isinstance(v, str) for v in host.get(field, [])):
                raise ValueError('invalid discovery list')
        if 'discovery_evidence' in host and not isinstance(host['discovery_evidence'], str):
            raise ValueError('invalid discovery evidence')
        review = host.get('review', {})
        if not isinstance(review, dict) or set(review) - {'path', 'source'} or (review and (not strings(review, ('path',)) or review.get('source', 'local') not in ('local', 'shared'))):
            raise ValueError('invalid review route')
    for model in manifest.get('models', []):
        if not isinstance(model, dict) or set(model) - {'host', 'session', 'role', 'candidate', 'catalog', 'catalog_evidence', 'entitlement', 'budget'} or not strings(model, ('host', 'session', 'role')):
            raise ValueError('invalid model role')
        if model['role'] not in ('helper', 'coder', 'reviewer') or not isinstance(model.get('candidate', ''), str) or not isinstance(model.get('catalog_evidence', ''), str):
            raise ValueError('invalid model candidate')
        catalog = model.get('catalog')
        if catalog is not None and (not isinstance(catalog, list) or any(not isinstance(v, str) for v in catalog)):
            raise ValueError('invalid model catalog')
        if model.get('entitlement', 'unknown') not in ('unknown', 'available', 'unavailable') or model.get('budget', 'unknown') not in ('unknown', 'approved', 'denied'):
            raise ValueError('invalid entitlement or budget')
    seen = set()
    for entry in manifest.get('adapter_files', []):
        if not isinstance(entry, dict) or set(entry) != {'path', 'sha256'} or not strings(entry, ('path', 'sha256')) or not re.fullmatch('[0-9a-f]{64}', entry['sha256']) or entry['path'] in seen:
            raise ValueError('invalid or duplicate adapter file')
        seen.add(entry['path'])


def inspect_extensions(root, manifest, shared_root):
    hosts = []
    sessions = {(h['host'], h['session']) for h in manifest.get('hosts', [])}
    for host in manifest.get('hosts', []):
        review = host.get('review', {})
        result = {'host': host['host'], 'session': host['session'],
                  'discovery': 'DECLARED' if host.get('discovery_evidence') else 'UNKNOWN',
                  'declared_discovered_skills': host.get('discovered_skills', []),
                  'declared_native_tools': host.get('native_tools'),
                  'native_tool_inventory': 'DECLARED' if 'native_tools' in host else 'UNKNOWN',
                  'invocation': 'NOT_TESTED', 'behavior_tested': False,
                  'review': {'status': 'BLOCKED', 'reason': 'Declare a readable review SKILL.md file route; native discovery is separate'}}
        if review:
            base = shared_root if review.get('source') == 'shared' else root
            try:
                if base is None:
                    raise ValueError('missing shared root')
                path = safe_path(base, review['path'])
                if path.name != 'SKILL.md' or not read_text(path).strip():
                    raise ValueError('missing review instructions')
                result['review'] = {'status': 'FILE_FALLBACK', 'path': str(path),
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'reason': 'Read the complete skill and references; same pinned diff, independence and evidence requirements; invocation NOT_TESTED'}
            except (ValueError, OSError, UnicodeError):
                pass
        hosts.append(result)
    models = []
    for model in manifest.get('models', []):
        reasons = []
        same_session = (model['host'], model['session']) in sessions
        catalog = model.get('catalog')
        candidate = model.get('candidate')
        if not same_session:
            candidate_status = 'SESSION_UNKNOWN'
        elif catalog is None or not model.get('catalog_evidence'):
            candidate_status = 'CATALOG_UNKNOWN'
        elif not candidate:
            candidate_status = 'UNSELECTED'
        elif candidate not in catalog:
            candidate_status = 'MISSING'
        else:
            candidate_status = 'LISTED'
        if candidate_status != 'LISTED':
            reasons.append('Provide a candidate from this host/session catalog with evidence')
        entitlement = model.get('entitlement', 'unknown')
        budget = model.get('budget', 'unknown')
        if entitlement != 'available':
            reasons.append('Confirm entitlement without a paid probe')
        if budget != 'approved':
            reasons.append('Obtain budget decision before model execution')
        models.append({'host': model['host'], 'session': model['session'], 'role': model['role'],
                       'candidate': candidate, 'candidate_status': candidate_status,
                       'entitlement': entitlement, 'budget': budget,
                       'status': 'UNBOUND' if reasons else 'VALIDATED_DECLARATION',
                       'behavior_tested': False, 'next_steps': reasons,
                       'reason': 'Supplied session inventory only; no runtime access or model configuration changed'})
    plan = []
    for entry in manifest.get('adapter_files', []):
        try:
            path = safe_path(root, entry['path'])
            if not path.exists():
                status = 'PROPOSE_ADD'
            elif path.is_file() and path.stat().st_size <= MAX_BYTES and hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']:
                status = 'NOOP'
            else:
                status = 'BLOCKED'
            plan.append({'path': entry['path'], 'status': status,
                         'reason': 'Dry run only; existing different content requires reviewed merge and backup; never overwrite'})
        except (ValueError, OSError, UnicodeError):
            plan.append({'path': '[rejected]', 'status': 'BLOCKED', 'reason': 'Unsafe or unreadable adapter path'})
    return {'hosts': hosts, 'model_roles': models, 'adapter_plan': plan}


def inspect(root, manifest, shared_root=None):
    validate_manifest(manifest)
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('root must be a directory')
    if shared_root is not None:
        shared_root = Path(shared_root).resolve(strict=True)
        if not shared_root.is_dir():
            raise ValueError('shared skill root must be a directory')
    output = {'schema_version': 1, 'root': str(root),
              'read_only': True, 'commands_executed': 0,
              'instructions': inspect_paths(root, manifest.get('instructions', ['AGENTS.md', 'CLAUDE.md'])),
              'workflow': inspect_paths(root, manifest.get('workflow', [])),
              'dependency_files': inspect_paths(root, manifest.get('dependency_files', ['package.json', 'go.mod', 'pyproject.toml'])),
              'skills': [], 'commands': [], 'integrations': [],
              'declared_conflicts': [], 'routing': route(manifest.get('scope', {}))}
    for skill in manifest.get('skills', []):
        base = shared_root if skill.get('source') == 'shared' else root
        if base is None:
            result = state(status='BLOCKED', reason='Explicit shared skill root not supplied')
        else:
            checked = inspect_paths(base, [skill['path']])[0]
            result = {k: v for k, v in checked.items() if k != 'path'}
        output['skills'].append(dict(name=skill['name'], **result))
    for relative in manifest.get('command_files', ['package.json', 'Makefile']):
        try:
            path = safe_path(root, relative)
            if not path.exists():
                continue
            if path.name not in ('package.json', 'Makefile', 'makefile', 'GNUmakefile'):
                output['commands'].append(dict(file=relative, **state(True, status='UNKNOWN', reason='Unsupported command format; contents not read; manual inspection required')))
                continue
            content = read_text(path)
            if path.name == 'package.json':
                package = json.loads(content)
                if not isinstance(package, dict):
                    raise ValueError('package must be an object')
                scripts = package.get('scripts', {})
                if not isinstance(scripts, dict) or any(not isinstance(v, str) for v in scripts.values()):
                    raise ValueError('scripts must map names to strings')
                entries = scripts.items()
            elif path.name in ('Makefile', 'makefile', 'GNUmakefile'):
                # Targets are detected only. Recipes, prerequisites, includes and
                # expansions can hide effects: never classify a target as safe.
                entries = [(m.group(1), content) for m in re.finditer(r'^([A-Za-z0-9_.-]+)\s*:(?!=)', content, re.M)]
            else:
                output['commands'].append(dict(file=relative, **state(True, status='UNKNOWN', reason='Unsupported command format; manual inspection required')))
                continue
            for name, command in entries:
                indicators = [label for label, regex in EFFECTS.items() if re.search(regex, str(command), re.I)]
                output['commands'].append({'file': relative, 'name': name,
                    'side_effect_indicators': indicators, 'status': 'UNKNOWN',
                    'reason': 'Heuristic only; transitive scripts/recipes require manual review. No command is certified safe.'})
        except (ValueError, OSError, UnicodeError, TypeError):
            output['commands'].append(dict(file='[uninspected]', **state(status='BLOCKED', reason='Unsafe, malformed or unreadable command file')))
    for integration in manifest.get('integrations', []):
        files = inspect_paths(root, integration.get('config_paths', []))
        declared = integration.get('declared_availability', 'unknown')
        freshness = integration.get('declared_freshness', 'unknown')
        blocked = declared == 'unavailable' or freshness == 'stale'
        output['integrations'].append(dict(name=integration['name'],
            **state(any(f['detected'] for f in files), False, 'BLOCKED' if blocked else 'UNKNOWN',
                'User-declared stale/unavailable; safe fallback required' if blocked else 'Config existence is not registration, availability, freshness or runtime proof'),
            config_paths=files, declared_availability=declared, declared_freshness=freshness))
    for conflict in manifest.get('conflicts', []):
        output['declared_conflicts'].append({'id': conflict['id'], 'status': 'BLOCKED',
            'reason': 'Resolve acceptance/contract/ADR versus observed implementation explicitly; code does not authorize a contract violation'})
    output.update(inspect_extensions(root, manifest, shared_root))
    output['limitations'] = ['No semantic contradiction detection; declared conflicts only',
        'No runtime, MCP, model bindings, hook, CLI discovery or skill invocation proof',
        'No recursive scan or command execution; undeclared paths may be missed',
        'No edits, installations, registration, credentials or permissions changes',
        'configured stays false until separate human-reviewed adaptation; behavior_tested stays false']
    return output

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--manifest', required=True, help='Relative path within root, or explicit absolute non-secret JSON file outside root')
    parser.add_argument('--shared-skill-root', help='Explicit trusted shared skill root, otherwise no external reads')
    args = parser.parse_args()
    try:
        root = Path(args.root).resolve(strict=True)
        manifest = load_manifest(root, args.manifest)
        print(json.dumps(inspect(root, manifest, args.shared_skill_root), ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError):
        parser.exit(2, 'Preflight BLOCKED: invalid, unsafe or unreadable input; no repository commands executed.\n')

if __name__ == '__main__':
    main()
