import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gateway

class AssetCacheTests(unittest.TestCase):
    def test_hashed_assets_revalidate_without_caching_html_or_api(self):
        class Backend(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'application/javascript')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(b'fixture')
        backend = ThreadingHTTPServer(('127.0.0.1', 0), Backend)
        server = ThreadingHTTPServer(('127.0.0.1', 0), gateway.Handler)
        server.backend = f'http://127.0.0.1:{backend.server_port}'
        for item in (backend, server):
            threading.Thread(target=item.serve_forever, daemon=True).start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            url = base + '/assets/index-abcdefgh.js'
            with opener.open(url) as result:
                self.assertEqual(result.read(), b'fixture')
                self.assertIn('immutable', result.headers['Cache-Control'])
                etag = result.headers['ETag']
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                opener.open(urllib.request.Request(url, headers={'If-None-Match': etag}))
            self.assertEqual(ctx.exception.code, 304)
            for path in ('/', '/api/private', '/images/avatar.png', '/assets/patch.js'):
                with opener.open(base + path) as result:
                    self.assertEqual(result.headers['Cache-Control'], 'no-cache')
                    self.assertIsNone(result.headers.get('ETag'))
        finally:
            for item in (server, backend):
                item.shutdown()
                item.server_close()
