"""
Candidate tracker.
Reads EVERY day of census already collected and writes data/track.md: one row
per candidate, one column per day, showing the number of DISTINCT providers
serving that model at its native precision. Also computes, for each challenger,
how many consecutive days it has led the current reference, which is the
20-day stickiness test in the methodology.

Config lives in candidates.json at the repository root. Re-run any time; it
rebuilds the whole history from the saved census, so a gap or a fix in the
config is picked up retrospectively.
"""
import json
import os
import glob
import datetime

CONFIG = "candidates.json"
OUT = os.path.join("data", "track.md")
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

lines = [f"# Candidate tracking, rebuilt {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
         "",
         "Qualifying providers = distinct providers serving the checkpoint at its native precision.",
         "Bracketed figure is the total provider count at any precision, for context.",
         ""]

series = {}   # (grade, model) -> {day: qualifying}

for grade, entries in cfg["grades"].items():
    lines += [f"## {grade}", "",
              "| Model | Native | " + " | ".join(d[5:] for d in days) + " |",
              "|---|---|" + "---|" * len(days)]
    for e in entries:
        row, per_day = [], {}
        for d in days:
            q, total = qualifying_count(os.path.join("data", "census", d), e["openrouter_id"], e["native_precision"])
            per_day[d] = q
            row.append("-" if q is None else f"**{q}** ({total})")
        series[(grade, e["openrouter_id"])] = per_day
        marker = " *(reference)*" if e.get("reference") else ""
        prec = e["native_precision"]
        prec_str = " or ".join(prec) if isinstance(prec, list) else prec
        lines.append(f"| {e['openrouter_id']}{marker} | {prec_str} | " + " | ".join(row) + " |")
    lines.append("")

    # Stickiness: consecutive days each non-reference entry beat the reference.
    ref = next((e for e in entries if e.get("reference")), None)
    if ref:
        ref_series = series[(grade, ref["openrouter_id"])]
        lines += [f"### Stickiness against {ref['openrouter_id']}", ""]
        for e in entries:
            if e.get("reference"):
                continue
            streak = 0
            for d in reversed(days):
                a, b = series[(grade, e["openrouter_id"])].get(d), ref_series.get(d)
                if a is None or b is None or a <= b:
                    break
                streak += 1
            if streak == 0:
                state = "not leading"
            elif streak >= STICKINESS_DAYS:
                state = f"**ROLLOVER TRIGGERED**, {streak} consecutive days"
            else:
                state = f"leading {streak} of {STICKINESS_DAYS} consecutive days"
            lines.append(f"- {e['openrouter_id']}: {state}")
        lines.append("")

# Watchlist: any model in the grade's price band that is not yet a candidate
lines += ["## Watchlist", "",
          "Models seen in the census with five or more providers at a single declared",
          "precision that are not listed above. Check whether they belong in a grade.", ""]
latest = os.path.join("data", "census", days[-1], "endpoints")
known = {e["openrouter_id"] for entries in cfg["grades"].values() for e in entries}
found = []
for path in glob.glob(os.path.join(latest, "*.json")):
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
print(f"Tracked {len(days)} days across {sum(len(v) for v in cfg['grades'].values())} candidates.")
