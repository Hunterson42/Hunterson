"""
What moved the price: the split of a day's change into prices and who delivered (methodology, section 16;
decision D55; notes/like-for-like.md). It is worked out from the prices paid that the two days' pages show,
shown beneath the change line on pages written from 27 November 2026, and added to the data files.
Run with: python3 -m unittest discover tests
"""
import copy
import csv
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "site"))
import publish  # noqa: E402

ASSESS = os.path.join(ROOT, "data", "assessments")


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class SplitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.days = publish.load(ASSESS)["standard"]
        cls.at = {d["date"]: i for i, d in enumerate(cls.days)}

    def split(self, date):
        i = self.at[date]
        return publish.like_for_like(self.days[i], publish.day_before(self.days, i))

    def test_23_november_was_prices_down_and_who_delivered_up(self):
        """Crusoe cut its price from $1.20 to $0.78; AtlasCloud and GMICloud were no longer listed."""
        lfl = self.split("2026-11-23")
        self.assertEqual(lfl["providers"], 12)
        self.assertEqual(lfl["output"], {"prices": "-8.35", "delivered": "+5.82"})
        self.assertEqual(lfl["input"], {"prices": "-8.16", "delivered": "+6.42"})
        self.assertEqual(publish.moved_text(lfl), "Prices paid by the 12 providers in both figures: input down 8.16%, "
                         "output down 8.35%. Who delivered: input up 6.42%, output up 5.82%.")

    def test_a_price_cut_and_a_return_are_told_apart(self):
        self.assertEqual(self.split("2026-11-25")["output"], {"prices": "-1.30", "delivered": "0.00"})   # CoreWeave
        self.assertEqual(self.split("2026-11-26")["output"], {"prices": "0.00", "delivered": "-2.98"})   # Novita
        self.assertEqual(self.split("2026-11-18")["output"], {"prices": "0.00", "delivered": "-4.39"})   # Baidu

    def test_the_two_parts_multiply_to_the_published_change(self):
        n = 0
        for i, d in enumerate(self.days):
            lfl = publish.like_for_like(d, publish.day_before(self.days, i))
            if not lfl:
                continue
            b = publish.day_before(self.days, i)
            for side in ("input", "output"):
                total = Decimal(d["price"][side]) / Decimal(b["price"][side])
                parts = (1 + Decimal(lfl[side]["prices"]) / 100) * (1 + Decimal(lfl[side]["delivered"]) / 100)
                self.assertLess(abs(parts - total), Decimal("0.0002"), (d["date"], side))
            n += 1
        self.assertGreater(n, 10)

    def test_not_shown_without_a_price_the_day_before(self):
        self.assertIsNone(self.split("2026-11-03"))      # the first assessment: the day before was shadow
        self.assertIsNone(self.split("2026-11-17"))      # 16 November had no price
        self.assertIsNone(publish.day_before(self.days, self.at["2026-11-17"]))

    def test_not_shown_across_a_change_of_reference_or_with_fewer_than_five_in_both(self):
        day, before = self.days[self.at["2026-11-23"]], self.days[self.at["2026-11-20"]]
        self.assertIsNone(publish.like_for_like(dict(day, checkpoint="deepseek/deepseek-v4.1-flash-1017"), before))
        few = dict(day, providers=[q for q in day["providers"] if q["provider"] in ("Cohere", "CoreWeave", "Crusoe", "Makora")])
        self.assertIsNone(publish.like_for_like(few, before))

    def test_the_next_assessment_day_skips_weekends_and_the_two_holidays(self):
        self.assertEqual(publish.next_assessment_day("2026-11-20"), "2026-11-23")
        self.assertEqual(publish.next_assessment_day("2026-12-24"), "2026-12-28")
        self.assertEqual(publish.next_assessment_day("2026-12-31"), "2027-01-04")

    def test_hidden_when_nothing_moved(self):
        self.assertEqual(publish.moved_html(self.split("2026-11-24")), "")       # the change line says "Unchanged"
        self.assertIn('href="%s"' % publish.LIKE_FOR_LIKE_NOTE, publish.moved_html(self.split("2026-11-23")))

    def test_the_incoming_reference_is_split_against_its_own_figure(self):
        i = self.at["2026-11-26"]
        summary, _ = publish.incoming_html(self.days[i], publish.day_before(self.days, i))
        self.assertIn("What moved it since 25 November.", summary)
        self.assertIn("Who delivered: input up 8.27%, output up 7.62%.", summary)    # Baidu and DeepInfra rate-limited


