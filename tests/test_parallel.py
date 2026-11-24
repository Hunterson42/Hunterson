"""
Tests for the parallel period, when the reference changes after the first
publication (methodology section 4.5; roadmap step 61): both references
published side by side, the daily ratio, the average at the end, the emergency
rule and the switch, through the assessor, the pages, the post and the data.

Every window here is made up in a temporary folder, as in tests/test_assess.py.
Run from the repository root:  python3 tests/test_parallel.py
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal, ROUND_HALF_UP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "site"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assess  # noqa: E402
import publish  # noqa: E402
import test_assess as T  # noqa: E402

OLD, NEW = "deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4.1-flash-1017"
FIRST = dt.date(2026, 10, 15)
DAYS = [d.isoformat() for d in assess.windows_between(FIRST, dt.date(2026, 12, 31))]


def provs(scale="1", n=6):
    """n providers that pass every test, the new checkpoint's prices `scale` times the old's."""
    k = Decimal(scale)
    return {name: T.spec(str(o * k), str(i * k)) for name, (o, i) in list(T.GOOD.items())[:n]}


def make_window(root, day, by_cp):
    """One window probing several checkpoints: by_cp is checkpoint -> {provider: spec}."""
    folder = os.path.join(root, "data", "probes", day)
    for cp, providers in by_cp.items():
        endpoints = []
        for name, s in providers.items():
            endpoints.append({"provider_name": name, "tag": name.lower() + "/fp8", "quantization": "fp8",
                              "pricing": {"prompt": str(T.per_token(s["in"])), "completion": str(T.per_token(s["out"])),
                                          "discount": s["discount"], "overrides": s["overrides"]}})
            for rnd in (1, 2, 3):
                rec = T.request(day, name, rnd, s)
                rec["target"]["checkpoint"] = cp
                T.write(os.path.join(folder, "requests", "%s__%s__r%d.json" % (assess.slug_of(cp), name, rnd)), rec)
        T.write(os.path.join(folder, "listing", assess.file_slug(cp) + ".json"),
                {"checkpoint": cp, "fetched_utc": day + "T14:05:03Z", "accepted_precisions": ["fp8"],
                 "response": {"data": {"endpoints": endpoints}}})
    T.write(os.path.join(folder, "manifest.json"),
            {"mode": "daily", "day": day, "started_utc": day + "T14:05:03Z", "finished_utc": day + "T14:36:00Z",
             "prompt_sha256": assess.FROZEN_PROMPT_SHA256, "probe": list(by_cp), "accept_line_1": T.LINES[0],
             "accept_line_2": T.LINES[1], "rounds": 3, "script_commit": "abc123"})


class ParallelPeriodTests(unittest.TestCase):
    def setUp(self):
        assess._WINDOW_CACHE.clear()
        self.root = tempfile.mkdtemp()
        cands = T.load(os.path.join(ROOT, "candidates.json"))
        cands.pop("changes", None)
        T.write(os.path.join(self.root, "candidates.json"), cands)
        panel = T.load(os.path.join(ROOT, "panel.json"))
        panel["probe"] = [OLD, NEW]
        panel["launch_date"] = DAYS[8]
        panel["assessment"] = dict(assess.DEFAULTS, first_window=FIRST.isoformat(), methodology_version="1.0")
        T.write(os.path.join(self.root, "panel.json"), panel)
        T.write(os.path.join(self.root, "affiliations.json"), {"groups": []})

    def tearDown(self):
        shutil.rmtree(self.root)

    def declare(self, first_day, **settings):
        p = os.path.join(self.root, "candidates.json")
        c = T.load(p)
        c["changes"] = [{"from": OLD, "to": NEW, "first_day": first_day, "run_completed": "2026-10-26"}]
        T.write(p, c)
        p = os.path.join(self.root, "panel.json")
        panel = T.load(p)
        panel["assessment"].update(settings)
        T.write(p, panel)

    def windows(self, upto, low=()):
        """Windows DAYS[0] to DAYS[upto]; on the indexes in `low` the old checkpoint has only four providers."""
        for i in range(upto + 1):
            make_window(self.root, DAYS[i], {OLD: provs("1", 4 if i in low else 6), NEW: provs("1.1")})

    def run_to(self, i):
        assess._WINDOW_CACHE.clear()
        return assess.assess_all(self.root, today=dt.date.fromisoformat(DAYS[i]),
                                 now=dt.datetime.fromisoformat(DAYS[i] + "T14:45:00+00:00"), verbose=False)

    def rec(self, i, cp):
        return T.load(os.path.join(self.root, "data", "assessments", DAYS[i], assess.slug_of(cp) + ".json"))

    # The assessor --------------------------------------------------------------

    def test_without_a_declared_change_the_challenger_stays_a_shadow(self):
        self.windows(10)
        self.run_to(10)
        self.assertEqual(self.rec(10, OLD)["status"], "published")
        self.assertEqual((self.rec(10, NEW)["status"], self.rec(10, NEW)["rollover"]), ("shadow", None))

    def test_both_are_published_side_by_side_with_the_daily_ratio(self):
        self.declare(DAYS[9], parallel_days=4)
        self.windows(11)
        self.run_to(11)
        self.assertEqual(self.rec(8, NEW)["status"], "shadow")               # before the period
        for i, n in ((9, 1), (10, 2), (11, 3)):
            old, new = self.rec(i, OLD), self.rec(i, NEW)
            self.assertEqual((old["reference"], old["status"]), (True, "published"))
            self.assertEqual((new["reference"], new["status"]), (False, "published"))
            self.assertEqual(old["rollover"], new["rollover"])
            r = new["rollover"]
            self.assertEqual((r["kind"], r["day"], r["days"], r["first_day"], r["last_day"], r["switch_day"]),
                             ("parallel", n, 4, DAYS[9], DAYS[12], DAYS[13]))
            want = (Decimal(new["price"]["output"]) / Decimal(old["price"]["output"])).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP)
            self.assertEqual(r["daily_ratio"]["output"], str(want))
            self.assertIsNone(r["average"])

    def test_the_average_on_the_last_day_and_the_switch_the_day_after(self):
        self.declare(DAYS[9], parallel_days=4)
        self.windows(14)
        self.run_to(14)
        daily = [Decimal(self.rec(i, NEW)["rollover"]["daily_ratio"]["output"]) for i in range(9, 13)]
        avg = str((sum(daily) / 4).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
        last = self.rec(12, NEW)["rollover"]
        self.assertEqual((last["day"], last["average"]["output"], last["average"]["days"]), (4, avg, 4))
        new, old = self.rec(13, NEW), self.rec(13, OLD)
        self.assertEqual((new["reference"], new["status"]), (True, "published"))
        self.assertEqual((old["reference"], old["status"], old["rollover"]), (False, "shadow", None))
        self.assertEqual((new["rollover"]["kind"], new["rollover"]["from"], new["rollover"]["ratio"]),
                         ("switch", "DeepSeek V4.1-Flash", avg))
        self.assertEqual(new["rollover"]["ratios"], {k: last["average"][k] for k in ("output", "input", "blended")})
        self.assertIsNone(self.rec(14, NEW)["rollover"])                     # only the first day says so
        self.assertTrue(self.rec(14, NEW)["reference"])

    def test_a_day_with_no_figure_on_one_side_has_no_ratio_and_is_left_out_of_the_average(self):
        self.declare(DAYS[9], parallel_days=4)
        self.windows(13, low=(10,))
        self.run_to(13)
        self.assertIsNone(self.rec(10, OLD)["price"])
        self.assertIsNone(self.rec(10, NEW)["rollover"]["daily_ratio"])
        self.assertEqual(self.rec(12, NEW)["rollover"]["average"]["days"], 3)

    def test_a_missed_window_in_the_period_is_not_published_on_both_sides(self):
        self.declare(DAYS[9], parallel_days=4)
        self.windows(9)
        self.windows(11)
        shutil.rmtree(os.path.join(self.root, "data", "probes", DAYS[10]))
        self.run_to(11)
        for cp in (OLD, NEW):
            r = self.rec(10, cp)
            self.assertEqual((r["status"], r["reason"]), ("not_published", "No probe ran in the window"))
            self.assertEqual(r["rollover"]["day"], 2)

    def test_the_emergency_rule_ends_the_period_on_its_tenth_day(self):
        self.declare(DAYS[9])                                                # 30 days
        self.windows(19, low=range(10, 15))                                  # days 2 to 6 below five
        self.run_to(19)
        r = self.rec(14, NEW)["rollover"]
        self.assertEqual((r["day"], r["days"], r["last_day"], r["emergency"]), (6, 10, DAYS[18], True))
        self.assertEqual(self.rec(10, NEW)["rollover"]["days"], 30)          # not known on day 2
        self.assertIsNotNone(self.rec(18, NEW)["rollover"]["average"])
        self.assertEqual(self.rec(19, NEW)["rollover"]["kind"], "switch")
        self.assertTrue(self.rec(19, NEW)["reference"])

    def test_the_emergency_rule_ends_the_period_at_once_after_the_tenth_day(self):
        self.declare(DAYS[9])
        self.windows(21, low=range(16, 21))                                  # days 8 to 12 below five
        self.run_to(21)
        r = self.rec(20, NEW)["rollover"]
        self.assertEqual((r["day"], r["days"], r["last_day"], r["emergency"]), (12, 12, DAYS[20], True))
        self.assertIsNotNone(r["average"])
        self.assertEqual(self.rec(21, NEW)["rollover"]["kind"], "switch")

    def test_a_change_must_be_well_formed(self):
        info = assess.checkpoints_info(T.load(os.path.join(ROOT, "candidates.json")))
        bad = [{"from": OLD, "to": NEW},                                            # no first day
               {"from": OLD, "to": "nobody/none", "first_day": "2026-11-25"},       # unknown checkpoint
               {"from": OLD, "to": "z-ai/glm-5.2", "first_day": "2026-11-25"},      # another grade
               {"from": OLD, "to": NEW, "first_day": "2026-11-28"}]                 # a Saturday
        for c in bad:
            with self.assertRaises(ValueError):
                assess.declared_changes({"changes": [c]}, info)
        self.assertEqual(assess.declared_changes({}, info), [])

    def test_every_declared_change_records_its_completed_run(self):
        info = assess.checkpoints_info(T.load(os.path.join(ROOT, "candidates.json")))
        for c in assess.declared_changes(T.load(os.path.join(ROOT, "candidates.json")), info):
            self.assertTrue(c.get("run_completed"), "a change is declared only once the run of 20 days is complete")
            self.assertLess(c["run_completed"], c["first_day"], "and before the period's first day")

    def test_the_change_declared_on_24_november_runs_to_7_january(self):
        """Rule 1.21: 1017's run was completed by the census of 24 November 2026. The period is 30 assessment
        days from Wednesday 25 November, leaving out 25 December and 1 January, so its last day is Thursday
        7 January 2027 and 1017 is the reference from Friday 8 January."""
        cands = T.load(os.path.join(ROOT, "candidates.json"))
        info = assess.checkpoints_info(cands)
        (c,) = [c for c in assess.declared_changes(cands, info) if c["to"] == NEW]
        self.assertEqual((c["from"], c["run_completed"]), (OLD, "2026-11-24"))
        self.assertTrue(info[OLD]["reference"])
        s = assess.settings(T.load(os.path.join(ROOT, "panel.json")))
        days, last, emergency = assess.period_timeline(c, s, ROOT, c["first"] - dt.timedelta(days=1))
        self.assertEqual((days[0], len(days), last, emergency), (dt.date(2026, 11, 25), 30, dt.date(2027, 1, 7), False))
        for holiday in (dt.date(2026, 12, 25), dt.date(2027, 1, 1)):
            self.assertNotIn(holiday, days)
        self.assertEqual(assess.windows_between(last + dt.timedelta(days=1), last + dt.timedelta(days=14))[0],
                         dt.date(2027, 1, 8))
        for day in (dt.date(2026, 11, 23), dt.date(2026, 11, 24)):      # nothing changes before the first day
            eff, current = assess.effective_info(info, [c], s, ROOT, day)
            self.assertEqual((eff[OLD]["publishes"], eff[NEW]["publishes"], current), (True, False, []))

    # The site, the post and the data -------------------------------------------

    def build(self, upto):
        out = os.path.join(self.root, "site")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "site", "publish.py"),
                            os.path.join(self.root, "data", "assessments"), out, "--preview",
                            "--today", DAYS[upto]], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return out

    def read(self, *parts):
        with open(os.path.join(*parts)) as f:
            return f.read()

    def test_the_pages_the_post_and_the_data_through_the_period(self):
        self.declare(DAYS[9], parallel_days=4)
        self.windows(14)
        self.run_to(14)
        out = self.build(14)
        first = self.read(out, "standard", DAYS[9], "index.html")
        self.assertIn("The reference is changing. From today", first)
        self.assertIn("today is day 1", first)
        self.assertIn('id="incoming"', first)
        self.assertIn('id="incoming-panel"', first)
        self.assertNotIn("The leading challenger", first)
        self.assertLess(first.index('id="panel"'), first.index('id="incoming-panel"'))
        last = self.read(out, "standard", DAYS[12], "index.html")
        self.assertIn("Today is the last day of the period", last)
        switch = self.read(out, "standard", DAYS[13], "index.html")
        self.assertIn("The reference changed today, from DeepSeek V4.1-Flash to DeepSeek V4.1-Flash-1017", switch)
        self.assertNotIn('id="incoming"', switch)
        later = self.read(out, "standard", DAYS[14], "index.html")
        self.assertNotIn("The reference changed today", later)
        self.assertIn("The leading challenger", later)                       # the old reference, for information
        post = self.read(out, "tweet", "standard", DAYS[9] + ".txt")
        self.assertIn("Day 1 of 4: the reference is changing.", post)
        self.assertIn("DeepSeek V4.1-Flash-1017: input", post)
        self.assertIn("Last day side by side. Average ratio",
                      self.read(out, "tweet", "standard", DAYS[12] + ".txt"))
        self.assertIn("New reference, ratio", self.read(out, "tweet", "standard", DAYS[13] + ".txt"))
        import csv
        with open(os.path.join(out, "data", "assessments.csv")) as f:
            rows = {r["date"]: r for r in csv.DictReader(f)}
        self.assertEqual((rows[DAYS[8]]["parallel_day"], rows[DAYS[8]]["challenger_status"]), ("", "shadow"))
        self.assertEqual((rows[DAYS[9]]["parallel_day"], rows[DAYS[9]]["parallel_days"],
                          rows[DAYS[9]]["challenger_status"]), ("1", "4", "published"))
        self.assertEqual(rows[DAYS[9]]["conversion_output_ratio"], "")
        avg = self.rec(12, NEW)["rollover"]["average"]["output"]
        self.assertEqual(rows[DAYS[12]]["conversion_output_ratio"], avg)
        self.assertEqual((rows[DAYS[13]]["rollover_ratio"], rows[DAYS[13]]["conversion_output_ratio"],
                          rows[DAYS[13]]["reference"]), (avg, avg, "DeepSeek V4.1-Flash-1017"))

    def test_the_post_in_the_period_fits_even_with_long_figures(self):
        roll = {"kind": "parallel", "from": "A model with a much longer name than any yet",
                "to": "Another model with a much longer name than any yet", "day": 1, "days": 30,
                "daily_ratio": {"output": "1.0301", "input": "1.0402", "blended": "1.0503"}, "average": None,
                "to_checkpoint": "x/y"}
        price = {"input": "12.3456", "output": "98.7654", "blended": "17.0000"}
        day = {"date": "2026-11-25", "name": roll["from"], "price": price, "contributors": 15, "panel": 18,
               "rollover": roll, "incoming": {"name": roll["to"], "price": price, "contributors": 15, "panel": 18,
                                              "rollover": roll}}
        text = publish.tweet_text(day, None, "https://hunterson.org", publish.grade("standard"))
        url = text.rsplit("\n", 1)[1]
        self.assertLessEqual(len(text) - len(url) + publish.URL_WEIGHT, publish.TWEET_LIMIT)
        self.assertIn("Reference: input $12.3456", text)

    def test_a_day_outside_a_period_keeps_its_record_fingerprint(self):
        day = {"date": "2026-11-13", "status": "published", "name": "DeepSeek V4.1-Flash", "price": {"output": "1"},
               "providers": [], "challenger": None}
        fields_before = publish.record_of(day, None)
        self.assertEqual(fields_before, publish.record_of(dict(day, incoming=None), None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
