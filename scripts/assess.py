"""
The assessor. Turns each window's raw files into that day's assessment, by the
rules in the methodology, section 7, and the roadmap, Appendix A.4. Runs in the
private repository, Hunterson-raw, when the server pushes a window's files.

For each probed checkpoint, each provider in the window's listing at an
accepted precision is tested in this order, and the first test it fails is the
reason it is excluded:

    1. Listed       at an accepted precision in the listing saved in the window,
                    bought through an endpoint of standard priority (D34)
    2. Reliable     a completed request in at least 8 of the previous 10 windows;
                    a window with no finished probe counts against everyone
    3. Complete     at least 2 of its 3 requests completed, meaning a reply came
                    back with the provider's token counts
    4. Correct      every completed request gives both check answers as its first
                    two lines, ignoring letter case, and was stopped by the
                    500-token limit
    5. Clean        no reasoning tokens, reasoning text or cached input tokens
    6. Fast enough  median first token within the limit, and median speed from
                    the first token at least the floor (two requests: their average)
    7. Same input   its input token count within 1 per cent of the panel's median
    8. Receipt      the receipt splits input and output cost, and the total is
                    within 1 per cent of the listed prices in force at the moment
                    of the request, including any time-of-day price, times the
                    tokens counted

Each contributor gives its price paid, the receipt's cost of input and of output
divided by the tokens counted, the median across its completed requests.
Providers in one group in affiliations.json give one observation, the member
with the lowest output price paid (Rule 10). With fewer than five contributors
there is no price. Otherwise the price is the interquartile mean, a quarter of
the count rounded down dropped from each end, of output and of input
separately; the blend is 16 parts input to 1 output from the two means. Each is
worked from unrounded per-token prices and given in US dollars per million
tokens to four decimal places, halves rounded up. The same is done with each
provider's listed discount removed.

Writes one file per probed checkpoint per window, data/assessments/DATE/SLUG.json,
in the form launch/sample.py sets out (roadmap Appendix D.5). A file is written
once and never changed. These files stay private until go-live (decision D26).
The assessor never reads data/offwindow/.

Usage:
    python3 scripts/assess.py
        assess every window up to today that has no assessment yet. A window
        earlier than today with no finished probe is recorded as missed.
    python3 scripts/assess.py --report DAY_OR_FOLDER [--ignore-reliability] [--first-token SECONDS]
        print what the rules give for one window (YYYY-MM-DD), or for any probe
        folder such as an off-window reading, and write nothing. Off-window
        folders are never windows, so reliability is not applied to them.

Uses only the Python standard library.
"""
import datetime as dt
import json
import os
import statistics
import sys
from decimal import Decimal, ROUND_HALF_UP

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import affiliations  # noqa: E402
import service_tiers  # noqa: E402

FROZEN_PROMPT_SHA256 = "140afc12e0c154fd2cb843197da5d3bc673c9e1cea6e0585236b2f41a2a8b24a"   # Rule 9
EXCLUDED_DAYS = {(12, 25), (1, 1)}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MILLION = Decimal(1000000)
Q4 = Decimal("0.0001")
SCHEMA = 1

DEFAULTS = {
    "first_window": "2026-10-15",
    "methodology_version": "0.9",
    "max_first_token_seconds": 2.0,
    "min_output_tokens_per_second": 30,
    "reliability_windows": 10,
    "reliability_needed": 8,
    "complete_needed": 2,
    "input_tolerance": 0.01,
    "receipt_tolerance": 0.01,
    "minimum_contributors": 5,
    "blend_input_weight": 16,
}


def load_json(path):
    with open(path) as f:
        return json.load(f)


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def parse_time(text):
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


def q4(x):
    return str(Decimal(x).quantize(Q4, rounding=ROUND_HALF_UP))


def dec(x):
    return None if x is None else Decimal(str(x))


def median(values):
    v = sorted(values)
    n = len(v)
    if not n:
        return None
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def iqm(values):
    """Interquartile mean: a quarter of the count, rounded down, dropped from each end."""
    v = sorted(values)
    k = len(v) // 4
    kept = v[k:len(v) - k] if k else v
    return sum(kept, Decimal(0)) / len(kept)


def short(text, n=60):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 3] + "..."


# Configuration ------------------------------------------------------------

