"""
Census collector.
Fetches the public OpenRouter model catalogue and, for each model, the list
of provider endpoints (price, quantisation, context, uptime). Saves the raw
JSON responses to a dated folder. Run once a day. No API key needed.

The record of each day (meta.json) says what took it: on GitHub, the workflow
event; on the London server, "server", set by scripts/runner.py through the
CENSUS_TRIGGER setting; otherwise "manual". It also records the commit of the
code that took it.
"""
import json
import os
import subprocess
import time
import datetime
import urllib.request

BASE = "https://openrouter.ai/api/v1"
today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
out_dir = os.path.join("data", "census", today)
os.makedirs(out_dir, exist_ok=True)

if os.path.exists(os.path.join(out_dir, "models.json")) and not os.environ.get("FORCE_CENSUS"):
    print(f"Census for {today} already exists; not overwriting. Set FORCE_CENSUS=1 to override.")
    raise SystemExit(0)

started = datetime.datetime.now(datetime.timezone.utc)
meta = {
    "day": today,
    "started_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "trigger": os.environ.get("GITHUB_EVENT_NAME") or os.environ.get("CENSUS_TRIGGER") or "manual",
    "run_id": os.environ.get("GITHUB_RUN_ID"),
}
try:
    meta["script_commit"] = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                           timeout=10).stdout.strip() or None
except Exception:
    meta["script_commit"] = None


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "inference-assessment-census/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


# 1. The full model list.
models = get_json(f"{BASE}/models")
with open(os.path.join(out_dir, "models.json"), "w") as f:
    json.dump(models, f, indent=2)

# 2. Per-model endpoints. Paced to avoid rate limiting.
endpoints_dir = os.path.join(out_dir, "endpoints")
os.makedirs(endpoints_dir, exist_ok=True)
for m in models.get("data", []):
    model_id = m["id"]
    safe_name = model_id.replace("/", "__")
    try:
        ep = get_json(f"{BASE}/models/{model_id}/endpoints")
        with open(os.path.join(endpoints_dir, f"{safe_name}.json"), "w") as f:
            json.dump(ep, f, indent=2)
    except Exception as e:
        with open(os.path.join(endpoints_dir, f"{safe_name}.ERROR.txt"), "w") as f:
            f.write(str(e))
    time.sleep(0.4)

meta["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
meta["models"] = len(models.get("data", []))
meta["errors"] = len([n for n in os.listdir(endpoints_dir) if n.endswith(".ERROR.txt")])
with open(os.path.join(out_dir, "meta.json"), "w") as f:
    json.dump(meta, f, indent=2)

print(f"Census complete for {today}: {len(models.get('data', []))} models.")
