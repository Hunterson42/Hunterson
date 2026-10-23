"""
Market data from OpenRouter's Data API, for the derived series and for
commentary (decision D38, rule 1.17).

The census says what is offered and the probe what it costs. This says how
much is bought: tokens by model each day, the share of them in requests that
call tools, tokens by length of request, traffic by task, the apps that buy,
the cost of an agent session, and benchmark scores. It is read through
OpenRouter's published Data API with the project's own key, and saved exactly
as received. What is read, and why it may be read, is in market_sources.json.

    python3 scripts/marketdata.py --slot morning   a reading, into data/market/DATE-HHMM/;
                                                   the runner takes one a day, after the census
    python3 scripts/marketdata.py                  a reading by hand (slot "manual")
    python3 scripts/marketdata.py --test           one request of each kind, printed,
                                                   nothing written
    python3 scripts/marketdata.py --backfill       once only: the history the API still
                                                   serves, from 1 January 2025
    python3 scripts/marketdata.py --report FOLDER  what a saved reading holds

What each reading holds.

- Every day: the daily token rankings (all requests, requests that call tools,
  and each length of request) for the last four completed days, and the share
  of traffic by task over the trailing seven days. The four days overlap from
  one reading to the next, so a missed day is filled by the next reading and
  any figure OpenRouter restates is caught.
- In the first reading of each week (Monday to Sunday, UTC): the top apps by
  tokens over the previous week, overall and in each subcategory; the cost of
  an agent session, every page; and the benchmark scores. The session costs,
  the benchmark scores and the task shares are served only as they stand now,
  so a reading not taken is lost for good. The rankings are served back to
  1 January 2025, and --backfill takes that history once, while it is served.

What it is not. Never an input to the assessment. OpenRouter is one venue;
its shares describe its own customers, not the whole market, and are labelled
so wherever they are used.

The rules it follows.

- A dataset is read only if market_sources.json enables its source and the key
  is set. The data is licensed under CC BY 4.0; the responses are still kept
  privately, as the census is, and only derived figures are published, with
  OpenRouter's citation and the as_of date the response gives.
- A reading is written once. It is assembled in a hidden folder and moved into
  place, with its manifest.json, only when every request has been tried, so a
  folder in data/market/ is either complete or absent. A folder is never reused.
- One "morning" reading a day. One backfill, ever.
- Requests are spaced to stay inside OpenRouter's limit of 30 a minute, and a
  reading stops early, recording the rest as not tried, if the service keeps
  refusing, so that a daily limit is never hammered.
- The key travels only in the request's Authorization header. Any copy of it
  that comes back in a response is replaced with [key] before anything is
  saved or printed.

Keys come from the environment, as the runner passes them, or else from
keys.env in RUNNER_HOME (default /root), so that --test can be run by hand.

Uses only the Python standard library.
"""
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.environ.get("MARKET_REPO") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(REPO, "market_sources.json")
BASE = os.path.join(REPO, "data", "market")
USER_AGENT = "hunterson-marketdata/1.0"
TIMEOUT = int(os.environ.get("MARKET_TIMEOUT", 60))
ATTEMPTS = 3
RETRY_PAUSE = float(os.environ.get("MARKET_RETRY_PAUSE", 10))
RECENT_DAYS = 4                 # completed days in each daily reading's window
STOP_AFTER_REFUSALS = 5         # requests refused in a row before a reading stops early
SLOTS = ("morning", "manual")


def utc_now():
    fixed = os.environ.get("MARKET_NOW")          # for the tests only
    if fixed:
        return dt.datetime.fromisoformat(fixed).replace(tzinfo=dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path):
    with open(path) as f:
        return json.load(f)


