"""
Tests for the Hunterson Data Licence (decision D32).
Run from the repository root:  python3 tests/test_licence.py

The licence is published twice: as LICENCE-DATA.md in the repository and as the
page docs/licence/index.html, served at https://hunterson.org/licence/. These
tests fail if the two ever say different things, or if the methodology stops
pointing to the licence.
"""
import html
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, rel)) as f:
        return f.read()


def plain_markdown_lines(text):
    """Each line of the licence as words, without markdown."""
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or re.match(r"^\|[-| ]+\|$", line):
            continue
        if line.startswith("|"):
            lines += [c.strip() for c in line.strip("|").split("|") if c.strip()]
            continue
        line = re.sub(r"^#+ |^\d+\. ", "", line).replace("`", "")
        lines.append(line)
    return lines


def page_text(text):
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)       # block elements already sit on lines of their own
    return re.sub(r"\s+", " ", html.unescape(text))


class LicenceTests(unittest.TestCase):
    def test_page_says_what_the_licence_says(self):
        page = page_text(read("docs/licence/index.html"))
        for line in plain_markdown_lines(read("LICENCE-DATA.md")):
            self.assertIn(re.sub(r"\s+", " ", line), page, "missing from the page: " + line)

    def test_page_has_a_title_and_works_without_external_files(self):
        page = read("docs/licence/index.html")
        self.assertIn("<title>Hunterson Data Licence</title>", page)
        self.assertNotRegex(page, r"<(script|link)\b")

    def test_methodology_points_to_the_licence(self):
        method = read("METHODOLOGY.md")
        section = method[method.index("## 13. Using the numbers"):method.index("## 14.")]
        self.assertIn("https://hunterson.org/licence/", section)
        self.assertIn("LICENCE-DATA.md", section)
        self.assertNotIn("for any purpose", section)

    def test_repository_licence_carves_out_the_figures(self):
        text = read("LICENSE.md")
        self.assertIn("LICENCE-DATA.md", text)
        self.assertIn("CC0 1.0", text)

    def test_no_dashes_the_house_style_forbids(self):
        for rel in ("LICENCE-DATA.md", "docs/licence/index.html"):
            self.assertNotRegex(read(rel), "[–—]", rel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
