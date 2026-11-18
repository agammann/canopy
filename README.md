# Canopy

Canopy compares how absences and proposed training affect coverage for a small volunteer team. It models a baseline, each single-person absence and optional pairs. The reports show hypothetical ways to cover roles. A coordinator checks the assumptions, verifies qualifications and makes any staffing decision independently.

Canopy requires Python 3.10 or newer and uses only the standard library. Run these commands from this directory.

```sh
python canopy.py examples --pair Ada,Bo > report.txt
python -m unittest discover -s tests -v
```

The fictional example covers both roles with nobody absent. When Ada is absent, both roles are uncovered. In that scenario, qualifying Cy as a supervisor makes both roles coverable. Open or print the plain-text report from an editor. Use `--pair` once per distinct pair for additional two-person scenarios. The order of the two people does not change the scenario.

## CSV format

Supply a folder containing UTF-8 CSV files with exactly these headers:

- `roster.csv`: `shift,role,requires` — one row per role slot. `requires` is `-` or a supervisor role that must also be covered in the same shift. Duplicate slots are rejected; use distinct role names for multiple slots.
- `availability.csv`: `shift,person` — availability for the entire shift.
- `qualifications.csv`: `person,role` — existing qualifications.
- `training.csv`: `person,role` — user-proposed options. A header alone means none.

Use consistent identifiers and CSV quoting. One person covers at most one role per shift. Different shifts are assumed not to overlap; model overlapping shifts as one shift. Each covered dependent role requires a covered supervisor role in its shift; ratios and individual pairings are not modeled. Options are assessed separately. Ranking sums extra covered slots across all displayed scenarios including baseline; this is not probability or a fairness metric. Ties are alphabetical. Results are one optimal witness; other optimal witnesses may leave different roles uncovered. Candidate lists ignore competition and supervision and do not prove feasibility.

## Limitations

Canopy assumes complete availability and qualification data. Its model excludes fatigue, preferences, travel, role priorities, training costs, supervision ratios and fairness. Use the evidence for hypothetical coverage planning and verify staffing and safety requirements independently. No coordinator co-design has been performed.

Exhaustive search supports small cases with up to 18 slots, 100 people, 500 rows per CSV, 256 characters per field and 500 total scenario solves including training. The JSON-encoded report is limited to 1,000,000 bytes. Exceeding a limit stops the analysis with an error. Reduce field lengths, roles, people or training options and try again. Protect any reports containing personal information.

[VolunteerShiftAI](https://github.com/HeroicSwan/volunteershift-ai) provides nonprofit scheduling with cost and fairness constraints. [Better Impact](https://www.betterimpact.com/volunteer-management-software) provides broader volunteer management, scheduling and training. Canopy explores counterfactual coverage and proposed training under explicit assumptions. This is not a uniqueness claim; demand remains unvalidated.

MIT licensed; original clean-room code, no third-party runtime dependencies.

## Local interface

Run `python ui.py` to open the local interface. If the browser does not open, use the loopback URL printed in the terminal. Stop the server with Ctrl+C.

1. Select **Load example data** or choose the four CSV files.
2. Enter both exact person IDs for a two-person scenario or leave both fields blank. The interface supports one pair. Use the CLI for several.
3. Select **Analyze coverage** and inspect the assumptions, eligible people and coverage results. Run the analysis again after changing the files or pair.
4. Use **Download report** for plain text or **Print report** in the browser.

The server binds to a random loopback port and processes inputs in memory. Manage downloaded and printed copies separately. Local uploads must finish within two seconds. Retry if the interface is busy. An overloaded connection may close. Keep the interface on loopback and use small, trusted local datasets.
