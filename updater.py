"""Authenticated signed updates for this deployment repository."""
import ast
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import zipfile

FILES = ('deploy.py', 'gateway.py', 'updater.py', 'install-service.sh', 'README.md',
         'VERSION', 'LICENSE', 'web/navigation.css', 'web/update.js', 'web/update.html',
         'docs/UPDATE-FLOW.md')
MAX_PACKAGE = 4 * 1024 * 1024
LOCK = threading.Lock()

def version(root):
    return (root / 'VERSION').read_text().strip()

def maintenance_key(root):
    path = root / 'runtime/update-key'
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:
            out.write(secrets.token_urlsafe(32))
    return path.read_text().strip()

def verify(root, payload):
    if len(payload) > MAX_PACKAGE:
        raise ValueError('更新包超过 4 MiB')
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
        names = archive.namelist()
        expected = set(FILES) | {'update.json', 'update.sig', 'updates.pub'}
        if len(names) != len(expected) or set(names) != expected:
            raise ValueError('更新包文件列表不正确')
        if sum(x.file_size for x in archive.infolist()) > MAX_PACKAGE:
            raise ValueError('解压后文件过大')
        if any((x.external_attr >> 16) & 0o170000 == 0o120000 for x in archive.infolist()):
            raise ValueError('更新包不能包含符号链接')
        if archive.read('updates.pub') != (root / 'updates.pub').read_bytes():
            raise ValueError('更新签名公钥与当前安装不一致')
        raw = archive.read('update.json')
        sig = base64.b64decode(archive.read('update.sig'), validate=True)
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            (tmp / 'manifest').write_bytes(raw)
            (tmp / 'signature').write_bytes(sig)
            result = subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-inkey',
                str(root / 'updates.pub'), '-rawin', '-in', str(tmp / 'manifest'),
                '-sigfile', str(tmp / 'signature')], capture_output=True)
            if result.returncode:
                raise ValueError('更新包签名不正确')
        manifest = json.loads(raw)
        new = manifest['version']
        if manifest.get('project') != 'zxyszx/subnest-x-preview' or not re.fullmatch(r'\d+\.\d+\.\d+', new):
            raise ValueError('更新包不是此项目的有效版本')
        if tuple(map(int, new.split('.'))) <= tuple(map(int, version(root).split('.'))):
            raise ValueError('只能安装比当前版本更新的更新包')
        if set(manifest['files']) != set(FILES):
            raise ValueError('清单不完整')
        content = {}
        for name in FILES:
            data = archive.read(name)
            if hashlib.sha256(data).hexdigest() != manifest['files'][name]:
                raise ValueError(f'文件校验失败：{name}')
            if name.endswith('.py'):
                ast.parse(data, filename=name)
            content[name] = data
        if content['VERSION'].decode().strip() != new:
            raise ValueError('版本文件不一致')
        return manifest, content
    except (zipfile.BadZipFile, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('无效更新包') from exc

def apply(root, payload):
    if not LOCK.acquire(blocking=False):
        raise ValueError('另一项更新正在进行')
    try:
        if (root / 'runtime/pending-update.json').exists():
            raise ValueError('已有更新等待重启，请先重启服务')
        manifest, files = verify(root, payload)
        backup = root / 'runtime/backups' / (time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
        backup.mkdir(parents=True, mode=0o700)
        existed = []
        for name in FILES:
            target = root / name
            if target.is_symlink():
                raise ValueError('安装目录含不受支持的符号链接')
            if target.exists():
                dest = backup / 'code' / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, dest)
                existed.append(name)
        # Snapshot SQLite consistently while the application is still running.
        data = root / 'runtime/data'
        if data.exists():
            shutil.copytree(data, backup / 'data', ignore=shutil.ignore_patterns('*.db', '*.db-wal', '*.db-shm'))
            for db in data.glob('*.db'):
                with sqlite3.connect(f'file:{db}?mode=ro', uri=True) as source, sqlite3.connect(backup / 'data' / db.name) as dest:
                    source.backup(dest)
        replaced = []
        try:
            for name, content in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + '.update-tmp')
                temporary.write_bytes(content)
                temporary.replace(target)
                replaced.append(name)
            pending = {'from': version(backup / 'code'), 'to': manifest['version'], 'backup': str(backup)}
            (root / 'runtime/pending-update.json').write_text(json.dumps(pending))
        except Exception:
            for name in reversed(replaced):
                if name in existed:
                    shutil.copy2(backup / 'code' / name, root / name)
                else:
                    (root / name).unlink(missing_ok=True)
            raise
        return {'version': manifest['version'], 'state': 'ready', 'message': '更新包已校验并安装，等待重启；尚未确认新版本运行成功。'}
    finally:
        LOCK.release()
