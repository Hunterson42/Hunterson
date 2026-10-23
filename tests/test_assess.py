"""
Tests for scripts/assess.py, the assessor, and the provider groups of Rule 10.
Run from the repository root:  python3 tests/test_assess.py

Every window here is made up in a temporary folder: no raw OpenRouter response
is used or kept, so these tests can be public.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import affiliations  # noqa: E402
import assess  # noqa: E402

CP = "deepseek/deepseek-v4.1-flash"
SLUG = "deepseek-v4.1-flash"
FIRST = dt.date(2026, 10, 15)
LINES = ("ISLAND DUKE Prospero", "LAST SPEAKER Sebastian")

# Six providers that pass, priced so the figure can be worked by hand: output
# 0.40 to 0.90 and input 0.10 to 0.15 per million, all with a 20 per cent discount.
GOOD = {f"Good{i}": (Decimal("0.40") + Decimal("0.10") * i, Decimal("0.10") + Decimal("0.01") * i) for i in range(6)}


def per_token(per_million):
    return Decimal(per_million) / Decimal(1000000)


def load(path):
    with open(path) as f:
        return json.load(f)


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f)


def spec(out="0.60", inp="0.12", **kw):
    s = {"out": Decimal(out), "in": Decimal(inp), "discount": 0.2, "overrides": None}
    s.update(kw)
    return s


def request(day, provider, rnd, s):
    """One made-up request record in the probe's format."""
    pin, pout = per_token(s["in"]), per_token(s["out"])
    pt, ct = s.get("prompt_tokens", 7613), 500
    factor = Decimal(str(s.get("charge", 1)))
    fails = s.get("fail_rounds", ())
    start = f"{day}T14:{5 + 15 * (rnd - 1):02d}:04.000000Z"
    rec = {
        "target": {"route": "openrouter", "checkpoint": CP, "provider": provider,
                   "tag": s.get("tag") or provider.lower() + "/fp8",
                   "quantization": "fp8",
                   "listed": {"prompt": str(pin), "completion": str(pout), "discount": s["discount"],
                              "overrides": s["overrides"]}},
        "round": rnd, "started_utc": start, "http_status": 200, "error": None,
        "chunks": [], "first_token_s": s.get("ttft", 0.8), "total_s": s.get("ttft", 0.8) + 6.0,
        "finish_reason": s.get("finish", "length"), "usage": None,
    }
    if rnd in fails:
        rec.update({"http_status": 429, "error": "HTTP 429", "first_token_s": None})
        return rec
    lines = s.get("lines", LINES)
    rec["chunks"] = [{"t": 0.8, "text": "\n".join(lines) + "\n"}, {"t": 1.0, "text": "The island " * 10}]
    if s.get("reasoning_text"):
        rec["chunks"].insert(0, {"t": 0.5, "reasoning": "thinking"})
    cin, cout = pin * pt * factor, pout * ct * factor
    usage = {"prompt_tokens": pt, "completion_tokens": ct, "cost": float(cin + cout),
             "completion_tokens_details": {"reasoning_tokens": s.get("reasoning", 0)},
             "prompt_tokens_details": {"cached_tokens": 0}}
    if s.get("split", True):
        usage["cost_details"] = {"upstream_inference_prompt_cost": float(cin),
                                 "upstream_inference_completions_cost": float(cout)}
    rec["usage"] = usage
    return rec


