#!/usr/bin/env python3
"""Separate explicit network phase: only a DB cache is mounted, never product code."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import selectors
import subprocess
import time
import tempfile
import scanner as s



UPDATE_SECONDS = 600
OUTPUT_BYTES = 1024 * 1024  # per stdout/stderr, per command


def error_text(error):
    return type(error).__name__ + ': ' + str(error)[:2048]


def docker_call(prefix, args, env, timeout=UPDATE_SECONDS):
    """Always attach bounded separate-stream diagnostics, including cancellation."""
    streams = [bytearray(), bytearray()]; truncated = [False, False]
    process = None; selector = None; primary = None; reap_errors = []
    started = time.monotonic()
    try:
        s.need(timeout > 0, 'updater aggregate deadline exceeded')
        process = subprocess.Popen(prefix + args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = started + timeout
        selector = selectors.DefaultSelector()
        for i, stream in enumerate((process.stdout, process.stderr)):
            selector.register(stream, selectors.EVENT_READ, i)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            s.need(remaining > 0, 'updater command timeout')
            for key, _ in selector.select(min(0.1, remaining)):
                data = os.read(key.fileobj.fileno(), min(65536, OUTPUT_BYTES + 1 - len(streams[key.data])))
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                room = OUTPUT_BYTES - len(streams[key.data])
                streams[key.data].extend(data[:room])
                truncated[key.data] = len(data) > room
                s.need(not truncated[key.data], 'updater command output limit')
        process.wait(timeout=max(0.001, deadline - time.monotonic()))
    except BaseException as error:
        primary = error
    finally:
        if selector is not None:
            selector.close()
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill(); process.wait(timeout=5)
            except BaseException as error:
                reap_errors.append(error_text(error))
            for stream in (process.stdout, process.stderr):
                try: stream.close()
                except BaseException as error: reap_errors.append(error_text(error))
    record = {'argv': prefix + args, 'exit': process.returncode if process else None,
              'failure': error_text(primary) if primary else None, 'elapsed': time.monotonic() - started,
              'stdout': streams[0].decode('utf-8', errors='replace'),
              'stderr': streams[1].decode('utf-8', errors='replace'),
              'stdout_truncated': truncated[0], 'stderr_truncated': truncated[1],
              'capture_complete': primary is None and not reap_errors, 'reap_errors': reap_errors}
    if primary is None and reap_errors:
        primary = s.Blocked('updater CLI reap failed')
    if primary is not None:
        primary.command_receipt = record
        raise primary
    result = subprocess.CompletedProcess(prefix + args, record['exit'], record['stdout'], record['stderr'])
    result.command_receipt = record
    return result


class UpdateFailure(s.Blocked):
    def __init__(self, primary, audit):
        self.primary = primary
        self.audit = audit
        super().__init__(error_text(primary))


def write_receipt(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def recorded_call(audit, prefix, args, env, timeout):
    result = None; primary = None
    try:
        result = docker_call(prefix, args, env, timeout=timeout)
    except BaseException as error:
        primary = error
    record = getattr(primary if primary else result, 'command_receipt', None)
    if record is None:  # Mock/spawn failures still retain command identity.
        record = {'argv': prefix + args, 'exit': getattr(result, 'returncode', None),
                  'stdout': getattr(result, 'stdout', '')[:OUTPUT_BYTES],
                  'stderr': getattr(result, 'stderr', '')[:OUTPUT_BYTES],
                  'failure': error_text(primary) if primary else None, 'capture_complete': False}
    audit['commands'].append(record)
    try:
        write_receipt(Path(audit['receipts']) / ('command-%02d.json' % len(audit['commands'])), record)
    except BaseException as error:
        audit['persistence_errors'].append(error_text(error))
        if primary is None: primary = error
    if primary is not None: raise primary
    return result


def validate_download(cache):
    """Reject the entire untrusted download closure before writing or chmod."""
    s.canonical(cache)
    s.need(cache.is_dir() and {p.name for p in cache.iterdir()} == {'db'},
           'unexpected download closure')
    db = s.canonical(cache / 'db')
    s.need(stat.S_ISDIR(db.lstat().st_mode) and
           {p.name for p in db.iterdir()} == {'trivy.db', 'metadata.json'},
           'unexpected DB download closure')
    for name in ('trivy.db', 'metadata.json'):
        s.regular(db / name)


def exclusive_json(path, value):
    """Never follow or replace an existing metadata inode."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')


