import contextlib
import io
import json
from pathlib import Path
import socket
import sys
import threading
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deploy

class StartupTests(unittest.TestCase):
    def test_active_listener_is_not_mistaken_for_reusable_port(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('0.0.0.0', 0)); listener.listen()
            port=listener.getsockname()[1]
            with self.assertRaisesRegex(SystemExit, str(port)):
                deploy.check_ports([port])

    def test_reuse_port_after_server_actively_closes_connection(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('0.0.0.0', 0)); listener.listen()
            port=listener.getsockname()[1]
            with socket.create_connection(('127.0.0.1',port),timeout=2) as client:
                connection,_=listener.accept()
                connection.sendall(b'fixture')
                connection.close()  # The server side actively closes, entering TIME_WAIT.
                self.assertEqual(client.recv(32),b'fixture')
                self.assertEqual(client.recv(32),b'')
        deploy.check_ports([port])
        with socket.socket() as restarted:
            restarted.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            restarted.bind(('0.0.0.0',port));restarted.listen()

    def test_readiness_waits_for_running_version_and_pending_clear(self):
        states=[{'running':'0.1.0','pending':False}, {'running':'0.2.2','pending':True}, {'running':'0.2.2','pending':False}]
        class Backend(BaseHTTPRequestHandler):
            requests=0
            def log_message(self,*args):pass
            def do_GET(self):
                self.assert_path=self.path
                state=states[min(Backend.requests,len(states)-1)];Backend.requests+=1
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps(state).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Backend)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                deploy.wait_ready(server.server_port,'0.2.2',timeout=5)
            self.assertEqual(Backend.requests,3)
        finally:server.shutdown();server.server_close()

    def test_readiness_timeout_is_failure(self):
        with mock.patch.object(deploy.time,'monotonic',side_effect=[0,2]):
            with self.assertRaisesRegex(SystemExit,'Readiness failed'):
                deploy.wait_ready(1,'0.2.2',timeout=1)

if __name__=='__main__':unittest.main()
