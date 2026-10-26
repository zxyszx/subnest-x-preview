#!/usr/bin/env python3
"""Build a signed repository update ZIP (private key stays under runtime/)."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile
from updater import FILES, version
root = Path(__file__).resolve().parent
manifest = {'project': 'zxyszx/subnest-x-preview', 'version': version(root),
            'notes': ['恢复原版检查更新入口和深色主题样式', '版本号显示本项目运行版本，保留官方程序版本独立性', '保留端口重启修复、在线签名更新及现有数据和设置'],
            'files': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in FILES}}
raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode()
with tempfile.TemporaryDirectory() as folder:
    temp = Path(folder)
    (temp / 'manifest').write_bytes(raw)
    subprocess.run(['openssl', 'pkeyutl', '-sign', '-inkey', str(root / 'runtime/update-signing-private.pem'),
                    '-rawin', '-in', str(temp / 'manifest'), '-out', str(temp / 'signature')], check=True)
    output = root / f'subnest-x-preview-{version(root)}.zip'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(root / name, name)
        archive.write(root / 'updates.pub', 'updates.pub')
        archive.writestr('update.json', raw)
        archive.writestr('update.sig', base64.b64encode((temp / 'signature').read_bytes()))
    print(output)