def settings(panel):
    s = dict(DEFAULTS)
    s.update(panel.get("assessment") or {})
    return s


def checkpoints_info(candidates):
    """openrouter_id -> {grade, name, reference, accepted}."""
    out = {}
    for grade_key, entries in candidates["grades"].items():
        grade = grade_key.split(" (")[0].split(",")[0].strip()
        for e in entries:
            p = e["native_precision"]
            out[e["openrouter_id"]] = {
                "grade": grade,
                "name": e.get("name") or e["openrouter_id"].split("/")[-1],
                "reference": bool(e.get("reference")),
                "accepted": p if isinstance(p, list) else [p],
            }
    return out


def slug_of(checkpoint):
    return checkpoint.split("/")[-1]


def file_slug(text):
    """The probe's file-name form of a checkpoint (scripts/probe.py, slug)."""
    return "".join(c if c.isalnum() or c in "-." else "_" for c in text.lower())


# Windows ------------------------------------------------------------------

def is_window(day):
    return day.weekday() < 5 and (day.month, day.day) not in EXCLUDED_DAYS


def windows_between(first, last):
    """Every window from first to last, inclusive, as dates."""
    d, out = first, []
    while d <= last:
        if is_window(d):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def previous_windows(day, first, count):
    """The `count` windows before `day`, from the first window on. Fewer exist early on."""
    out, d = [], day - dt.timedelta(days=1)
    while d >= first and len(out) < count:
        if is_window(d):
            out.append(d)
        d -= dt.timedelta(days=1)
    return out


class Window:
    """One probe folder: its manifest, listings and request records."""

    def __init__(self, folder):
        self.folder = folder
        self.exists = os.path.isdir(folder)
        mpath = os.path.join(folder, "manifest.json")
        self.manifest = load_json(mpath) if os.path.exists(mpath) else None
        self.records = {}
        req_dir = os.path.join(folder, "requests")
        if os.path.isdir(req_dir):
            for name in sorted(os.listdir(req_dir)):
                if not name.endswith(".json"):
                    continue
                rec = load_json(os.path.join(req_dir, name))
                t = rec.get("target") or {}
                key = (t.get("checkpoint"), t.get("route"), t.get("provider"))
                self.records.setdefault(key, []).append(rec)

    @property
    def problem(self):
        """Why this folder is not a valid window, or None."""
        if not self.exists:
            return "No probe ran in the window"
        if not self.manifest:
            return "The probe did not finish in the window"
        if self.manifest.get("prompt_sha256") != FROZEN_PROMPT_SHA256:
            return "The test piece was not the frozen one (Rule 9)"
        return None

    def listing(self, checkpoint):
        path = os.path.join(self.folder, "listing", file_slug(checkpoint) + ".json")
        return load_json(path) if os.path.exists(path) else None

    def completed_providers(self, checkpoint, route="openrouter"):
        if self.problem:
            return set()
        return {k[2] for k, recs in self.records.items()
                if k[0] == checkpoint and k[1] == route and any(completed(r) for r in recs)}


_WINDOW_CACHE = {}


def window_for(root, day):
    key = (root, day)
    if key not in _WINDOW_CACHE:
        _WINDOW_CACHE[key] = Window(os.path.join(root, "data", "probes", day.isoformat()))
    return _WINDOW_CACHE[key]


# One request --------------------------------------------------------------

def completed(rec):
    u = rec.get("usage") or {}
    return (rec.get("http_status") == 200 and not rec.get("error")
            and u.get("prompt_tokens") is not None and u.get("completion_tokens") is not None)


def reply(rec):
    return "".join(c.get("text", "") for c in rec.get("chunks") or [])


def speed(rec):
    u = rec.get("usage") or {}
    ft, total = rec.get("first_token_s"), rec.get("total_s")
    if ft is None or not total or total <= ft or not u.get("completion_tokens"):
        return None
    return u["completion_tokens"] / (total - ft)


