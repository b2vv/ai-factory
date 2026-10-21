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
import tempfile
import scanner as s


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
def private_update_directory(root):
    # TemporaryDirectory's permission-repair cleanup may chmod downloaded file inodes.
    # This cleanup changes permissions only through opened directory descriptors.
    path = Path(tempfile.mkdtemp(prefix='update-', dir=root)).resolve()
    try:
        yield path
    finally:
        remove_private_tree(path)


def initialize(root):
    root = s.canonical(root, exists=False)
    s.need(root.parent.is_dir() and not root.exists(), 'new dedicated storage directory required')
    s.need(not any((p / '.git').exists() for p in root.parents), 'storage must be outside Git')
    s.disjoint(root, s.HERE.parent.parent)
    root.mkdir(mode=0o700)
    s.write_json(root / 'owner.json', {'owner': 'AI Factory', 'schema_version': 1})
    return {'status': 'INITIALIZED'}


def verify_updater(obj, image_id, image, cache, command):
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
    s.need(len(binds) == 1 and s.canonical(binds[0]['Source']) == cache and
           binds[0]['Destination'] == '/cache' and binds[0]['RW'], 'updater must mount only DB cache')
    s.need(all(v['Type'] == 'bind' or (v['Type'] == 'tmpfs' and v['Destination'] == '/tmp') for v in mounts),
           'unexpected updater volume')
    s.verify_tmpfs(h.get('Tmpfs'))
    env = dict(x.split('=', 1) for x in c.get('Env', []))
    expected = {'HOME': '/tmp', 'TRIVY_DISABLE_TELEMETRY': 'true'}
    s.need(all(env.get(k) == v for k, v in expected.items()) and set(env) <= set(expected) | s.SAFE_IMAGE_ENV,
           'unexpected updater environment')


def update(root, m, socket):
    root = s.store_root(root)
    s.need(s.PIN.fullmatch(m['db']['repository'] or ''), 'reviewed immutable DB OCI digest required')
    image = m['engines']['trivy']['image']
    lock = root / 'update.lock'
    s.canonical(lock, exists=False)
    if lock.exists():
        s.regular(lock)
    with lock.open('a') as locked:
        fcntl.flock(locked, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with private_update_directory(root) as work:
            cache = work / 'cache'; cache.mkdir()
            home = work / 'home'; home.mkdir()
            env = {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin', 'HOME': str(home), 'DOCKER_CONFIG': str(home)}
            prefix = ['docker', '--host', 'unix://' + str(socket)]
            r = s.docker_call(prefix, ['image', 'inspect', image], env)
            s.need(r.returncode == 0, 'pinned updater image unavailable locally')
            info = json.loads(r.stdout)[0]
            s.need(image in info.get('RepoDigests', []) and info['Os'] + '/' + info['Architecture'] == m['engines']['trivy']['platform'],
                   'updater digest/platform mismatch')
            command = ['fs', '--download-db-only', '--db-repository', m['db']['repository'],
                       '--cache-dir', '/cache', '--disable-telemetry']
            name = 'factory-db-' + s.uuid.uuid4().hex
            try:
                args = ['create', '--name', name, '--pull', 'never', '--network', 'bridge', '--read-only',
                        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--user',
                        str(os.getuid()) + ':' + str(os.getgid()), '--tmpfs', '/tmp:rw,noexec,nosuid,size=256m',
                        '--mount', 'type=bind,src=' + str(cache) + ',dst=/cache', '--env', 'HOME=/tmp',
                        '--env', 'TRIVY_DISABLE_TELEMETRY=true', '--entrypoint', 'trivy', image] + command
                r = s.docker_call(prefix, args, env)
                s.need(r.returncode == 0, 'updater create failed')
                r = s.docker_call(prefix, ['inspect', name], env)
                s.need(r.returncode == 0, 'updater inspect failed')
                verify_updater(json.loads(r.stdout)[0], info['Id'], image, cache, command)
                r = s.docker_call(prefix, ['start', '--attach', name], env)
                s.need(r.returncode == 0, 'DB download failed')
                r = s.docker_call(prefix, ['inspect', '--format', '{{json .State}}', name], env)
                s.need(r.returncode == 0, 'updater final state unavailable')
                state = json.loads(r.stdout)
                s.need(not state['Running'] and state['ExitCode'] == 0 and not state.get('OOMKilled') and
                       not state.get('Error'), 'updater failed')
            finally:
                cleanup = s.docker_call(prefix, ['rm', '--force', name], env)
                s.need(cleanup.returncode == 0, 'updater cleanup failed; inspect named container: ' + name)
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
    except s.Blocked as e:
        result = {'status': 'BLOCKED', 'reason': str(e)}
    except (OSError, ValueError, TypeError, KeyError, s.subprocess.SubprocessError):
        result = {'status': 'ERROR', 'reason': 'DB update/configuration failure'}
    print(json.dumps(result, indent=2))
    return s.EXIT.get(result['status'], 0)


if __name__ == '__main__':
    raise SystemExit(main())