def remove_private_tree(path):
    """Unlink files without chmod, including hardlinks and symlinks from downloads."""
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        def clear(directory):
            # Directories cannot be regular-file hardlinks. Never chmod any file inode.
            os.fchmod(directory, 0o700)
            for name in os.listdir(directory):
                entry = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if stat.S_ISDIR(entry.st_mode):
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                    try:
                        clear(child)
                    finally:
                        os.close(child)
                    os.rmdir(name, dir_fd=directory)
                else:
                    os.unlink(name, dir_fd=directory)
        clear(fd)
    finally:
        os.close(fd)
    os.rmdir(path)


@contextmanager
def private_update_directory(root, audit=None):
    # TemporaryDirectory's permission-repair cleanup may chmod downloaded file inodes.
    # This cleanup changes permissions only through opened directory descriptors.
    path = Path(tempfile.mkdtemp(prefix='update-', dir=root)).resolve()
    if audit is not None: audit['work'] = str(path)
    primary = None
    try:
        yield path
    except BaseException as error:
        primary = error
        raise
    finally:
        if audit is None or not audit.get('removal_uncertain'):
            try:
                remove_private_tree(path)
            except BaseException as error:
                if audit is not None:
                    audit['cleanup_errors'].append(error_text(error))
                    audit['work_retained'] = True
                if primary is None: raise
        elif audit is not None:
            audit['work_retained'] = True


def initialize(root):
    root = s.canonical(root, exists=False)
    s.need(root.parent.is_dir() and not root.exists(), 'new dedicated storage directory required')
    s.need(not any((p / '.git').exists() for p in root.parents), 'storage must be outside Git')
    s.disjoint(root, s.HERE.parent.parent)
    root.mkdir(mode=0o700)
    s.write_json(root / 'owner.json', {'owner': 'AI Factory', 'schema_version': 1})
    return {'status': 'INITIALIZED'}


def verify_updater(obj, image_id, image, cache, command, *, path_identity=None):
    identify = s.canonical if path_identity is None else path_identity
    h, c = obj['HostConfig'], obj['Config']
    s.need(obj['Image'] == image_id and c['Image'] == image and h['NetworkMode'] == 'bridge', 'updater image/network mismatch')
    s.need(h['ReadonlyRootfs'] and not h.get('Privileged') and not h.get('CapAdd') and
           set(x.upper() for x in h.get('CapDrop', [])) == {'ALL'} and
           any(v in h.get('SecurityOpt', []) for v in ('no-new-privileges:true', 'no-new-privileges')), 'unsafe updater privileges')
    s.need(not h.get('Devices') and not h.get('DeviceRequests') and not h.get('VolumesFrom') and
           not h.get('PortBindings') and not h.get('PidMode') and h.get('IpcMode') != 'host', 'unsafe updater sharing')
    s.need(c['Entrypoint'] == ['trivy'] and c['Cmd'] == command and
           c['User'] == str(os.getuid()) + ':' + str(os.getgid()), 'updater process mismatch')
    mounts = obj['Mounts']
    binds = [v for v in mounts if v['Type'] == 'bind']
    s.need(len(binds) == 1 and str(identify(binds[0]['Source'])) == str(identify(cache)) and
           binds[0]['Destination'] == '/cache' and binds[0]['RW'], 'updater must mount only DB cache')
    s.need(all(v['Type'] == 'bind' or (v['Type'] == 'tmpfs' and v['Destination'] == '/tmp') for v in mounts),
           'unexpected updater volume')
    s.need(h.get('NanoCpus') == 2000000000 and h.get('Memory') == 2 * 1024**3 and
           h.get('MemorySwap') == 2 * 1024**3 and h.get('PidsLimit') == 128, 'updater resource mismatch')
    s.verify_tmpfs(h.get('Tmpfs'), max_bytes=1024 * 1024 * 1024)
    env = dict(x.split('=', 1) for x in c.get('Env', []))
    expected = {'HOME': '/tmp', 'TRIVY_DISABLE_TELEMETRY': 'true'}
    s.need(all(env.get(k) == v for k, v in expected.items()) and set(env) <= set(expected) | s.SAFE_IMAGE_ENV,
           'unexpected updater environment')