def price_in_force(listed, when):
    """The listed (prompt, completion) per-token prices at a moment, honouring any
    time-of-day override in the listing: utc_days, and utc_start and utc_end as
    HHMM, an end of 0 meaning midnight. The first override that matches applies."""
    hm = when.hour * 100 + when.minute
    for o in listed.get("overrides") or []:
        days = [d.lower() for d in o.get("utc_days") or []]
        if days and WEEKDAYS[when.weekday()] not in days:
            continue
        if o.get("utc_start") is not None or o.get("utc_end") is not None:
            start = int(o.get("utc_start") or 0)
            end = int(o.get("utc_end") if o.get("utc_end") is not None else 2400) or 2400
            inside = (start <= hm < end) if start < end else (hm >= start or hm < end)
            if not inside:
                continue
        return dec(o.get("prompt", listed.get("prompt"))), dec(o.get("completion", listed.get("completion")))
    return dec(listed.get("prompt")), dec(listed.get("completion"))


def receipt(rec):
    """(input cost, output cost, total) from the receipt, or None where missing."""
    u = rec.get("usage") or {}
    c = u.get("cost_details") or {}
    return (dec(c.get("upstream_inference_prompt_cost")), dec(c.get("upstream_inference_completions_cost")),
            dec(u.get("cost")))


# One provider -------------------------------------------------------------

