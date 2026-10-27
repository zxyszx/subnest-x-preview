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
            'notes': ['更新弹窗继承当前主题、原版字体和装饰边框', '精简首屏，维护口令和手动 ZIP 导入默认收起，修复底部空白', '异步打开用户菜单时显示本项目运行版本', '增加可展开更新说明；暂未提供预发布源时明确禁用该通道', '保留签名校验、安装前备份和重启后版本确认'],
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
