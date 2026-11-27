"""
The note of 30 November 2026 on discount depth (methodology section 4.5; D40, tripwire 11). A note
quotes figures, and a published note is never changed, so every figure it gives is worked out again
here from the assessment files.
Run with: python3 -m unittest discover tests
"""
import json
import os
import sys
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import tripwires  # noqa: E402

REF = "deepseek-v4.1-flash"


def record(date, checkpoint=REF):
    with open(os.path.join(ROOT, "data", "assessments", date, checkpoint + ".json"), encoding="utf-8") as f:
        return json.load(f)


def one_place(x):
    return str(Decimal(x).quantize(Decimal("0.1")))


class DiscountDepthNoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "site_notes.json"), encoding="utf-8") as f:
            cls.note = [n for n in json.load(f)["notes"] if n["date"] == "2026-11-30"][0]
        days = sorted(d for d in os.listdir(os.path.join(ROOT, "data", "assessments"))
                      if os.path.isfile(os.path.join(ROOT, "data", "assessments", d, REF + ".json")))
        cls.depths = [(d, tripwires.depth(record(d))) for d in days]
        cls.depths = [(d, x) for d, x in cls.depths if x is not None]

    def depth_and_average(self, date):
        i = [d for d, _ in self.depths].index(date)
        prev = [x for _, x in self.depths[i - 20:i]]
        self.assertEqual(len(prev), 20)
        return self.depths[i][1], sum(prev) / len(prev)

    def test_the_depths_and_averages_it_quotes(self):
        text = self.note["text"]
        d26, a26 = self.depth_and_average("2026-11-26")
        d27, a27 = self.depth_and_average("2026-11-27")
        self.assertGreaterEqual(d26 - a26, 10)
        self.assertGreaterEqual(d27 - a27, 10)
        self.assertIn("discounts took %s per cent off the output price on 26 November and %s per cent on 27 November, "
                      "against %s and %s per cent on average" % (one_place(d26), one_place(d27), one_place(a26), one_place(a27)), text)
        self.assertLess(self.depths[[d for d, _ in self.depths].index("2026-11-25")][1] - a26, 10)   # first tripped on 26 November

    def test_the_providers_it_names(self):
        day = {q["provider"]: q for q in record("2026-11-27")["providers"]}
        before = {q["provider"]: q for q in record("2026-11-26")["providers"]}
        middle = [n for n, q in day.items() if q.get("in_mean")]
        self.assertEqual(len(middle), 6)
        discounted = sorted(n for n in middle if Decimal(day[n]["measured"]["discount"]) > 0)
        self.assertEqual(discounted, ["Crusoe", "Novita"])
        for name, paid in (("Crusoe", "0.7800"), ("Novita", "0.6000")):
            q = day[name]
            self.assertEqual(q["output"], paid)
            self.assertEqual((Decimal(paid) / (1 - Decimal(q["measured"]["discount"]))).quantize(Decimal("0.01")), Decimal("1.20"))
        both = [n for n, q in day.items() if q["result"] == "contributor" and before.get(n, {}).get("result") == "contributor"]
        self.assertTrue(both)
        for n in both:
            self.assertEqual((day[n]["output"], day[n]["input"]), (before[n]["output"], before[n]["input"]), n)
        self.assertEqual(day["SiliconFlow"]["result"], "excluded")
        self.assertFalse(day["SiliconFlow"]["tests"]["Fast enough"])
        self.assertEqual((before["SiliconFlow"]["output"], before["SiliconFlow"]["measured"]["discount"]), ("1.2000", "0"))
        crusoe_1017 = [q for q in record("2026-11-27", REF + "-1017")["providers"] if q["provider"] == "Crusoe"][0]
        self.assertEqual(crusoe_1017["output"], "0.7800")

    def test_it_is_shown_first_on_the_next_assessment_day(self):
        """Neither 26 nor 27 November's page can take it, since a day's page is written once."""
        self.assertEqual(self.note["date"], "2026-11-30")
        for d in ("2026-11-26", "2026-11-27"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "docs", "standard", d, "index.html")))
        self.assertIn("section 4.5", self.note["text"])


if __name__ == "__main__":
    unittest.main()