def make_window(root, day, providers, finished=True, prompt=assess.FROZEN_PROMPT_SHA256, folder=None,
                listed_only=None):
    """listed_only: endpoints in the listing that were not bought, name -> spec."""
    folder = folder or os.path.join(root, "data", "probes", day)
    endpoints = []
    for name, s in list(providers.items()) + list((listed_only or {}).items()):
        endpoints.append({"provider_name": name, "tag": s.get("tag") or name.lower() + "/fp8", "quantization": "fp8",
                          "pricing": {"prompt": str(per_token(s["in"])), "completion": str(per_token(s["out"])),
                                      "discount": s["discount"], "overrides": s["overrides"]}})
        if name not in providers:
            continue
        for rnd in (1, 2, 3):
            write(os.path.join(folder, "requests", f"{name}__r{rnd}.json"), request(day, name, rnd, s))
    write(os.path.join(folder, "listing", assess.file_slug(CP) + ".json"),
          {"checkpoint": CP, "fetched_utc": f"{day}T14:05:03Z", "accepted_precisions": ["fp8"],
           "response": {"data": {"endpoints": endpoints}}})
    if finished:
        write(os.path.join(folder, "manifest.json"),
              {"mode": "daily", "day": day, "started_utc": f"{day}T14:05:03Z", "finished_utc": f"{day}T14:36:00Z",
               "prompt_sha256": prompt, "probe": [CP], "accept_line_1": LINES[0], "accept_line_2": LINES[1],
               "rounds": 3, "script_commit": "abc123"})


