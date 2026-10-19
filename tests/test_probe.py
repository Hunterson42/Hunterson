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

_DAYS = sorted(glob.glob(os.path.join(ROOT, "data", "census", "*")))
if not _DAYS:
    print("These tests need the raw census, which is kept in the private repository. Skipped.")
    sys.exit(0)
CENSUS = _DAYS[-1]


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
        shutil.copy(os.path.join(ROOT, "candidates.json"), self.dir)
        # The control group's accounts are pointed at the mock too, so no test reaches a real provider.
        panel = load(os.path.join(ROOT, "panel.json"))
        for d in panel.get("direct", []):
            d["base_url"] = self.base
        with open(os.path.join(self.dir, "panel.json"), "w") as f:
            json.dump(panel, f)
        self.key_names = [d["key_env"] for d in panel.get("direct", [])]
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
        env = dict(os.environ, OPENROUTER_BASE=self.base, OPENROUTER_API_KEY=key, PROBE_ANY_DAY="1")
        env.update({name: key for name in self.key_names})
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "probe.py"), *args],
                              cwd=self.dir, env=env, capture_output=True, text=True, timeout=120)

    def expected_targets(self):
        """Distinct providers at fp8 in the saved census, per probed checkpoint, plus
        each control-group account that sells that checkpoint."""
        n = 0
        panel = load(os.path.join(ROOT, "panel.json"))
        for cp in panel["probe"]:
            n += sum(1 for d in panel.get("direct", []) if cp in d.get("models", {}))
            path = os.path.join(CENSUS, "endpoints", cp.replace("/", "__") + ".json")
            if not os.path.exists(path):
                continue          # not in this census day; the probe records it and moves on
            with open(path) as f:
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
        self.assertEqual(len(os.listdir(os.path.join(out[0], "listing"))), len(load(os.path.join(ROOT, "panel.json"))["probe"]))
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
        accounts = load(os.path.join(ROOT, "panel.json")).get("direct", [])
        for body in mock_openrouter.SEEN:
            self.assertEqual(body["max_tokens"], 500)
            if "provider" not in body:
                # Bought direct: the provider's own model name and its own switch for thinking.
                sellers = [d for d in accounts if body["model"] in d["models"].values()]
                self.assertTrue(sellers, body["model"])
                self.assertTrue(any(all(body.get(k) == v for k, v in d["extra"].items()) for d in sellers),
                                "a direct request must carry its account's switch for thinking")
                self.assertEqual(body["stream_options"], {"include_usage": True})
                nonces.add(body["messages"][0]["content"].splitlines()[0])
                continue
            self.assertEqual(len(body["provider"]["only"]), 1)
            self.assertFalse(body["provider"]["allow_fallbacks"])
            self.assertEqual(body["reasoning"], {"enabled": False})
            first_line = body["messages"][0]["content"].splitlines()[0]
            self.assertTrue(first_line.startswith("PROBE "))
            nonces.add(first_line)
        self.assertEqual(len(nonces), len(mock_openrouter.SEEN), "every request needs its own first line")

    def test_one_endpoint_per_provider_lowest_price(self):
        self.run_probe("--rehearsal")
        tags = {b["provider"]["only"][0] for b in mock_openrouter.SEEN if "provider" in b}
        first = load(os.path.join(ROOT, "panel.json"))["probe"][0]
        with open(os.path.join(CENSUS, "endpoints", first.replace("/", "__") + ".json")) as f:
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

    def test_unlisted_checkpoint_is_recorded_not_fatal(self):
        cands = os.path.join(self.dir, "candidates.json")
        c = load(cands)
        std = next(k for k in c["grades"] if k.startswith("Standard"))
        c["grades"][std].append({"openrouter_id": "test/not-listed", "native_precision": "fp8"})
        with open(cands, "w") as f:
            json.dump(c, f)
        probe = load(os.path.join(ROOT, "panel.json"))["probe"] + ["test/not-listed"]
        r = self.run_probe("--rehearsal", panel_changes={"probe": probe})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = glob.glob(os.path.join(self.dir, "data", "rehearsals", "*"))[0]
        listing = load(os.path.join(out, "listing", "test_not-listed.json"))
        self.assertIsNone(listing["response"])
        self.assertEqual(listing["error"], "HTTP 404")
        manifest = load(os.path.join(out, "manifest.json"))
        self.assertFalse([t for t in manifest["targets"] if t.startswith("test_not-listed")])
        self.assertTrue(manifest["targets"])      # the other checkpoints were still probed

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
        errors = {load(p)["target"]["route"]: load(p)["error"] for p in out}
        self.assertEqual(errors["openrouter"], "missing key OPENROUTER_API_KEY")
        self.assertTrue(all(load(p)["error"].startswith("missing key ") for p in out))

    def test_test_mode_prints_and_writes_nothing(self):
        r = self.run_probe("--test")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("input tokens:", r.stdout)
        self.assertIn("receipt / listed:", r.stdout)
        listed = [cp for cp in load(os.path.join(ROOT, "panel.json"))["probe"]
                  if os.path.exists(os.path.join(CENSUS, "endpoints", cp.replace("/", "__") + ".json"))]
        self.assertEqual(r.stdout.count("via "), len(listed))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "data")))

    def test_test_direct_gives_one_line_per_account(self):
        panel = load(os.path.join(ROOT, "panel.json"))
        novita = next(d for d in panel["direct"] if d["provider"] == "Novita")
        mock_openrouter.THINK_MODEL = novita["models"][panel["probe"][0]]     # a name only Novita uses
        try:
            r = self.run_probe("--test-direct")
        finally:
            mock_openrouter.THINK_MODEL = None
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [ln for ln in r.stdout.splitlines() if " OK " in ln or " ERROR " in ln]
        expected = sum(len([cp for cp in d["models"] if cp in panel["probe"]]) for d in panel["direct"])
        self.assertEqual(len(lines), expected)
        self.assertTrue(all(" OK in " in ln for ln in lines), r.stdout)
        thinking = [ln for ln in lines if "thinking YES" in ln]
        self.assertEqual(len(thinking), 1, "thinking sent as reasoning_content must be caught")
        self.assertTrue(thinking[0].startswith("Novita"))
        self.assertFalse([b for b in mock_openrouter.SEEN if "provider" in b], "only the control group is tested")
        self.assertFalse(os.path.exists(os.path.join(self.dir, "data")))

    def test_offwindow_reading_has_its_own_folder(self):
        r = self.run_probe("--offwindow", "weekend", panel_changes={"round_spacing_minutes": 0})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = glob.glob(os.path.join(self.dir, "data", "offwindow", "*"))
        self.assertEqual(len(out), 1)
        self.assertRegex(os.path.basename(out[0]), r"^\d{4}-\d{2}-\d{2}-\d{4}$")
        manifest = load(os.path.join(out[0], "manifest.json"))
        self.assertEqual((manifest["mode"], manifest["offwindow_kind"]), ("offwindow", "weekend"))
        self.assertEqual(manifest["requests_made"], 3 * self.expected_targets())
        self.assertFalse(os.path.exists(os.path.join(self.dir, "data", "probes")),
                         "an off-window reading must never land among the windows")

    def test_offwindow_needs_a_kind(self):
        r = self.run_probe("--offwindow")
        self.assertEqual(r.returncode, 2)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "data")))

    def test_each_request_has_a_total_time_limit(self):
        mock_openrouter.SLOW_TAG = "novita/fp8"
        try:
            r = self.run_probe("--test", panel_changes={"timeout_seconds": 2, "read_timeout_seconds": 1,
                                                        "probe": load(os.path.join(ROOT, "panel.json"))["probe"][:1]})
        finally:
            mock_openrouter.SLOW_TAG = None
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ERROR: time limit: no complete reply within 2 seconds", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
