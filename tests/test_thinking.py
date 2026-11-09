"""
Tests for scripts/thinking.py, the report on the research readings with thinking
left on (decision D52, roadmap step 63), on made-up readings.
Run with: python3 -m unittest discover tests
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import thinking  # noqa: E402

REF = "deepseek/deepseek-v4.1-flash"
LISTED = {"prompt": "0.0000003", "completion": "0.0000012"}
PIN, POUT = 0.3e-6, 1.2e-6


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f)


def rec(provider, out_tokens, reasoning=0, effort=None, out_price=POUT, answer="ISLAND DUKE Prospero\nLAST SPEAKER Sebastian\nOnce",
        error=None, started="2026-11-14T14:40:05Z"):
    if error:
        return {"target": {"checkpoint": REF, "route": "openrouter", "provider": provider, "listed": LISTED},
                "effort": effort, "started_utc": started, "http_status": 429, "error": error, "chunks": [],
                "usage": None}
    chunks = [{"t": 0.4, "reasoning": "Let me think about the passage."}] if reasoning else []
    chunks += [{"t": 2.5 if reasoning else 0.5, "text": answer}]
    cin, cout = 7900 * PIN, out_tokens * out_price
    return {"target": {"checkpoint": REF, "route": "openrouter", "provider": provider, "listed": LISTED},
            "effort": effort, "started_utc": started, "http_status": 200, "error": None, "chunks": chunks,
            "first_token_s": chunks[-1]["t"], "total_s": 30.0, "finish_reason": "length",
            "usage": {"prompt_tokens": 7900, "completion_tokens": out_tokens,
                      "completion_tokens_details": {"reasoning_tokens": reasoning},
                      "cost": cin + cout,
                      "cost_details": {"upstream_inference_prompt_cost": cin, "upstream_inference_completions_cost": cout}}}


class ThinkingReportTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        base = os.path.join(self.root, "data", "offwindow")
        self.weekend = os.path.join(base, "2026-11-14-1405")
        self.folder = os.path.join(base, "2026-11-14-1440-thinking")
        write(os.path.join(self.weekend, "manifest.json"),
              {"offwindow_kind": "weekend", "day": "2026-11-14", "started_utc": "2026-11-14T14:05:00Z"})
        for p in ("P1", "P2"):
            write(os.path.join(self.weekend, "requests", p + ".json"),
                  rec(p, 500, started="2026-11-14T14:05:10Z"))
        write(os.path.join(self.folder, "manifest.json"),
              {"offwindow_kind": "thinking", "day": "2026-11-14", "started_utc": "2026-11-14T14:40:00Z",
               "checkpoint": REF, "efforts": ["low", "high"], "max_output_tokens": 8000,
               "accept_line_1": "ISLAND DUKE Prospero", "accept_line_2": "LAST SPEAKER Sebastian"})
        recs = {
            "P1__low": rec("P1", 8000, 300, "low"),
            "P1__high": rec("P1", 8000, 1500, "high"),
            # P2 charges a tenth more per output token with thinking on, and ignores the effort.
            "P2__low": rec("P2", 8000, 900, "low", out_price=POUT * 1.1),
            "P2__high": rec("P2", 8000, 900, "high", out_price=POUT * 1.1, answer="ISLAND DUKE Antonio\nLAST SPEAKER Ariel"),
            "P3__high": rec("P3", 0, effort="high", error="HTTP 429"),
            "P3__low": rec("P3", 8000, 0, "low"),
        }
        for name, r in recs.items():
            write(os.path.join(self.folder, "requests", name + ".json"), r)

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_report(self, **kw):
        lines = []
        rows = thinking.report(self.folder, out=lines.append, **kw)
        return "\n".join(lines), rows

    def test_finds_the_same_days_weekend_reading(self):
        text, _ = self.run_report()
        self.assertIn("Thinking off for comparison: " + self.weekend, text)

    def test_each_reply_is_described(self):
        _, rows = self.run_report()
        d = {(p, e): x for p, e, x in rows}
        self.assertEqual(len(rows), 6)
        self.assertTrue(d[("P1", "high")]["thought"] and d[("P1", "high")]["correct"])
        self.assertEqual(d[("P1", "high")]["reasoning_tokens"], 1500)
        self.assertFalse(d[("P2", "high")]["correct"])
        self.assertFalse(d[("P3", "low")]["thought"], "no thinking tokens and no thinking text")
        self.assertFalse(d[("P3", "high")]["completed"])
        self.assertAlmostEqual(float(d[("P1", "low")]["receipt_gap"]), 0.0, places=6)
        self.assertGreater(float(d[("P2", "low")]["receipt_gap"]), 1)

    def test_price_on_against_off_and_the_effort_honoured(self):
        text, _ = self.run_report()
        rows = {(ln.split()[0], ln.split()[1]): ln for ln in text.splitlines() if ln[:2] in ("P1", "P2", "P3")}
        self.assertTrue(rows[("P1", "high")].endswith("1.000"), rows[("P1", "high")])
        self.assertTrue(rows[("P2", "high")].endswith("1.100"), rows[("P2", "high")])
        self.assertIn("no reply: HTTP 429", rows[("P3", "high")])
        self.assertIn("Effort high: 2 of 3 replied; 2 thought, median 1,200 thinking tokens (from 900 to 1,500)", text)
        self.assertIn("on 2 providers", text)
        self.assertIn("Effort honoured (high thinks at least a fifth more than low): 1 of 2; not: P2.", text)

    def test_against_another_folder_and_without_one(self):
        text, _ = self.run_report(against=self.weekend)
        self.assertIn("1.100", text)
        shutil.rmtree(self.weekend)
        text, _ = self.run_report()
        self.assertIn("no weekend reading that day", text)
        self.assertNotIn("on against off", text)

    def test_main_lists_every_thinking_reading(self):
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(thinking.main([]), 0)
            self.assertIn("2026-11-14-1440-thinking", out.getvalue())
            shutil.rmtree(os.path.join(self.root, "data"))
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(thinking.main([]), 0)
            self.assertIn("No thinking readings yet", out.getvalue())
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
