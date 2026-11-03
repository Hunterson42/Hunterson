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


if __name__ == "__main__":
    unittest.main()
