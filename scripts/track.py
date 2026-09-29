"""
Candidate tracker.
Reads EVERY day of census already collected and writes data/track.md:
a summary table of the latest day, then one row per candidate per day of
history, then the stickiness streaks, then the watchlist.

Config lives in candidates.json at the repository root. Re-run any time; it
rebuilds the whole history from the saved census, so a fix in the config is
picked up retrospectively.
"""
import json
import os
import glob
import datetime

CONFIG = "candidates.json"
OUT = os.path.join("data", "track.md")
SITE_OUT = os.path.join("data", "site", "track.json")
STICKINESS_DAYS = 20


def load_config():
    with open(CONFIG) as f:
        return json.load(f)


def qualifying_count(census_dir, openrouter_id, native_precision):
    """Distinct providers serving this model at an accepted precision, on one day.
    native_precision may be a single string or a list of acceptable tags."""
    accepted = native_precision if isinstance(native_precision, list) else [native_precision]
    path = os.path.join(census_dir, "endpoints", openrouter_id.replace("/", "__") + ".json")
    if not os.path.exists(path):
        return None, None
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None, None
    endpoints = (data.get("data") or {}).get("endpoints") or []
    if not endpoints:
        return None, None
    all_providers, native_providers = set(), set()
    for ep in endpoints:
        name = ep.get("provider_name", "unknown")
        all_providers.add(name)
        if (ep.get("quantization") or "unspecified") in accepted:
            native_providers.add(name)
    return len(native_providers), len(all_providers)


cfg = load_config()
days = sorted(os.path.basename(p) for p in glob.glob(os.path.join("data", "census", "*"))
              if os.path.isdir(p))
if not days:
    raise SystemExit("no census data found")

# Pass one: compute every series once, as (qualifying, total) per day.
series = {}
stickiness = {}  # (grade, id) -> (state text, streak); filled below, shared by both outputs
for grade, entries in cfg["grades"].items():
    for e in entries:
        per_day = {}
        for d in days:
            per_day[d] = qualifying_count(os.path.join("data", "census", d),
                                          e["openrouter_id"], e["native_precision"])
        series[(grade, e["openrouter_id"])] = per_day

lines = [f"# Candidate tracking, rebuilt {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
         "",
         "Qualifying providers = distinct providers serving the checkpoint at its native precision.",
         "Bracketed figure in the history tables is the total provider count at any precision.",
         ""]

# Summary of the latest day.
lines += [f"## Latest: {days[-1]}", "",
          "Change is against seven days earlier. Share is qualifying providers as a percentage of all providers serving the model.",
          "",
          "| Grade | Model | Qualifying | All | Share | 7d change |",
          "|---|---|---|---|---|---|"]
prev_day = days[-8] if len(days) >= 8 else days[0]
for grade, entries in cfg["grades"].items():
    for e in entries:
        per_day = series[(grade, e["openrouter_id"])]
        latest_q, latest_total = per_day[days[-1]]
        prev_q = per_day[prev_day][0]
        if latest_q is None:
            change = "-"
        elif prev_q is None:
            change = "new"
        else:
            diff = latest_q - prev_q
            change = f"{diff:+d}" if diff else "0"
        share = "-" if not latest_q or not latest_total else f"{100 * latest_q / latest_total:.0f}%"
        marker = " *(reference)*" if e.get("reference") else ""
        lines.append(f"| {grade.split(' (')[0]} | {e['openrouter_id']}{marker} | "
                     f"**{'-' if latest_q is None else latest_q}** | {latest_total or '-'} | {share} | {change} |")
lines.append("")

