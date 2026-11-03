"""
Checks on the site's hand-written pages, the census and the licence, which the
publisher does not build: each carries the site's header, with the same menu as
the price pages, and the census page no longer says the price is not yet assessed.
Run with: python3 -m unittest discover tests
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ["docs/census/index.html", "docs/licence/index.html"]


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def menu(html):
    nav = re.search(r'<nav aria-label="Site">(.*?)</nav>', html, re.S)
    return re.findall(r">([^<]+)</a>", nav.group(1)) if nav else []


class SitePageTests(unittest.TestCase):
    def test_every_page_has_the_price_pages_menu(self):
        expected = menu(read("scripts/site/page.html"))
        self.assertEqual(expected, ["Price", "Methodology", "Census", "Data", "About"])
        for rel in PAGES:
            html = read(rel)
            self.assertEqual(menu(html), expected, rel)
            self.assertIn('class="home" href="../"', html, rel)

    def test_the_census_page_says_what_it_is(self):
        html = read("docs/census/index.html")
        self.assertNotIn("No price is being assessed", html)
        self.assertNotIn("Census phase", html)
        self.assertIn("<h1>Census of models and providers</h1>", html)
        self.assertIn('aria-current="page">Census</a>', html)

    def test_the_fonts_the_pages_load_exist(self):
        for rel in PAGES:
            for font in re.findall(r'url\("\.\./assets/fonts/([^"]+)"\)', read(rel)):
                self.assertTrue(os.path.exists(os.path.join(ROOT, "scripts", "site", "assets", "fonts", font)), font)


if __name__ == "__main__":
    unittest.main()
