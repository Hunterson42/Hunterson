"""
GPU-hour prices, for the derived series (decision D36, rule 1.16).

Reads each GPU cloud's own price list through that provider's customer API,
with the project's own key, and saves the responses exactly as received. The
sources, and the reasons each may be read, are in gpu_sources.json.

    python3 scripts/gpuprices.py --slot morning    a reading, into data/gpu/DATE-HHMM/;
    python3 scripts/gpuprices.py --slot window     the runner takes one of each a day,
                                                   after the census and after the window
    python3 scripts/gpuprices.py                   a reading by hand (slot "manual")
    python3 scripts/gpuprices.py --test            reads every source that has a key,
                                                   prints what came back, writes nothing
    python3 scripts/gpuprices.py --report FOLDER   the GPU prices a saved reading holds,
                                                   for the GPUs of interest; add --all
                                                   for every GPU

Why it exists. The derived series sets the price of the daily test job beside
what a GPU costs to rent: break-even jobs per GPU-hour, and the share of the
hour a GPU must be busy to pay its rent. A history of GPU-hour prices from the
first day of the assessment cannot be collected later, so collection starts
before the series is published.

What it is not. Never an input to the assessment. Never published as a GPU
price index: Silicon Data and Ornn publish those, and this is a small panel of
list prices, labelled as such.

The rules it follows.

- A source is read only if gpu_sources.json enables it and its key is set.
  --test also tries a source that is not enabled, if its key is set, so that an
  address can be confirmed before the source is enabled; it writes nothing.
- A reading is written once. It is assembled in a hidden folder and moved into
  place, with its manifest.json, only when every source has been tried, so a
  folder in data/gpu/ is either complete or absent. A folder is never reused.
- One reading per slot per day. The runner's "morning" reading comes after the
  census, at about 06:20 UTC, which is night in the United States; its
  "window" reading comes after the probe, at about 14:40 UTC, morning in the
  United States. Two readings a day show whether stock levels differ between
  the two.
- A source that fails is recorded with the reason, and the others go on.
- Keys travel only in the request's Authorization header. Any copy of a key
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
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.environ.get("GPU_REPO") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.path.join(REPO, "gpu_sources.json")
BASE = os.path.join(REPO, "data", "gpu")
USER_AGENT = "hunterson-gpuprices/1.0"
TIMEOUT = int(os.environ.get("GPU_TIMEOUT", 60))
ATTEMPTS = 3
RETRY_PAUSE = float(os.environ.get("GPU_RETRY_PAUSE", 5))
MAX_PAGES = 20
SLOTS = ("morning", "window", "manual")

FAMILIES = [
    ("GB300", r"GB\s*300"), ("GB200", r"GB\s*200"), ("B300", r"(?<!G)B\s*300"),
    ("B200", r"(?<!G)B\s*200"), ("H200", r"H\s*200"), ("H100", r"H\s*100"),
    ("H800", r"H\s*800"), ("H20", r"H\s*20(?!\d)"), ("A100", r"A\s*100"), ("A800", r"A\s*800"),
    ("L40S", r"L\s*40\s*S"), ("MI355X", r"MI\s*355"), ("MI325X", r"MI\s*325"),
    ("MI300X", r"MI\s*300"), ("RTX PRO 6000", r"RTX\s*PRO\s*6000"),
    ("RTX 5090", r"RTX\s*5090"), ("RTX 4090", r"RTX\s*4090"),
]


def utc_now():
    fixed = os.environ.get("GPU_NOW")          # for the tests only
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


# Reading -------------------------------------------------------------------

def fetch(url, key):
    """(HTTP status or None, body bytes, error text or None). Retries a busy or
    broken service; never retries a refusal."""
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


def next_cursor(obj):
    if not isinstance(obj, dict):
        return None
    for holder in (obj, obj.get("pagination"), obj.get("page_info"), obj.get("meta")):
        if isinstance(holder, dict):
            for name in ("next_cursor", "nextCursor", "next_page_token"):
                value = holder.get(name)
                if isinstance(value, str) and value:
                    return value
    return None


def with_cursor(url, cursor):
    return url + ("&" if "?" in url else "?") + "cursor=" + urllib.parse.quote(cursor, safe="")


def read_request(source, request, key, folder):
    """Reads one request, following pages if asked, and saves each page raw.
    Returns its manifest entry."""
    entry = {"source": source["id"], "provider": source["provider"], "request": request["name"],
             "url": request["url"], "started_utc": iso(utc_now()), "pages": []}
    url, seen = request["url"], set()
    for page in range(1, MAX_PAGES + 1):
        status, body, error = fetch(url, key)
        try:
            parsed = json.loads(body.decode("utf-8")) if body else None
            ext = "json"
        except (UnicodeDecodeError, ValueError):
            parsed, ext = None, "txt"
        name = f"{source['id']}-{request['name']}" + (f"-p{page}" if page > 1 else "") + f".{ext}"
        if folder and body:
            with open(os.path.join(folder, name), "wb") as f:
                f.write(body)
        entry["pages"].append({"file": name if body else None, "http_status": status, "bytes": len(body),
                               "sha256": sha256_bytes(body) if body else None, "error": error})
        if error or request.get("paginate") != "cursor":
            break
        cursor = next_cursor(parsed)
        if not cursor or cursor in seen:
            break
        seen.add(cursor)
        url = with_cursor(request["url"], cursor)
    errors = [p["error"] for p in entry["pages"] if p["error"]]
    entry["status"] = "failed" if errors else "ok"
    if errors:
        entry["error"] = errors[0]
    entry["finished_utc"] = iso(utc_now())
    return entry


def clear_stale_partials(age=3600):
    """A reading stopped part way, by a time limit or a restart, leaves a hidden
    folder behind. It was never a reading, so it is removed once it is an hour old."""
    if not os.path.isdir(BASE):
        return
    for name in os.listdir(BASE):
        path = os.path.join(BASE, name)
        if name.startswith(".partial-") and os.path.isdir(path) and time.time() - os.path.getmtime(path) > age:
            shutil.rmtree(path, ignore_errors=True)


def todays_slots(day):
    taken = set()
    if not os.path.isdir(BASE):
        return taken
    for name in os.listdir(BASE):
        if not name.startswith(day + "-"):
            continue
        try:
            taken.add(load_json(os.path.join(BASE, name, "manifest.json")).get("slot"))
        except (OSError, ValueError):
            continue
    return taken


def take_reading(slot, test=False):
    config = load_json(SOURCES)
    sources = config["sources"]
    keys = load_keys([s["key_env"] for s in sources if s.get("key_env")])
    now = utc_now()
    day, name = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d-%H%M")

    if not test:
        clear_stale_partials()
        if slot != "manual" and slot in todays_slots(day):
            print(f"The {slot} reading for {day} is already in data/gpu; nothing to take.")
            return 0
        if os.path.exists(os.path.join(BASE, name)):
            print(f"data/gpu/{name} already exists; a reading is never overwritten.")
            return 0

    plan = []
    for s in sources:
        key = keys.get(s.get("key_env"))
        if not key:
            plan.append((s, None, "skipped: no key"))
        elif not s.get("enabled") and not test:
            plan.append((s, None, "skipped: not enabled"))
        else:
            plan.append((s, key, None))
    if not any(key for _, key, _ in plan):
        print("No source can be read: none is both enabled and has a key in keys.env.")
        for s, _, why in plan:
            print(f"  {s['provider']}: {why}")
        return 0 if test else 1

    if test:
        folder = tempfile.mkdtemp(prefix="gpu-test-")          # outside the repository; removed at the end
    else:
        os.makedirs(BASE, exist_ok=True)
        folder = tempfile.mkdtemp(prefix=".partial-", dir=BASE)
    manifest = {
        "schema": 1, "reading": name, "slot": slot, "started_utc": iso(now),
        "trigger": os.environ.get("GPU_TRIGGER") or "manual", "script_commit": script_commit(),
        "sources_sha256": sha256_bytes(open(SOURCES, "rb").read()), "requests": [],
    }
    try:
        for s, key, why in plan:
            if not key:
                for r in s["requests"]:
                    manifest["requests"].append({"source": s["id"], "provider": s["provider"],
                                                 "request": r["name"], "url": r["url"], "status": why})
                continue
            for r in s["requests"]:
                entry = read_request(s, r, key, folder)
                if test and not s.get("enabled"):
                    entry["note"] = "not enabled; tried for --test only"
                manifest["requests"].append(entry)
                if test:
                    describe_for_test(s, r, entry, folder)
        manifest["finished_utc"] = iso(utc_now())
        ok = [e for e in manifest["requests"] if e.get("status") == "ok"]
        if test:
            for s, key, why in plan:
                if not key:
                    print(f"\n{s['provider']}: {why}")
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
    for e in manifest["requests"]:
        detail = e.get("error") or e["status"]
        print(f"{e['provider']} {e['request']}: {detail}")
    print(f"GPU prices: data/gpu/{name}, {len(ok)} of {len(manifest['requests'])} requests answered.")
    tried = [e for e in manifest["requests"] if e["status"] in ("ok", "failed")]
    return 0 if ok or not tried else 1


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


def describe_for_test(source, request, entry, folder):
    """What --test prints for one request: the status, the shape of the reply,
    and the prices the parser finds in it for the GPUs of interest. The key was
    removed from the reply before it was saved, so it cannot be printed."""
    print(f"\n{source['provider']} {request['name']}" + (" (not enabled)" if not source.get("enabled") else ""))
    print(f"  {request['url']}")
    parser = PARSERS.get(source.get("parser"))
    interest = set(load_json(SOURCES).get("gpus_of_interest") or [])
    for p in entry["pages"]:
        print(f"  HTTP {p['http_status']}, {p['bytes']} bytes" + (f", {p['error']}" if p["error"] else ""))
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
            rows = [r for r in parser(obj, request["name"]) if family(r["name"]) in interest] if parser else []
        except Exception as ex:
            print(f"  the parser failed: {type(ex).__name__}: {ex}")
            continue
        for r in rows[:12]:
            print(f"  {family(r['name']):6} on demand {money(r['on_demand']):>8}  spot {money(r['spot']):>8}  "
                  + (f"12 months {money(r['term_12m'])}  " if r.get("term_12m") else "")
                  + f"stock {r['availability'] or '-'}  ({r['name']}, {r['gpus']} GPU, unit {r.get('unit')})")
            if implausible(r):
                print("  PROBLEM: " + implausible(r))
        if parser and not rows:
            print("  no H100, H200 or B200 prices found in this reply")


# Interpreting a reading -----------------------------------------------------

def family(name):
    text = (name or "").upper()
    for fam, pattern in FAMILIES:
        if re.search(pattern, text):
            return fam
    return None


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Novita states its prices in hundred-thousandths of a dollar: its H100 SXM's
# 339000 on demand and 170000 spot are $3.39 and $1.70 an hour, the prices on
# its public page on 23 October 2026. The reply's "precision" field, 10, is not
# the number of decimal places the documentation says, so it is not used; a
# price outside PLAUSIBLE is reported as a problem, in case the scale changes.
NOVITA_DIVISOR = 100_000
HOURS_PER_MONTH = 730          # the hours in a month, as CME's compute futures count them


def parse_novita(obj, request):
    rows = []
    for p in (obj or {}).get("data") or []:
        gpu = ((p.get("resource_spec") or {}).get("gpu")) or {}
        if not gpu:
            continue
        pricing = p.get("pricing") or {}

        def price(kind):
            v = num((pricing.get(kind) or {}).get("final_price"))
            return v / NOVITA_DIVISOR if v is not None else None
        terms = {}
        for t in pricing.get("prepaid") or []:
            months, v = t.get("duration_months"), num(t.get("final_price"))
            if isinstance(months, int) and v is not None:
                terms[months] = v / NOVITA_DIVISOR / HOURS_PER_MONTH     # a monthly price, as an hourly rate
        rows.append({"name": gpu.get("name") or p.get("name"), "gpus": 1,
                     "on_demand": price("postpaid"), "spot": price("spot"),
                     "term_1m": terms.get(1), "term_12m": terms.get(12),
                     "availability": p.get("inventory_state"), "unit": "per_hour",
                     "note": "per GPU-hour; prepaid months at 730 hours"})
    return rows


def parse_deepinfra(obj, request):
    rows = []
    for g in (obj or {}).get("gpus") or []:
        config = str(g.get("gpu_config") or "")
        m = re.match(r"\s*(\d+)\s*[xX]", config)
        count = int(m.group(1)) if m else 1
        total = num(g.get("usd_per_hour"))
        rows.append({"name": config, "gpus": count, "on_demand": total / count if total is not None else None,
                     "spot": None, "availability": "available" if g.get("available") else "not available",
                     "unit": "per_hour", "note": "configuration price divided by its GPUs" if count > 1 else ""})
    return rows


def parse_runpod(obj, request):
    rows = []
    for g in (obj or {}).get("gpus") or []:
        price = g.get("price") or {}
        cloud = "secure" if request == "secure" else "community"
        rows.append({"name": g.get("name") or g.get("id"), "gpus": 1, "on_demand": num(price.get(cloud)),
                     "spot": None, "availability": g.get("availability"), "unit": "per_hour",
                     "note": f"{cloud} cloud"})
    return rows


def parse_lambda(obj, request):
    rows = []
    data = (obj or {}).get("data") or {}
    for key, item in (data.items() if isinstance(data, dict) else []):
        it = (item or {}).get("instance_type") or {}
        gpus = ((it.get("specs") or {}).get("gpus")) or 1
        cents = num(it.get("price_cents_per_hour"))
        regions = (item or {}).get("regions_with_capacity_available")
        rows.append({"name": it.get("gpu_description") or it.get("name") or key, "gpus": gpus,
                     "on_demand": cents / 100 / gpus if cents is not None else None, "spot": None,
                     "availability": f"{len(regions)} regions with capacity" if isinstance(regions, list) else None,
                     "unit": "per_hour", "note": "instance price divided by its GPUs" if gpus > 1 else ""})
    return rows


PARSERS = {"novita": parse_novita, "deepinfra": parse_deepinfra, "runpod": parse_runpod, "lambda": parse_lambda}


def rows_from_reading(folder):
    """Every price row a saved reading holds, with its source. Derived; never written."""
    manifest = load_json(os.path.join(folder, "manifest.json"))
    parsers = {s["id"]: s.get("parser") for s in load_json(SOURCES)["sources"]}
    rows, problems = [], []
    for e in manifest["requests"]:
        if e.get("status") != "ok":
            continue
        parser = PARSERS.get(parsers.get(e["source"]))
        for p in e.get("pages", []):
            if not p.get("file") or not p["file"].endswith(".json") or not parser:
                continue
            try:
                obj = load_json(os.path.join(folder, p["file"]))
                for r in parser(obj, e["request"]):
                    r.update({"provider": e["provider"], "source": e["source"], "family": family(r["name"])})
                    rows.append(r)
                    odd = implausible(r)
                    if odd:
                        problems.append(f"{p['file']}: {r['name']}: {odd}")
            except Exception as ex:            # a changed format is reported, never fatal
                problems.append(f"{p['file']}: {type(ex).__name__}: {ex}")
    return rows, problems


PLAUSIBLE = (0.02, 100.0)      # US dollars per GPU-hour; anything outside means a misread scale


def implausible(row):
    """A price no GPU rents for means the reply's scale was misread: Novita's
    "precision" field once turned $3.39 into $0.00."""
    for field in ("on_demand", "spot", "term_1m", "term_12m"):
        v = row.get(field)
        if isinstance(v, (int, float)) and not PLAUSIBLE[0] <= v <= PLAUSIBLE[1]:
            return f"{field.replace('_', ' ')} of ${v:.6f} per GPU-hour is outside ${PLAUSIBLE[0]} to " \
                   f"${PLAUSIBLE[1]:.0f}; the reply's format may have changed"
    return None


def money(v):
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "-"


def report(folder, show_all=False):
    if not os.path.isabs(folder) and not os.path.isdir(folder):
        folder = os.path.join(BASE, folder)
    rows, problems = rows_from_reading(folder)
    interest = set(load_json(SOURCES).get("gpus_of_interest") or [])
    if not show_all:
        rows = [r for r in rows if r["family"] in interest]
    rows.sort(key=lambda r: (r["family"] or "~", r["provider"], r["on_demand"] or 0))
    print(f"GPU prices in {os.path.basename(folder.rstrip('/'))}, US dollars per GPU-hour"
          + ("" if show_all else f", {', '.join(sorted(interest))} only"))
    print(f"{'GPU':8} {'Provider':10} {'On demand':>10} {'Spot':>8} {'12 months':>10}  {'Stock':18} As listed")
    for r in rows:
        print(f"{(r['family'] or '?'):8} {r['provider']:10} {money(r['on_demand']):>10} {money(r['spot']):>8} "
              f"{money(r.get('term_12m')):>10}  {str(r['availability'] or '-'):18} {r['name']}"
              + (f" ({r['note']})" if r.get("note") else ""))
    if not rows:
        print("  none")
    for p in problems:
        print("PROBLEM: " + p)
    return 1 if problems else 0


def main(argv):
    if "--report" in argv:
        i = argv.index("--report")
        if i + 1 >= len(argv):
            print(__doc__)
            return 2
        return report(argv[i + 1], show_all="--all" in argv)
    if "--test" in argv:
        return take_reading("manual", test=True)
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
