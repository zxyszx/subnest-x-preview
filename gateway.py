"""Public UI gateway; preserves upstream auth/HTML, adds this repository's update UI."""
import hashlib
import hmac
import json
import sqlite3
from datetime import datetime, timezone
import mimetypes
import re
from pathlib import Path
import select
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qsl
import updater

PREFIX = '/__preview/'

RELEASE_API = 'https://api.github.com/repos/zxyszx/subnest-x-preview/releases/latest'
ASSET_PREFIX = 'https://github.com/zxyszx/subnest-x-preview/releases/download/'

def latest_release(channel="stable"):
    if channel not in ("stable", "prerelease"): raise ValueError("更新通道无效")
    request = urllib.request.Request(RELEASE_API if channel == "stable" else RELEASE_API.removesuffix("/latest"), headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'SubNest-X-Preview'})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024: raise ValueError('版本信息过大')
    release = json.loads(raw)
    if channel == 'prerelease':
        release = next((item for item in release if item.get('prerelease') and not item.get('draft')), None)
        if not release: raise ValueError('当前没有可用的预发布版')
    tag = release.get('tag_name', '')
    import re
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag): raise ValueError('发布版本格式无效')
    expected = f'subnest-x-preview-{tag[1:]}.zip'
    for asset in release.get('assets', []):
        url = asset.get('browser_download_url', '')
        if asset.get('name') == expected and url == ASSET_PREFIX + tag + '/' + expected:
            return {'version': tag[1:], 'notes': release.get('body', ''), 'url': url}
    raise ValueError('该版本没有签名更新包，请稍后重试')

def download_release():
    release = latest_release()
    with urllib.request.urlopen(release['url'], timeout=60) as response:
        payload = response.read(updater.MAX_PACKAGE + 1)
    if len(payload) > updater.MAX_PACKAGE: raise ValueError('更新包超过 4 MiB')
    return payload

def administrator_session(root, cookie):
    """Validate against the pinned runtime's own sessions; never trust a client role."""
    try:
        raw = next((item.strip().split('=', 1)[1] for item in (cookie or '').split(';')
                    if item.strip().startswith('traffic_info_access_token=')), None)
        if raw is None: return False
        token = json.loads(raw)
        if not isinstance(token, str) or not 1 <= len(token) <= 512: return False
        db_path = root / 'runtime/data/mmwx.db'
        with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True, timeout=3) as db:
            row = db.execute('SELECT s.expires_at FROM sessions s JOIN users u ON u.username=s.username '
                             "WHERE s.token=? AND u.role='admin' AND u.is_active=1", (token,)).fetchone()
        if not row: return False
        # The pinned Go runtime stores time.String(), including timezone and monotonic suffix.
        match = re.match(r'^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.(\d+))? ?([+-]\d{2}:?\d{2}|Z)', row[0])
        if not match: return False
        date, clock, fraction, zone = match.groups()
        zone = zone.replace('Z', '+00:00')
        if len(zone) == 5: zone = zone[:3] + ':' + zone[3:]
        expires = datetime.fromisoformat(date+'T'+clock+('.'+fraction[:6] if fraction else '')+zone.replace('Z','+00:00'))
        return expires > datetime.now(timezone.utc)
    except (ValueError, TypeError, sqlite3.Error, OSError):
        return False

