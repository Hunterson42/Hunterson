"""
Probe. Runs on the London server only, weekdays at 14:05 UTC, started by
scripts/runner.py.

Buys the fixed test job from every provider serving each probed checkpoint at
an accepted precision, through OpenRouter, pinned to one endpoint per request
with fallback switched off. Also probes any direct control accounts listed in
panel.json. Saves everything raw. The assessor, on GitHub, does the judging.

Usage:
    python3 scripts/probe.py               daily run, writes data/probes/DATE/
    python3 scripts/probe.py --test        one request per checkpoint, prints a
                                           summary, writes nothing
    python3 scripts/probe.py --test-direct one request per control-group account per
                                           checkpoint, one line each, writes nothing
    python3 scripts/probe.py --try-switches PROVIDER [PROVIDER ...]
                                           for each named control-group account and
                                           checkpoint, one short request with each
                                           known way of switching thinking off, one
                                           line each, writes nothing
    python3 scripts/probe.py --rehearsal   the whole daily run at once, without
                                           the waits between rounds, written to
                                           data/rehearsals/DATE-HHMM/
    python3 scripts/probe.py --offwindow weekend|random
                                           the daily procedure at another time,
                                           for research only (decision D28),
                                           written to data/offwindow/DATE-HHMM/.
                                           Never read by the assessor.

Each request has a total time limit (timeout_seconds in panel.json), as well as
a limit on any one wait for data (read_timeout_seconds), so a stalled or
trickling reply cannot hold the run open.

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


def fetch_listing(checkpoint, attempts=3, pause=5):
    """The venue's endpoint listing for one checkpoint, tried up to three times.

    A checkpoint whose listing cannot be read gets no targets that day, and the
    reason is recorded in its listing file; the other checkpoints are still probed.
    A missing listing (HTTP 404) is not retried."""
    fetched = utc_now()
    error = None
    for attempt in range(attempts):
        try:
            body = http_get_json(f"{OPENROUTER}/models/{checkpoint}/endpoints")
            return {"checkpoint": checkpoint, "fetched_utc": iso(fetched), "response": body}
        except urllib.error.HTTPError as err:
            error = f"HTTP {err.code}"
            if err.code == 404:
                break
        except Exception as err:  # network failure or unreadable reply
            error = f"{type(err).__name__}: {err}"
        if attempt < attempts - 1:
            time.sleep(pause * (attempt + 1))
    return {"checkpoint": checkpoint, "fetched_utc": iso(fetched), "response": None, "error": error}


def per_token(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def venue_targets(listing, accepted):
    """One target per provider: its lowest-priced endpoint at an accepted precision."""
    best = {}
    endpoints = (((listing.get("response") or {}).get("data") or {}).get("endpoints")) or []
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


def run_request(t, prompt_body, round_no, day, max_tokens, timeout, read_timeout=None):
    """One streamed request. Returns a raw record; never raises.

    timeout is the most the whole request may take, in seconds; read_timeout is
    the most any one wait for data may take. A request that runs out of time is
    stopped and recorded with the error "time limit", keeping what had arrived."""
    read_timeout = min(timeout, read_timeout or timeout)
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
        with urllib.request.urlopen(req, timeout=read_timeout) as resp:
            record["http_status"] = resp.status
            for raw in resp:
                if time.perf_counter() - t0 > timeout:
                    record["error"] = f"time limit: no complete reply within {timeout} seconds"
                    break
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
                    # The venue calls thinking text "reasoning"; providers bought direct
                    # usually call it "reasoning_content". Either way it is recorded.
                    thinking = delta.get("reasoning") or delta.get("reasoning_content")
                    if thinking:
                        chunk["reasoning"] = thinking
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


# The ways providers are known to accept a switch for thinking, tried in turn by
# --try-switches. The first is no switch at all, which is the default behaviour.
THINKING_SWITCHES = [
    {},
    {"enable_thinking": False},
    {"chat_template_kwargs": {"thinking": False}},
    {"chat_template_kwargs": {"enable_thinking": False}},
    {"chat_template_kwargs": {"thinking_mode": "chat"}},
    {"thinking": {"type": "disabled"}},
    {"reasoning_effort": "none"},
    {"reasoning": {"enabled": False}},
]


def thought(record):
    """True if the reply carried thinking, however the provider sent it."""
    u = record.get("usage") or {}
    return bool((u.get("completion_tokens_details") or {}).get("reasoning_tokens")
                or any(c.get("reasoning") for c in record["chunks"])
                or "<think>" in reply_text(record)[:200])


def try_switches(panel, names, prompt_body, day, timeout, read_timeout):
    accounts = [d for d in panel.get("direct", []) if d["provider"] in names]
    missing = sorted(set(names) - {d["provider"] for d in accounts})
    if missing or not names:
        print("Name one or more control-group accounts exactly as in panel.json: "
              + ", ".join(d["provider"] for d in panel.get("direct", [])))
        return 2
    for d in accounts:
        for checkpoint in panel["probe"]:
            if checkpoint not in d.get("models", {}):
                continue
            for switch in THINKING_SWITCHES:
                t = direct_targets({"direct": [dict(d, extra=switch)]}, checkpoint)[0]
                # 60 tokens is enough to see whether the reply starts with thinking or the answer.
                rec = run_request(t, prompt_body, 0, day, 60, timeout, read_timeout)
                label = json.dumps(switch, separators=(",", ":")) if switch else "no switch"
                if rec["error"]:
                    detail = rec.get("error_body")
                    detail = detail if isinstance(detail, str) else json.dumps(detail or "")
                    result = f"ERROR {rec['error']} {' '.join(detail.split())[:80]}"
                elif thought(rec):
                    result = "thinking YES"
                else:
                    lines = [ln.strip() for ln in reply_text(rec).splitlines() if ln.strip()]
                    result = "thinking no: " + ((lines[0] if lines else "(empty)")[:24])
                print(f"{d['provider']:<11} {t['model'][:34]:<34} {label:<48} {result}")
    return 0


def one_line(record):
    """One line per request, for --test-direct: enough to see that the model name,
    the key and the switch for thinking all work."""
    t = record["target"]
    u = record.get("usage") or {}
    head = f"{t['provider']:<11} {t.get('model') or t['checkpoint']:<36}"
    if record["error"]:
        detail = record.get("error_body")
        detail = detail if isinstance(detail, str) else json.dumps(detail or "")
        return f"{head} ERROR {record['error']} {' '.join(detail.split())[:160]}"
    lines = [ln.strip() for ln in reply_text(record).splitlines() if ln.strip()]
    thinking = thought(record)
    usage = f"in {u.get('prompt_tokens')} out {u.get('completion_tokens')}" if u else "NO TOKEN COUNTS"
    return (f"{head} OK {usage}, thinking {'YES' if thinking else 'no'}, finish {record['finish_reason']}, "
            f"first token {record['first_token_s']} s, first line: {(lines[0] if lines else '(empty)')[:28]}")


def main(argv):
    mode, offwindow_kind, direct_only = "daily", None, False
    if "--try-switches" in argv:
        names = argv[argv.index("--try-switches") + 1:]
        panel = load_json("panel.json")
        with open("prompt.txt") as f:
            prompt_body = f.read()
        return try_switches(panel, names, prompt_body, utc_now().strftime("%Y-%m-%d"),
                            int(panel.get("timeout_seconds", 120)), int(panel.get("read_timeout_seconds", 60)))
    if "--test-direct" in argv:
        mode, direct_only = "test", True
    elif "--test" in argv:
        mode = "test"
    elif "--rehearsal" in argv:
        mode = "rehearsal"
    elif "--offwindow" in argv:
        mode = "offwindow"
        i = argv.index("--offwindow")
        offwindow_kind = argv[i + 1] if i + 1 < len(argv) else None
        if offwindow_kind not in ("weekend", "random"):
            print("--offwindow needs a kind: weekend or random")
            return 2

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
    if mode == "daily" and start.weekday() >= 5 and not os.environ.get("PROBE_ANY_DAY"):
        print(f"{day} is a weekend day, so there is no window. Use --offwindow weekend.")
        return 0

    if mode == "daily":
        out_dir = os.path.join("data", "probes", day)
    elif mode == "rehearsal":
        out_dir = os.path.join("data", "rehearsals", start.strftime("%Y-%m-%d-%H%M"))
    elif mode == "offwindow":
        out_dir = os.path.join("data", "offwindow", start.strftime("%Y-%m-%d-%H%M"))
    else:
        out_dir = None
    if out_dir and os.path.exists(os.path.join(out_dir, "manifest.json")):
        print(f"{out_dir} already has a manifest; not overwriting.")
        return 0

    max_tokens = int(panel.get("max_output_tokens", 500))
    timeout = int(panel.get("timeout_seconds", 120))
    read_timeout = int(panel.get("read_timeout_seconds", 60))

    # 1. Listing snapshot and the day's panel.
    listings, targets = {}, []
    for checkpoint in panel["probe"]:
        accepted = accepted_precisions(candidates, checkpoint)
        listing = fetch_listing(checkpoint)
        listing["accepted_precisions"] = accepted
        listings[checkpoint] = listing
        found = venue_targets(listing, accepted)
        if mode == "test" and direct_only:
            targets += direct_targets(panel, checkpoint)
        elif mode == "test":
            wanted = panel.get("test_provider")
            pick = [t for t in found if t["provider"] == wanted] or found[:1]
            targets += pick
        else:
            targets += found + direct_targets(panel, checkpoint)
        if out_dir:
            write_json(os.path.join(out_dir, "listing", slug(checkpoint) + ".json"), listing)

    if mode == "test":
        if not targets:
            print("No control-group account in panel.json." if direct_only else
                  "No provider found at an accepted precision. Check panel.json and candidates.json.")
            return 1
        print(f"Prompt sha256: {prompt_sha256}\n")
        for t in targets:
            rec = run_request(t, prompt_body, 0, day, max_tokens, timeout, read_timeout)
            print(one_line(rec) if direct_only else summarise(rec) + "\n")
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
        rec = run_request(t, prompt_body, r, day, max_tokens, timeout, read_timeout)
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
        "offwindow_kind": offwindow_kind,
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
        "timeout_seconds": timeout,
        "read_timeout_seconds": read_timeout,
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
