# Canopy

Experimental offline planning for small volunteer teams. Compare a baseline, every single-person absence, optional two-person absences, and individually proposed training options. Outputs hypothetical coverage witnesses, never invitations or assignments.

Requires Python 3.10+. No dependencies. Run:

```sh
python canopy.py examples --pair Ada,Bo > report.txt
python -m unittest discover -s tests -v
```

The example is entirely fictional. Print the plain-text report from an editor. Training Cy as a supervisor restores both roles when Ada is absent.

## CSV format

Supply a folder containing UTF-8 CSV files with exactly these headers:

- `roster.csv`: `shift,role,requires` — one row per role slot. `requires` is `-` or a supervisor role that must also be covered in the same shift. Duplicate slots are rejected; use distinct role names for multiple slots.
- `availability.csv`: `shift,person` — availability for the entire shift.
- `qualifications.csv`: `person,role` — existing qualifications.
- `training.csv`: `person,role` — user-proposed options. A header alone means none.

Use consistent identifiers and CSV quoting. One person covers at most one role per shift. Different shifts are assumed not to overlap; model overlapping shifts as one shift. Each covered dependent role requires a covered supervisor role in its shift; ratios and individual pairings are not modeled. Options are assessed separately. Ranking sums extra covered slots across all displayed scenarios including baseline; this is not probability or a fairness metric. Ties are alphabetical. Results are one optimal witness; other optimal witnesses may leave different roles uncovered. Candidate lists ignore competition and supervision and do not prove feasibility.

## Limitations

Alpha prototype, not validated scheduling, safety, legal or staffing advice. It assumes complete, correct data and cannot model fatigue, preferences, travel, role priorities, training costs, supervision ratios, or fairness. A coordinator must verify qualifications and decide independently. Exhaustive search is for small cases (maximum 18 slots, 100 people, 500 rows per CSV, 256 characters per field, and 500 total scenario solves including training). The report is limited to 1,000,000 bytes when JSON-encoded for the interface. If a case exceeds a limit, Canopy stops with an explicit error instead of presenting a partial answer; reduce field lengths, roles, people, or training options and retry. Data stays in local files and terminal; protect personal reports. No coordinator co-design has yet been performed.

[VolunteerShiftAI](https://github.com/HeroicSwan/volunteershift-ai) provides nonprofit scheduling with cost and fairness constraints. [Better Impact](https://www.betterimpact.com/volunteer-management-software) provides broader volunteer management, scheduling and training. Canopy explores counterfactual coverage and proposed training under explicit assumptions. This is not a uniqueness claim; demand remains unvalidated.

MIT licensed; original clean-room code, no third-party runtime dependencies.

## Local interface

Run `python ui.py` to open the local interface. It binds to a random loopback port and rejects requests with a nonlocal Host header; stop it with Ctrl+C. Load four CSV files or the fictional example, optionally enter two exact person IDs, and select Analyze coverage. Download a text report or use Print report. Inputs are processed in memory and are not saved by Canopy. Browser downloads and printed copies are your responsibility. The interface supports one manual pair; the CLI can compare several. If the interface is busy, retry in a moment; local uploads must finish promptly, within two seconds. The interface and exhaustive analysis are intended for small trusted local datasets, not network deployment.
