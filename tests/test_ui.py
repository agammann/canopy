import io
import json
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

if __name__ == '__main__': unittest.main()
