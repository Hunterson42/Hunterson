"""
Checks on methodology 1.0 and the IOSCO statement beside it.
Run with: python3 -m unittest discover tests
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


PARAGRAPHS = ["1.%d" % n for n in range(1, 7)] + ["2.%d" % n for n in range(1, 22) if n != 13]


class MethodologyTests(unittest.TestCase):
    def test_every_square_bracket_is_settled(self):
        text = re.sub(r"\[[^\]]*\]\([^)]*\)", "", read("METHODOLOGY.md"))     # links are not brackets
        self.assertNotIn("[", text, "a square bracket is left unsettled in version 1.0")

    def test_version_and_panel_agree(self):
        import json
        self.assertIn("Version 1.0, ", read("METHODOLOGY.md"))
        with open(os.path.join(ROOT, "panel.json")) as f:
            self.assertEqual(json.load(f)["assessment"]["methodology_version"], "1.0")

    def test_the_tie_rule_starts_on_a_stated_day_and_is_the_only_use_of_market_data(self):
        text = read("METHODOLOGY.md")
        self.assertIn("The tie rule applies from the census of 31 October 2026.", text)
        self.assertIn("It is the only place in these rules where the venue's market data is used.", text)

    def test_section_17_points_to_the_statement(self):
        text = read("METHODOLOGY.md")
        section = text[text.index("## 17."):text.index("## 18.")]
        self.assertIn("IOSCO.md", section)
        self.assertNotIn("written to follow", section)

    def test_the_statement_covers_every_paragraph(self):
        rows = [l for l in read("IOSCO.md").splitlines() if re.match(r"\| [12]\.\d", l)]
        found = {re.match(r"\| ([12]\.\d+)", l).group(1) for l in rows}
        self.assertEqual(found, set(PARAGRAPHS))
        for row in rows:
            self.assertRegex(row.rstrip(" |").split("|")[-1].strip(),
                             r"^(Met|Met in another form|Met, more strictly|Partly met|Not met|Not applicable|Met from the first publication)$")

    def test_the_statement_is_public(self):
        self.assertRegex(read("scripts/mirror.sh"), r"FILES=\([^)]*\bIOSCO\.md\b")

    def test_no_dashes_the_house_style_forbids(self):
        for rel in ("METHODOLOGY.md", "IOSCO.md"):
            self.assertNotRegex(read(rel), "[–—]", rel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
