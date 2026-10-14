"""
Probe. Runs on the London server only, weekdays at 14:05 UTC.

Buys the fixed test job from every provider serving each probed checkpoint at
an accepted precision, through OpenRouter, pinned to one endpoint per request
with fallback switched off. Also probes any direct control accounts listed in
panel.json. Saves everything raw. The assessor, on GitHub, does the judging.

Usage:
    python3 scripts/probe.py               daily run, writes data/probes/DATE/
    python3 scripts/probe.py --test        one request per checkpoint, prints a
                                           summary, writes nothing
    python3 scripts/probe.py --rehearsal   the whole daily run at once, without
                                           the waits between rounds, written to
                                           data/rehearsals/DATE-HHMM/

Reads panel.json, candidates.json and prompt.txt from the repository root, and
API keys from the environment (OPENROUTER_API_KEY, plus one per direct
account). Uses only the Python standard library.
"""
import concurrent.futures
import datetime
import hashlib
import json
import os
import random
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

OPENROUTER = os.environ.get("OPENROUTER_BASE", "https://openrouter.ai/api/v1").rstrip("/")
USER_AGENT = "hunterson-probe/1.0"
EXCLUDED_DAYS = {(12, 25), (1, 1)}


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def load_json(path):
    with open(path) as f:
        return json.load(f)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1)


def slug(text):
    return "".join(c if c.isalnum() or c in "-." else "_" for c in text.lower())


def accepted_precisions(candidates, checkpoint):
    """Accepted precision tags for a checkpoint, from candidates.json."""
    for entries in candidates["grades"].values():
        for e in entries:
            if e["openrouter_id"] == checkpoint:
                p = e["native_precision"]
                return p if isinstance(p, list) else [p]
    raise SystemExit(f"{checkpoint} is not in candidates.json, so its accepted precision is unknown")


def http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def fetch_listing(checkpoint):
    fetched = utc_now()
    body = http_get_json(f"{OPENROUTER}/models/{checkpoint}/endpoints")
    return {"checkpoint": checkpoint, "fetched_utc": iso(fetched), "response": body}


