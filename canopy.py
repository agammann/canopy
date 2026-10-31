"""Small, exhaustive coverage analysis; no allocation is made."""
import argparse
import csv
import io
from pathlib import Path

MAX_SOLVE_VISITS = 100_000
MAX_REPORT_VISITS = 500_000
MAX_CSV_ROWS = 500
MAX_PEOPLE = 100
MAX_SCENARIO_SOLVES = 500
MAX_IDENTIFIER_CHARS = 256
MAX_REPORT_JSON_BYTES = 1_000_000


def validate_identifier(value):
    if len(value) > MAX_IDENTIFIER_CHARS:
        raise ValueError(f'identifier exceeds the {MAX_IDENTIFIER_CHARS}-character limit')
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError('identifiers must contain valid Unicode')


class ReportBuilder:
    """Bound the UI JSON response before joining any report fragments."""
    def __init__(self):
        # json.dumps({'report': ''}) contributes this many ASCII bytes.
        self.remaining = MAX_REPORT_JSON_BYTES - 14
        self.parts = []

    def add(self, text):
        for char in text:
            code = ord(char)
            if 0xD800 <= code <= 0xDFFF:
                raise ValueError('identifiers must contain valid Unicode')
            if char in '\"\\\b\f\n\r\t':
                cost = 2
            elif code < 0x20 or 0x7F <= code <= 0xFFFF:
                cost = 6
            elif code > 0xFFFF:
                cost = 12
            else:
                cost = 1
            self.remaining -= cost
            if self.remaining < 0:
                raise ValueError('report exceeds the output size limit; reduce the input')
        self.parts.append(text)

    def line(self, *parts):
        for part in parts:
            self.add(part)
        self.add('\n')

    def separated(self, values):
        for index, value in enumerate(values):
            if index:
                self.add(', ')
            self.add(value)

    def finish(self):
        return ''.join(self.parts)


def read_text(text, name, fields):
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff"), newline=""))
    rows = []
    try:
        if reader.fieldnames != fields:
            raise ValueError(f'{name}: expected columns {fields}')
        for row in reader:
            if len(rows) >= MAX_CSV_ROWS:
                raise ValueError(f'{name}: at most {MAX_CSV_ROWS} rows')
            if None in row or not all(row.values()) or any(not v.strip() for v in row.values()):
                raise ValueError(f'{name}: empty or extra field')
            for value in row.values():
                validate_identifier(value)
            rows.append(row)
    except csv.Error as exc:
        raise ValueError(f'{name}: invalid or oversized CSV field') from exc
    if len({tuple(r.values()) for r in rows}) != len(rows):
        raise ValueError(f'{name}: duplicate row')
    return rows


def load(folder):
    folder = Path(folder)
    names = ('roster', 'availability', 'qualifications', 'training')
    return load_texts({n: (folder / (n + '.csv')).read_text(encoding='utf-8-sig') for n in names})


def load_texts(texts):
    slots = read_text(texts['roster'], 'roster.csv', ['shift', 'role', 'requires'])
    avail = read_text(texts['availability'], 'availability.csv', ['shift', 'person'])
    skills = read_text(texts['qualifications'], 'qualifications.csv', ['person', 'role'])
    training = read_text(texts['training'], 'training.csv', ['person', 'role'])
    if not slots or len(slots) > 18:
        raise ValueError('roster must have 1-18 role slots')
    if len({(r['shift'], r['role']) for r in slots}) != len(slots):
        raise ValueError('each role must be unique within a shift')
    shifts = {r['shift'] for r in slots}
    people = {r['person'] for r in avail}
    if len(people) > MAX_PEOPLE:
        raise ValueError(f'availability.csv: at most {MAX_PEOPLE} people')
    if any(r['shift'] not in shifts for r in avail):
        raise ValueError('availability references unknown shift')
    if any(r['person'] not in people for r in skills + training):
        raise ValueError('qualification or training references unknown person')
    for s in slots:
        if s['requires'] != '-' and not any(t['shift'] == s['shift'] and t['role'] == s['requires'] for t in slots):
            raise ValueError('required supervisor role missing in shift')
    # A role cannot supervise itself, directly or through a cycle.
    for shift in shifts:
        dependencies = {s['role']: s['requires'] for s in slots if s['shift'] == shift and s['requires'] != '-'}
        for role in dependencies:
            seen = set()
            current = role
            while current in dependencies:
                if current in seen:
                    raise ValueError('supervision rules contain a cycle')
                seen.add(current)
                current = dependencies[current]
    return slots, avail, skills, training