def read_keys_file(path):
    keys = {}
    try:
        with open(path) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:]
                name, value = line.split("=", 1)
                keys[name.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return keys


def load_keys(names):
    keys = {n: os.environ.get(n) for n in names if os.environ.get(n)}
    missing = [n for n in names if n not in keys]
    if missing:
        from_file = read_keys_file(os.path.join(os.environ.get("RUNNER_HOME", "/root"), "keys.env"))
        keys.update({n: from_file[n] for n in missing if from_file.get(n)})
    return keys


def script_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except Exception:
        return None


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def scrub(data, key):
    """Any copy of the key in a response is replaced before it is saved or printed."""
    if key and isinstance(data, bytes):
        return data.replace(key.encode(), b"[key]")
    if key and isinstance(data, str):
        return data.replace(key, "[key]")
    return data


# What to read --------------------------------------------------------------

def day(d):
    return d.strftime("%Y-%m-%d")


def window_for(dates, today):
    """(start_date, end_date) for a request; None leaves the server's default,
    the most recent completed UTC day."""
    if dates == "recent":
        return day(today - dt.timedelta(days=RECENT_DAYS)), None
    if dates == "last-week":
        monday = today - dt.timedelta(days=today.weekday())
        return day(monday - dt.timedelta(days=7)), day(monday - dt.timedelta(days=1))
    return None, None


def backfill_windows(kind, today, data_start):
    """The history still served: calendar years for the daily rankings (the API
    allows at most 366 days a request), calendar months for the app rankings.
    Ends with the last completed day or month before today."""
    yesterday = today - dt.timedelta(days=1)
    start = dt.date.fromisoformat(data_start)
    out = []
    if kind == "years":
        year = start.year
        while dt.date(year, 1, 1) <= yesterday:
            first = max(start, dt.date(year, 1, 1))
            last = dt.date(year, 12, 31)
            out.append((day(first), None if last >= yesterday else day(last)))
            year += 1
    elif kind == "months":
        first = dt.date(start.year, start.month, 1)
        while True:
            following = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
            last = following - dt.timedelta(days=1)
            if last > yesterday:
                break
            out.append((day(first), day(last)))
            first = following
    return out


def expand(dataset):
    """One request per value of the dataset's "each" parameter, or one request."""
    params = dict(dataset.get("params") or {})
    each = dataset.get("each") or {}
    if not each:
        return [(dataset["name"], params)]
    (param, values), = each.items()
    return [(f"{dataset['name']}-{v}", dict(params, **{param: v})) for v in values]


def plan_reading(config, today, kinds, sample=False):
    """Every request a reading makes: (source, dataset, request name, params, window)."""
    plan = []
    for s in config["sources"]:
        for ds in s["datasets"]:
            if "backfill" in kinds:
                if not ds.get("backfill"):
                    continue
                for name, params in expand(ds):
                    for start, end in backfill_windows(ds["backfill"], today, config["data_start"]):
                        plan.append((s, ds, f"{name}-{start}", params, (start, end)))
                continue
            every = ds.get("every", "day")
            if (every == "day" and "daily" not in kinds) or (every == "week" and "weekly" not in kinds):
                continue
            requests = expand(ds)
            if sample:
                requests = requests[:1]
            for name, params in requests:
                plan.append((s, ds, name, params, window_for(ds.get("dates"), today)))
    return plan


# Reading -------------------------------------------------------------------

def fetch(url, key):
    """(HTTP status or None, body bytes, error text or None). Retries a busy or
    broken service; never retries a refusal of the key or of the request."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    error = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.status, scrub(resp.read(), key), None
        except urllib.error.HTTPError as e:
            body = scrub(e.read() or b"", key)
            if e.code in (429, 500, 502, 503, 504) and attempt < ATTEMPTS:
                time.sleep(RETRY_PAUSE * attempt)
                continue
            return e.code, body, f"HTTP {e.code}"
        except Exception as e:            # network, time-out, TLS
            error = type(e).__name__
            if attempt < ATTEMPTS:
                time.sleep(RETRY_PAUSE * attempt)
    return None, b"", error


def build_url(source, dataset, params, window, offset=None):
    query = dict(params)
    start, end = window
    if start:
        query["start_date"] = start
    if end:
        query["end_date"] = end
    if offset:
        query["offset"] = offset
    url = source["base_url"].rstrip("/") + dataset["path"]
    return url + ("?" + urllib.parse.urlencode(query) if query else "")


def rows_in(obj):
    data = obj.get("data") if isinstance(obj, dict) else None
    return len(data) if isinstance(data, list) else None


class Pacer:
    """Keeps requests at least `gap` seconds apart, inside the per-minute limit."""

    def __init__(self, gap):
        self.gap, self.last = gap, None

    def wait(self):
        if self.last is not None:
            pause = self.gap - (time.monotonic() - self.last)
            if pause > 0:
                time.sleep(pause)
        self.last = time.monotonic()


def read_request(source, dataset, name, params, window, key, folder, pacer, first_page_only=False):
    """Reads one request, following offset pages if the dataset has them, and
    saves each page raw. Returns its manifest entry."""
    entry = {"source": source["id"], "dataset": dataset["path"], "request": name,
             "window": {"start_date": window[0], "end_date": window[1]},
             "started_utc": iso(utc_now()), "pages": []}
    pages = dataset.get("pages") or {}
    limit = (dataset.get("params") or {}).get("limit")
    offset = 0
    while True:
        url = build_url(source, dataset, params, window, offset)
        pacer.wait()
        status, body, error = fetch(url, key)
        try:
            parsed = json.loads(body.decode("utf-8")) if body else None
            ext = "json"
        except (UnicodeDecodeError, ValueError):
            parsed, ext = None, "txt"
        file = name + (f"-p{offset // pages['offset_step'] + 1}" if offset else "") + f".{ext}"
        if folder and body:
            with open(os.path.join(folder, file), "wb") as f:
                f.write(body)
        rows = rows_in(parsed) if not error else None
        entry["pages"].append({"url": url, "file": file if body else None, "http_status": status,
                               "bytes": len(body), "sha256": sha256_bytes(body) if body else None,
                               "rows": rows, "error": error})
        if error or first_page_only or not pages or rows is None or not limit or rows < limit:
            break
        offset += pages["offset_step"]
        if offset > pages["max_offset"]:
            break
    errors = [p["error"] for p in entry["pages"] if p["error"]]
    entry["status"] = "failed" if errors else "ok"
    if errors:
        entry["error"] = errors[0]
    entry["finished_utc"] = iso(utc_now())
    return entry


def clear_stale_partials(age=3600):
    """A reading stopped part way leaves a hidden folder behind. It was never a
    reading, so it is removed once it is an hour old."""
    if not os.path.isdir(BASE):
        return
    for name in os.listdir(BASE):
        path = os.path.join(BASE, name)
        if name.startswith(".partial-") and os.path.isdir(path) and time.time() - os.path.getmtime(path) > age:
            shutil.rmtree(path, ignore_errors=True)


def saved_manifests():
    out = []
    if not os.path.isdir(BASE):
        return out
    for name in sorted(os.listdir(BASE)):
        if name.startswith("."):
            continue
        try:
            out.append((name, load_json(os.path.join(BASE, name, "manifest.json"))))
        except (OSError, ValueError):
            continue
    return out


def weekly_taken(today):
    """Whether a reading this week (Monday to Sunday, UTC) already holds the
    weekly datasets."""
    monday = today - dt.timedelta(days=today.weekday())
    for name, m in saved_manifests():
        try:
            taken = dt.date.fromisoformat(name[:10])
        except ValueError:
            continue
        if "weekly" in (m.get("kinds") or []) and monday <= taken <= monday + dt.timedelta(days=6):
            return True
    return False


def take_reading(slot, test=False, backfill=False):
    config = load_json(SOURCES)
    now = utc_now()
    today = now.date()
    name = now.strftime("%Y-%m-%d-%H%M")
    sources = [s for s in config["sources"] if s.get("enabled") or test]
    keys = load_keys([s["key_env"] for s in sources])
    readable = [s for s in sources if keys.get(s["key_env"])]
    if not readable:
        print("No source can be read: none is both enabled and has a key in keys.env.")
        for s in config["sources"]:
            print(f"  {s['provider']}: " + ("not enabled" if not s.get("enabled") else f"no {s['key_env']}"))
        return 0 if test else 1
    config = dict(config, sources=readable)

    if backfill:
        kinds = ["backfill"]
    elif test:
        kinds = ["daily", "weekly"]
    else:
        kinds = ["daily"] + ([] if weekly_taken(today) else ["weekly"])
    if not test:
        clear_stale_partials()
        if slot == "morning" and any(n.startswith(day(today)) and m.get("slot") == "morning"
                                     for n, m in saved_manifests()):
            print(f"The morning reading for {day(today)} is already in data/market; nothing to take.")
            return 0
        if os.path.exists(os.path.join(BASE, name)):
            print(f"data/market/{name} already exists; a reading is never overwritten.")
            return 0

    plan = plan_reading(config, today, kinds, sample=test)
    if backfill:
        # Taken once. A second --backfill takes only what earlier ones did not get.
        done = {e["request"] for _, m in saved_manifests() if "backfill" in (m.get("kinds") or [])
                for e in m["requests"] if e.get("status") == "ok"}
        if done:
            plan = [p for p in plan if p[2] not in done]
            if not plan:
                print("The backfill is complete; nothing is left to take.")
                return 0
            print(f"An earlier backfill got {len(done)} requests; taking the {len(plan)} it did not.")
        print(f"Backfill: {len(plan)} requests or more, about {len(plan) * 3 // 60 + 1} minutes.")
    if test:
        folder = tempfile.mkdtemp(prefix="market-test-")          # outside the repository; removed at the end
    else:
        os.makedirs(BASE, exist_ok=True)
        folder = tempfile.mkdtemp(prefix=".partial-", dir=BASE)
    manifest = {
        "schema": 1, "reading": name, "slot": "backfill" if backfill else slot, "kinds": kinds,
        "started_utc": iso(now), "trigger": os.environ.get("MARKET_TRIGGER") or "manual",
        "script_commit": script_commit(), "sources_sha256": sha256_bytes(open(SOURCES, "rb").read()),
        "requests": [],
    }
    pacer = Pacer(float(os.environ.get("MARKET_PACE", readable[0].get("pace_seconds", 2.5))))
    refused, stopped = 0, None
    try:
        for s, ds, req_name, params, window in plan:
            if stopped:
                manifest["requests"].append({"source": s["id"], "dataset": ds["path"], "request": req_name,
                                             "window": {"start_date": window[0], "end_date": window[1]},
                                             "status": "not tried: " + stopped})
                continue
            entry = read_request(s, ds, req_name, params, window, keys[s["key_env"]], folder, pacer,
                                 first_page_only=test)
            manifest["requests"].append(entry)
            if test:
                describe_for_test(entry, folder)
            statuses = [p["http_status"] for p in entry["pages"]]
            refused = refused + 1 if entry["status"] == "failed" and (statuses[-1] in (401, 403, 429, None)) else 0
            if refused >= STOP_AFTER_REFUSALS:
                stopped = f"the reading stopped after {refused} refusals in a row"
        manifest["finished_utc"] = iso(utc_now())
        ok = [e for e in manifest["requests"] if e.get("status") == "ok"]
        if test:
            print(f"\n{len(ok)} of {len(manifest['requests'])} requests answered. Nothing was written.")
            return 0
        with open(os.path.join(folder, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)
            f.write("\n")
        os.chmod(folder, 0o755)          # mkdtemp makes it private to its owner
        os.rename(folder, os.path.join(BASE, name))
        folder = None
    finally:
        if folder and os.path.isdir(folder):
            shutil.rmtree(folder)
    failed = [e for e in manifest["requests"] if e.get("status") != "ok"]
    for e in failed[:20]:
        print(f"{e['request']}: {e.get('error') or e['status']}")
    if len(failed) > 20:
        print(f"... and {len(failed) - 20} more not answered")
    print(f"Market data: data/market/{name}, {', '.join(kinds)}, "
          f"{len(ok)} of {len(manifest['requests'])} requests answered.")
    return 0 if ok and not stopped else 1


# Showing what came back ----------------------------------------------------

def shape(obj, depth=0):
    """The field names of a reply, two levels down, so a changed format can be
    seen at a glance. Values are not shown."""
    if isinstance(obj, dict):
        inner = ", ".join(f"{k}" + (f": {shape(v, depth + 1)}" if depth < 1 and isinstance(v, (dict, list)) else "")
                          for k, v in list(obj.items())[:12])
        return "{" + inner + "}"
    if isinstance(obj, list):
        return f"[{len(obj)} x {shape(obj[0], depth + 1)}]" if obj else "[]"
    return type(obj).__name__


def describe_for_test(entry, folder):
    """What --test prints for one request: the status, the shape of the reply,
    and one line of what it says."""
    print(f"\n{entry['request']}")
    for p in entry["pages"]:
        print(f"  {p['url']}")
        print(f"  HTTP {p['http_status']}, {p['bytes']} bytes"
              + (f", {p['rows']} rows" if p["rows"] is not None else "")
              + (f", {p['error']}" if p["error"] else ""))
        if not p.get("file"):
            continue
        path = os.path.join(folder, p["file"])
        if not p["file"].endswith(".json"):
            with open(path, "rb") as f:
                print("  reply, not JSON: " + f.read(300).decode("utf-8", "replace").replace("\n", " "))
            continue
        obj = load_json(path)
        print("  shape: " + shape(obj)[:600])
        if p["error"]:
            print("  reply: " + json.dumps(obj)[:300])
            continue
        try:
            for line in SUMMARIES.get(summary_kind(entry["dataset"]), lambda o: [])(obj)[:4]:
                print("  " + line)
        except Exception as ex:
            print(f"  PROBLEM: the reply could not be read: {type(ex).__name__}: {ex}")


def tokens(value):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "-"
    for size, unit in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if n >= size:
            return f"{n / size:.2f}{unit}"
    return f"{n:,.0f}"


def pct(x):
    return f"{100 * x:.1f}%" if isinstance(x, (int, float)) else "-"


def as_of(obj):
    meta = (obj.get("meta") if isinstance(obj, dict) else None) or {}
    data = obj.get("data") if isinstance(obj, dict) else None
    return meta.get("as_of") or (data.get("as_of") if isinstance(data, dict) else None) or "-"


def summary_kind(path):
    return {"/datasets/rankings-daily": "rankings", "/classifications/task": "tasks",
            "/datasets/app-rankings": "apps", "/datasets/session-cost": "session-cost",
            "/benchmarks": "benchmarks"}.get(path)


def by_day(obj):
    days = {}
    for r in obj["data"]:
        days.setdefault(r["date"], []).append(r)
    return days


def sum_tokens(rows):
    return sum(float(r["total_tokens"]) for r in rows)


def summary_rankings(obj):
    days = by_day(obj)
    if not days:
        return [f"no days in the window (as of {as_of(obj)})"]
    latest = max(days)
    rows = days[latest]
    total = sum_tokens(rows)
    top = sorted((r for r in rows if r["model_permaslug"] != "other"), key=lambda r: -float(r["total_tokens"]))[:3]
    lines = [f"{len(days)} days to {latest}; {latest}: {tokens(total)} tokens, {len(rows)} rows (as of {as_of(obj)})"]
    lines.append("top: " + "; ".join(f"{r['model_permaslug']} {pct(float(r['total_tokens']) / total)}"
                                      for r in top) if total else "top: none")
    return lines


def summary_tasks(obj):
    data = obj["data"]
    macro = sorted(data.get("macro_categories") or [], key=lambda m: -(m.get("token_share") or 0))
    return [f"{len(data.get('classifications') or [])} classifications over {data.get('window_days')} days "
            f"(as of {as_of(obj)})",
            "token share: " + "; ".join(f"{m.get('label') or m.get('key')} {pct(m.get('token_share'))}"
                                        for m in macro)]


def summary_apps(obj):
    rows = obj["data"]
    meta = obj.get("meta") or {}
    top = rows[:3]
    return [f"{len(rows)} apps, {meta.get('start_date')} to {meta.get('end_date')}, "
            f"{tokens(sum(float(r['total_tokens']) for r in rows))} tokens in all",
            "top: " + "; ".join(f"{r.get('rank')}. {r.get('app_name')} {tokens(r.get('total_tokens'))}" for r in top)]


def summary_session_cost(obj):
    rows = obj["data"]
    meta = obj.get("meta") or {}
    by_turns = {}
    for r in rows:
        by_turns.setdefault(r.get("turn_range"), []).append(float(r["median_session_cost_usd"]))
    def median(v):
        v = sorted(v)
        return (v[len(v) // 2] + v[(len(v) - 1) // 2]) / 2
    def first_turn(k):
        head = str(k).split("-")[0]
        return int(head) if head.isdigit() else 10 ** 6
    return [f"{len(rows):,} cells, {meta.get('window_days')} days to {meta.get('window_end_date')} "
            f"(as of {as_of(obj)})",
            "median of the medians: " + "; ".join(f"{k} ${median(v):,.2f}" for k, v in sorted(
                by_turns.items(), key=lambda kv: first_turn(kv[0])))]


def summary_benchmarks(obj):
    rows = obj["data"]
    sources = {}
    for r in rows:
        sources[r.get("source")] = sources.get(r.get("source"), 0) + 1
    return [f"{len(rows)} items (as of {as_of(obj)}): " + "; ".join(f"{k} {v}" for k, v in sorted(
        sources.items(), key=lambda kv: str(kv[0])))]


SUMMARIES = {"rankings": summary_rankings, "tasks": summary_tasks, "apps": summary_apps,
             "session-cost": summary_session_cost, "benchmarks": summary_benchmarks}


def load_entry(folder, entry):
    """The reply to one request, every page joined into one."""
    merged = None
    for p in entry["pages"]:
        if not (p.get("file") or "").endswith(".json"):
            raise ValueError(f"{p.get('file')} is not JSON")
        obj = load_json(os.path.join(folder, p["file"]))
        if merged is None:
            merged = obj
        else:
            merged["data"] = merged["data"] + obj["data"]
    return merged


def latest_total(obj):
    days = by_day(obj)
    latest = max(days)
    return latest, sum_tokens(days[latest])


def report(folder):
    """One line per kind of data a saved reading holds, so that a reading can be
    checked at a glance. Derived; never written."""
    if not os.path.isabs(folder) and not os.path.isdir(folder):
        folder = os.path.join(BASE, folder)
    manifest = load_json(os.path.join(folder, "manifest.json"))
    reqs = manifest["requests"]
    ok = [e for e in reqs if e.get("status") == "ok"]
    print(f"Market data in {manifest['reading']}: {manifest['slot']}, {', '.join(manifest['kinds'])}; "
          f"{len(ok)} of {len(reqs)} requests answered")
    problems = [f"{e['request']}: {e.get('error') or e['status']}" for e in reqs if e.get("status") != "ok"]
    if manifest["slot"] == "backfill":
        windows = sorted({e["window"]["start_date"] for e in ok if e["window"]["start_date"]})
        print(f"Backfill windows from {windows[0] if windows else '-'} to {windows[-1] if windows else '-'}")
    else:
        replies = {}
        for e in ok:
            try:
                replies[e["request"]] = (e, load_entry(folder, e))
            except Exception as ex:            # a changed format is reported, never fatal
                problems.append(f"{e['pages'][0].get('file')}: {type(ex).__name__}: {ex}")
        grouped = {"rankings-context-": [], "apps-": []}
        for name, (e, obj) in replies.items():
            prefix = next((g for g in grouped if name.startswith(g)), None)
            try:
                if prefix:
                    grouped[prefix].append((name[len(prefix):], obj))
                    continue
                lines = SUMMARIES.get(summary_kind(e["dataset"]), lambda o: [])(obj)
                if name == "rankings-tool-calling" and "rankings" in replies:
                    day_, tools = latest_total(obj)
                    all_days = by_day(replies["rankings"][1])
                    if day_ in all_days:
                        lines.append(f"{pct(tools / sum_tokens(all_days[day_]))} of all tokens on {day_}")
                pages = f", {len(e['pages'])} pages" if len(e["pages"]) > 1 else ""
                print(f"{name}{pages}: " + " | ".join(lines))
            except Exception as ex:
                problems.append(f"{e['pages'][0]['file']}: {type(ex).__name__}: {ex}")
        try:
            if grouped["rankings-context-"]:
                totals = [(b, *latest_total(obj)) for b, obj in grouped["rankings-context-"]]
                whole = sum(t for _, _, t in totals)
                print(f"tokens by length of request, {max(d for _, d, _ in totals)}: "
                      + "; ".join(f"{b} {pct(t / whole) if whole else '-'}" for b, _, t in totals))
            if grouped["apps-"]:
                subs = sorted(((sub, sum(float(r["total_tokens"]) for r in obj["data"]), len(obj["data"]))
                               for sub, obj in grouped["apps-"]), key=lambda x: -x[1])
                print("apps by subcategory, tokens in the listed apps: "
                      + "; ".join(f"{sub} {tokens(t)} ({n})" for sub, t, n in subs))
        except Exception as ex:
            problems.append(f"grouped lines: {type(ex).__name__}: {ex}")
    for p in problems[:20]:
        print("PROBLEM: " + p)
    if len(problems) > 20:
        print(f"PROBLEM: ... and {len(problems) - 20} more requests not answered")
    return 1 if problems else 0


def main(argv):
    if "--report" in argv:
        i = argv.index("--report")
        if i + 1 >= len(argv):
            print(__doc__)
            return 2
        return report(argv[i + 1])
    if "--test" in argv:
        return take_reading("manual", test=True)
    if "--backfill" in argv:
        return take_reading("manual", backfill=True)
    slot = "manual"
    if "--slot" in argv:
        i = argv.index("--slot")
        slot = argv[i + 1] if i + 1 < len(argv) else ""
        if slot not in SLOTS:
            print(f"--slot must be one of {', '.join(SLOTS)}")
            return 2
    return take_reading(slot)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
