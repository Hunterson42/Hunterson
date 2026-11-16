"""
Checks on the census page, which the publisher does not build: it carries the
site's header, with the same menu as every other page, and the same footer
links, and it no longer says the price is not yet assessed.
Run with: python3 -m unittest discover tests
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "site"))
import publish  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class CensusPageTests(unittest.TestCase):
    def test_the_census_page_has_the_sites_menu_and_footer(self):
        html = read("docs/census/index.html")
        self.assertIn(publish.nav_html("../", "Census"), html)
        self.assertIn(publish.foot_links_html("../"), html)
        self.assertIn('class="home" href="../"', html)
        self.assertIn(publish.head_links("../").splitlines()[0], html)

    def test_the_census_page_says_what_it_is(self):
        html = read("docs/census/index.html")
        self.assertNotIn("No price is being assessed", html)
        self.assertNotIn("Census phase", html)
        self.assertIn("<h1>Census of models and providers</h1>", html)

    def test_the_fonts_the_census_page_loads_exist(self):
        for font in re.findall(r'url\("\.\./assets/fonts/([^"]+)"\)', read("docs/census/index.html")):
            self.assertTrue(os.path.exists(os.path.join(ROOT, "scripts", "site", "assets", "fonts", font)), font)


class SiteNotesTests(unittest.TestCase):
    """site_notes.json is read by the Publish workflow each day, so a note added by
    pull request must be complete, dated, and in the site's house style."""

    def test_every_note_is_complete_and_shows_on_its_day(self):
        import datetime as dt
        import json
        notes = json.loads(read("site_notes.json"))["notes"]
        for n in notes:
            self.assertEqual(set(n), {"date", "grade", "title", "text"}, n)
            day = dt.date.fromisoformat(n["date"])
            self.assertIn(n["grade"], ("standard",))
            self.assertFalse(n["title"].endswith("."), "the page adds the full stop after the title")
            self.assertTrue(n["text"].endswith("."))
            self.assertNotRegex(n["title"] + n["text"], "[\u2013\u2014]")
            grade = {"key": n["grade"]}
            self.assertIn(n["title"], publish.notes_html(notes, grade, n["date"], "day"))
            later = (day + dt.timedelta(days=30)).isoformat()
            self.assertIn(n["title"], publish.notes_html(notes, grade, later, "latest"))
            for other in ((day - dt.timedelta(days=1)).isoformat(), (day + dt.timedelta(days=31)).isoformat()):
                self.assertNotIn(n["title"], publish.notes_html(notes, grade, other, "latest"))

    def test_every_note_is_dated_on_an_assessment_day(self):
        """A note shows on a permanent page only if its date has one: never a weekend,
        25 December or 1 January. A note about a past day is dated the next assessment
        day, since a day's page, once written, is never changed (the 16 November gap)."""
        import datetime as dt
        import json
        for n in json.loads(read("site_notes.json"))["notes"]:
            day = dt.date.fromisoformat(n["date"])
            self.assertLess(day.weekday(), 5, n["date"])
            self.assertNotIn((day.month, day.day), ((12, 25), (1, 1)), n["date"])


class CitePageTests(unittest.TestCase):
    """The citation kit (twelve-month strategy, phase 1): one page with everything a writer needs to cite a
    figure, built each day from the latest assessment, and linked from the menu and from each day's line."""

    @classmethod
    def setUpClass(cls):
        import shutil
        import tempfile
        cls.tmp = tempfile.mkdtemp()
        cls.out = os.path.join(cls.tmp, "site")
        shutil.copytree(os.path.join(ROOT, "docs"), cls.out)
        publish.build(os.path.join(ROOT, "data", "assessments"), cls.out,
                      notes=__import__("json").loads(read("site_notes.json"))["notes"])
        cls.html = open(os.path.join(cls.out, "cite", "index.html"), encoding="utf-8").read()
        rows = list(__import__("csv").DictReader(open(os.path.join(cls.out, "data", "assessments.csv"), encoding="utf-8")))
        cls.last = [r for r in rows if r["grade"] == "standard" and r["status"] == "published"][-1]

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp)

    def test_the_line_to_paste_is_the_latest_days_line(self):
        day = open(os.path.join(self.out, "standard", self.last["date"], "index.html"), encoding="utf-8").read()
        line = re.search(r'<p id="cite-text">(.*?)</p>', self.html).group(1)
        self.assertIn(self.last["output"], line)
        self.assertIn("https://hunterson.org/standard/%s/" % self.last["date"], line)
        if 'id="cite-text"' in day and "How to cite" in day:      # a page built since the kit
            self.assertEqual(line, re.search(r'<p id="cite-text">(.*?)</p>', day).group(1))

    def test_it_gives_the_addresses_the_licence_a_reference_and_a_contact(self):
        for text in ("https://hunterson.org/standard/YYYY-MM-DD/", "/og/standard/YYYY-MM-DD.png",
                     "../data/assessments.csv", "../data/latest.json", "../feed.xml", "@misc{hunterson-standard-",
                     "Source: Hunterson Standard Inference, Europe, hunterson.org", "../licence/",
                     "mailto:malcolm@hunterson.org?subject=Subscribe", "first Tuesday of each month"):
            self.assertIn(text.replace("&", "&amp;") if "&" in text else text, self.html, text)
        self.assertNotRegex(self.html, "[\u2013\u2014]")

    def test_it_is_in_the_menu_the_sitemap_and_beside_each_new_days_line(self):
        self.assertIn(publish.nav_html("../", "Cite"), self.html)
        self.assertIn("https://hunterson.org/cite/", open(os.path.join(self.out, "sitemap.xml")).read())
        fresh = os.path.join(self.tmp, "fresh")              # pages already written keep their old design
        publish.build(os.path.join(ROOT, "data", "assessments"), fresh, preview=True)
        day = open(os.path.join(fresh, "standard", self.last["date"], "index.html"), encoding="utf-8").read()
        self.assertIn('href="../../cite/">How to cite</a>', day)

    @unittest.skipUnless(os.path.isdir(os.path.join(ROOT, "register")), "the send log is kept in the private repository")
    def test_the_send_log_has_the_documented_columns_and_is_never_mirrored(self):
        header = read("register/sends.csv").splitlines()[0].split(",")
        guide = read("register/README.md")
        for col in header:
            self.assertIn("| `%s` |" % col, guide)
        mirror = read("scripts/mirror.sh")
        self.assertNotIn("register", re.search(r"DIRS=\(([^)]*)\)", mirror).group(1))
        self.assertIn('"${DST:?}/register"', mirror)


if __name__ == "__main__":
    unittest.main()