def solve(data, absent=(), extra=None, budget=None):
    slots, avail, skills, _ = data
    availability = {(r['shift'], r['person']) for r in avail}
    qualifications = {(r['person'], r['role']) for r in skills}
    if extra:
        qualifications.add(extra)
    candidates = [sorted(p for sh, p in availability if sh == s['shift'] and p not in absent and (p, s['role']) in qualifications) for s in slots]
    role_index = {(s['shift'], s['role']): i for i, s in enumerate(slots)}
    best = None
    visits = 0
    def visit(i, assignments, used):
        nonlocal best, visits
        visits += 1
        if visits > MAX_SOLVE_VISITS or (budget is not None and budget[0] <= 0):
            raise ValueError('analysis is too complex; reduce roles or candidates')
        if budget is not None:
            budget[0] -= 1
        # An assigned dependent role cannot remain valid if its supervisor was
        # omitted or all remaining eligible supervisors are already occupied.
        for j, person in enumerate(assignments):
            required = slots[j]['requires']
            if person is None or required == '-':
                continue
            supervisor = role_index[(slots[j]['shift'], required)]
            if supervisor < i:
                if assignments[supervisor] is None:
                    return
            elif not any((slots[supervisor]['shift'], p) not in used for p in candidates[supervisor]):
                return
        if i == len(slots):
            covered = {(s['shift'], s['role']) for s, p in zip(slots, assignments) if p}
            if any(p and s['requires'] != '-' and (s['shift'], s['requires']) not in covered for s, p in zip(slots, assignments)):
                return
            score = sum(p is not None for p in assignments)
            if best is None or score > best[0]:
                best = (score, assignments[:])
            return
        if best and sum(p is not None for p in assignments) + len(slots) - i <= best[0]:
            return
        for person in candidates[i] + [None]:
            key = (slots[i]['shift'], person)
            if person is not None and key in used:
                continue
            visit(i + 1, assignments + [person], used | ({key} if person else set()))
    visit(0, [], set())
    return best, candidates


def report(data, pairs=()):
    slots, avail, skills, training = data
    # report() is also callable directly, bypassing the CSV parser.
    for rows in (slots, avail, skills, training):
        for row in rows:
            for value in row.values():
                validate_identifier(value)
    people = sorted({r['person'] for r in avail})
    if len(people) > MAX_PEOPLE:
        raise ValueError(f'analysis allows at most {MAX_PEOPLE} people')
    pairs = list(pairs)
    if any(len(x) != 2 or len(set(x)) != 2 or not set(x) <= set(people) for x in pairs):
        raise ValueError('each pair must contain two distinct known people')
    if (1 + len(people) + len(pairs)) * (1 + len(training)) > MAX_SCENARIO_SOLVES:
        raise ValueError(f'analysis exceeds the {MAX_SCENARIO_SOLVES} scenario limit; reduce people, pairs, or training options')
    scenarios = [()] + [(p,) for p in people] + pairs
    output = ReportBuilder()
    output.line('CANOPY - coverage evidence')
    output.line('Planning only: assignments below are hypothetical, not invitations or permission.')
    output.line('Assumptions: each person covers at most one role per shift; availability and qualifications are complete; required supervisor roles must be covered in the same shift.')
    output.line('')
    baseline_scores = []
    budget = [MAX_REPORT_VISITS]
    for absent in scenarios:
        (score, assignment), candidates = solve(data, absent, budget=budget)
        baseline_scores.append(score)
        output.add('Absent: ')
        if absent:
            output.separated(absent)
        else:
            output.add('nobody')
        output.line(f' - {score}/{len(slots)} slots covered')
        for s, p, c in zip(slots, assignment, candidates):
            output.add('  ')
            output.add(s['shift'])
            output.add(' / ')
            output.add(s['role'])
            output.add(': ')
            output.add(p or 'UNCOVERED')
            output.add(' (eligible: ')
            if c:
                output.separated(c)
            else:
                output.add('none')
            output.line('; supervisor: ', s['requires'], ')')
    output.line('')
    output.line('TRAINING OPTIONS - one at a time; improvement summed across listed scenarios')
    options = []
    for row in training:
        extra = (row['person'], row['role'])
        if any((s['person'], s['role']) == extra for s in skills):
            raise ValueError('training option already qualified')
        scores = [solve(data, absent, extra, budget=budget)[0][0] for absent in scenarios]
        options.append((sum(a-b for a,b in zip(scores, baseline_scores)), extra, scores))
    for gain, (person, role), scores in sorted(options, key=lambda x: (-x[0], x[1])):
        output.add('  ')
        output.add(person)
        output.add(' -> ')
        output.add(role)
        output.add(f': +{gain} covered slots across scenarios; scores ')
        output.separated(map(str, scores))
        output.line('')
    if not options:
        output.line('  No user-proposed options.')
    return output.finish()


def main():
    parser = argparse.ArgumentParser(description='Compare small volunteer coverage scenarios offline.')
    parser.add_argument('folder', help='folder containing the four CSV files')
    parser.add_argument('--pair', action='append', default=[], metavar='PERSON,PERSON', help='add a two-person absence scenario')
    args = parser.parse_args()
    try:
        pairs = [tuple(p.split(',')) for p in args.pair]
        print(report(load(args.folder), pairs), end='')
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Canopy: {exc}\n')

if __name__ == '__main__':
    main()

