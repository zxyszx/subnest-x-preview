"""The original update controls must use real administrator sessions and signed installs."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gateway
import updater
ROOT=Path(__file__).resolve().parents[1]

class NativeUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'runtime/data').mkdir(parents=True)
        self.db=self.root/'runtime/data/mmwx.db'
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE sessions(token TEXT,username TEXT,expires_at TEXT)')
            db.execute('CREATE TABLE users(username TEXT,role TEXT,is_active INTEGER)')
            db.execute("INSERT INTO users VALUES('fixture','admin',1)")
        self.expiry(datetime.now(timezone.utc)+timedelta(days=1))
        self.cookie='other=ok; traffic_info_access_token="fixture-token"'
    def tearDown(self):self.temp.cleanup()
    def expiry(self,time):
        with sqlite3.connect(self.db) as db:
            db.execute('DELETE FROM sessions')
            db.execute('INSERT INTO sessions VALUES(?,?,?)',('fixture-token','fixture',time.strftime('%Y-%m-%d %H:%M:%S.%f %z UTC m=+3600')))
    def test_actual_go_session_format_and_cookie(self):
        self.assertTrue(gateway.administrator_session(self.root,self.cookie))
        for cookie in ['', 'traffic_info_access_token="wrong"', 'traffic_info_access_token=null', 'traffic_info_access_token=broken']:
            self.assertFalse(gateway.administrator_session(self.root,cookie))
    def test_expired_disabled_and_non_admin_are_rejected(self):
        self.expiry(datetime.now(timezone.utc)-timedelta(seconds=1))
        self.assertFalse(gateway.administrator_session(self.root,self.cookie))
        self.expiry(datetime.now(timezone.utc)+timedelta(days=1))
        for role,active in [('user',1),('admin',0)]:
            with sqlite3.connect(self.db) as db:db.execute('UPDATE users SET role=?,is_active=?',(role,active))
            self.assertFalse(gateway.administrator_session(self.root,self.cookie))
    def test_force_only_allows_same_version_never_downgrade(self):
        import shutil
        for name in updater.FILES+('updates.pub',):
            dest=self.root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
        package=(ROOT/('subnest-x-preview-'+updater.version(ROOT)+'.zip')).read_bytes()
        with self.assertRaises(ValueError):updater.verify(self.root,package)
        updater.verify(self.root,package,allow_same=True)
        (self.root/'VERSION').write_text('99.0.0')
        with self.assertRaises(ValueError):updater.verify(self.root,package,allow_same=True)
    def test_install_requires_same_origin_admin_and_runs_backup_before_restart(self):
        from http.server import ThreadingHTTPServer
        server=ThreadingHTTPServer(('127.0.0.1',0),gateway.Handler)
        server.root=self.root;server.key='unused'
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base='http://127.0.0.1:'+str(server.server_port)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def post(headers):
            req=urllib.request.Request(base+'/__preview/install',data=json.dumps({'target':'0.2.6','force':True}).encode(),headers=headers)
            return opener.open(req,timeout=5)
        valid={'Origin':base,'X-Requested-With':'SubNest-Update','Cookie':self.cookie}
        try:
            for overrides,expected in [({'Cookie':''},401),({'Origin':'https://other.example'},403),({'Origin':''},403),({'X-Requested-With':''},403)]:
                with self.assertRaises(urllib.error.HTTPError) as caught:post({**valid,**overrides})
                self.assertEqual(caught.exception.code,expected)
            calls=[]
            with mock.patch.object(gateway.subprocess,'run',return_value=mock.Mock(returncode=0)),mock.patch.object(gateway,'latest_release',return_value={'version':'0.2.6','url':'https://fixture'}),mock.patch.object(gateway.urllib.request,'urlopen') as download,mock.patch.object(updater,'apply',side_effect=lambda *a,**k:calls.append(('apply',k))),mock.patch.object(gateway.threading,'Timer') as timer:
                download.return_value.__enter__.return_value.read.return_value=b'package'
                scheduled=threading.Event()
                timer.return_value.start.side_effect=lambda:(calls.append(('restart',{})),scheduled.set())
                self.assertEqual(json.load(post(valid))['state'],'restarting')
                self.assertTrue(scheduled.wait(2))
                self.assertEqual(calls,[('apply',{'allow_same':True}),('restart',{})])
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