def test_provider(cp, provider, recs, ctx):
    """Every test, each judged on its own. Returns (checks, measured): checks is an
    ordered list of (test, passed, reason)."""
    s = ctx["settings"]
    done = [r for r in recs if completed(r)]
    measured = {"tag": (recs[0]["target"].get("tag") if recs else ctx["listed_tags"].get(provider)),
                "requests": len(recs), "completed": len(done)}
    listed = (recs[0]["target"].get("listed") if recs else None) or ctx["listed_prices"].get(provider) or {}
    if listed.get("discount") is not None:
        measured["discount"] = str(listed["discount"])
    checks = []

    # 1. Listed, in the standard service class (decision D34).
    bought = recs[0]["target"].get("tag") if recs else None
    tier = service_tiers.not_observed(ctx.get("tiers"), provider, bought, ctx.get("tier_day"))
    if tier:
        checks.append(("Listed", False, f"Listed: bought {bought}, a {tier.get('class', 'non-standard')} "
                                        "tier, which is not observed (D34)"))
    elif provider in (ctx.get("tier_only") or {}):
        only = ctx["tier_only"][provider]
        checks.append(("Listed", False, f"Listed: only a {only.get('class', 'non-standard')} tier at an "
                                        "accepted precision, which is not observed (D34)"))
    else:
        checks.append(("Listed", provider in ctx["listed_tags"],
                       "Listed: not at an accepted precision in the window's listing"))

    # 2. Reliable.
    if ctx["previous"] is None:
        checks.append(("Reliable", True, None))
    else:
        n = sum(1 for w in ctx["previous"] if provider in w)
        measured["reliability"] = f"{n} of {len(ctx['previous'])}"
        checks.append(("Reliable", n >= s["reliability_needed"],
                       f"Reliable: completed requests in {n} of the previous {len(ctx['previous'])} windows, "
                       f"at least {s['reliability_needed']} of the last {s['reliability_windows']} needed"))

    # 3. Complete.
    rounds = ctx["rounds"]
    errors = sorted({short(r.get("error") or "no token counts", 40) for r in recs if not completed(r)})
    why = f"Complete: {len(done)} of {rounds} requests completed"
    if errors:
        why += " (" + "; ".join(errors) + ")"
    checks.append(("Complete", len(done) >= s["complete_needed"], why))

    # 4. Correct.
    want = [ctx["accept"][0].strip().casefold(), ctx["accept"][1].strip().casefold()]
    bad = None
    for r in done:
        lines = [ln.strip() for ln in reply(r).splitlines() if ln.strip()]
        if [ln.casefold() for ln in lines[:2]] != want:
            if not lines and any(c.get("reasoning") for c in r.get("chunks") or []):
                bad = "Correct: no answer, only reasoning text"
            elif not lines:
                bad = "Correct: an empty reply"
            else:
                bad = "Correct: the first two lines were " + " / ".join(short(ln, 40) for ln in lines[:2])
            break
        if r.get("finish_reason") != "length":
            bad = f"Correct: ended by {r.get('finish_reason') or 'nothing'}, not the 500-token limit"
            break
    checks.append(("Correct", bool(done) and bad is None, bad or "Correct: no completed request"))

    # 5. Clean.
    dirty = None
    for r in done:
        u = r["usage"]
        if (u.get("completion_tokens_details") or {}).get("reasoning_tokens"):
            dirty = "Clean: reasoning tokens in the usage record"
        elif (u.get("prompt_tokens_details") or {}).get("cached_tokens"):
            dirty = "Clean: cached input tokens in the usage record"
        elif any(c.get("reasoning") for c in r.get("chunks") or []):
            dirty = "Clean: reasoning text in the reply"
        if dirty:
            break
    checks.append(("Clean", dirty is None, dirty))

    # 6. Fast enough.
    fts = [r["first_token_s"] for r in done if r.get("first_token_s") is not None]
    sps = [x for x in (speed(r) for r in done) if x is not None]
    ft, sp = median(fts), median(sps)
    if ft is not None:
        measured["first_token_s"] = round(ft, 2)
    if sp is not None:
        measured["tokens_per_second"] = round(sp, 1)
    limit, floor = float(ctx["max_first_token"]), float(s["min_output_tokens_per_second"])
    if ft is None or sp is None:
        checks.append(("Fast enough", False, "Fast enough: no first token was timed"))
    elif ft > limit:
        checks.append(("Fast enough", False,
                       f"Fast enough: median first token {ft:.2f} seconds, limit {limit:.2f}"))
    elif sp < floor:
        checks.append(("Fast enough", False,
                       f"Fast enough: median speed {sp:.1f} tokens per second, minimum {floor:g}"))
    else:
        checks.append(("Fast enough", True, None))

    # 7. Same input.
    tokens = median([r["usage"]["prompt_tokens"] for r in done])
    if tokens is not None:
        measured["input_tokens"] = tokens
    panel_median = ctx["input_median"]
    if tokens is None or panel_median is None:
        checks.append(("Same input", False, "Same input: no input count"))
    else:
        ok = abs(tokens - panel_median) <= s["input_tolerance"] * panel_median
        checks.append(("Same input", ok, f"Same input: {tokens:,.0f} input tokens, panel median {panel_median:,.0f}"))

    # 8. Receipt matches. The price paid is recorded for every provider whose
    # receipts split the cost, so the day's table can show it; only contributors'
    # prices enter the figure.
    paid_in, paid_out, wrong, worst = [], [], None, None
    tol = Decimal(str(s["receipt_tolerance"]))
    for r in done:
        cin, cout, total = receipt(r)
        u = r["usage"]
        if cin is None or cout is None or total is None:
            wrong = wrong or "Receipt: the receipt does not split the cost of input and output"
            continue
        paid_in.append(cin / u["prompt_tokens"])
        paid_out.append(cout / u["completion_tokens"])
        pin, pout = price_in_force(listed, parse_time(r["started_utc"]))
        if pin is None or pout is None:
            wrong = wrong or "Receipt: no listed price to check against"
            continue
        expected = pin * u["prompt_tokens"] + pout * u["completion_tokens"]
        gap = (total - expected) / expected * 100 if expected > 0 else Decimal(100)
        if worst is None or abs(gap) > abs(worst):
            worst = gap
        if abs(total - expected) > tol * expected and not wrong:
            wrong = "Receipt: charged %s per cent %s the listed price" % (
                abs(gap).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), "above" if gap > 0 else "below")
    if worst is not None:
        measured["receipt_vs_listed_percent"] = str(worst.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    checks.append(("Receipt", bool(done) and wrong is None, wrong or "Receipt: no completed request"))
    if paid_out and len(paid_out) == len(done):
        measured["paid"] = {"output": median(paid_out), "input": median(paid_in)}
    return checks, measured


# One checkpoint on one day ------------------------------------------------

def assess_checkpoint(cp, info, win, day, ctx_base, groups, ignore_reliability=False):
    s = ctx_base["settings"]
    listing = win.listing(cp) or {}
    endpoints = (((listing.get("response") or {}).get("data") or {}).get("endpoints")) or []
    accepted = listing.get("accepted_precisions") or info["accepted"]
    listed_tags, listed_prices, tier_only = {}, {}, {}
    for ep in endpoints:
        if (ep.get("quantization") or "unspecified") not in accepted:
            continue
        name = ep.get("provider_name", "unknown")
        tier = service_tiers.not_observed(ctx_base.get("tiers"), name, ep.get("tag"), ctx_base.get("tier_day"))
        if tier:
            # D34: a tier that is not observed; the provider is observed through
            # its standard endpoint, if it lists one.
            tier_only.setdefault(name, tier)
            continue
        price = dec((ep.get("pricing") or {}).get("completion"))
        if name not in listed_tags or (price is not None and price < dec(listed_prices[name].get("completion") or 9)):
            listed_tags[name] = ep.get("tag")
            listed_prices[name] = ep.get("pricing") or {}
    tier_only = {k: v for k, v in tier_only.items() if k not in listed_tags}
    venue = {k[2]: v for k, v in win.records.items() if k[0] == cp and k[1] == "openrouter"}
    panel = sorted(set(listed_tags) | set(venue) | set(tier_only), key=str.lower)

    previous = None
    if not ignore_reliability and ctx_base.get("window_day"):
        previous = [window_for(ctx_base["root"], w).completed_providers(cp)
                    for w in previous_windows(ctx_base["window_day"], ctx_base["first"], s["reliability_windows"])]

    per_provider_tokens = [median([r["usage"]["prompt_tokens"] for r in recs if completed(r)])
                           for recs in venue.values() if any(completed(r) for r in recs)]
    ctx = dict(ctx_base, listed_tags=listed_tags, listed_prices=listed_prices, tier_only=tier_only,
               previous=previous,
               input_median=median(per_provider_tokens))

    results = []
    for prov in panel:
        checks, measured = test_provider(cp, prov, venue.get(prov, []), ctx)
        failed = next((c for c in checks if not c[1]), None)
        results.append({"provider": prov, "checks": checks, "measured": measured,
                        "reason": failed[2] if failed else None})

    # Rule 10: one observation per group, the member with the lowest output price paid.
    mapping = affiliations.group_of(groups, day.isoformat() if hasattr(day, "isoformat") else day)
    passing = [r for r in results if r["reason"] is None]
    best = {}
    for r in sorted(passing, key=lambda r: (r["measured"]["paid"]["output"], r["provider"].lower())):
        g = affiliations.canonical(r["provider"], mapping)
        if g in best:
            r["reason"] = f"Counted with {best[g]['provider']}, Rule 10"
        else:
            best[g] = r
    contributors = [r for r in results if r["reason"] is None]

    n = len(contributors)
    price = undiscounted = None
    if n >= s["minimum_contributors"]:
        outs = [r["measured"]["paid"]["output"] for r in contributors]
        ins = [r["measured"]["paid"]["input"] for r in contributors]
        w = Decimal(s["blend_input_weight"])
        mo, mi = iqm(outs), iqm(ins)
        price = {"output": q4(mo * MILLION), "input": q4(mi * MILLION),
                 "blended": q4((w * mi + mo) / (w + 1) * MILLION)}

        def undisc(r, side):
            d = dec(r["measured"].get("discount")) or Decimal(0)
            return r["measured"]["paid"][side] / (1 - d) if d < 1 else r["measured"]["paid"][side]
        uo = iqm([undisc(r, "output") for r in contributors])
        ui = iqm([undisc(r, "input") for r in contributors])
        undiscounted = {"output": q4(uo * MILLION), "input": q4(ui * MILLION),
                        "blended": q4((w * ui + uo) / (w + 1) * MILLION)}
    k = n // 4
    order = sorted(contributors, key=lambda r: (r["measured"]["paid"]["output"], r["provider"].lower()))
    in_mean = {r["provider"]: not (k and (i < k or i >= n - k)) for i, r in enumerate(order)}

    providers = []
    for r in results:
        m = dict(r["measured"])
        paid = m.pop("paid", None)
        if paid:
            m["paid_output"], m["paid_input"] = q4(paid["output"] * MILLION), q4(paid["input"] * MILLION)
        entry = {"provider": r["provider"]}
        if r["reason"] is None:
            entry.update({"result": "contributor", "in_mean": in_mean[r["provider"]] if price else None,
                          "output": m["paid_output"], "input": m["paid_input"]})
        else:
            entry.update({"result": "excluded", "reason": r["reason"]})
        entry["measured"] = m
        entry["tests"] = {name: ok for name, ok, _ in r["checks"]}
        providers.append(entry)
    return {"panel": len(panel), "contributors": n, "price": price, "undiscounted": undiscounted,
            "providers": providers, "results": results}


def control_results(cp, win, ctx_base):
    """The control group, bought direct: the same tests where they apply, reported
    separately and never in the price. The direct route has no venue listing and
    no venue receipt, so Listed and Receipt do not apply; how its price is read is
    set when the control group is wired in (roadmap step 19)."""
    out = []
    direct = {k[2]: v for k, v in win.records.items() if k[0] == cp and k[1] == "direct"}
    if not direct:
        return out
    toks = [median([r["usage"]["prompt_tokens"] for r in recs if completed(r)])
            for recs in direct.values() if any(completed(r) for r in recs)]
    ctx = dict(ctx_base, listed_tags={p: None for p in direct}, listed_prices={}, previous=None,
               input_median=median(toks))
    for prov in sorted(direct, key=str.lower):
        checks, measured = test_provider(cp, prov, direct[prov], ctx)
        checks = [c for c in checks if c[0] not in ("Listed", "Reliable", "Receipt")]
        failed = next((c for c in checks if not c[1]), None)
        measured.pop("paid", None)
        out.append({"provider": prov, "route": "direct",
                    "result": "passed" if not failed else "failed",
                    "reason": failed[2] if failed else None, "measured": measured})
    return out


# Writing ------------------------------------------------------------------

def context(root, panel, day, win, first, max_first_token=None):
    s = settings(panel)
    man = win.manifest or {}
    tier_day = day.isoformat() if day else (man.get("day") or (man.get("started_utc") or "")[:10])
    return {"root": root, "settings": s, "first": first, "window_day": day,
            "tiers": panel.get("service_tiers"), "tier_day": tier_day,
            "rounds": int(man.get("rounds") or panel.get("rounds", 3)),
            "accept": (man.get("accept_line_1") or panel["accept_line_1"],
                       man.get("accept_line_2") or panel["accept_line_2"]),
            "max_first_token": max_first_token if max_first_token is not None else s["max_first_token_seconds"]}


def status_for(info, panel, day, has_price):
    launch = panel.get("launch_date")
    if not info["reference"] or not launch or day.isoformat() < launch:
        return "shadow"
    return "published" if has_price else "not_published"


def record(cp, info, day, panel, s, result, problem, win, now):
    status = status_for(info, panel, day, bool(result and result["price"]))
    if problem:
        reason = problem
    elif not result["price"]:
        n = result["contributors"]
        reason = f"{n} contributor{'' if n == 1 else 's'}, below the minimum of {s['minimum_contributors']}"
    else:
        reason = None
    man = (win.manifest or {}) if win else {}
    rec = {
        "schema": SCHEMA,
        "date": day.isoformat(),
        "checkpoint": cp,
        "name": info["name"],
        "grade": info["grade"],
        "reference": info["reference"],
        "status": status,
        "reason": reason,
        "methodology_version": s["methodology_version"],
        "published_utc": now if status != "shadow" else None,
        "assessed_utc": now,
        "window": {"start_utc": man.get("started_utc"), "end_utc": man.get("finished_utc")} if man else None,
        "panel": result["panel"] if result else 0,
        "contributors": result["contributors"] if result else 0,
        "price": result["price"] if result else None,
        "undiscounted": result["undiscounted"] if result else None,
        "providers": result["providers"] if result else [],
        "rollover": None,
        "limits": {"max_first_token_seconds": s["max_first_token_seconds"],
                   "min_output_tokens_per_second": s["min_output_tokens_per_second"]},
        "evidence": {
            "probe_commit": man.get("script_commit"),
            "prompt_sha256": man.get("prompt_sha256"),
            "fingerprints": f"data/hashes/probes/{day.isoformat()}.sha256" if man else None,
        },
    }
    if result and result.get("control"):
        rec["control"] = result["control"]
    return rec


def write_once(path, rec):
    if os.path.exists(path):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)
    return True