# History tables and stickiness.
for grade, entries in cfg["grades"].items():
    lines += [f"## {grade}", "",
              "| Model | Native | " + " | ".join(d[5:] for d in days) + " |",
              "|---|---|" + "---|" * len(days)]
    for e in entries:
        row = []
        for d in days:
            q, total = series[(grade, e["openrouter_id"])][d]
            row.append("-" if q is None else f"**{q}** ({total})")
        marker = " *(reference)*" if e.get("reference") else ""
        prec = e["native_precision"]
        prec_str = " or ".join(prec) if isinstance(prec, list) else prec
        lines.append(f"| {e['openrouter_id']}{marker} | {prec_str} | " + " | ".join(row) + " |")
    lines.append("")

    ref = next((e for e in entries if e.get("reference")), None)
    if ref:
        ref_series = series[(grade, ref["openrouter_id"])]
        lines += [f"### Stickiness against {ref['openrouter_id']}", ""]
        for e in entries:
            if e.get("reference"):
                continue
            streak = 0
            for d in reversed(days):
                a = series[(grade, e["openrouter_id"])][d][0]
                b = ref_series[d][0]
                if a is None or b is None or a <= b:
                    break
                streak += 1
            if streak == 0:
                state = "not leading"
            elif streak >= STICKINESS_DAYS:
                state = f"**ROLLOVER TRIGGERED**, {streak} consecutive days"
            else:
                state = f"leading {streak} of {STICKINESS_DAYS} consecutive days"
            stickiness[(grade, e["openrouter_id"])] = (state.replace("**", ""), streak)
            lines.append(f"- {e['openrouter_id']}: {state}")
        lines.append("")

# Watchlist.
lines += ["## Watchlist", "",
          "Models seen in the census with five or more providers at a single declared",
          "precision that are not listed above. Check whether they belong in a grade.", ""]
latest_dir = os.path.join("data", "census", days[-1], "endpoints")
known = {e["openrouter_id"] for entries in cfg["grades"].values() for e in entries}
found = []
for path in glob.glob(os.path.join(latest_dir, "*.json")):
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        continue
    body = data.get("data") or {}
    mid = body.get("id")
    if not mid or mid in known or mid in cfg.get("ignore", []):
        continue
    by_prec = {}
    for ep in body.get("endpoints") or []:
        by_prec.setdefault(ep.get("quantization") or "unspecified", set()).add(ep.get("provider_name", "unknown"))
    by_prec.pop("unspecified", None)
    if not by_prec:
        continue
    best_prec, best = max(by_prec.items(), key=lambda kv: len(kv[1]))
    if len(best) >= 5:
        found.append((len(best), mid, best_prec))
found.sort(reverse=True)
for n, mid, prec in found[:25]:
    lines.append(f"- {mid}: {n} providers at {prec}")
if not found:
    lines.append("- none")

os.makedirs("data", exist_ok=True)
with open(OUT, "w") as f:
    f.write("\n".join(lines) + "\n")
# Machine-readable copy for the website, built from the SAME series, stickiness
# and watchlist computed above, so the page and track.md cannot disagree.
def _unpublished(name):
    low = name.lower()
    return "not published" in low or "monitoring only" in low


site = {
    "schema_version": 1,
    "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "first_day": days[0],
    "latest_day": days[-1],
    "days": days,
    "stickiness_days": STICKINESS_DAYS,
    "grades": [],
    "watchlist": [{"id": mid, "providers": n, "precision": prec} for n, mid, prec in found[:25]],
}
for grade, entries in cfg["grades"].items():
    ref = next((e for e in entries if e.get("reference")), None)
    g = {
        "name": grade,
        "short": grade.split(" (")[0],
        "published": not _unpublished(grade),
        "reference": ref["openrouter_id"] if ref else None,
        "candidates": [],
    }
    for e in entries:
        per_day = series[(grade, e["openrouter_id"])]
        prec = e["native_precision"]
        state, streak = stickiness.get((grade, e["openrouter_id"]), (None, 0))
        g["candidates"].append({
            "id": e["openrouter_id"],
            "reference": bool(e.get("reference")),
            "native_precision": prec if isinstance(prec, list) else [prec],
            "qualifying": [per_day[d][0] for d in days],
            "all": [per_day[d][1] for d in days],
            "stickiness": None if e.get("reference") else {"state": state, "streak": streak},
        })
    site["grades"].append(g)

os.makedirs(os.path.dirname(SITE_OUT), exist_ok=True)
with open(SITE_OUT, "w") as f:
    json.dump(site, f, indent=1)

print(f"Tracked {len(days)} days across {sum(len(v) for v in cfg['grades'].values())} candidates.")
