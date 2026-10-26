#!/usr/bin/env python3
"""Install a pinned official runtime; never bundle local accounts or databases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import socket
import subprocess
import time
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / 'runtime'
VERSION = 'v0.6.0'
DIGESTS = {
    'linux-amd64': '65afbb5f07fe38d1dd91085b7ad021c7c6f6de548fc951da136728d582654b28',
    'linux-arm64': 'd82995e894f1813748c0a1397d35aff0f3d0a0cbff024ed6a312e590599169cf',
    'darwin-arm64': 'f0105de37fc42cbbf61f8fc9142bd34f45a3e0d0ae04b352d268ecfcc46517a7',
    'darwin-amd64': '012f62c08f645c57d1c38c4749c3340e289e077d89320b045d9e354953b672f1',
}

def target():
    machine = platform.machine().lower()
    arch = {'x86_64': 'amd64', 'amd64': 'amd64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(machine)
    value = f'{platform.system().lower()}-{arch}'
    if value not in DIGESTS:
        raise SystemExit(f'Unsupported platform: {value}')
    return value

def digest(path):
    with path.open('rb') as stream:
        hasher = hashlib.sha256()
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
        return hasher.hexdigest()

def install():
    name = target()
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    binary = RUNTIME / 'mmwx'
    if binary.exists() and digest(binary) == DIGESTS[name]:
        print(f'Official {VERSION} runtime already verified.')
        return
    url = f'https://github.com/iluobei/miaomiaowuX/releases/download/{VERSION}/mmwx-{name}'
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=RUNTIME, delete=False) as output:
            tmp = Path(output.name)
            with urllib.request.urlopen(url, timeout=120) as response:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
        if digest(tmp) != DIGESTS[name]:
            raise SystemExit('SHA-256 mismatch; refusing to run download.')
        tmp.chmod(0o700)
        tmp.replace(binary)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    print(f'Installed verified official {VERSION} for {name}.')

def check_ports(ports):
    # Like the actual HTTP listener, allow reuse after closed TCP connections.
    # An active listener still fails; never terminate another process for a port.
    for port in ports:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try: probe.bind(('0.0.0.0', port))
            except OSError as exc:
                raise SystemExit(f'Cannot bind port {port}: {exc}. Check: ss -ltnp') from exc

def wait_ready(port, expected, timeout=120):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    last = 'service not reachable'
    while time.monotonic() < deadline:
        try:
            with opener.open(f'http://127.0.0.1:{port}/__preview/version', timeout=2) as response:
                state = json.load(response)
            if state.get('running') == expected and not state.get('pending'):
                print(f'Preview v{expected} verified ready on {port}', flush=True)
                return
            last = f'waiting for v{expected}, reported running={state.get("running")}'
        except Exception as exc: last = str(exc)
        time.sleep(.5)
    raise SystemExit(f'Readiness failed after {timeout}s: {last}. Check journalctl -u subnest-x-preview -n 80 --no-pager')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'run', 'check', 'wait'])
    parser.add_argument('--port', type=int, default=12890)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65534:
        parser.error('Port must be between 1024 and 65534')
    if args.action == 'install':
        install()
    elif args.action == 'wait':
        wait_ready(args.port, (ROOT / 'VERSION').read_text().strip())
    elif args.action == 'run':
        binary = RUNTIME / 'mmwx'
        if not binary.exists() or digest(binary) != DIGESTS[target()]:
            raise SystemExit('Runtime missing or changed. Run: python3 deploy.py install')
        # Run the pinned upstream behind a gateway; preserve original Host and application data.
        config = RUNTIME / 'preview-config.yaml'
        backend_port = args.port + 1
        config.write_text(f'mode: release\nport: {backend_port}\n')
        env = os.environ.copy()
        env['PORT'] = str(backend_port)
        import gateway
        check_ports((args.port, backend_port))
        backend = subprocess.Popen([str(binary), '-c', str(config)], cwd=RUNTIME, env=env)
        def stop(*_):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, stop)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            for attempt in range(180):
                if backend.poll() is not None:
                    raise SystemExit('Official runtime exited before readiness')
                try:
                    with opener.open(f'http://127.0.0.1:{backend_port}/', timeout=1):
                        break
                except Exception:
                    time.sleep(.5)
            else:
                raise SystemExit('Official runtime did not become ready')
            gateway.serve(ROOT, args.port, f'http://127.0.0.1:{backend_port}')
        except KeyboardInterrupt:
            pass
        finally:
            backend.terminate()
            try:
                backend.wait(timeout=8)
            except subprocess.TimeoutExpired:
                backend.kill()
                backend.wait()
    else:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{args.port}/', timeout=10) as response:
            if response.status != 200 or b'<html' not in response.read().lower():
                raise SystemExit('Unexpected HTTP response')
        print(f'HTTP OK on port {args.port}; this is not a full business-flow test.')

if __name__ == '__main__':
    main()