class Handler(BaseHTTPRequestHandler):
    def do_GET(self): self.handle_request()
    def do_POST(self): self.handle_request()
    def do_PUT(self): self.handle_request()
    def do_PATCH(self): self.handle_request()
    def do_DELETE(self): self.handle_request()
    def do_OPTIONS(self): self.handle_request()
    def log_message(self, *args): pass

    def send_bytes(self, code, content, mime='application/json; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try: self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError): pass

    def json(self, code, content):
        self.send_bytes(code, json.dumps(content, ensure_ascii=False).encode())

    def authorized(self):
        supplied = self.headers.get('Authorization', '').removeprefix('Bearer ')
        # Python 3.9 supports removeprefix. Never put maintenance keys in URLs/logs.
        return hmac.compare_digest(supplied.encode(), self.server.key.encode())

    def local_update(self, route):
        public = {'update': 'web/update.html', 'update.js': 'web/update.js', 'navigation.css': 'web/navigation.css'}
        name = route[len(PREFIX):]
        if self.command == 'GET' and name == 'version':
            return self.json(200, {'running': self.server.running, 'installed': updater.version(self.server.root),
                'upstream': '0.6.0', 'pending': (self.server.root / 'runtime/pending-update.json').exists()})
        if self.command == 'GET' and name == 'latest':
            try: return self.json(200, latest_release(dict(parse_qsl(urlsplit(self.path).query)).get('channel', 'stable')))
            except ValueError as exc: return self.json(400, {'error': str(exc)})
            except Exception: return self.json(502, {'error': '无法检查更新，请稍后重试。'})
        if self.command == 'GET' and name in public:
            file = self.server.root / public[name]
            return self.send_bytes(200, file.read_bytes(), (mimetypes.guess_type(file.name)[0] or 'text/plain') + '; charset=utf-8')
        if self.command != 'POST' or name not in ('inspect', 'apply', 'restart', 'download', 'install'):
            return self.json(404, {'error': '未找到更新接口'})
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            return self.json(403, {'error': '拒绝跨站请求'})
        if name == 'install':
            if not origin or self.headers.get('X-Requested-With') != 'SubNest-Update':
                return self.json(403, {'error': '拒绝跨站请求'})
            if not administrator_session(self.server.root, self.headers.get('Cookie')):
                return self.json(401, {'error': '管理员登录已失效，请重新登录后重试'})
            return self.install_release()
        if not self.authorized():
            return self.json(401, {'error': '维护口令不正确。请在服务器读取 runtime/update-key。'})
        if name == 'download':
            try:
                payload = download_release()
                updater.verify(self.server.root, payload)
                return self.send_bytes(200, payload, 'application/zip')
            except Exception as exc: return self.json(400, {'error': str(exc)})
        if name == 'restart':
            try:
                result = subprocess.run(['systemctl', 'is-active', '--quiet', 'subnest-x-preview'], timeout=5)
                if result.returncode: raise ValueError('当前不是 systemd 托管的服务，请在终端重启启动命令')
                # Send the response before a separate process asks systemd to stop us.
                self.json(202, {'state': 'restarting'})
                threading.Timer(1, lambda: subprocess.Popen(['systemctl', 'restart', 'subnest-x-preview'], start_new_session=True)).start()
            except OSError:
                self.json(409, {'error': '当前环境无法调用 systemd，请在服务器执行 systemctl restart subnest-x-preview；本机预览请重启启动命令。'})
            except (ValueError, subprocess.TimeoutExpired) as exc:
                self.json(409, {'error': str(exc)})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= updater.MAX_PACKAGE:
                return self.json(413, {'error': '更新包为空或超过 4 MiB'})
            self.connection.settimeout(30)
            payload = self.rfile.read(length)
            if len(payload) != length: raise ValueError('更新包上传不完整')
            if name == 'inspect':
                manifest, _ = updater.verify(self.server.root, payload)
                return self.json(200, {'version': manifest['version'], 'notes': manifest.get('notes', []), 'verified': True})
            return self.json(200, updater.apply(self.server.root, payload))
        except Exception as exc:
            return self.json(400, {'error': str(exc)})

    def install_release(self):
        """One original update action: verify, back up, install, then restart."""
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1024: raise ValueError('更新请求无效')
            self.connection.settimeout(10)
            options = json.loads(self.rfile.read(length))
            if not isinstance(options, dict) or type(options.get('force')) is not bool: raise ValueError('更新请求无效')
            result = subprocess.run(['systemctl', 'is-active', '--quiet', 'subnest-x-preview'], timeout=5)
            if result.returncode: raise ValueError('当前环境不支持在线重启，更新未执行')
            target = options.get('target')
            marker = self.server.root / 'runtime/pending-update.json'
            if marker.exists():
                if json.loads(marker.read_text()).get('to') != target: raise ValueError('已有其他更新等待重启')
            else:
                release = latest_release(options.get('channel', 'stable'))
                if release['version'] != target: raise ValueError('发布版本已变化，请重新检查')
                with urllib.request.urlopen(release['url'], timeout=60) as response:
                    payload = response.read(updater.MAX_PACKAGE + 1)
                updater.apply(self.server.root, payload, allow_same=options['force'])
            self.json(202, {'state': 'restarting', 'version': target})
            threading.Timer(1, lambda: subprocess.Popen(['systemctl', 'restart', 'subnest-x-preview'], start_new_session=True)).start()
        except (OSError, ValueError, subprocess.SubprocessError):
            # Do not expose package paths, credentials, or internal maintenance instructions.
            self.json(400, {'error': '更新未完成，请重新检查后重试；已安装的更新会保留到服务重启。'})

    def handle_request(self):
        route = urlsplit(self.path).path
        if route.startswith(PREFIX): return self.local_update(route)
        if route.startswith('/api/admin/update/apply'):
            return self.json(409, {'error': '本部署由 SubNest X 预览更新维护，请使用用户菜单中的“检查更新”。'})
        if self.headers.get('Upgrade', '').lower() == 'websocket':
            return self.websocket()
        try:
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length) if length else None
            headers = {k:v for k,v in self.headers.items() if k.lower() not in ('connection','accept-encoding','content-length')}
            request = urllib.request.Request(self.server.backend + self.path, data=body, headers=headers, method=self.command)
            try:
                response = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=30)
            except urllib.error.HTTPError as exc: response = exc
            if 'text/event-stream' in response.headers.get('Content-Type',''):
                self.send_response(response.status)
                self.send_header('Content-Type','text/event-stream')
                self.send_header('Cache-Control','no-cache')
                self.end_headers()
                try:
                    while chunk := response.read1(65536):
                        self.wfile.write(chunk); self.wfile.flush()
                finally: response.close()
                return
            data = response.read(); response.close()
            # Only immutable, content-hashed frontend builds may be cached long term.
            # Never apply this policy to HTML, APIs, credentials or uploaded images.
            asset = self.command == 'GET' and response.status == 200 and re.fullmatch(
                r'/assets/[A-Za-z0-9_./-]+-[A-Za-z0-9_-]{8,}\.(?:js|css|woff2?|png|svg|webp)', route)
            etag = '"' + hashlib.sha256(data).hexdigest() + '"' if asset else None
            if asset and any(value.strip().removeprefix('W/') in (etag, '*')
                             for value in self.headers.get('If-None-Match', '').split(',')):
                self.send_response(304)
                self.send_header('ETag', etag)
                self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
                self.end_headers()
                return
            if 'text/html' in response.headers.get('Content-Type','') and b'</head>' in data:
                tags = ('<link rel="stylesheet" href="/__preview/navigation.css?v=' + self.server.running + '">'
                        '<script defer src="/__preview/update.js?v=' + self.server.running + '"></script>').encode()
                data = data.replace(b'</head>', tags + b'</head>', 1)
            self.send_response(response.status)
            for key,value in response.headers.items():
                if key.lower() not in ('connection','content-length','content-encoding','transfer-encoding','etag') and not (asset and key.lower() == 'cache-control'):
                    self.send_header(key,value)
            if asset:
                self.send_header('ETag', etag)
                self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers(); self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError,TimeoutError): pass
        except (OSError,ValueError): self.json(502, {'error':'本机原版服务暂未就绪，请稍后刷新。'})

    def websocket(self):
        backend = urlsplit(self.server.backend)
        try:
            with socket.create_connection((backend.hostname, backend.port), timeout=10) as upstream:
                raw = f'{self.command} {self.path} HTTP/1.1\r\n' + ''.join(f'{k}: {v}\r\n' for k,v in self.headers.items()) + '\r\n'
                upstream.sendall(raw.encode('latin-1')); upstream.settimeout(None)
                while True:
                    ready,_,_ = select.select([self.connection,upstream],[],[],30)
                    for source in ready:
                        data = source.recv(65536)
                        if not data: return
                        (upstream if source is self.connection else self.connection).sendall(data)
        except OSError: pass
        finally: self.close_connection = True

def create_server(root, port, backend):
    # Server starts only after the official runtime passes HTTP readiness.
    server = ThreadingHTTPServer(('0.0.0.0',port),Handler)
    server.root, server.backend = root, backend
    server.key = updater.maintenance_key(root)
    server.running = updater.version(root)
    pending = root / 'runtime/pending-update.json'
    if pending.exists():
        entry = json.loads(pending.read_text())
        if entry.get('to') == server.running:
            (root / 'runtime/last-update.json').write_text(json.dumps(entry))
            pending.unlink()
    return server

def serve(root, port, backend):
    server = create_server(root, port, backend)
    print(f'Preview v{server.running} listening on {port}', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
