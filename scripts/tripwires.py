"""
The tripwires the data can check, computed each weekday (decision D48).

After each assessment the Tripwires workflow runs this script. It reports each
tripwire's state and how near it is, writes the report to
data/tripwires/DATE.md, privately, and pings the tripwire alarm at
healthchecks.io with the report: a failure when a tripwire trips that had not
tripped on the previous window, so that the alarm emails the project mailbox
once for each new trip; otherwise a success. If the script cannot run, the
alarm is not pinged, and it emails when its grace time ends.

What it checks (roadmap section 3.5):

 1. Fewer than five contributors to the reference on 20 assessment days in a
    row, from the launch date: the grade is withdrawn (methodology 4.6).
 6. More than two missed assessment days in the last 30 windows: diagnose
    within a week; fix or publicly mark the break.
 9. More than a quarter of the reference's panel failing the receipt check on
    five assessment days in a row: find out whether the listing or the charge
    has changed.
11. A stale reference (D40): the leading challenger's OpenRouter tokens more
    than twice the reference's on 20 days in a row; or the reference's discount
    depth on output 10 points or more above its average over the previous 20
    assessment days with a figure. Either publishes a note on the site the same
    day, through site_notes.json.
D35. Cached replies excluding more than a quarter of any probed checkpoint's
    panel in five windows in a row: propose a new test piece, with 30 days'
    notice.
D50. Oversight: a reminder 7 days before publication would suspend itself,
    and again 2 days before.

The leading challenger is the probed checkpoint in the reference's grade with
the most providers, as on the site. Its tokens and the reference's come from
OpenRouter's daily rankings in data/market/ (D38), matched through the
census's canonical names; a later reading of the same day replaces an earlier
one. A reference missing from a day's rankings while the challenger is listed
counts as more than twice.

Usage:
    python3 scripts/tripwires.py [--today YYYY-MM-DD] [--write]

--write saves the report to data/tripwires/DATE.md. The workflow pings the
alarm from the exit code: 0 nothing new, 3 a tripwire newly tripped.
Uses only the Python standard library.
"""
import datetime as dt
import glob
import json
import os
import re
import sys
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (HERE, os.path.join(HERE, "site")):
    if p not in sys.path:
        sys.path.insert(0, p)
import assess  # noqa: E402
import oversight  # noqa: E402

MISSED = ("No probe ran in the window", "The probe did not finish in the window",
          "The test piece was not the frozen one")
CACHED = "Clean: cached input tokens"
NEWLY_TRIPPED = 3


# Reading the data ---------------------------------------------------------

def load_day(root, day):
    """{checkpoint: record} for one day's assessments."""
    out = {}
    for path in sorted(glob.glob(os.path.join(root, "data", "assessments", day.isoformat(), "*.json"))):
        with open(path) as f:
            rec = json.load(f)
        out[rec["checkpoint"]] = rec
    return out


def reference_of(day_recs):
    return next((r for r in day_recs.values() if r.get("reference")), None)


def windows(root, panel, asof):
    first = dt.date.fromisoformat(panel["assessment"]["first_window"])
    return assess.windows_between(first, asof)


def canonical_names(root, asof):
    """{openrouter id: canonical slug} from the latest census on or before asof."""
    days = sorted(d for d in os.listdir(os.path.join(root, "data", "census")) if d <= asof.isoformat())
    for d in reversed(days):
        path = os.path.join(root, "data", "census", d, "models.json")
        if os.path.exists(path):
            with open(path) as f:
                models = json.load(f)
            rows = models.get("data", models) if isinstance(models, dict) else models
            return {m["id"]: m.get("canonical_slug") or m["id"] for m in rows}
    return {}


def daily_tokens(root, before):
    """{date: {canonical slug: tokens}} for days before `before`, from every reading."""
    out = {}
    for folder in sorted(glob.glob(os.path.join(root, "data", "market", "*", "manifest.json"))):
        folder = os.path.dirname(folder)
        with open(os.path.join(folder, "manifest.json")) as f:
            manifest = json.load(f)
        for req in manifest.get("requests") or []:
            if req.get("dataset") != "/datasets/rankings-daily":
                continue
            if not re.match(r"^rankings(-\d{4}-\d{2}-\d{2})?$", req.get("request") or ""):
                continue
            for page in req.get("pages") or []:
                path = os.path.join(folder, page.get("file") or "")
                if not page.get("file") or not os.path.exists(path):
                    continue
                with open(path) as f:
                    rows = (json.load(f) or {}).get("data") or []
                fresh = {}
                for r in rows:
                    if r.get("date") and r["date"] < before.isoformat():
                        fresh.setdefault(r["date"], {})[r["model_permaslug"]] = float(r["total_tokens"])
                out.update(fresh)                 # a later reading of a day replaces an earlier one
    return out


