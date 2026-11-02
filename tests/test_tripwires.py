"""
Tests for scripts/tripwires.py, on made-up assessments, census and market data.
Run with: python3 -m unittest discover tests
"""
import contextlib
import datetime as dt
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import tripwires  # noqa: E402

REF, CH = "deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4.1-flash-1017"


def weekdays(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5 and (d.month, d.day) not in ((12, 25), (12, 26), (1, 1)):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


class Tree:
    def __init__(self, launch="2026-11-03", first="2026-10-15"):
        self.root = tempfile.mkdtemp()
        self.write("panel.json", {"launch_date": launch, "assessment": {"first_window": first}})
        self.write("data/census/2026-10-15/models.json", {"data": [
            {"id": REF, "canonical_slug": REF + "-20260910"}, {"id": CH, "canonical_slug": CH + "-20261017"}]})
        self.write("data/oversight.json", {"lapse_days": 45, "confirmed": ["2026-11-02"], "suspensions": []})

    def write(self, rel, obj):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(obj, f)

    def day(self, d, contributors=13, panel=16, receipt_fails=0, cached=0, reason=None, depth=16, ch_panel=15):
        price = None
        if contributors >= 5 and not reason:
            und = "1.0000"
            price = {"output": "%.4f" % (1 - depth / 100), "input": "0.2000", "blended": "0.2400"}
        providers = [{"provider": "P%d" % i, "result": "contributor", "tests": {"Receipt": i >= receipt_fails}}
                     for i in range(panel - cached)]
        providers += [{"provider": "C%d" % i, "result": "excluded", "reason": "Clean: cached input tokens in the usage record",
                       "tests": {"Receipt": True}} for i in range(cached)]
        status = "shadow" if d.isoformat() < "2026-11-03" else ("published" if price else "not_published")
        self.write("data/assessments/%s/ref.json" % d, {
            "checkpoint": REF, "name": "DeepSeek V4.1-Flash", "grade": "Standard", "reference": True,
            "status": status, "reason": reason, "panel": 0 if reason else panel, "contributors": contributors,
            "price": price, "undiscounted": {"output": und} if price else None, "providers": [] if reason else providers})
        self.write("data/assessments/%s/ch.json" % d, {
            "checkpoint": CH, "name": "DeepSeek V4.1-Flash-1017", "grade": "Standard", "reference": False,
            "status": "shadow", "panel": ch_panel, "contributors": 8, "price": None, "providers": []})

    def tokens(self, ratios, end):
        """ratios[i] is the challenger's tokens over the reference's on the i-th of the days ending the day before end."""
        rows = []
        for i, r in enumerate(ratios):
            d = (end - dt.timedelta(days=len(ratios) - i)).isoformat()
            rows += [{"date": d, "model_permaslug": REF + "-20260910", "total_tokens": "1000"},
                     {"date": d, "model_permaslug": CH + "-20261017", "total_tokens": str(1000 * r)}]
        self.write("data/market/x/rankings.json", {"data": rows})
        self.write("data/market/x/manifest.json", {"requests": [{"dataset": "/datasets/rankings-daily",
                                                                  "request": "rankings", "pages": [{"file": "rankings.json"}]}]})

    def run(self, today):
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            text, newly = tripwires.report(self.root, today)
            with contextlib.redirect_stdout(io.StringIO()):
                code = tripwires.main(["--today", today.isoformat(), "--write"])
            return text, newly, code
        finally:
            os.chdir(cwd)

    def close(self):
        shutil.rmtree(self.root)


class TripwireTests(unittest.TestCase):
    def setUp(self):
        self.t = Tree()

    def tearDown(self):
        self.t.close()

    def fill(self, days, **kw):
        for d in days:
            self.t.day(d, **kw)

    def test_a_quiet_day_is_clear_and_writes_the_report(self):
        days = weekdays(dt.date(2026, 10, 15), 20)
        self.fill(days)
        text, newly, code = self.t.run(days[-1])
        self.assertEqual((newly, code), ([], 0))
        self.assertNotIn("TRIPPED", text)
        self.assertTrue(os.path.exists(os.path.join(self.t.root, "data", "tripwires", days[-1].isoformat() + ".md")))

    def test_1_trips_on_the_twentieth_day_without_a_figure_from_launch(self):
        days = weekdays(dt.date(2026, 10, 15), 40)
        launch = days.index(dt.date(2026, 11, 3))
        self.fill(days[:launch])
        self.fill(days[launch:], contributors=4)
        _, newly, code = self.t.run(days[launch + 19])
        self.assertEqual((newly, code), (["1"], 3))
        text, newly, code = self.t.run(days[launch + 20])
        self.assertEqual((newly, code), ([], 0))
        self.assertIn("Tripwire 1, too few contributors: TRIPPED", text)

    def test_6_trips_on_the_third_missed_day_in_thirty(self):
        days = weekdays(dt.date(2026, 10, 15), 25)
        self.fill(days)
        for d in (days[5], days[12]):
            self.t.day(d, contributors=0, reason="No probe ran in the window")
        self.assertEqual(self.t.run(days[-1])[1], [])
        self.t.day(days[-1], contributors=0, reason="The probe did not finish in the window")
        self.assertEqual(self.t.run(days[-1])[1], ["6"])

    def test_9_trips_on_the_fifth_day_of_receipt_failures(self):
        days = weekdays(dt.date(2026, 10, 15), 15)
        self.fill(days[:10])
        self.fill(days[10:], receipt_fails=5)
        self.assertEqual(self.t.run(days[13])[1], [])
        self.assertEqual(self.t.run(days[14])[1], ["9"])
        self.fill(days[10:], receipt_fails=4)                  # a quarter exactly is not more than a quarter
        self.assertEqual(self.t.run(days[14])[1], [])

    def test_11_trips_on_the_twentieth_day_above_twice(self):
        days = weekdays(dt.date(2026, 10, 15), 25)
        self.fill(days)
        end = days[-1]
        self.t.tokens([1.5] + [2.5] * 19, end)                 # 19 days above twice
        self.assertEqual(self.t.run(end)[1], [])
        nxt = end + dt.timedelta(days=1 if end.weekday() < 4 else 3)
        self.t.day(nxt)
        self.t.tokens([1.5] + [2.5] * 20, nxt)                 # the twentieth; the previous window saw fewer
        text, newly, _ = self.t.run(nxt)
        self.assertEqual(newly, ["11"])
        self.assertIn("2.50 times the reference's", text)

    def test_11_trips_when_the_discount_deepens_by_ten_points(self):
        days = weekdays(dt.date(2026, 10, 15), 22)
        self.fill(days[:21], depth=16)
        self.t.day(days[21], depth=25.9)
        self.assertEqual(self.t.run(days[21])[1], [])
        self.t.day(days[21], depth=26)
        self.assertEqual(self.t.run(days[21])[1], ["11"])

    def test_d35_trips_on_the_fifth_window_of_caching(self):
        days = weekdays(dt.date(2026, 10, 15), 12)
        self.fill(days[:7])
        self.fill(days[7:], cached=5)
        self.assertEqual(self.t.run(days[10])[1], [])
        self.assertEqual(self.t.run(days[11])[1], ["D35"])

    def test_oversight_reminds_seven_days_and_two_days_before(self):
        days = weekdays(dt.date(2026, 10, 15), 45)
        self.fill(days)
        self.assertEqual(self.t.run(dt.date(2026, 12, 9))[1], [])
        self.assertEqual(self.t.run(dt.date(2026, 12, 10))[1], ["O7"])      # suspends from 18 December
        self.assertEqual(self.t.run(dt.date(2026, 12, 11))[1], [])
        self.assertEqual(self.t.run(dt.date(2026, 12, 15))[1], ["O2"])


if __name__ == "__main__":
    unittest.main()
