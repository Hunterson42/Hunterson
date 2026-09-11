"""
Census collector.
Fetches the public OpenRouter model catalogue and, for each model, the list
of provider endpoints (price, quantisation, context, uptime). Saves the raw
JSON responses to a dated folder. Run once a day. No API key needed.
"""
import json
import os
import time
import datetime
import urllib.request

BASE = "https://openrouter.ai/api/v1"
today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
out_dir = os.path.join("data", "census", today)
os.makedirs(out_dir, exist_ok=True)


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

print(f"Census complete for {today}: {len(models.get('data', []))} models.")
