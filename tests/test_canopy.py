import sys
import unittest
from unittest.mock import patch
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
    def test_impossible_supervisor_does_not_explore_every_assignment(self):
        count = 8
        slots = [{'shift': 'S', 'role': 'Supervisor', 'requires': '-'}]
        slots += [{'shift': 'S', 'role': f'R{i}', 'requires': 'Supervisor'} for i in range(count)]
        people = [f'P{i}' for i in range(count)]
        available = [{'shift': 'S', 'person': person} for person in people]
        qualified = [{'person': person, 'role': f'R{i}'} for person in people for i in range(count)]
        visits = 0
        def guard(frame, event, _arg):
            nonlocal visits
            if event == 'call' and frame.f_code.co_name == 'visit' and frame.f_code.co_filename == canopy.__file__:
                visits += 1
                if visits > 5000:
                    raise AssertionError('solver explored too many impossible assignments')
        prior = sys.getprofile()
        try:
            sys.setprofile(guard)
            result, _ = canopy.solve((slots, available, qualified, []))
        finally:
            sys.setprofile(prior)
        self.assertEqual(result[0], 0)
    def test_later_supervisor_still_uses_an_available_person(self):
        slots = [{'shift': 'S', 'role': 'Food', 'requires': 'Supervisor'},
                 {'shift': 'S', 'role': 'Supervisor', 'requires': '-'}]
        available = [{'shift': 'S', 'person': person} for person in ('Ada', 'Bo')]
        qualified = [{'person': 'Ada', 'role': 'Food'},
                     {'person': 'Ada', 'role': 'Supervisor'},
                     {'person': 'Bo', 'role': 'Food'}]
        result, _ = canopy.solve((slots, available, qualified, []))
        self.assertEqual(result, (2, ['Bo', 'Ada']))
    def test_search_limit_returns_error_instead_of_partial_result(self):
        with patch.object(canopy, 'MAX_SOLVE_VISITS', 2):
            with self.assertRaisesRegex(ValueError, 'too complex'):
                canopy.solve(self.data)

    def test_scenario_work_is_bounded_before_solver_calls(self):
        slots = [{'shift': 'S', 'role': 'Food', 'requires': '-'}]
        available = [{'shift': 'S', 'person': f'P{i:02d}'} for i in range(50)]
        training = [{'person': f'P{i:02d}', 'role': 'Food'} for i in range(20)]
        with patch.object(canopy, 'solve', side_effect=AssertionError('solver must not run')):
            with self.assertRaisesRegex(ValueError, 'scenario limit'):
                canopy.report((slots, available, [], training))

if __name__ == '__main__': unittest.main()