def per_token(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def venue_targets(listing, accepted):
    """One target per provider: its lowest-priced endpoint at an accepted precision."""
    best = {}
    endpoints = ((listing["response"].get("data") or {}).get("endpoints")) or []
    for ep in endpoints:
        if (ep.get("quantization") or "unspecified") not in accepted:
            continue
        pricing = ep.get("pricing") or {}
        out_price = per_token(pricing.get("completion"))
        if out_price is None or not ep.get("tag"):
            continue
        name = ep.get("provider_name", "unknown")
        if name not in best or out_price < best[name][0]:
            best[name] = (out_price, ep)
    targets = []
    for name, (_, ep) in sorted(best.items()):
        pricing = ep.get("pricing") or {}
        targets.append({
            "route": "openrouter",
            "checkpoint": listing["checkpoint"],
            "provider": name,
            "tag": ep["tag"],
            "quantization": ep.get("quantization"),
            "listed": {
                "prompt": pricing.get("prompt"),
                "completion": pricing.get("completion"),
                "discount": pricing.get("discount"),
                "overrides": pricing.get("overrides"),
            },
        })
    return targets


def direct_targets(panel, checkpoint):
    targets = []
    for d in panel.get("direct", []):
        model = (d.get("models") or {}).get(checkpoint)
        if not model:
            continue
        targets.append({
            "route": "direct",
            "checkpoint": checkpoint,
            "provider": d["provider"],
            "base_url": d["base_url"].rstrip("/"),
            "model": model,
            "key_env": d["key_env"],
            "extra": d.get("extra") or {},
        })
    return targets


def target_id(t):
    name = t["tag"] if t["route"] == "openrouter" else t["provider"]
    return f"{slug(t['checkpoint'])}__{t['route']}__{slug(name)}"


def build_request(t, prompt_body, nonce, max_tokens):
    content = nonce + "\n\n" + prompt_body
    body = {
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "top_p": 1,
        "stream": True,
    }
    if t["route"] == "openrouter":
        body["model"] = t["checkpoint"]
        body["provider"] = {"only": [t["tag"]], "allow_fallbacks": False}
        body["reasoning"] = {"enabled": False}
        body["transforms"] = []
        url = f"{OPENROUTER}/chat/completions"
        key = os.environ.get("OPENROUTER_API_KEY")
        key_env = "OPENROUTER_API_KEY"
    else:
        body["model"] = t["model"]
        body["stream_options"] = {"include_usage": True}
        body.update(t["extra"])
        url = f"{t['base_url']}/chat/completions"
        key = os.environ.get(t["key_env"])
        key_env = t["key_env"]
    return url, key, key_env, body


def run_request(t, prompt_body, round_no, day, max_tokens, timeout):
    """One streamed request. Returns a raw record; never raises."""
    nonce = f"PROBE {day} {target_id(t)} round {round_no} {uuid.uuid4().hex[:12]}"
    url, key, key_env, body = build_request(t, prompt_body, nonce, max_tokens)
    record = {
        "target": {k: v for k, v in t.items() if k != "extra"},
        "round": round_no,
        "nonce": nonce,
        "request": {k: v for k, v in body.items() if k != "messages"},
        "started_utc": iso(utc_now()),
        "http_status": None,
        "error": None,
        "error_body": None,
        "response_id": None,
        "served_by": None,
        "chunks": [],
        "first_token_s": None,
        "total_s": None,
        "finish_reason": None,
        "usage": None,
    }
    if not key:
        record["error"] = f"missing key {key_env}"
        return record
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-Title": "Hunterson probe",
        },
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            record["http_status"] = resp.status
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue  # blank lines and keep-alive comments
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                elapsed = time.perf_counter() - t0
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    record["chunks"].append({"t": round(elapsed, 4), "unparsed": payload[:500]})
                    continue
                if obj.get("error"):
                    record["error"] = "error in stream"
                    record["error_body"] = obj["error"]
                record["response_id"] = record["response_id"] or obj.get("id")
                record["served_by"] = record["served_by"] or obj.get("provider")
                if obj.get("usage"):
                    record["usage"] = obj["usage"]
                for choice in obj.get("choices") or []:
                    if choice.get("finish_reason"):
                        record["finish_reason"] = choice["finish_reason"]
                    delta = choice.get("delta") or {}
                    chunk = {"t": round(elapsed, 4)}
                    if delta.get("content"):
                        chunk["text"] = delta["content"]
                        if record["first_token_s"] is None:
                            record["first_token_s"] = round(elapsed, 4)
                    if delta.get("reasoning"):
                        chunk["reasoning"] = delta["reasoning"]
                    if len(chunk) > 1:
                        record["chunks"].append(chunk)
    except urllib.error.HTTPError as e:
        record["http_status"] = e.code
        record["error"] = f"HTTP {e.code}"
        try:
            record["error_body"] = e.read().decode("utf-8", errors="replace")[:4000]
        except Exception:
            pass
    except Exception as e:  # timeouts, resets, DNS
        record["error"] = f"{type(e).__name__}: {e}"
    record["total_s"] = round(time.perf_counter() - t0, 4)
    record["finished_utc"] = iso(utc_now())
    return record


def reply_text(record):
    return "".join(c.get("text", "") for c in record["chunks"])


def script_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except Exception:
        return None


def summarise(record):
    """Plain-language summary of one request, for --test."""
    u = record.get("usage") or {}
    t = record["target"]
    lines = [f"{t['checkpoint']} via {t.get('tag') or t['provider']} ({t['route']})"]
    if record["error"]:
        lines.append(f"  ERROR: {record['error']}")
        if record["error_body"]:
            lines.append(f"  detail: {json.dumps(record['error_body'])[:600]}")
        return "\n".join(lines)
    text = reply_text(record)
    first_line = text.strip().splitlines()[0] if text.strip() else "(empty reply)"
    ptok, ctok = u.get("prompt_tokens"), u.get("completion_tokens")
    rtok = (u.get("completion_tokens_details") or {}).get("reasoning_tokens")
    ctd = (u.get("prompt_tokens_details") or {}).get("cached_tokens")
    lines += [
        f"  input tokens:      {ptok}   (target 7,500 to 8,500)",
        f"  output tokens:     {ctok}   (should be 500)",
        f"  reasoning tokens:  {rtok}   (must be 0 or missing)",
        f"  cached tokens:     {ctd}   (must be 0 or missing)",
        f"  finish reason:     {record['finish_reason']}   (must be length)",
        f"  first line:        {first_line[:120]}",
        f"  first token after: {record['first_token_s']} s",
        f"  total time:        {record['total_s']} s",
    ]
    if record["first_token_s"] is not None and ctok and record["total_s"] > record["first_token_s"]:
        speed = ctok / (record["total_s"] - record["first_token_s"])
        lines.append(f"  speed:             {speed:.1f} output tokens per second")
    listed = t.get("listed") or {}
    pin, pout = per_token(listed.get("prompt")), per_token(listed.get("completion"))
    cost = u.get("cost")
    if cost is not None:
        lines.append(f"  charged:           ${cost:.6f}")
    if pin is not None and pout is not None and ptok is not None and ctok is not None:
        expected = ptok * pin + ctok * pout
        lines.append(f"  listed price x tokens: ${expected:.6f}")
        if cost:
            lines.append(f"  receipt / listed:  {cost / expected:.4f}   (1.0000 means the listed price was paid)")
    return "\n".join(lines)


