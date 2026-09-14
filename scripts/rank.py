"""
Selection query, browser-readable version.
Reads today's census and writes data/rank/YYYY-MM-DD.md: a table of models
ranked by the number of DISTINCT providers serving them, with a breakdown by
declared quantisation and the spread of posted completion prices.
Runs inside GitHub Actions after census.py; no local Python needed.
"""
import json
import os
import glob
import datetime
import statistics
import collections

today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
folder = os.path.join("data", "census", today, "endpoints")
out_dir = os.path.join("data", "rank")
os.makedirs(out_dir, exist_ok=True)


def per_million(value):
    """OpenRouter quotes USD per token as a string; convert to USD per million."""
    try:
        return float(value) * 1_000_000
    except (TypeError, ValueError):
        return None


rows = []
for path in glob.glob(os.path.join(folder, "*.json")):
    with open(path) as f:
        data = json.load(f)
    body = data.get("data", {}) or {}
    endpoints = body.get("endpoints", []) or []
    if not endpoints:
        continue
    model_id = body.get("id") or os.path.basename(path).replace("__", "/").replace(".json", "")
    providers = set()
    quants = collections.Counter()
    completion_prices = []
    for ep in endpoints:
        providers.add(ep.get("provider_name", "unknown"))
        quants[ep.get("quantization") or "unspecified"] += 1
        p = per_million((ep.get("pricing") or {}).get("completion"))
        if p is not None and p > 0:
            completion_prices.append(p)
    if completion_prices:
        lo, mid, hi = min(completion_prices), statistics.median(completion_prices), max(completion_prices)
    else:
        lo = mid = hi = None
    rows.append({
        "model": model_id,
        "providers": len(providers),
        "endpoints": len(endpoints),
        "quants": quants,
        "lo": lo, "mid": mid, "hi": hi,
    })

rows.sort(key=lambda r: (-r["providers"], r["model"]))


def fmt(x):
    return "" if x is None else f"{x:.2f}"


def quant_str(c):
    return ", ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda kv: -kv[1]))


lines = [
    f"# Census ranking, {today}",
    "",
    "Models ranked by number of distinct providers. Prices are posted completion (output) prices in USD per million tokens, across all endpoints regardless of quantisation.",
    "",
    "| Rank | Model | Providers | Endpoints | Quantisation (count) | Output $/M low | median | high |",
    "|---|---|---|---|---|---|---|---|",
]
for i, r in enumerate(rows[:40], 1):
    lines.append(f"| {i} | {r['model']} | {r['providers']} | {r['endpoints']} | {quant_str(r['quants'])} | {fmt(r['lo'])} | {fmt(r['mid'])} | {fmt(r['hi'])} |")

eligible = [r for r in rows if r["providers"] >= 5]
lines += [
    "",
    f"## Models with five or more distinct providers: {len(eligible)}",
    "",
]
for r in eligible:
    lines.append(f"- {r['model']}: {r['providers']} providers, {quant_str(r['quants'])}")

with open(os.path.join(out_dir, f"{today}.md"), "w") as f:
    f.write("\n".join(lines) + "\n")

print(f"Ranking written for {today}: {len(rows)} models, {len(eligible)} with 5+ providers.")