class AssessTests(unittest.TestCase):
    def setUp(self):
        assess._WINDOW_CACHE.clear()
        self.root = tempfile.mkdtemp()
        shutil.copy(os.path.join(ROOT, "candidates.json"), self.root)
        panel = load(os.path.join(ROOT, "panel.json"))
        panel["probe"] = [CP]
        panel["launch_date"] = None
        panel["assessment"] = dict(assess.DEFAULTS, first_window=FIRST.isoformat())
        write(os.path.join(self.root, "panel.json"), panel)
        write(os.path.join(self.root, "affiliations.json"), {"groups": []})
        self.days = [d.isoformat() for d in assess.windows_between(FIRST, dt.date(2026, 10, 30))]

    def tearDown(self):
        shutil.rmtree(self.root)

    def history(self, n, providers):
        """n earlier windows in which every provider completed its requests."""
        for day in self.days[:n]:
            make_window(self.root, day, providers)

    def run_all(self, today):
        return assess.assess_all(self.root, today=dt.date.fromisoformat(today),
                                 now=dt.datetime.fromisoformat(today + "T14:45:00+00:00"), verbose=False)

    def result(self, day):
        return load(os.path.join(self.root, "data", "assessments", day, SLUG + ".json"))

    def set_panel(self, **changes):
        p = os.path.join(self.root, "panel.json")
        panel = load(p)
        panel.update(changes)
        write(p, panel)

    # The figure ------------------------------------------------------------

    def test_the_figure_by_hand(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        self.history(8, provs)
        make_window(self.root, self.days[8], provs)
        self.run_all(self.days[8])
        r = self.result(self.days[8])
        self.assertEqual(r["contributors"], 6)
        # A quarter of six, rounded down, is one: drop 0.40 and 0.90, average 0.50 to 0.80.
        self.assertEqual(r["price"], {"output": "0.6500", "input": "0.1250", "blended": "0.1559"})
        # Discount of 20 per cent removed: 0.65 / 0.8 and 0.125 / 0.8 = 0.15625, rounded half up.
        self.assertEqual(r["undiscounted"], {"output": "0.8125", "input": "0.1563", "blended": "0.1949"})
        in_mean = {p["provider"]: p["in_mean"] for p in r["providers"]}
        self.assertFalse(in_mean["Good0"] or in_mean["Good5"])
        self.assertTrue(all(in_mean[f"Good{i}"] for i in range(1, 5)))
        self.assertEqual(r["status"], "shadow")
        self.assertIsNone(r["published_utc"])
        self.assertTrue(r["reference"])
        self.assertEqual((r["grade"], r["name"]), ("Standard", "DeepSeek V4.1-Flash"))

    def test_worked_example_and_rounding(self):
        # Methodology section 7: 0.30 to 1.50, seven contributors, gives 0.5200.
        prices = [Decimal(x) for x in ("0.30", "0.40", "0.45", "0.50", "0.55", "0.70", "1.50")]
        self.assertEqual(assess.q4(assess.iqm(prices)), "0.5200")
        self.assertEqual(assess.q4(Decimal("0.00005")), "0.0001")
        self.assertEqual(assess.q4(Decimal("0.123449999")), "0.1234")
        self.assertEqual(assess.median([Decimal(1), Decimal(2)]), Decimal("1.5"))

    # The tests, in order -------------------------------------------------------

    def test_each_test_excludes_with_its_reason(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        provs.update({
            "Incomplete": spec(fail_rounds=(1, 2)),
            "Wrong": spec(lines=(LINES[0], "LAST SPEAKER Miranda")),
            "Stopped": spec(finish="stop"),
            "Thinker": spec(reasoning=120),
            "Slow": spec(ttft=2.5),
            "Odd input": spec(prompt_tokens=7800),
            "Overcharged": spec(charge="1.05"),
            "No split": spec(split=False),
        })
        self.history(8, provs)
        make_window(self.root, self.days[8], provs)
        self.run_all(self.days[8])
        reasons = {p["provider"]: p.get("reason") for p in self.result(self.days[8])["providers"]}
        self.assertTrue(reasons["Incomplete"].startswith("Complete: 1 of 3 requests completed (HTTP 429)"))
        self.assertEqual(reasons["Wrong"], "Correct: the first two lines were ISLAND DUKE Prospero / LAST SPEAKER Miranda")
        self.assertEqual(reasons["Stopped"], "Correct: ended by stop, not the 500-token limit")
        self.assertEqual(reasons["Thinker"], "Clean: reasoning tokens in the usage record")
        self.assertEqual(reasons["Slow"], "Fast enough: median first token 2.50 seconds, limit 2.00")
        self.assertEqual(reasons["Odd input"], "Same input: 7,800 input tokens, panel median 7,613")
        self.assertEqual(reasons["Overcharged"], "Receipt: charged 5.0 per cent above the listed price")
        self.assertEqual(reasons["No split"], "Receipt: the receipt does not split the cost of input and output")
        self.assertEqual(self.result(self.days[8])["contributors"], 6)

    def test_a_tier_that_is_not_observed_is_excluded_from_its_date(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        provs["Cheap"] = spec("0.20", "0.05", tag="cheap/fp8/flex")
        only = {"FlexOnly": spec("0.25", "0.06", tag="flexonly/fp8/flex")}
        self.set_panel(service_tiers={"not_observed": [
            {"provider": p, "tag_ends_with": "/flex", "class": "lower-priority", "from": self.days[8]}
            for p in ("Cheap", "FlexOnly")]})
        for day in self.days[:9]:
            make_window(self.root, day, provs, listed_only=only)
        self.run_all(self.days[8])
        before = {p["provider"]: p for p in self.result(self.days[7])["providers"]}
        after = {p["provider"]: p for p in self.result(self.days[8])["providers"]}
        # Before its date the tier is observed as before: Listed passes.
        self.assertTrue(before["Cheap"]["tests"]["Listed"])
        # From its date, what was bought on it is excluded, and the reason says why.
        self.assertFalse(after["Cheap"]["tests"]["Listed"])
        self.assertEqual(after["Cheap"]["reason"],
                         "Listed: bought cheap/fp8/flex, a lower-priority tier, which is not observed (D34)")
        self.assertEqual(after["FlexOnly"]["reason"],
                         "Listed: only a lower-priority tier at an accepted precision, which is not observed (D34)")
        self.assertEqual(self.result(self.days[8])["contributors"], 6)
        # The figure is the six good providers' alone.
        self.assertEqual(self.result(self.days[8])["price"]["output"], "0.6500")

    def test_first_failure_is_the_reason(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        provs["Both"] = spec(ttft=3.0, charge="1.2")         # slow and overcharged: Fast comes first
        self.history(8, provs)
        make_window(self.root, self.days[8], provs)
        self.run_all(self.days[8])
        both = next(p for p in self.result(self.days[8])["providers"] if p["provider"] == "Both")
        self.assertTrue(both["reason"].startswith("Fast enough"))
        self.assertFalse(both["tests"]["Receipt"])
        self.assertEqual(both["measured"]["receipt_vs_listed_percent"], "20.00")

    def test_reliability_needs_eight_of_ten(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        provs["Patchy"] = spec()
        others = {k: v for k, v in provs.items() if k != "Patchy"}
        for i, day in enumerate(self.days[:10]):
            make_window(self.root, day, others if i in (0, 4, 7) else provs)
        make_window(self.root, self.days[10], provs)
        self.run_all(self.days[10])
        patchy = next(p for p in self.result(self.days[10])["providers"] if p["provider"] == "Patchy")
        self.assertEqual(patchy["reason"], "Reliable: completed requests in 7 of the previous 10 windows, "
                                           "at least 8 of the last 10 needed")

    def test_the_ninth_window_is_the_first_with_a_figure(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        for day in self.days[:9]:
            make_window(self.root, day, provs)
        self.run_all(self.days[8])
        self.assertIsNone(self.result(self.days[7])["price"])
        self.assertIsNotNone(self.result(self.days[8])["price"])

    def test_a_missed_window_counts_against_everyone(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        for i, day in enumerate(self.days[:10]):
            if i not in (2, 5, 6):
                make_window(self.root, day, provs)
        make_window(self.root, self.days[10], provs)
        self.run_all(self.days[10])
        r = self.result(self.days[10])
        self.assertEqual(r["contributors"], 0)
        self.assertTrue(all("7 of the previous 10" in p["reason"] for p in r["providers"]))
        missed = self.result(self.days[2])
        self.assertEqual(missed["reason"], "No probe ran in the window")
        self.assertEqual((missed["panel"], missed["contributors"], missed["price"]), (0, 0, None))

    def test_an_unfinished_probe_or_changed_prompt_is_not_a_window(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        make_window(self.root, self.days[0], provs, finished=False)
        make_window(self.root, self.days[1], provs, prompt="0" * 64)
        self.run_all(self.days[2])
        self.assertEqual(self.result(self.days[0])["reason"], "The probe did not finish in the window")
        self.assertEqual(self.result(self.days[1])["reason"], "The test piece was not the frozen one (Rule 9)")

    def test_fewer_than_five_gives_no_price(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in list(GOOD.items())[:4]}
        self.history(8, provs)
        make_window(self.root, self.days[8], provs)
        self.run_all(self.days[8])
        r = self.result(self.days[8])
        self.assertEqual((r["contributors"], r["price"], r["undiscounted"]), (4, None, None))
        self.assertEqual(r["reason"], "4 contributors, below the minimum of 5")

    def test_published_and_not_published_after_launch(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        self.history(9, provs)
        make_window(self.root, self.days[9], dict(list(provs.items())[:4]))
        self.set_panel(launch_date=self.days[8])
        self.run_all(self.days[9])
        self.assertEqual(self.result(self.days[7])["status"], "shadow")
        launched = self.result(self.days[8])
        self.assertEqual(launched["status"], "published")
        self.assertEqual(launched["published_utc"], self.days[9] + "T14:45:00Z")
        self.assertEqual(self.result(self.days[9])["status"], "not_published")

    # Prices by time of day ---------------------------------------------------

    def test_receipt_uses_the_price_in_force_at_the_time(self):
        double_until_two = [{"utc_start": 0, "utc_end": 1400, "prompt": str(per_token("0.24")),
                             "completion": str(per_token("1.20"))},
                            {"utc_start": 1400, "utc_end": 0, "prompt": str(per_token("0.12")),
                             "completion": str(per_token("0.60"))}]
        double_from_two = [{"utc_start": 1400, "utc_end": 1500, "prompt": str(per_token("0.24")),
                            "completion": str(per_token("1.20"))}]
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        provs["Cheap afternoons"] = spec(overrides=double_until_two)
        provs["Dear afternoons"] = spec(overrides=double_from_two)
        self.history(8, provs)
        make_window(self.root, self.days[8], provs)
        self.run_all(self.days[8])
        res = {p["provider"]: p for p in self.result(self.days[8])["providers"]}
        self.assertEqual(res["Cheap afternoons"]["result"], "contributor")
        self.assertEqual(res["Dear afternoons"]["reason"], "Receipt: charged 50.0 per cent below the listed price")

    def test_override_matching(self):
        listed = {"prompt": "1", "completion": "2", "overrides": [
            {"utc_days": ["saturday", "sunday"], "prompt": "1", "completion": "2"},
            {"utc_start": 100, "utc_end": 400, "utc_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
             "prompt": "3", "completion": "4"},
            {"utc_start": 2200, "utc_end": 100, "prompt": "5", "completion": "6"}]}
        at = assess.price_in_force
        self.assertEqual(at(listed, dt.datetime(2026, 10, 19, 2, 0)), (Decimal(3), Decimal(4)))     # Monday 02:00
        self.assertEqual(at(listed, dt.datetime(2026, 10, 24, 2, 0)), (Decimal(1), Decimal(2)))     # Saturday
        self.assertEqual(at(listed, dt.datetime(2026, 10, 19, 23, 30)), (Decimal(5), Decimal(6)))   # wraps midnight
        self.assertEqual(at(listed, dt.datetime(2026, 10, 19, 14, 5)), (Decimal(1), Decimal(2)))    # no override
        self.assertEqual(at({"prompt": "1", "completion": "2"}, dt.datetime(2026, 10, 19, 14, 5)), (Decimal(1), Decimal(2)))

    # Rule 10 -------------------------------------------------------------------

    def test_a_group_gives_one_observation(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        provs["Reseller A"] = spec("0.30", "0.08")
        provs["Reseller B"] = spec("0.31", "0.08")
        provs["Reseller C"] = spec("0.32", "0.08")
        self.history(9, provs)
        make_window(self.root, self.days[9], provs)
        write(os.path.join(self.root, "affiliations.json"), {"groups": [{
            "name": "Network", "members": ["Reseller A", "Reseller B", "Reseller C"], "basis": "resale of one source",
            "evidence": ["https://example.invalid/network"], "recorded": self.days[8], "from": self.days[9], "until": None}]})
        self.run_all(self.days[9])
        before, after = self.result(self.days[8]), self.result(self.days[9])
        self.assertEqual(before["contributors"], 9, "a group never applies before its from day")
        self.assertEqual(after["contributors"], 7)
        res = {p["provider"]: p for p in after["providers"]}
        self.assertEqual(res["Reseller A"]["result"], "contributor")
        self.assertEqual(res["Reseller B"]["reason"], "Counted with Reseller A, Rule 10")
        self.assertEqual(res["Reseller C"]["reason"], "Counted with Reseller A, Rule 10")
        # Nine names would put a reseller in the middle and give 0.5040; seven sources give 0.6000.
        self.assertEqual(after["price"]["output"], "0.6000")

    def test_register_is_checked(self):
        path = os.path.join(self.root, "affiliations.json")
        bad = [{"name": "X", "members": ["A"], "evidence": ["e"], "recorded": "2026-11-01", "from": "2026-11-02"},
               {"name": "X", "members": ["A", "B"], "evidence": [], "recorded": "2026-11-01", "from": "2026-11-02"},
               {"name": "X", "members": ["A", "B"], "evidence": ["e"], "recorded": "2026-11-02", "from": "2026-11-02"}]
        for g in bad:
            write(path, {"groups": [g]})
            with self.assertRaises(ValueError):
                affiliations.load(path)
        write(path, {"groups": [{"name": "X", "members": ["A", "B"], "evidence": ["e"], "recorded": "2026-11-01",
                                 "from": "2026-11-02", "until": None}]})
        groups = affiliations.load(path)
        self.assertEqual(affiliations.group_of(groups, "2026-11-01"), {})
        self.assertEqual(affiliations.group_of(groups, "2026-11-02"), {"A": "X", "B": "X"})
        self.assertEqual(affiliations.load(os.path.join(ROOT, "affiliations.json")), [],
                         "the published register starts empty")

    def test_tracker_counts_a_group_once(self):
        shutil.copytree(os.path.join(ROOT, "scripts"), os.path.join(self.root, "scripts"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        write(os.path.join(self.root, "candidates.json"), {"grades": {"Standard (30B active or fewer)": [
            {"openrouter_id": "lab/model", "native_precision": "fp8", "reference": True}]}})
        for day in ("2026-11-02", "2026-11-03"):
            write(os.path.join(self.root, "data", "census", day, "models.json"), {"data": [{"id": "lab/model"}]})
            write(os.path.join(self.root, "data", "census", day, "endpoints", "lab__model.json"), {"data": {"endpoints": [
                {"provider_name": n, "quantization": "fp8"} for n in ("A", "B", "C")]}})
        write(os.path.join(self.root, "affiliations.json"), {"groups": [{
            "name": "AB", "members": ["A", "B"], "evidence": ["e"], "recorded": "2026-11-02", "from": "2026-11-03"}]})
        r = subprocess.run([sys.executable, "scripts/track.py"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.root, "data", "track.md")) as f:
            row = next(line for line in f if line.startswith("| lab/model"))
        self.assertIn("**3** (3) | **2** (2)", row)

    def test_control_group_is_reported_separately(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        self.history(8, provs)
        day = self.days[8]
        make_window(self.root, day, provs)
        for name, s in (("Good1", spec()), ("Thinks", spec(reasoning_text=True))):
            for rnd in (1, 2, 3):
                rec = request(day, name, rnd, s)
                rec["target"] = {"route": "direct", "checkpoint": CP, "provider": name, "model": "lab/Model"}
                rec["usage"].pop("cost_details", None)
                write(os.path.join(self.root, "data", "probes", day, "requests", f"direct-{name}__r{rnd}.json"), rec)
        self.run_all(day)
        r = self.result(day)
        self.assertEqual(r["price"]["output"], "0.6500", "the control group never enters the price")
        self.assertEqual(r["contributors"], 6)
        control = {c["provider"]: c for c in r["control"]}
        self.assertEqual(control["Good1"]["result"], "passed")
        self.assertEqual(control["Thinks"]["reason"], "Clean: reasoning text in the reply")

    # Writing ---------------------------------------------------------------

    def test_written_once_and_today_waits(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        make_window(self.root, self.days[0], provs)
        first = self.run_all(self.days[1])
        self.assertEqual([os.path.basename(os.path.dirname(p)) for p in first], [self.days[0]],
                         "today's window may still be on its way, so nothing is written for it yet")
        path = os.path.join(self.root, "data", "assessments", self.days[0], SLUG + ".json")
        with open(path) as f:
            before = f.read()
        self.set_panel(assessment=dict(assess.DEFAULTS, first_window=FIRST.isoformat(), max_first_token_seconds=0.1))
        self.assertEqual(self.run_all(self.days[1]), [])
        with open(path) as f:
            self.assertEqual(f.read(), before, "an assessment is never rewritten")
        later = self.run_all(self.days[2])
        self.assertEqual(self.result(self.days[1])["reason"], "No probe ran in the window")
        self.assertEqual(len(later), 1)

    def test_offwindow_readings_are_never_assessed(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        make_window(self.root, "2026-10-17", provs, folder=os.path.join(self.root, "data", "offwindow", "2026-10-17-1405"))
        self.run_all(self.days[1])
        written = os.listdir(os.path.join(self.root, "data", "assessments"))
        self.assertEqual(written, [self.days[0]])
        self.assertNotIn("2026-10-17", written)

    def test_report_writes_nothing(self):
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        folder = os.path.join(self.root, "data", "offwindow", "2026-10-17-1405")
        make_window(self.root, "2026-10-17", provs, folder=folder)
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with open(os.devnull, "w") as quiet:
                old, sys.stdout = sys.stdout, quiet
                try:
                    self.assertEqual(assess.report(folder, root=self.root), 0)
                finally:
                    sys.stdout = old
        finally:
            os.chdir(cwd)
        self.assertFalse(os.path.exists(os.path.join(self.root, "data", "assessments")))

    def test_the_publisher_reads_what_the_assessor_writes(self):
        publish = os.path.join(ROOT, "launch", "publish.py")
        if not os.path.exists(publish):
            self.skipTest("the launch site is kept in the private repository")
        provs = {n: spec(str(o), str(i)) for n, (o, i) in GOOD.items()}
        self.history(9, provs)
        self.run_all(self.days[9])
        out = os.path.join(self.root, "site")
        r = subprocess.run([sys.executable, publish, os.path.join(self.root, "data", "assessments"), out, "--preview"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(out, "standard", self.days[8], "index.html")) as f:
            self.assertIn("0.6500", f.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
