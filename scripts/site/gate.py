"""
Which days of the assessments the mirror may make public.

The assessments, data/assessments/DATE/, stay private until the launch date in
panel.json. From that date the mirror copies to the public repository:

- every day before the launch date: the shadow period, already fingerprinted
  and timestamped as each day was assessed;
- each later day once its page has been built in docs/, so that an assessment
  is fingerprinted and timestamped by the mirror run that follows the
  assessor, before it is published by the run that follows the publisher
  (decision D33);
- but never a day on which publication was suspended because oversight was not
  confirmed (decision D50, oversight.py). If data/oversight.json is missing,
  no day from the launch date on is copied, so that a lost record withholds
  the figures rather than publishing them.

Prints one DATE per line, in date order.

Usage:
    python3 scripts/site/gate.py PRIVATE_CHECKOUT [--today YYYY-MM-DD]

Uses only the Python standard library.
"""
import datetime as dt
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import oversight  # noqa: E402


def public_days(root, today):
    try:
        with open(os.path.join(root, "panel.json")) as f:
            launch = json.load(f).get("launch_date")
    except FileNotFoundError:
        return []
    base = os.path.join(root, "data", "assessments")
    if not launch or today.isoformat() < launch or not os.path.isdir(base):
        return []
    days = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)) and not d.startswith("."))
    record = os.path.join(root, "data", "oversight.json")
    st = oversight.status(oversight.load(record), today) if os.path.exists(record) else None
    if st is None:
        print("gate: data/oversight.json is missing, so no assessment from %s on is made public." % launch,
              file=sys.stderr)
    out = []
    for d in days:
        if d < launch:
            out.append(d)
        elif d > today.isoformat() or st is None or oversight.excluded(d, st):
            continue
        elif glob.glob(os.path.join(root, "docs", "*", d, "index.html")):
            out.append(d)
    return out


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(__doc__)
        return 2
    today = dt.datetime.now(dt.timezone.utc).date()
    if "--today" in argv:
        today = dt.date.fromisoformat(argv[argv.index("--today") + 1])
    for d in public_days(argv[0], today):
        print(d)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
