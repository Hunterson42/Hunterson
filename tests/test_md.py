"""
Tests for scripts/site/md.py, the Markdown renderer behind the site's documents,
and a check that each document the site shows renders with nothing left over.
Run with: python3 -m unittest discover tests
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "site"))
import md  # noqa: E402
import sitepages  # noqa: E402


class MarkdownTests(unittest.TestCase):
    def test_headings_take_githubs_anchors(self):
        out, heads = md.render("# Title\n\n## 1. Who grants this licence\n\n## 1. Who grants this licence")
        self.assertIn('<h2 id="1-who-grants-this-licence">1. Who grants this licence</h2>', out)
        self.assertIn('id="1-who-grants-this-licence-1"', out)
        self.assertEqual(heads[0], (1, "Title", "title"))

    def test_paragraphs_lists_rules_and_tables(self):
        out, _ = md.render("One\ntwo.\n\n---\n\n- a\n- b\n\n3. c\n4. d\n\n| A | B |\n|---|---|\n| x | `y` |\n")
        self.assertIn("<p>One two.</p>", out)
        self.assertIn("<hr>", out)
        self.assertIn("<ul>\n<li>a</li>\n<li>b</li>\n</ul>", out)
        self.assertIn('<ol start="3">', out)
        self.assertIn('<th scope="col">A</th>', out)
        self.assertIn("<td><code>y</code></td>", out)

    def test_inline_marks_links_and_addresses(self):
        link = sitepages.linker("../")
        out, _ = md.render("**Bold** and *it*, see [the licence](LICENCE-DATA.md#3-free-use), "
                           "[notes](notes/selection.md), https://example.org/x. and a@b.org", link)
        self.assertIn("<strong>Bold</strong>", out)
        self.assertIn("<em>it</em>", out)
        self.assertIn('<a href="../licence/#3-free-use">the licence</a>', out)
        self.assertIn('<a href="https://github.com/Hunterson42/Hunterson/blob/main/notes/selection.md">notes</a>', out)
        self.assertIn('<a href="https://example.org/x">https://example.org/x</a>.', out)
        self.assertIn('<a href="mailto:a@b.org">a@b.org</a>', out)

    def test_html_in_the_text_is_shown_not_run(self):
        out, _ = md.render("A <script>x</script> & `<b>`\n\n```\n<i>a</i>\n```")
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("&amp;", out)
        self.assertIn("<code>&lt;b&gt;</code>", out)
        self.assertIn("<pre><code>&lt;i&gt;a&lt;/i&gt;</code></pre>", out)

    def test_sections_are_taken_by_title(self):
        text = "# R\n\n## A\n\none\n\n## B\n\ntwo\n\n### B1\n\nthree\n\n## C\n\nfour"
        self.assertEqual(md.section(text, ["B"]), "## B\n\ntwo\n\n### B1\n\nthree\n")
        with self.assertRaises(ValueError):
            md.section(text, ["D"])

    def test_every_document_renders_with_nothing_left_over(self):
        for name in [d[0] for d in sitepages.DOCS] + ["README.md"]:
            with open(os.path.join(ROOT, name), encoding="utf-8") as f:
                out, heads = md.render(f.read(), sitepages.linker("../"))
            text = re.sub(r"<pre>.*?</pre>|<code>.*?</code>", "", out, flags=re.S)
            text = re.sub(r"<[^>]+>", "\n", text)
            self.assertNotRegex(text, r"\*\*|\]\(|^\s*\|", name)
            self.assertTrue(heads, name)
            self.assertNotIn("\x00", out, name)

    def test_the_methodology_states_its_version(self):
        with open(os.path.join(ROOT, "METHODOLOGY.md"), encoding="utf-8") as f:
            self.assertEqual(sitepages.methodology_version(f.read()), ("1.0", "30 October 2026"))


if __name__ == "__main__":
    unittest.main()