def assess_all(root=".", today=None, now=None, verbose=True):
    panel = load_json(os.path.join(root, "panel.json"))
    info = checkpoints_info(load_json(os.path.join(root, "candidates.json")))
    groups = affiliations.load(os.path.join(root, "affiliations.json"))
    s = settings(panel)
    first = dt.date.fromisoformat(s["first_window"])
    now_dt = now or utc_now()
    today = today or now_dt.date()
    stamp = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    written = []
    for day in windows_between(first, today):
        win = window_for(root, day)
        problem = win.problem
        if problem and day >= today:
            continue                      # today's files may still be on their way
        probed = (win.manifest or {}).get("probe") if not problem else None
        if probed:
            cps = probed
        else:
            cps = [cp for cp in panel["probe"] if info.get(cp, {}).get("reference")]
        for cp in cps:
            if cp not in info:
                print(f"{day}: {cp} is not in candidates.json; skipped")
                continue
            path = os.path.join(root, "data", "assessments", day.isoformat(), slug_of(cp) + ".json")
            if os.path.exists(path):
                continue
            result = None
            if not problem:
                ctx = context(root, panel, day, win, first)
                result = assess_checkpoint(cp, info[cp], win, day, ctx, groups)
                result["control"] = control_results(cp, win, ctx)
            rec = record(cp, info[cp], day, panel, s, result, problem, win, stamp)
            if write_once(path, rec):
                written.append(path)
                fig = rec["price"]["output"] if rec["price"] else "no price"
                if verbose:
                        print(f"{day} {slug_of(cp)}: {rec['status']}, {rec['contributors']} of {rec['panel']} "
                          f"contributors, {fig}" + (f" ({rec['reason']})" if rec["reason"] else ""))
    if not written and verbose:
        print("Nothing new to assess.")
    return written


