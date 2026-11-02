"""
Oversight of the published figures (decision D50, CONTINUITY.md).

Hunterson is produced by one person, and the daily assessment runs without
anyone touching it. So publication stops by itself if the producer has not
confirmed oversight within the previous 45 days: the publishing step builds no
new day, and the site says that publication is suspended. When oversight is
confirmed again, the days in between are never published; they are shown as a
break in the series.

The record is data/oversight.json, kept privately:

    {"lapse_days": 45, "confirmed": ["2026-11-02", ...],
     "suspensions": [{"from": "2026-12-18", "to": "2026-12-21"}, ...]}

Usage:
    python3 scripts/site/oversight.py status  [PATH] [--today YYYY-MM-DD]
    python3 scripts/site/oversight.py confirm [PATH] [--today YYYY-MM-DD]

"confirm" is run by the Confirm oversight workflow, one click in the private
repository's Actions tab. Uses only the Python standard library.
"""
import datetime as dt
import json
import os
import sys

DEFAULT = os.path.join("data", "oversight.json")
LAPSE_DAYS = 45


def load(path=DEFAULT):
    with open(path) as f:
        return json.load(f)


def status(record, today):
    """{"last_confirmed", "lapse_days", "suspended_since" (or None), "days_left",
    "excluded": [(from, to), ...]}, every date as YYYY-MM-DD."""
    lapse = int(record.get("lapse_days") or LAPSE_DAYS)
    confirmed = sorted(record.get("confirmed") or [])
    if not confirmed:
        raise ValueError("no confirmation of oversight is recorded")
    last = dt.date.fromisoformat(confirmed[-1])
    first_suspended = last + dt.timedelta(days=lapse + 1)
    since = first_suspended.isoformat() if today >= first_suspended else None
    return {
        "last_confirmed": last.isoformat(),
        "lapse_days": lapse,
        "suspended_since": since,
        "days_left": (first_suspended - today).days - 1 if not since else 0,
        "excluded": [(s["from"], s["to"]) for s in record.get("suspensions") or []],
    }


def excluded(day, st):
    """True if a figure for this day must not be published: within a past
    suspension, or on or after the start of the current one."""
    if st["suspended_since"] and day >= st["suspended_since"]:
        return True
    return any(a <= day <= b for a, b in st["excluded"])


def confirm(record, today):
    """Record a confirmation today. If publication was suspended, the
    suspension is closed at yesterday and kept, so those days stay unpublished."""
    st = status(record, today)
    out = dict(record)
    if st["suspended_since"]:
        out["suspensions"] = list(record.get("suspensions") or []) + [
            {"from": st["suspended_since"], "to": (today - dt.timedelta(days=1)).isoformat()}]
    out["confirmed"] = sorted(set((record.get("confirmed") or []) + [today.isoformat()]))
    return out


def main(argv):
    if not argv or argv[0] not in ("status", "confirm"):
        print(__doc__)
        return 2
    today = dt.datetime.now(dt.timezone.utc).date()
    if "--today" in argv:
        today = dt.date.fromisoformat(argv[argv.index("--today") + 1])
    rest = [a for i, a in enumerate(argv[1:], 1) if not a.startswith("--") and argv[i - 1] != "--today"]
    path = rest[0] if rest else DEFAULT
    record = load(path)
    if argv[0] == "confirm":
        record = confirm(record, today)
        with open(path, "w") as f:
            json.dump(record, f, indent=2)
            f.write("\n")
        print("Oversight confirmed on %s." % today.isoformat())
    st = status(record, today)
    print(json.dumps(st))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
