import io
import http.client
import json
import socket
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
import ui

class InterfaceTests(unittest.TestCase):
    def handler(self, method, path, body=b'', token=None, host='127.0.0.1:8765'):
        handler = ui.Handler.__new__(ui.Handler)
        handler.server = SimpleNamespace(server_port=8765)
        handler.path = path
        handler.headers = {'Content-Length': str(len(body)), 'Host': host}
        if token: handler.headers['X-Canopy-Token'] = token
        handler.rfile = io.BytesIO(body)
        handler._arm_read_deadline = lambda: None
        handler._clear_read_deadline = lambda: None
        output = []
        handler.send = lambda status, content, mime: output.append((status, content))
        getattr(handler, 'do_' + method)()
        return output[0]
    def test_example_and_analysis(self):
        status, raw = self.handler('GET', '/example')
        self.assertEqual(status, 200)
        body = json.dumps({'files': json.loads(raw), 'pairs': [['Ada', 'Bo']]}).encode()
        status, raw = self.handler('POST', '/analyze', body, ui.TOKEN)
        self.assertEqual(status, 200)
        self.assertIn('Cy -> Supervisor', json.loads(raw)['report'])
    def test_bad_pair_and_missing_token(self):
        files = {n: (Path(__file__).resolve().parents[1] / 'examples' / (n + '.csv')).read_text(encoding='utf-8-sig') for n in ('roster', 'availability', 'qualifications', 'training')}
        body = json.dumps({'files': files, 'pairs': [['Ada', 'Ada']]}).encode()
        self.assertEqual(self.handler('POST', '/analyze', body)[0], 403)
        status, raw = self.handler('POST', '/analyze', body, ui.TOKEN)
        self.assertEqual(status, 400)
        self.assertIn('distinct known people', json.loads(raw)['error'])
    def test_html_served(self):
        status, raw = self.handler('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(b'Plan for absence', raw)
        self.assertNotIn(b'__TOKEN__', raw)

    def test_loopback_host_names_with_the_bound_port_work(self):
        for host in ('127.0.0.1:8765', 'localhost:8765'):
            with self.subTest(host=host):
                status, raw = self.handler('GET', '/', host=host)
                self.assertEqual(status, 200)
                self.assertIn(ui.TOKEN.encode(), raw)
    def test_foreign_or_malformed_host_cannot_read_token_or_submit_analysis(self):
        for host in ('foreign.example:8765', '127.0.0.1:9999', '127.0.0.1:8765.evil',
                     '[::1]:8765',
                     'localhost:8765@foreign.example', '[::1', '', '127.0.0.1'):
            with self.subTest(host=host):
                status, raw = self.handler('GET', '/', host=host)
                self.assertEqual(status, 403)
                self.assertNotIn(ui.TOKEN.encode(), raw)
                status, _ = self.handler('POST', '/analyze', b'{}', ui.TOKEN, host=host)
                self.assertEqual(status, 403)

    def test_many_people_are_rejected_before_repeated_analysis(self):
        files = {
            'roster': 'shift,role,requires\nS,Food,-\n',
            'availability': 'shift,person\n' + ''.join(f'S,P{i:04d}\n' for i in range(4000)),
            'qualifications': 'person,role\n',
            'training': 'person,role\n',
        }
        body = json.dumps({'files': files, 'pairs': []}).encode()
        self.assertLess(len(body), ui.MAX_BODY)
        status, raw = self.handler('POST', '/analyze', body, ui.TOKEN)
        self.assertEqual(status, 400)
        self.assertIn('at most', json.loads(raw)['error'])

    def test_incomplete_local_requests_release_the_interface(self):
        for partial_request in (
            b'GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n',
            b'POST /analyze HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n'
            b'X-Canopy-Token: {token}\r\nContent-Length: 100\r\n\r\n{{',
        ):
            with self.subTest(partial_request=partial_request[:4]):
                server = ui.BoundedHTTPServer(('127.0.0.1', 0), ui.Handler)
                server_errors = []
                server.handle_error = lambda *args: server_errors.append(args)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                stalled = socket.create_connection(('127.0.0.1', server.server_port), timeout=3)
                second = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                try:
                    stalled.sendall(partial_request.replace(b'{port}', str(server.server_port).encode())
                                    .replace(b'{token}', ui.TOKEN.encode()))
                    time.sleep(0.05)
                    start = time.monotonic()
                    second.request('GET', '/example')
                    response = second.getresponse()
                    response.read()
                    self.assertEqual(response.status, 200)
                    self.assertLess(time.monotonic() - start, 0.8)
                    if partial_request.startswith(b'POST'):
                        stalled.settimeout(1)
                        self.assertIn(b'408 Request Timeout', stalled.recv(256))
                finally:
                    second.close()
                    stalled.close()
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=3)
                self.assertFalse(server_errors)

    def test_many_incomplete_clients_have_bounded_workers(self):
        started = threading.Event()
        release = threading.Event()
        count_lock = threading.Lock()
        active = 0
        peak = 0

        class PausedHandler(ui.Handler):
            def setup(self):
                nonlocal active, peak
                super().setup()
                with count_lock:
                    active += 1
                    peak = max(peak, active)
                    if active == ui.MAX_ACTIVE_REQUESTS:
                        started.set()
                release.wait(timeout=3)
            def finish(self):
                nonlocal active
                try:
                    super().finish()
                finally:
                    with count_lock:
                        active -= 1

        server = ui.BoundedHTTPServer(('127.0.0.1', 0), PausedHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        clients = []
        try:
            for _ in range(10):
                client = socket.create_connection(('127.0.0.1', server.server_port), timeout=2)
                clients.append(client)
                client.sendall(b'GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n')
            self.assertTrue(started.wait(timeout=2))
            with count_lock:
                self.assertEqual(peak, ui.MAX_ACTIVE_REQUESTS)
            clients[-1].settimeout(1)
            busy_reply = bytearray()
            while chunk := clients[-1].recv(1024):
                busy_reply.extend(chunk)
            self.assertIn(b'503 Service Unavailable', busy_reply)
            self.assertIn(b'The local interface is busy. Retry in a moment.', busy_reply)
        finally:
            release.set()
            for client in clients:
                client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_busy_response_reaches_http_clients_without_waiting_for_input(self):
        started = threading.Event()
        release = threading.Event()
        count_lock = threading.Lock()
        active = 0

        class PausedHandler(ui.Handler):
            def setup(self):
                nonlocal active
                super().setup()
                with count_lock:
                    active += 1
                    if active == ui.MAX_ACTIVE_REQUESTS:
                        started.set()
                release.wait(timeout=3)

        server = ui.BoundedHTTPServer(('127.0.0.1', 0), PausedHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        clients = []
        try:
            for _ in range(ui.MAX_ACTIVE_REQUESTS):
                client = socket.create_connection(('127.0.0.1', server.server_port), timeout=2)
                clients.append(client)
                client.sendall(b'GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n')
            self.assertTrue(started.wait(timeout=2))
            for _ in range(8):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
                try:
                    connection.request('GET', '/example')
                    response = connection.getresponse()
                    self.assertEqual(response.status, 503)
                    self.assertIn(b'busy', response.read())
                finally:
                    connection.close()
            for size in (100_000, ui.MAX_BODY):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
                try:
                    connection.request('POST', '/analyze', body=b'x' * size)
                    response = connection.getresponse()
                    self.assertEqual(response.status, 503)
                    self.assertIn(b'busy', response.read())
                finally:
                    connection.close()
            fragmented = socket.create_connection(('127.0.0.1', server.server_port), timeout=2)
            clients.append(fragmented)
            fragmented.settimeout(1)
            fragmented.sendall(b'POST /analyze HTTP/1.1\r\nHost: localhost\r\nContent-Length: 6\r\n\r\nabc')
            time.sleep(0.02)
            fragmented.sendall(b'def')
            response = http.client.HTTPResponse(fragmented)
            response.begin()
            self.assertEqual(response.status, 503)
            self.assertIn(b'busy', response.read())
            silent = socket.create_connection(('127.0.0.1', server.server_port), timeout=2)
            clients.append(silent)
            silent.settimeout(1)
            start = time.monotonic()
            self.assertIn(b'503 Service Unavailable', silent.recv(1024))
            self.assertLess(time.monotonic() - start, 0.8)
        finally:
            release.set()
            for client in clients:
                client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_busy_read_does_not_block_accepting_a_later_request(self):
        started = threading.Event()
        release_workers = threading.Event()
        busy_started = threading.Event()
        release_busy = threading.Event()
        count_lock = threading.Lock()
        active = 0
        completed = 0
        finished = threading.Event()

        class PausedHandler(ui.Handler):
            def setup(self):
                nonlocal active
                super().setup()
                with count_lock:
                    active += 1
                    if active == ui.MAX_ACTIVE_REQUESTS:
                        started.set()
                release_workers.wait(timeout=3)
        class GatedServer(ui.BoundedHTTPServer):
            def _send_busy(self, request):
                busy_started.set()
                release_busy.wait(timeout=2)
                super()._send_busy(request)
            def process_request_thread(self, request, client_address):
                nonlocal completed
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    with count_lock:
                        completed += 1
                        if completed == ui.MAX_ACTIVE_REQUESTS:
                            finished.set()

        server = GatedServer(('127.0.0.1', 0), PausedHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        clients = []
        try:
            for _ in range(ui.MAX_ACTIVE_REQUESTS):
                client = socket.create_connection(('127.0.0.1', server.server_port), timeout=2)
                clients.append(client)
                client.sendall(b'GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n')
            self.assertTrue(started.wait(timeout=2))
            silent = socket.create_connection(('127.0.0.1', server.server_port), timeout=2)
            clients.append(silent)
            self.assertTrue(busy_started.wait(timeout=2))
            release_workers.set()
            for client in clients[:-1]:
                client.close()
            self.assertTrue(finished.wait(timeout=2))
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=1)
            try:
                connection.request('GET', '/example')
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
            finally:
                connection.close()
        finally:
            release_workers.set()
            release_busy.set()
            for client in clients:
                client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_busy_response_workers_are_bounded(self):
        started = threading.Event()
        release_workers = threading.Event()
        busy_full = threading.Event()
        release_busy = threading.Event()
        count_lock = threading.Lock()
        active = 0
        busy = 0
        peak = 0

        class PausedHandler(ui.Handler):
            def setup(self):
                nonlocal active
                super().setup()
                with count_lock:
                    active += 1
                    if active == ui.MAX_ACTIVE_REQUESTS:
                        started.set()
                release_workers.wait(timeout=3)

        class GatedServer(ui.BoundedHTTPServer):
            def _send_busy(self, request):
                nonlocal busy, peak
                with count_lock:
                    busy += 1
                    peak = max(peak, busy)
                    if busy == ui.MAX_BUSY_RESPONSES:
                        busy_full.set()
                release_busy.wait(timeout=2)
                try:
                    super()._send_busy(request)
                finally:
                    with count_lock:
                        busy -= 1

        server = GatedServer(('127.0.0.1', 0), PausedHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        clients = []
        try:
            for _ in range(ui.MAX_ACTIVE_REQUESTS):
                client = socket.create_connection(('127.0.0.1', server.server_port), timeout=2)
                clients.append(client)
                client.sendall(b'GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n')
            self.assertTrue(started.wait(timeout=2))
            for _ in range(ui.MAX_BUSY_RESPONSES + 2):
                clients.append(socket.create_connection(('127.0.0.1', server.server_port), timeout=2))
            self.assertTrue(busy_full.wait(timeout=2))
            with count_lock:
                self.assertEqual(peak, ui.MAX_BUSY_RESPONSES)
            self.assertFalse(server._busy_slots.acquire(blocking=False))
        finally:
            release_workers.set()
            release_busy.set()
            for client in clients:
                client.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_slow_input_drip_has_an_absolute_deadline(self):
        for partial_request in (
            b'GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-Slow: ',
            b'POST /analyze HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n'
            b'X-Canopy-Token: {token}\r\nContent-Length: 100\r\n\r\n{',
        ):
            with self.subTest(partial_request=partial_request[:4]):
                server = ui.BoundedHTTPServer(('127.0.0.1', 0), ui.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                stalled = socket.create_connection(('127.0.0.1', server.server_port), timeout=3)
                stopped = threading.Event()
                drip = None
                try:
                    stalled.settimeout(3)
                    stalled.sendall(partial_request.replace(b'{port}', str(server.server_port).encode())
                                    .replace(b'{token}', ui.TOKEN.encode()))
                    def keep_sending():
                        while not stopped.wait(0.2):
                            try:
                                stalled.sendall(b'x')
                            except OSError:
                                return
                    drip = threading.Thread(target=keep_sending, daemon=True)
                    start = time.monotonic()
                    drip.start()
                    self.assertEqual(stalled.recv(256), b'')
                    self.assertLess(time.monotonic() - start, 2.8)
                finally:
                    stopped.set()
                    stalled.close()
                    if drip:
                        drip.join(timeout=1)
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=3)

if __name__ == '__main__': unittest.main()
