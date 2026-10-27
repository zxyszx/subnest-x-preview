"""Exercise shared CLI/web install paths using signed packages and isolated data."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import updater
import gateway

PACKAGE=ROOT / ('subnest-x-preview-'+updater.version(ROOT)+'.zip')
PAYLOAD=PACKAGE.read_bytes()

class UpdateFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        for name in updater.FILES+('updates.pub',):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/name,path)
        (self.root/'VERSION').write_text('0.2.4\n')
        data=self.root/'runtime/data';data.mkdir(parents=True)
        with sqlite3.connect(data/'fixture.db') as db:
            db.execute('create table marker (value text)')
            db.execute("insert into marker values ('keep settings')")
        (data/'wallpaper.jpg').write_bytes(b'wallpaper-fixture')
        (self.root/'runtime/update-key').write_text('fixture-only')
    def tearDown(self):self.temp.cleanup()
    def test_cli_inspect_and_install_without_git_and_without_auto_restart(self):
        for action in ['inspect','install']:
            result=subprocess.run([sys.executable,str(self.root/'updater.py'),action,str(PACKAGE)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse((self.root/'.git').exists())
        self.assertIn('尚未重启',result.stdout)
        self.assertEqual(updater.version(self.root),updater.version(ROOT))
        self.assertTrue((self.root/'runtime/pending-update.json').exists())
        with sqlite3.connect(self.root/'runtime/data/fixture.db') as db:
            self.assertEqual(db.execute('select value from marker').fetchone()[0],'keep settings')
        self.assertEqual((self.root/'runtime/data/wallpaper.jpg').read_bytes(),b'wallpaper-fixture')
        self.assertEqual((self.root/'runtime/update-key').read_text(),'fixture-only')
    def test_cli_rejects_bad_package_without_changing_version(self):
        bad=self.root/'bad.zip';bad.write_bytes(b'not a zip')
        result=subprocess.run([sys.executable,str(self.root/'updater.py'),'install',str(bad),'--restart'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(updater.version(self.root),'0.2.4')
        self.assertFalse((self.root/'runtime/pending-update.json').exists())
    def test_web_and_manual_installs_cannot_overlap_across_processes(self):
        with updater.installation_lock(self.root):
            result=subprocess.run([sys.executable,str(self.root/'updater.py'),'install',str(PACKAGE)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('另一项更新正在进行',result.stderr)
        self.assertEqual(updater.version(self.root),'0.2.4')
        updater.apply(self.root,PAYLOAD) # Lock is released after failed contender.
    def test_permissions_survive_file_replacement(self):
        target=self.root/'install-service.sh';target.chmod(0o750)
        updater.apply(self.root,PAYLOAD)
        self.assertEqual(target.stat().st_mode & 0o777,0o750)
    def test_marker_write_failure_restores_code(self):
        replace=Path.replace
        def fail(path,target):
            if path.name=='pending-update.json.tmp':raise OSError('marker write failure')
            return replace(path,target)
        with mock.patch.object(Path,'replace',fail):
            with self.assertRaisesRegex(OSError,'marker'):updater.apply(self.root,PAYLOAD)
        self.assertEqual(updater.version(self.root),'0.2.4')
        self.assertFalse((self.root/'runtime/pending-update.json').exists())
    def test_download_inspect_install_pending_and_restarted_gateway(self):
        server=gateway.create_server(self.root,0,'http://127.0.0.1:1')
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base='http://127.0.0.1:'+str(server.server_port)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def post(route,body=None,key='fixture-only'):
            req=urllib.request.Request(base+'/__preview/'+route,data=body if body is not None else b'',headers={'Authorization':'Bearer '+key,'Origin':base})
            return opener.open(req,timeout=10)
        try:
            with self.assertRaises(urllib.error.HTTPError) as caught:post('download',key='wrong')
            self.assertEqual(caught.exception.code,401)
            with mock.patch.object(gateway,'download_release',return_value=PAYLOAD):
                downloaded=post('download').read()
            self.assertEqual(downloaded,PAYLOAD)
            self.assertTrue(json.load(post('inspect',downloaded))['verified'])
            self.assertEqual(json.load(post('apply',downloaded))['state'],'ready')
            state=json.load(opener.open(base+'/__preview/version'))
            self.assertEqual(state['running'],'0.2.4')
            self.assertEqual(state['installed'],updater.version(ROOT))
            self.assertTrue(state['pending'])
            with self.assertRaises(urllib.error.HTTPError) as caught:post('apply',downloaded)
            self.assertIn('等待重启',caught.exception.read().decode())
            with mock.patch.object(gateway.subprocess,'run',return_value=mock.Mock(returncode=0)), mock.patch.object(gateway.threading,'Timer') as timer:
                scheduled=threading.Event()
                timer.return_value.start.side_effect=scheduled.set
                self.assertEqual(json.load(post('restart'))['state'],'restarting')
                self.assertTrue(scheduled.wait(2), 'Restart must be scheduled after the HTTP response')
                timer.return_value.start.assert_called_once()
        finally:server.shutdown();server.server_close()
        # Simulate the gateway boot after upstream readiness, not a real Linux systemd restart.
        restarted=gateway.create_server(self.root,0,'http://127.0.0.1:1')
        try:
            self.assertEqual(restarted.running,updater.version(ROOT))
            self.assertFalse((self.root/'runtime/pending-update.json').exists())
            self.assertTrue((self.root/'runtime/last-update.json').exists())
        finally:restarted.server_close()
    def test_restart_failure_is_reported_and_pending_state_is_retained(self):
        updater.apply(self.root,PAYLOAD)
        # Keep this gateway's process version at the old version to model pending restart.
        from http.server import ThreadingHTTPServer
        server=ThreadingHTTPServer(('127.0.0.1',0),gateway.Handler)
        server.root=self.root;server.running='0.2.4';server.key='fixture-only'
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/__preview/restart',data=b'',headers={'Authorization':'Bearer fixture-only'})
            with mock.patch.object(gateway.subprocess,'run',side_effect=FileNotFoundError('systemctl')):
                with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=5)
            self.assertEqual(caught.exception.code,409)
            self.assertTrue((self.root/'runtime/pending-update.json').exists())
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
