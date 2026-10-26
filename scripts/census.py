"""
Census collector.
Fetches the public OpenRouter model catalogue and, for each model, the list
of provider endpoints (price, quantisation, context, uptime). Saves the raw
JSON responses to a dated folder. Run once a day. No API key needed.

The record of each day (meta.json) says what took it: on GitHub, the workflow
event; on the London server, "server", set by scripts/runner.py through the
CENSUS_TRIGGER setting; otherwise "manual". It also records the commit of the
code that took it.

The first request, the list of every model, is the only one that can stop the
census, so it is tried three times: again after 15 seconds and after a further
45, and only when the reply stalls, the connection drops, the reply is cut off
partway, or OpenRouter answers with a rate limit or a server error. The record
of the day says how many tries it took. On 25 October 2026 a single stalled
reply to it stopped the server's census, and GitHub's backup took the day.
The requests for each model's endpoints are tried once, as before: a failure
there is written down as that model's error and the census carries on, and
retrying them during an outage would only drag a failure out towards the
runner's time limit.

OPENROUTER_BASE points it at another address, for the tests only.
"""
import datetime
import http.client
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

BASE = os.environ.get("OPENROUTER_BASE", "https://openrouter.ai/api/v1").rstrip("/")
LIST_WAITS = (15, 45)      # seconds before the second and the third try of the model list
HEADERS = {"User-Agent": "inference-assessment-census/0.1"}


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def retryable(error):
    """A stall, a dropped connection, a reply cut off partway, a rate limit or a
    server error. Any other refusal, such as a 404, is not worth repeating."""
    if isinstance(error, urllib.error.HTTPError):
        return error.code == 429 or error.code >= 500
    return isinstance(error, (OSError, http.client.HTTPException, ValueError))


def get_json_retrying(url, waits=LIST_WAITS, sleep=time.sleep):
    """(reply, tries). Tries once, and once more after each wait, while the
    failure is one worth repeating; otherwise the last failure is raised."""
    for tries in range(1, len(waits) + 2):
        try:
            return get_json(url), tries
        except Exception as e:
            if tries > len(waits) or not retryable(e):
                raise
            print(f"{url}: {type(e).__name__}: {e}; trying again in {waits[tries - 1]} seconds", flush=True)
            sleep(waits[tries - 1])


def main():
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    out_dir = os.path.join("data", "census", today)
    os.makedirs(out_dir, exist_ok=True)

    if os.path.exists(os.path.join(out_dir, "models.json")) and not os.environ.get("FORCE_CENSUS"):
        print(f"Census for {today} already exists; not overwriting. Set FORCE_CENSUS=1 to override.")
        return 0

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

    # 1. The full model list.
    models, meta["models_list_tries"] = get_json_retrying(f"{BASE}/models", LIST_WAITS)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
