import unittest
from pathlib import Path
import canopy

class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.data = canopy.load(Path(__file__).resolve().parents[1] / 'examples')
    def test_baseline(self):
        self.assertEqual(canopy.solve(self.data)[0][0], 2)
    def test_supervisor_absence_blocks_dependent_role(self):
        self.assertEqual(canopy.solve(self.data, ('Ada',))[0][0], 0)
    def test_training_removes_bottleneck(self):
        self.assertEqual(canopy.solve(self.data, ('Ada',), ('Cy', 'Supervisor'))[0][0], 2)
    def test_no_double_booking(self):
        self.assertEqual(canopy.solve(self.data, ('Ada', 'Bo'), ('Cy', 'Supervisor'))[0][0], 1)
    def test_report_and_pair(self):
        text = canopy.report(self.data, [('Ada', 'Bo')])
        self.assertIn('Absent: Ada, Bo', text)
        self.assertIn('Cy -> Supervisor', text)
    def test_invalid_pair(self):
        with self.assertRaises(ValueError): canopy.report(self.data, [('Ada', 'Ada')])
    def test_self_supervision_rejected(self):
        texts = {n: (Path(__file__).resolve().parents[1] / 'examples' / (n + '.csv')).read_text(encoding='utf-8-sig') for n in ('roster', 'availability', 'qualifications', 'training')}
        texts['roster'] = 'shift,role,requires\nMorning,Food,Food\n'
        with self.assertRaisesRegex(ValueError, 'cycle'): canopy.load_texts(texts)
    def test_extra_csv_field_rejected(self):
        texts = {n: (Path(__file__).resolve().parents[1] / 'examples' / (n + '.csv')).read_text(encoding='utf-8-sig') for n in ('roster', 'availability', 'qualifications', 'training')}
        texts['availability'] += 'Morning,Dee,extra\n'
        with self.assertRaisesRegex(ValueError, 'extra field'): canopy.load_texts(texts)
    def test_missing_supervisor_role_rejected(self):
        from tempfile import TemporaryDirectory
        import shutil
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
            for p in (Path(__file__).resolve().parents[1] / 'examples').iterdir(): shutil.copy(p, tmp)
            (Path(tmp) / 'roster.csv').write_text('shift,role,requires\nMorning,Food,Supervisor\n')
            with self.assertRaises(ValueError): canopy.load(tmp)

if __name__ == '__main__': unittest.main()