# The checks: each returns (tripped, the line for the report) ----------------

def check_1(recs, launch, asof):
    if not launch or asof.isoformat() < launch:
        return False, "Not counted until the launch date, %s." % launch
    run = 0
    for day, r in reversed(recs):
        if day.isoformat() < launch:
            break
        if r and r.get("price"):
            break
        run += 1
    return run >= 20, "%d assessment day%s in a row without a figure; trips at 20." % (run, "" if run == 1 else "s")


def check_6(recs, asof):
    last = recs[-30:]
    missed = [d.isoformat() for d, r in last if (r is None and d < asof) or
              (r and str(r.get("reason") or "").startswith(MISSED))]
    text = "%d missed in the last %d windows%s; trips above 2." % (
        len(missed), len(last), (": " + ", ".join(missed)) if missed else "")
    return len(missed) > 2, text


def receipt_failures(r):
    """(failures, panel, names): providers with at least one completed request whose
    receipt did not match. One that completed nothing has no receipt to fail."""
    if not r or not r.get("panel"):
        return None
    fails = [p["provider"] for p in r.get("providers") or []
             if (p.get("tests") or {}).get("Receipt") is False and (p.get("measured") or {}).get("completed")]
    return len(fails), r["panel"], fails


def check_9(recs):
    run, today = 0, None
    for day, r in reversed(recs):
        f = receipt_failures(r)
        if today is None:
            today = f
        if not f or f[0] * 4 <= f[1]:
            break
        run += 1
    now = ("%d of %d failed today%s" % (today[0], today[1], (" (" + ", ".join(today[2]) + ")") if today[2] else "")
           if today else "no assessment today")
    return run >= 5, "%s; more than a quarter on %d day%s in a row; trips at 5." % (now, run, "" if run == 1 else "s")


def depth(r):
    try:
        return 100 * (1 - Decimal(r["price"]["output"]) / Decimal(r["undiscounted"]["output"]))
    except (TypeError, KeyError, ArithmeticError):
        return None


def check_11(recs, all_days, names, tokens, asof):
    lines, tripped = [], False
    # (a) the leading challenger's tokens against the reference's
    ref = recs[-1][1] if recs and recs[-1][1] else None
    today = all_days[-1][1] if all_days else {}
    if ref:
        import publish
        others = [r for r in today.values() if not r.get("reference") and r.get("grade") == ref.get("grade")]
        lead = publish.leading(others)
    else:
        lead = None
    if not ref or not lead:
        lines.append("(a) No leading challenger today.")
    else:
        a, b = names.get(lead["checkpoint"]), names.get(ref["checkpoint"])
        run, latest = 0, None
        for d in sorted(tokens, reverse=True):
            c, rf = tokens[d].get(a), tokens[d].get(b)
            if c is None:
                break
            ratio = c / rf if rf else float("inf")
            if latest is None:
                latest = (d, ratio)
            if ratio <= 2:
                break
            run += 1
        if latest is None:
            lines.append("(a) %s: no token figures yet." % lead["name"])
        else:
            shown = "%.2f" % latest[1] if latest[1] != float("inf") else "unbounded, the reference not in the rankings"
            lines.append("(a) %s's OpenRouter tokens were %s times the reference's on %s; above twice on %d day%s in a "
                         "row; trips at 20." % (lead["name"], shown, latest[0], run, "" if run == 1 else "s"))
            tripped = run >= 20
    # (b) the reference's discount depth against its previous 20 days with a figure
    with_fig = [(d, depth(r)) for d, r in recs if r and depth(r) is not None]
    if not with_fig or with_fig[-1][0] != asof:
        lines.append("(b) No figure today.")
    elif len(with_fig) < 21:
        lines.append("(b) Discount depth %.2f points today; the average needs 20 earlier days with a figure, %d so far."
                     % (with_fig[-1][1], len(with_fig) - 1))
    else:
        prev = [x for _, x in with_fig[-21:-1]]
        avg = sum(prev) / len(prev)
        rise = with_fig[-1][1] - avg
        lines.append("(b) Discount depth %.2f points today, %.2f above the average of the previous 20 days with a "
                     "figure; trips at 10." % (with_fig[-1][1], rise))
        tripped = tripped or rise >= 10
    return tripped, " ".join(lines)


