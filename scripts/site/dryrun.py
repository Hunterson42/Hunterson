"""
A dry run of a whole publishing day on the last shadow window, with nothing
committed, published or posted (the go-live runbook, launch pull request item 8).

Copies data/assessments and docs/ into OUT, marks the reference assessment of
the last day with a figure as published, as though that day were the launch
date, and builds the site into OUT/site exactly as the Publish workflow will on
launch day, with the oversight record and the site notes. Prints the day's
post and its length as X counts it. The Publish workflow, run by hand with
"dry run" ticked, then draws the cards, checks the X credentials without
posting, and keeps OUT/site as a download.

    python3 scripts/site/dryrun.py OUT [--today YYYY-MM-DD]

Run from the repository root. Uses only the Python standard library.
"""
import datetime as dt
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import oversight  # noqa: E402
import publish  # noqa: E402


def last_day_with_figure(src):
    for day in sorted(os.listdir(src), reverse=True):
        folder = os.path.join(src, day)
        if not os.path.isdir(folder):
            continue
        for fn in sorted(os.listdir(folder)):
            with open(os.path.join(folder, fn)) as f:
                rec = json.load(f)
            if rec.get("reference") and rec.get("price"):
                return day, fn
    raise ValueError("no shadow assessment with a figure yet")


def run(root, out, today):
    shutil.rmtree(out, ignore_errors=True)
    src, site = os.path.join(out, "assessments"), os.path.join(out, "site")
    shutil.copytree(os.path.join(root, "data", "assessments"), src)
    if os.path.isdir(os.path.join(root, "docs")):
        shutil.copytree(os.path.join(root, "docs"), site)
    day, fn = last_day_with_figure(src)
    for later in [d for d in os.listdir(src) if d > day]:
        shutil.rmtree(os.path.join(src, later))
    path = os.path.join(src, day, fn)
    with open(path) as f:
        rec = json.load(f)
    rec.update(status="published", published_utc=rec.get("assessed_utc") or rec["date"] + "T14:40:00Z")
    with open(path, "w") as f:
        json.dump(rec, f, indent=2)
    st = oversight.status(oversight.load(os.path.join(root, "data", "oversight.json")), today)
    with open(os.path.join(root, "site_notes.json")) as f:
        notes = json.load(f).get("notes") or []
    built = publish.build(src, site, oversight_status=st, notes=notes)
    tweet = os.path.join(site, "tweet", "standard", day + ".txt")
    with open(tweet) as f:
        text = f.read()
    url = text.strip().splitlines()[-1]
    weight = len(text) - len(url) + publish.URL_WEIGHT
    print("Dry run on the assessment of %s, built as though it were the launch date: %d days in the grade, "
          "%d pages in the site." % (day, built, sum(len(f) for _, _, f in os.walk(site))))
    print("Oversight last confirmed %s; %d days before publication would suspend itself."
          % (st["last_confirmed"], st["days_left"]))
    print("The post, %d characters as X counts them, of %d:\n" % (weight, publish.TWEET_LIMIT))
    print(text)
    return day


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(__doc__)
        return 2
    today = dt.datetime.now(dt.timezone.utc).date()
    if "--today" in argv:
        today = dt.date.fromisoformat(argv[argv.index("--today") + 1])
    try:
        run(os.getcwd(), argv[0], today)
    except (ValueError, publish.WriteOnceError) as err:
        print("STOPPED: %s" % err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