# The report ---------------------------------------------------------------

def report(target, root=".", ignore_reliability=False, max_first_token=None):
    panel = load_json(os.path.join(root, "panel.json"))
    info = checkpoints_info(load_json(os.path.join(root, "candidates.json")))
    groups = affiliations.load(os.path.join(root, "affiliations.json"))
    s = settings(panel)
    first = dt.date.fromisoformat(s["first_window"])
    if os.path.isdir(target):
        folder, day = target, None
        name = os.path.basename(os.path.normpath(target))
        try:
            d = dt.date.fromisoformat(name)
            if os.path.normpath(folder) == os.path.normpath(os.path.join(root, "data", "probes", name)):
                day = d
        except ValueError:
            pass
    else:
        day = dt.date.fromisoformat(target)
        folder = os.path.join(root, "data", "probes", target)
    win = Window(folder)
    if win.problem:
        print(f"{folder}: {win.problem}")
        return 1
    on_day = day or dt.date.fromisoformat(win.manifest.get("day") or win.manifest["started_utc"][:10])
    ctx = context(root, panel, day, win, first, max_first_token)
    if day is None or ignore_reliability:
        ctx["window_day"] = None
    note = []
    if ctx["window_day"] is None:
        note.append("reliability not applied")
    if max_first_token is not None:
        note.append(f"first-token limit {max_first_token:g} seconds")
    print(f"{folder}  ({win.manifest.get('mode', 'daily')}{', ' + win.manifest['offwindow_kind'] if win.manifest.get('offwindow_kind') else ''}"
          f"; {', '.join(note) if note else 'the rules as they stand'})")
    for cp in win.manifest.get("probe") or panel["probe"]:
        if cp not in info:
            continue
        res = assess_checkpoint(cp, info[cp], win, on_day, ctx, groups, ignore_reliability=ctx["window_day"] is None)
        print(f"\n{info[cp]['name']}: {res['contributors']} of {res['panel']} contributors")
        for p in sorted(res["providers"], key=lambda p: (p["result"] != "contributor", p["provider"].lower())):
            m = p["measured"]
            timing = "first token %s s, %s tok/s" % (m.get("first_token_s", "-"), m.get("tokens_per_second", "-"))
            if p["result"] == "contributor":
                print(f"  {p['provider']:<16} {p['output']} / {p['input']}   {timing}")
            else:
                print(f"  {p['provider']:<16} EXCLUDED  {p['reason']}   {timing}")
        if res["price"]:
            pr, un = res["price"], res["undiscounted"]
            print(f"  Output {pr['output']}  Input {pr['input']}  Blended {pr['blended']}"
                  f"   (before discounts: {un['output']} / {un['input']} / {un['blended']})")
        else:
            print(f"  No price: fewer than {s['minimum_contributors']} contributors")
    return 0


def main(argv):
    if not argv:
        assess_all()
        return 0
    if argv[0] == "--report" and len(argv) >= 2:
        ft = None
        if "--first-token" in argv:
            ft = float(argv[argv.index("--first-token") + 1])
        return report(argv[1], ignore_reliability="--ignore-reliability" in argv, max_first_token=ft)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
