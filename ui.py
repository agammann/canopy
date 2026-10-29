"""Loopback-only UI. CSVs are processed in memory and never written by the app."""
import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import canopy

ROOT = Path(__file__).resolve().parent
TOKEN = secrets.token_urlsafe(32)
MAX_BODY = 1_000_000

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Do not log names or input.
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path == '/':
            body = (ROOT / 'ui.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN).encode('utf-8')
            self.send(200, body, 'text/html; charset=utf-8')
        elif self.path == '/example':
            data = {n: (ROOT / 'examples' / (n + '.csv')).read_text(encoding='utf-8-sig') for n in ('roster', 'availability', 'qualifications', 'training')}
            self.send(200, json.dumps(data).encode(), 'application/json')
        else:
            self.send(404, b'Not found', 'text/plain')
    def do_POST(self):
        if self.path != '/analyze' or self.headers.get('X-Canopy-Token') != TOKEN:
            self.send(403, b'Forbidden', 'text/plain'); return
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if length < 0 or length > MAX_BODY: raise ValueError('Input exceeds the 1 MB limit.')
            payload = json.loads(self.rfile.read(length))
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

if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}/'
    print(f'Canopy running at {url} (Ctrl+C to stop)', flush=True)
    webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