def check_d35(all_days):
    worst, tripped = [], False
    cps = sorted({cp for _, recs in all_days for cp in recs})
    for cp in cps:
        run, today = 0, None
        for _, recs in reversed(all_days):
            r = recs.get(cp)
            if not r or not r.get("panel"):
                break
            n = sum(1 for p in r.get("providers") or [] if str(p.get("reason") or "").startswith(CACHED))
            if today is None:
                today = (n, r["panel"])
            if n * 4 <= r["panel"]:
                break
            run += 1
        if today:
            worst.append("%s %d of %d today, %d in a row" % (cp.split("/")[-1], today[0], today[1], run))
        tripped = tripped or run >= 5
    return tripped, ("Excluded for cached input: " + "; ".join(worst) + "; trips at 5 in a row above a quarter."
                     if worst else "No assessments.")


def check_oversight(root, asof, within):
    path = os.path.join(root, "data", "oversight.json")
    if not os.path.exists(path):
        return False, "No oversight record yet."
    rec = oversight.load(path)
    rec = dict(rec, confirmed=[c for c in rec.get("confirmed") or [] if c <= asof.isoformat()])
    if not rec["confirmed"]:
        return False, "No confirmation recorded by this date."
    st = oversight.status(rec, asof)
    if st["suspended_since"]:
        return True, "Publication is suspended since %s; confirm oversight to resume." % st["suspended_since"]
    return st["days_left"] <= within, ("Last confirmed %s; %d days left before publication would suspend itself; "
                                       "reminds at %d." % (st["last_confirmed"], st["days_left"], within))


# Putting it together -------------------------------------------------------

CHECKS = [("1", "Tripwire 1, too few contributors"), ("6", "Tripwire 6, missed days"),
          ("9", "Tripwire 9, receipts"), ("11", "Tripwire 11, stale reference"),
          ("D35", "D35, cached replies"), ("O7", "D50, oversight, 7 days"), ("O2", "D50, oversight, 2 days")]


def evaluate(root, asof):
    with open(os.path.join(root, "panel.json")) as f:
        panel = json.load(f)
    launch = panel.get("launch_date")
    wins = [d for d in windows(root, panel, asof)]
    all_days = [(d, load_day(root, d)) for d in wins]
    all_days = [(d, recs) for d, recs in all_days if recs or d < asof]
    recs = [(d, reference_of(day_recs)) for d, day_recs in all_days]
    names = canonical_names(root, asof)
    tokens = daily_tokens(root, asof)
    return {
        "1": check_1(recs, launch, asof),
        "6": check_6(recs, asof),
        "9": check_9([x for x in recs if x[1]]),
        "11": check_11(recs, all_days, names, tokens, asof),
        "D35": check_d35(all_days),
        "O7": check_oversight(root, asof, 7),
        "O2": check_oversight(root, asof, 2),
    }


def previous_window(day):
    d = day - dt.timedelta(days=1)
    while not assess.is_window(d):
        d -= dt.timedelta(days=1)
    return d


def report(root, today):
    now, before = evaluate(root, today), evaluate(root, previous_window(today))
    newly = [k for k, _ in CHECKS if now[k][0] and not before[k][0]]
    lines = ["# Tripwires, %s" % today.isoformat(), ""]
    if newly:
        lines += ["**Newly tripped: %s.**" % ", ".join(dict(CHECKS)[k] for k in newly), ""]
    for key, title in CHECKS:
        tripped, text = now[key]
        lines.append("- **%s: %s.** %s" % (title, "TRIPPED" if tripped else "clear", text))
    lines += ["", "What each one asks for is in the roadmap, section 3.5, and in the docstring of scripts/tripwires.py."]
    return "\n".join(lines) + "\n", newly


def main(argv):
    today = dt.datetime.now(dt.timezone.utc).date()
    if "--today" in argv:
        today = dt.date.fromisoformat(argv[argv.index("--today") + 1])
    root = os.getcwd()
    text, newly = report(root, today)
    print(text)
    if "--write" in argv:
        os.makedirs(os.path.join(root, "data", "tripwires"), exist_ok=True)
        with open(os.path.join(root, "data", "tripwires", today.isoformat() + ".md"), "w") as f:
            f.write(text)
    return NEWLY_TRIPPED if newly else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
