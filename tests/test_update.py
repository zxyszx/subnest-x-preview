import importlib.util
import io
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import updater
import gateway
PAYLOAD = (ROOT / 'subnest-x-preview-0.2.0.zip').read_bytes()

class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in updater.FILES + ('updates.pub',):
            path = self.root / name; path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT / name,path)
        (self.root / 'VERSION').write_text('0.1.0\n')
        data = self.root / 'runtime/data'; data.mkdir(parents=True)
        with sqlite3.connect(data / 'mmwx.db') as db:
            db.execute('create table marker (value text)')
            db.execute("insert into marker values ('preserve settings')")
        (data / 'master.key').write_text('test-only-key')
    def tearDown(self): self.temp.cleanup()
    def test_valid_signed_package(self):
        manifest,files = updater.verify(self.root,PAYLOAD)
        self.assertEqual(manifest['version'],'0.2.0')
        self.assertIn('web/navigation.css',files)
    def test_release_asset_is_fixed_to_our_repository(self):
        import contextlib
        release={'tag_name':'v0.2.0','body':'release notes','assets':[{'name':'subnest-x-preview-0.2.0.zip','browser_download_url':gateway.ASSET_PREFIX+'v0.2.0/subnest-x-preview-0.2.0.zip'}]}
        def response(*args,**kwargs):return contextlib.closing(io.BytesIO(json.dumps(release).encode()))
        with mock.patch.object(gateway.urllib.request,'urlopen',response):
            self.assertEqual(gateway.latest_release()['version'],'0.2.0')
            release['assets'][0]['browser_download_url']='https://example.com/untrusted.zip'
            with self.assertRaisesRegex(ValueError,'签名更新包'):gateway.latest_release()
    def test_remote_download_cannot_exceed_package_limit(self):
        import contextlib
        with mock.patch.object(gateway,'latest_release',return_value={'url':'https://example.invalid/fixture'}), mock.patch.object(gateway.urllib.request,'urlopen',return_value=contextlib.closing(io.BytesIO(b'x'*(updater.MAX_PACKAGE+1)))):
            with self.assertRaisesRegex(ValueError,'4 MiB'):gateway.download_release()
    def test_tamper_rejected(self):
        data=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(PAYLOAD)) as source,zipfile.ZipFile(data,'w') as out:
            for name in source.namelist():
                out.writestr(name,b'tampered' if name=='web/navigation.css' else source.read(name))
        with self.assertRaisesRegex(ValueError,'校验失败'):updater.verify(self.root,data.getvalue())
    def test_duplicate_and_traversal_rejected(self):
        data=io.BytesIO(PAYLOAD)
        with zipfile.ZipFile(data,'a') as out:out.writestr('../runtime/data/mmwx.db',b'no')
        with self.assertRaisesRegex(ValueError,'列表'):updater.verify(self.root,data.getvalue())
    def test_signature_rejected(self):
        data=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(PAYLOAD)) as source,zipfile.ZipFile(data,'w') as out:
            for name in source.namelist():out.writestr(name,b'AAAA' if name=='update.sig' else source.read(name))
        with self.assertRaisesRegex(ValueError,'签名'):updater.verify(self.root,data.getvalue())
    def test_same_version_rejected(self):
        (self.root/'VERSION').write_text('0.2.0')
        with self.assertRaisesRegex(ValueError,'更新的'):updater.verify(self.root,PAYLOAD)
    def test_apply_backs_up_and_preserves_database(self):
        updater.apply(self.root,PAYLOAD)
        pending=json.loads((self.root/'runtime/pending-update.json').read_text())
        self.assertEqual(pending['from'],'0.1.0')
        backup=Path(pending['backup'])
        self.assertEqual((backup/'code/VERSION').read_text().strip(),'0.1.0')
        for dbpath in [self.root/'runtime/data/mmwx.db',backup/'data/mmwx.db']:
            with sqlite3.connect(dbpath) as db:self.assertEqual(db.execute('select value from marker').fetchone()[0],'preserve settings')
        self.assertEqual((self.root/'runtime/data/master.key').read_text(),'test-only-key')
        with self.assertRaisesRegex(ValueError,'等待重启'):updater.apply(self.root,PAYLOAD)
    def test_replace_failure_restores_code(self):
        original=Path.replace
        def fail(path,target):
            if path.name=='gateway.py.update-tmp':raise OSError('simulated disk failure')
            return original(path,target)
        before=(self.root/'deploy.py').read_bytes()
        with mock.patch.object(Path,'replace',fail):
            with self.assertRaises(OSError):updater.apply(self.root,PAYLOAD)
        self.assertEqual((self.root/'deploy.py').read_bytes(),before)
        self.assertEqual((self.root/'VERSION').read_text().strip(),'0.1.0')
        self.assertFalse((self.root/'runtime/pending-update.json').exists())
    def test_gateway_auth_injection_and_version(self):
        class Backend(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
                self.wfile.write(b'<html><head></head><body>upstream</body></html>')
        backend=ThreadingHTTPServer(('127.0.0.1',0),Backend)
        server=ThreadingHTTPServer(('127.0.0.1',0),gateway.Handler)
        server.root=self.root;server.backend=f'http://127.0.0.1:{backend.server_port}'
        server.key='fixture-only';server.running='0.1.0'
        for item in [backend,server]:threading.Thread(target=item.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}'
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def post(route,token='',origin=None):
            headers={'Authorization':'Bearer '+token}
            if origin:headers['Origin']=origin
            return opener.open(urllib.request.Request(base+route,data=PAYLOAD,headers=headers),timeout=5)
        try:
            self.assertIn(b'/__preview/navigation.css',opener.open(base).read())
            with self.assertRaises(urllib.error.HTTPError) as ctx:post('/__preview/apply')
            self.assertEqual(ctx.exception.code,401)
            with self.assertRaises(urllib.error.HTTPError) as ctx:post('/__preview/apply','fixture-only','http://other.example')
            self.assertEqual(ctx.exception.code,403)
            with self.assertRaises(urllib.error.HTTPError) as ctx:opener.open(base+'/api/admin/update/apply-sse')
            self.assertEqual(ctx.exception.code,409)
            self.assertTrue(json.load(post('/__preview/inspect','fixture-only'))['verified'])
            self.assertEqual(json.load(post('/__preview/apply','fixture-only'))['state'],'ready')
            state=json.load(opener.open(base+'/__preview/version'))
            self.assertEqual(state['running'],'0.1.0');self.assertEqual(state['installed'],'0.2.0');self.assertTrue(state['pending'])
        finally:
            for item in [server,backend]:item.shutdown();item.server_close()

if __name__=='__main__':unittest.main()