def main(argv):
    mode = "daily"
    if "--test" in argv:
        mode = "test"
    elif "--rehearsal" in argv:
        mode = "rehearsal"

    panel = load_json("panel.json")
    candidates = load_json("candidates.json")
    with open("prompt.txt") as f:
        prompt_body = f.read()
    prompt_sha256 = hashlib.sha256(prompt_body.encode()).hexdigest()

    start = utc_now()
    day = start.strftime("%Y-%m-%d")
    if mode == "daily" and (start.month, start.day) in EXCLUDED_DAYS:
        print(f"{day} is outside the delivery window by rule. No probe.")
        return 0

    if mode == "daily":
        out_dir = os.path.join("data", "probes", day)
    elif mode == "rehearsal":
        out_dir = os.path.join("data", "rehearsals", start.strftime("%Y-%m-%d-%H%M"))
    else:
        out_dir = None
    if out_dir and os.path.exists(os.path.join(out_dir, "manifest.json")):
        print(f"{out_dir} already has a manifest; not overwriting.")
        return 0

    max_tokens = int(panel.get("max_output_tokens", 500))
    timeout = int(panel.get("timeout_seconds", 120))

    # 1. Listing snapshot and the day's panel.
    listings, targets = {}, []
    for checkpoint in panel["probe"]:
        accepted = accepted_precisions(candidates, checkpoint)
        listing = fetch_listing(checkpoint)
        listing["accepted_precisions"] = accepted
        listings[checkpoint] = listing
        found = venue_targets(listing, accepted)
        if mode == "test":
            wanted = panel.get("test_provider")
            pick = [t for t in found if t["provider"] == wanted] or found[:1]
            targets += pick
        else:
            targets += found + direct_targets(panel, checkpoint)
        if out_dir:
            write_json(os.path.join(out_dir, "listing", slug(checkpoint) + ".json"), listing)

    if mode == "test":
        if not targets:
            print("No provider found at an accepted precision. Check panel.json and candidates.json.")
            return 1
        print(f"Prompt sha256: {prompt_sha256}\n")
        for t in targets:
            rec = run_request(t, prompt_body, 0, day, max_tokens, timeout)
            print(summarise(rec) + "\n")
        return 0

    # 2. Rounds.
    rounds = int(panel.get("rounds", 3))
    spacing = 0 if mode == "rehearsal" else 60 * float(panel.get("round_spacing_minutes", 15))
    deadline = start + datetime.timedelta(minutes=float(panel.get("max_minutes", 50)))
    workers = int(panel.get("concurrency", 4))
    lock = threading.Lock()
    done, not_reached, failed = 0, [], 0

    def one(t, r):
        nonlocal done, failed
        if utc_now() >= deadline:
            with lock:
                not_reached.append({"target": target_id(t), "round": r, "reason": "deadline"})
            return
        rec = run_request(t, prompt_body, r, day, max_tokens, timeout)
        write_json(os.path.join(out_dir, "requests", f"{target_id(t)}__r{r}.json"), rec)
        with lock:
            done += 1
            failed += 1 if rec["error"] else 0

    for r in range(1, rounds + 1):
        round_start = start + datetime.timedelta(seconds=spacing * (r - 1))
        wait = (round_start - utc_now()).total_seconds()
        if wait > 0:
            time.sleep(wait)
        order = targets[:]
        random.shuffle(order)
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(lambda t: one(t, r), order))

    end = utc_now()
    manifest = {
        "mode": mode,
        "day": day,
        "started_utc": iso(start),
        "finished_utc": iso(end),
        "deadline_utc": iso(deadline),
        "script_commit": script_commit(),
        "prompt_sha256": prompt_sha256,
        "probe": panel["probe"],
        "launch_date": panel.get("launch_date"),
        "accept_line_1": panel.get("accept_line_1"),
        "accept_line_2": panel.get("accept_line_2"),
        "rounds": rounds,
        "targets": [target_id(t) for t in targets],
        "requests_made": done,
        "requests_with_error": failed,
        "not_reached": not_reached,
    }
    write_json(os.path.join(out_dir, "manifest.json"), manifest)
    print(f"{mode} {day}: {len(targets)} targets, {done} requests, {failed} with errors, "
          f"{len(not_reached)} not reached. Saved to {out_dir}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
