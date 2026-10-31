import json
import io
import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import canopy
import ui


def sample(people):
    slots = [{'shift': 'S', 'role': 'Food', 'requires': '-'}]
    available = [{'shift': 'S', 'person': person} for person in people]
    qualified = [{'person': person, 'role': 'Food'} for person in people]
    return slots, available, qualified, []


def csv_files(people):
    return {
        'roster': 'shift,role,requires\nS,Food,-\n',
        'availability': 'shift,person\n' + ''.join(f'S,{person}\n' for person in people),
        'qualifications': 'person,role\n' + ''.join(f'{person},Food\n' for person in people),
        'training': 'person,role\n',
    }


class ReportBudgetTests(unittest.TestCase):
    def test_long_identifiers_are_rejected_before_report_amplification(self):
        people = [f'{i:03d}' + 'x' * 3997 for i in range(100)]
        with self.assertRaisesRegex(ValueError, 'limit|long|large'):
            canopy.report(sample(people))

    def test_short_identifiers_keep_full_hundred_person_report(self):
        people = [f'P{i:03d}' for i in range(100)]
        result = canopy.report(sample(people))
        self.assertEqual(result.count('Absent:'), 101)
        self.assertIn('P000, P001', result)
        self.assertLessEqual(len(json.dumps({'report': result}).encode()), canopy.MAX_REPORT_JSON_BYTES)

    def test_aggregate_budget_rejects_before_joining_large_candidates(self):
        people = [f'{i:03d}' + 'x' * 253 for i in range(100)]
        with self.assertRaisesRegex(ValueError, 'output size limit'):
            canopy.report(sample(people))

    def test_json_escaped_budget_exact_boundary(self):
        text = 'A"\\\n\x01\x7f\u00e9\U0001f642'
        exact = len(json.dumps({'report': text}).encode())
        with patch.object(canopy, 'MAX_REPORT_JSON_BYTES', exact):
            builder = canopy.ReportBuilder()
            builder.add(text)
            self.assertEqual(builder.finish(), text)
        with patch.object(canopy, 'MAX_REPORT_JSON_BYTES', exact - 1):
            builder = canopy.ReportBuilder()
            with self.assertRaisesRegex(ValueError, 'output size limit'):
                builder.add(text)

    def test_lone_surrogate_rejected(self):
        with self.assertRaisesRegex(ValueError, 'valid Unicode'):
            canopy.report(sample(['bad\ud800']))

    def test_csv_fields_are_bounded_during_read(self):
        value = 'x' * (canopy.MAX_IDENTIFIER_CHARS + 1)
        with self.assertRaisesRegex(ValueError, 'character limit'):
            canopy.read_text('shift,role,requires\n' + value + ',Food,-\n',
                             'roster.csv', ['shift', 'role', 'requires'])

    def test_ui_returns_clear_error_for_original_shape(self):
        cases = [([f'{i:03d}' + 'x' * 3997 for i in range(100)], 'character limit'),
                 (['x' * (csv.field_size_limit() + 1)], 'oversized CSV field')]
        for people, error in cases:
            with self.subTest(error=error):
                body = json.dumps({'files': csv_files(people), 'pairs': []}).encode()
                self.assertLess(len(body), ui.MAX_BODY)
                handler = ui.Handler.__new__(ui.Handler)
                handler.server = SimpleNamespace(server_port=8765)
                handler.path = '/analyze'
                handler.headers = {'Content-Length': str(len(body)), 'Host': '127.0.0.1:8765',
                                   'X-Canopy-Token': ui.TOKEN}
                handler.rfile = io.BytesIO(body)
                handler._arm_read_deadline = lambda: None
                handler._clear_read_deadline = lambda: None
                output = []
                handler.send = lambda status, content, mime: output.append((status, content))
                handler.do_POST()
                self.assertEqual(output[0][0], 400)
                self.assertIn(error, json.loads(output[0][1])['error'])

    def test_cli_reports_error_without_partial_output(self):
        files = csv_files(['x' * (canopy.MAX_IDENTIFIER_CHARS + 1)])
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in files.items():
                (Path(tmp) / (name + '.csv')).write_text(content, encoding='utf-8')
            result = subprocess.run([sys.executable, str(Path(canopy.__file__)), tmp],
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertIn('character limit', result.stderr)


if __name__ == '__main__':
    unittest.main()
