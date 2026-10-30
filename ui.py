"""Loopback-only UI. CSVs are processed in memory and never written by the app."""
import json
import secrets
import socket
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore, Lock, Timer
import canopy

ROOT = Path(__file__).resolve().parent
TOKEN = secrets.token_urlsafe(32)
MAX_BODY = 1_000_000
READ_TIMEOUT_SECONDS = 1.0
READ_DEADLINE_SECONDS = 2.0
MAX_ACTIVE_REQUESTS = 4
BUSY_BODY = b'{"error":"The local interface is busy. Retry in a moment."}'

class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, *args, **kwargs):
        self._request_slots = BoundedSemaphore(MAX_ACTIVE_REQUESTS)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._request_slots.acquire(blocking=False):
            try:
                reply = (b'HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\n'
                         b'Content-Type: application/json\r\nCache-Control: no-store\r\nContent-Length: '
                         + str(len(BUSY_BODY)).encode() + b'\r\n\r\n' + BUSY_BODY)
                request.sendall(reply)
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self._deadline_lock = Lock()
        self._deadline_id = 0
        self._deadline_timer = None
        self.request.settimeout(READ_TIMEOUT_SECONDS)
        self._arm_read_deadline()
        try:
            super().setup()
        except BaseException:
            self._clear_read_deadline()
            raise
    def _arm_read_deadline(self):
        with self._deadline_lock:
            self._deadline_id += 1
            deadline_id = self._deadline_id
            timer = Timer(READ_DEADLINE_SECONDS, self._expire_read, args=(deadline_id,))
            timer.daemon = True
            self._deadline_timer = timer
            timer.start()
    def _clear_read_deadline(self):
        with self._deadline_lock:
            self._deadline_id += 1
            timer = self._deadline_timer
            self._deadline_timer = None
        if timer:
            timer.cancel()
    def _expire_read(self, deadline_id):
        with self._deadline_lock:
            if deadline_id != self._deadline_id:
                return
            self._deadline_id += 1
            self._deadline_timer = None
            try:
                self.request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
    def parse_request(self):
        try:
            return super().parse_request()
        finally:
            self._clear_read_deadline()
    def finish(self):
        self._clear_read_deadline()
        super().finish()
    def handle_one_request(self):
        try:
            super().handle_one_request()
        except ConnectionError:
            self.close_connection = True
    def log_message(self, *args):
        pass  # Do not log names or input.
    def local_host(self):
        port = self.server.server_port
        return self.headers.get('Host') in {f'127.0.0.1:{port}', f'localhost:{port}'}
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if not self.local_host():
            self.send(403, b'Forbidden', 'text/plain'); return
        if self.path == '/':
            body = (ROOT / 'ui.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN).encode('utf-8')
            self.send(200, body, 'text/html; charset=utf-8')
        elif self.path == '/example':
            data = {n: (ROOT / 'examples' / (n + '.csv')).read_text(encoding='utf-8-sig') for n in ('roster', 'availability', 'qualifications', 'training')}
            self.send(200, json.dumps(data).encode(), 'application/json')
        else:
            self.send(404, b'Not found', 'text/plain')
    def do_POST(self):
        if not self.local_host():
            self.send(403, b'Forbidden', 'text/plain'); return
        if self.path != '/analyze' or self.headers.get('X-Canopy-Token') != TOKEN:
            self.send(403, b'Forbidden', 'text/plain'); return
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if length < 0 or length > MAX_BODY: raise ValueError('Input exceeds the 1 MB limit.')
            self._arm_read_deadline()
            try:
                raw = self.rfile.read(length)
            finally:
                self._clear_read_deadline()
            if len(raw) != length:
                raise TimeoutError('Incomplete request body')
            payload = json.loads(raw)
            texts = payload['files']
            if not isinstance(texts, dict) or set(texts) != {'roster', 'availability', 'qualifications', 'training'} or not all(isinstance(x, str) for x in texts.values()):
                raise ValueError('Provide all four CSV files.')
            pairs = payload.get('pairs', [])
            if not isinstance(pairs, list) or len(pairs) > 10 or any(not isinstance(p, list) for p in pairs):
                raise ValueError('Provide at most ten pairs.')
            data = canopy.load_texts(texts)
            result = canopy.report(data, pairs)
            self.send(200, json.dumps({'report': result}).encode(), 'application/json')
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self.send(400, json.dumps({'error': str(exc)}).encode(), 'application/json')
        except TimeoutError:
            self.close_connection = True
            try:
                self.send(408, b'Request timed out', 'text/plain')
            except OSError:
                pass

if __name__ == '__main__':
    server = BoundedHTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}/'
    print(f'Canopy running at {url} (Ctrl+C to stop)', flush=True)
    webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
