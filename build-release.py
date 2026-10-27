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
            'notes': ['前端内容哈希资源启用浏览器缓存与 ETag，减少主题整页切换时重复下载', '检查更新弹窗统一遮罩、刷新与关闭图标，支持 Escape、背景关闭及焦点恢复', '手动和网页更新共用签名校验与备份，增加跨进程安装锁及异常恢复', '统一命令支持检查、安装和重启，ZIP 安装无需 Git 元数据', '保留原版许可证、主题与业务数据；官方程序仍为 v0.6.0，主题图标同版对齐与真实服务器重启尚待验证'],
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