def _update(root, m, socket, audit):
    root = s.store_root(root)
    deadline = time.monotonic() + UPDATE_SECONDS
    def invoke(prefix, args, env):
        return recorded_call(audit, prefix, args, env, timeout=deadline - time.monotonic())
    s.need(s.PIN.fullmatch(m['db']['repository'] or ''), 'reviewed immutable DB OCI digest required')
    image = m['engines']['trivy']['image']
    lock = root / 'update.lock'
    s.canonical(lock, exists=False)
    if lock.exists():
        s.regular(lock)
    with lock.open('a') as locked:
        fcntl.flock(locked, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with private_update_directory(root, audit) as work:
            cache = work / 'cache'; cache.mkdir()
            home = work / 'home'; home.mkdir()
            env = {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin', 'HOME': str(home), 'DOCKER_CONFIG': str(home)}
            prefix = ['docker', '--host', 'unix://' + str(socket)]
            r = invoke(prefix, ['image', 'inspect', image], env)
            s.need(r.returncode == 0, 'pinned updater image unavailable locally')
            info = json.loads(r.stdout)[0]
            s.need(image in info.get('RepoDigests', []) and info['Os'] + '/' + info['Architecture'] == m['engines']['trivy']['platform'],
                   'updater digest/platform mismatch')
            command = ['fs', '--download-db-only', '--db-repository', m['db']['repository'],
                       '--cache-dir', '/cache', '--disable-telemetry']
            name = 'factory-db-' + s.uuid.uuid4().hex
            audit['container_name'] = name
            audit['cache'] = str(cache)
            # Persist identity before create; no container is possible if this write fails.
            write_receipt(Path(audit['receipts']) / 'resource.json', {'name': name, 'cache': str(cache)})
            primary = None
            audit['removal_uncertain'] = True
            try:
                args = ['create', '--name', name, '--pull', 'never', '--network', 'bridge', '--read-only',
                        '--platform', m['engines']['trivy']['platform'], '--cpus', '2', '--memory', '2g',
                        '--memory-swap', '2g', '--pids-limit', '128', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--user',
                        str(os.getuid()) + ':' + str(os.getgid()), '--tmpfs', '/tmp:rw,noexec,nosuid,size=1g',
                        '--mount', 'type=bind,src=' + str(cache) + ',dst=/cache', '--env', 'HOME=/tmp',
                        '--env', 'TRIVY_DISABLE_TELEMETRY=true', '--entrypoint', 'trivy', image] + command
                r = invoke(prefix, args, env)
                s.need(r.returncode == 0, 'updater create failed')
                candidate_id = r.stdout.strip()
                if len(candidate_id) == 64 and all(c in '0123456789abcdef' for c in candidate_id):
                    audit['container_id'] = candidate_id
                r = invoke(prefix, ['inspect', name], env)
                s.need(r.returncode == 0, 'updater inspect failed')
                verify_updater(json.loads(r.stdout)[0], info['Id'], image, cache, command)
                r = invoke(prefix, ['start', '--attach', name], env)
                s.need(r.returncode == 0, 'DB download failed')
                r = invoke(prefix, ['inspect', '--format', '{{json .State}}', name], env)
                s.need(r.returncode == 0, 'updater final state unavailable')
                state = json.loads(r.stdout)
                s.need(not state['Running'] and state['ExitCode'] == 0 and not state.get('OOMKilled') and
                       not state.get('Error'), 'updater failed')
            except BaseException as error:
                primary = error
            finally:
                try:
                    cleanup = recorded_call(audit, prefix, ['rm', '--force', name], env, timeout=15)
                    s.need(cleanup.returncode == 0, 'updater removal not confirmed')
                    audit['removal_uncertain'] = False
                except BaseException as error:
                    audit['cleanup_errors'].append(error_text(error))
                    if primary is None: primary = error
            if primary is not None: raise primary
            validate_download(cache)
            files = {}
            for n in ('db/trivy.db', 'db/metadata.json'):
                files[n] = s.sha(s.regular(cache / n))
            identity = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
            # Validate in a temporary Factory store before atomic publish; never overwrite a snapshot.
            staging = work / 'store'; staging.mkdir()
            s.write_json(staging / 'owner.json', {'owner': 'AI Factory', 'schema_version': 1})
            snapshot = staging / identity
            cache.rename(snapshot)
            exclusive_json(snapshot / 'snapshot.json', {'schema_version': 1, 'engine_image': image,
                           'db_source': m['db']['repository'], 'files': files})
            for p in snapshot.rglob('*'):
                s.canonical(p)
                p.chmod(0o555 if p.is_dir() else 0o444)
            snapshot.chmod(0o555)
            s.validate_snapshot(staging, identity, m)
            destination = root / identity
            s.canonical(destination, exists=False)
            if destination.exists():
                s.validate_snapshot(root, identity, m)
                return {'status': 'NOOP', 'snapshot': identity}
            # macOS requires a writable source directory for cross-parent rename.
            # Readers reject this brief unsealed state; file bytes remain read-only.
            snapshot.chmod(0o755)
            snapshot.rename(destination)
            destination.chmod(0o555)
            s.validate_snapshot(root, identity, m)
            return {'status': 'SNAPSHOT_CREATED', 'snapshot': identity}



def update(root, m, socket):
    root = s.store_root(root)
    receipts = Path(tempfile.mkdtemp(prefix='receipts-', dir=root))
    audit = {'receipts': str(receipts), 'commands': [], 'cleanup_errors': [],
             'persistence_errors': [], 'removal_uncertain': False, 'work_retained': False,
             'container_name': None, 'container_id': None}
    primary = None; result = None
    try:
        result = _update(root, m, socket, audit)
    except BaseException as error:
        primary = error
    audit['primary'] = error_text(primary) if primary else None
    audit['status'] = 'ERROR' if primary else 'SUCCESS'
    audit['result'] = result
    try:
        write_receipt(receipts / 'result.json', audit)
    except BaseException as error:
        audit['persistence_errors'].append(error_text(error))
        if primary is None: primary = error
    if primary is not None:
        audit['status'] = 'ERROR'
        audit['primary'] = error_text(primary)
        raise UpdateFailure(primary, audit) from primary
    result['receipts'] = str(receipts)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['init-store', 'update'])
    p.add_argument('--store', type=Path, required=True)
    p.add_argument('--socket', type=Path)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--network-authorized', action='store_true')
    a = p.parse_args()
    try:
        s.need(a.execute, 'explicit --execute required')
        if a.action == 'init-store':
            result = initialize(a.store)
        else:
            s.need(a.network_authorized and a.socket and a.socket.is_absolute(), 'explicit network authorization and local socket required')
            result = update(a.store, s.load_manifest(), a.socket)
    except UpdateFailure as e:
        result = {'status': 'ERROR', 'reason': str(e), 'diagnostics': e.audit}
    except s.Blocked as e:
        result = {'status': 'BLOCKED', 'reason': str(e)}
    except (OSError, ValueError, TypeError, KeyError, s.subprocess.SubprocessError):
        result = {'status': 'ERROR', 'reason': 'DB update/configuration failure'}
    print(json.dumps(result, indent=2))
    return s.EXIT.get(result['status'], 0)


if __name__ == '__main__':
    raise SystemExit(main())
