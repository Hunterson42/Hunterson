"""
Tests for scripts/probe.py against the mock in tests/mock_openrouter.py.
Run from the repository root:  python3 tests/test_probe.py
Nothing here touches the real OpenRouter or spends money.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import mock_openrouter  # noqa: E402

CENSUS = sorted(glob.glob(os.path.join(ROOT, "data", "census", "*")))[-1]


def load(path):
    with open(path) as f:
        return json.load(f)


class ProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = mock_openrouter.start(CENSUS)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/api/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        for name in ("candidates.json", "panel.json"):
            shutil.copy(os.path.join(ROOT, name), self.dir)
        with open(os.path.join(self.dir, "prompt.txt"), "w") as f:
            f.write("INSTRUCTIONS\n\nACT I. SCENE II.\nThe island.\n")
        mock_openrouter.SEEN.clear()

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_probe(self, *args, key="test-key", panel_changes=None):
        if panel_changes:
            p = os.path.join(self.dir, "panel.json")
            with open(p) as f:
                panel = json.load(f)
            panel.update(panel_changes)
            with open(p, "w") as f:
                json.dump(panel, f)
        env = dict(os.environ, OPENROUTER_BASE=self.base, OPENROUTER_API_KEY=key)
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "probe.py"), *args],
                              cwd=self.dir, env=env, capture_output=True, text=True, timeout=120)

    def expected_targets(self):
        """Distinct providers at fp8 in the saved census, per probed checkpoint."""
        n = 0
        for cp in ("z-ai/glm-5.3-flash", "deepseek/deepseek-v4.1-flash"):
            with open(os.path.join(CENSUS, "endpoints", cp.replace("/", "__") + ".json")) as f:
                eps = json.load(f)["data"]["endpoints"]
            n += len({e["provider_name"] for e in eps if e.get("quantization") == "fp8"})
        return n

    def test_rehearsal_writes_everything(self):
        r = self.run_probe("--rehearsal")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = glob.glob(os.path.join(self.dir, "data", "rehearsals", "*"))
        self.assertEqual(len(out), 1)
        manifest = load((os.path.join(out[0], "manifest.json")))
        n = self.expected_targets()
        self.assertEqual(len(manifest["targets"]), n)
        self.assertEqual(manifest["requests_made"], 3 * n)
        self.assertEqual(len(os.listdir(os.path.join(out[0], "listing"))), 2)
        recs = [load((p)) for p in glob.glob(os.path.join(out[0], "requests", "*.json"))]
        self.assertEqual(len(recs), 3 * n)
        good = [x for x in recs if not x["error"]]
        for x in good:
            self.assertEqual(x["finish_reason"], "length")
            self.assertEqual(x["usage"]["cost"], 0.00123)
            self.assertTrue("".join(c.get("text", "") for c in x["chunks"]).startswith("ISLAND DUKE Prospero"))
            self.assertIsNotNone(x["first_token_s"])
        self.assertEqual(manifest["requests_with_error"], len(recs) - len(good))

    def test_requests_are_pinned_and_reasoning_off(self):
        self.run_probe("--rehearsal")
        self.assertTrue(mock_openrouter.SEEN)
        nonces = set()
        for body in mock_openrouter.SEEN:
            self.assertEqual(len(body["provider"]["only"]), 1)
            self.assertFalse(body["provider"]["allow_fallbacks"])
            self.assertEqual(body["reasoning"], {"enabled": False})
            self.assertEqual(body["max_tokens"], 500)
            first_line = body["messages"][0]["content"].splitlines()[0]
            self.assertTrue(first_line.startswith("PROBE "))
            nonces.add(first_line)
        self.assertEqual(len(nonces), len(mock_openrouter.SEEN), "every request needs its own first line")

    def test_one_endpoint_per_provider_lowest_price(self):
        self.run_probe("--rehearsal")
        tags = {b["provider"]["only"][0] for b in mock_openrouter.SEEN}
        with open(os.path.join(CENSUS, "endpoints", "z-ai__glm-5.3-flash.json")) as f:
            eps = json.load(f)["data"]["endpoints"]
        for ep in eps:
            if ep.get("quantization") != "fp8":
                self.assertNotIn(ep["tag"], tags, "a non-native endpoint was probed")

    def test_failures_are_recorded_not_fatal(self):
        self.run_probe("--rehearsal")
        out = glob.glob(os.path.join(self.dir, "data", "rehearsals", "*", "requests", "*.json"))
        recs = [load((p)) for p in out]
        refused = [x for x in recs if x["target"].get("tag") == mock_openrouter.REFUSE_TAG]
        broken = [x for x in recs if x["target"].get("tag") == mock_openrouter.BREAK_TAG]
        if refused:
            self.assertTrue(all(x["http_status"] == 404 and x["error_body"] for x in refused))
        if broken:
            self.assertTrue(all(x["error"] == "error in stream" for x in broken))
        self.assertTrue(refused or broken, "census day has neither test tag at fp8")

    def test_daily_run_never_overwrites(self):
        changes = {"round_spacing_minutes": 0}
        first = self.run_probe(panel_changes=changes)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_probe()
        self.assertIn("not overwriting", second.stdout)

    def test_missing_key_is_recorded(self):
        r = self.run_probe("--rehearsal", key="")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = glob.glob(os.path.join(self.dir, "data", "rehearsals", "*", "requests", "*.json"))
        self.assertTrue(all(load((p))["error"] == "missing key OPENROUTER_API_KEY" for p in out))

    def test_test_mode_prints_and_writes_nothing(self):
        r = self.run_probe("--test")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("input tokens:", r.stdout)
        self.assertIn("receipt / listed:", r.stdout)
        self.assertEqual(r.stdout.count("via "), 2)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "data")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