class SiteTests(unittest.TestCase):
    """Pages already written keep their record and their design; new pages and the data files carry the split."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.out = os.path.join(cls.tmp, "site")
        shutil.copytree(os.path.join(ROOT, "docs"), cls.out)
        cls.notes = json.loads(read("site_notes.json"))["notes"]
        publish.build(ASSESS, cls.out, notes=cls.notes)
        cls.fresh = os.path.join(cls.tmp, "fresh")
        publish.build(ASSESS, cls.fresh, preview=True, notes=cls.notes)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_pages_already_written_are_unchanged(self):
        for day in sorted(os.listdir(os.path.join(ROOT, "docs", "standard"))):
            old = os.path.join(ROOT, "docs", "standard", day, "index.html")
            if os.path.isfile(old):
                with open(old, encoding="utf-8") as a, open(os.path.join(self.out, "standard", day, "index.html"), encoding="utf-8") as b:
                    self.assertEqual(a.read(), b.read(), day)

    def test_a_new_page_shows_it_beneath_the_change(self):
        with open(os.path.join(self.fresh, "standard", "2026-11-23", "index.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn('<p class="fix-moved">What moved it since 20 November. Prices paid by the 12 providers in both figures: '
                      'input down 8.16%, output down 8.35%. Who delivered: input up 6.42%, output up 5.82%.', html)
        self.assertLess(html.index('class="fix-change"'), html.index('class="fix-moved"'))
        with open(os.path.join(self.fresh, "standard", "2026-11-24", "index.html"), encoding="utf-8") as f:
            self.assertNotIn('class="fix-moved"', f.read())

    def test_the_data_files_carry_it(self):
        with open(os.path.join(self.out, "data", "assessments.csv"), encoding="utf-8") as f:
            rows = {r["date"]: r for r in csv.DictReader(f) if r["grade"] == "standard"}
        r = rows["2026-11-23"]
        self.assertEqual((r["like_for_like_providers"], r["output_change_from_prices"], r["output_change_from_delivery"],
                          r["input_change_from_prices"], r["input_change_from_delivery"]), ("12", "-8.35", "+5.82", "-8.16", "+6.42"))
        self.assertEqual(rows["2026-11-17"]["like_for_like_providers"], "")
        with open(os.path.join(self.out, "data", "index.html"), encoding="utf-8") as f:
            page = f.read()
        for col in ("like_for_like_providers", "input_change_from_prices", "output_change_from_delivery"):
            self.assertIn("<code>%s</code>" % col, page)


class NoteTests(unittest.TestCase):
    """Section 16: each further figure is defined in a published note, with its sources, before it is first published."""

    def test_the_note_defines_it_and_is_published_with_the_repository(self):
        note = read("notes/like-for-like.md")
        for text in ("section 16", "interquartile mean", "at least five providers", "four decimal places",
                     "like_for_like_providers", "input_change_from_prices", "output_change_from_prices",
                     "input_change_from_delivery", "output_change_from_delivery", "27 November 2026"):
            self.assertIn(text, note)
        self.assertNotRegex(note, "[\u2013\u2014!]")
        self.assertTrue(publish.LIKE_FOR_LIKE_NOTE.endswith("/notes/like-for-like.md"))
        self.assertIn("notes", re.search(r"DIRS=\(([^)]*)\)", read("scripts/mirror.sh")).group(1).split())


if __name__ == "__main__":
    unittest.main()
