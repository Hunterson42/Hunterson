"""
Tests for scripts/gpuprices.py, the GPU-hour price readings (decision D36).
Run from the repository root:  python3 tests/test_gpuprices.py

A local web server stands in for the GPU clouds' APIs, with replies in the form
each provider documents, so nothing touches Novita, DeepInfra, RunPod or
Lambda. Each test copies the script into a throwaway repository with its own
gpu_sources.json pointing at that server.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEYS = {"NOVITA_API_KEY": "nov-secret-123", "DEEPINFRA_API_KEY": "di-secret-456",
        "RUNPOD_API_KEY": "rp-secret-789", "LAMBDA_API_KEY": "lam-secret-000"}

NOVITA_PAGE_1 = {"data": [{
    "id": "p-h100", "name": "1x H100 SXM 80GB", "type": "gpu", "category": "instance",
    "resource_spec": {"gpu": {"spec_id": "h100", "name": "NVIDIA H100 SXM 80GB", "memory_gb": 80,
                              "min": 1, "max": 8, "available": 3, "max_available": 8},
                      "cpu": 16, "memory_gb": 128},
    "pricing": {"precision": 5, "postpaid": {"base_price": 339000, "final_price": 339000, "unit": "per_hour"},
                "spot": {"base_price": 170000, "final_price": 170000, "unit": "per_hour"}, "prepaid": []},
    "inventory_state": "normal", "deployable": True}], "next_cursor": "page-2"}
NOVITA_PAGE_2 = {"data": [{
    "id": "p-4090", "name": "1x RTX 4090 24GB",
    "resource_spec": {"gpu": {"name": "NVIDIA GeForce RTX 4090", "memory_gb": 24, "min": 1, "max": 8}},
    "pricing": {"precision": 5, "postpaid": {"final_price": 35000, "unit": "per_hour"}, "spot": None},
    "inventory_state": "high"}], "next_cursor": ""}
DEEPINFRA = {"gpus": [{"gpu_config": "8xH100-80GB", "usd_per_hour": 19.92, "available": True},
                      {"gpu_config": "B200-180GB", "usd_per_hour": 4.49, "available": False}]}
RUNPOD = {"gpus": [{"id": "NVIDIA H200", "name": "H200 SXM", "memory": 141,
                    "price": {"secure": 3.59, "community": 3.29}, "availability": "LOW"}]}


class Mock(BaseHTTPRequestHandler):
    seen = []
    lambda_status = 500

    def log_message(self, *args):
        pass

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        auth = self.headers.get("Authorization", "")
        Mock.seen.append((url.path, auth))
        q = parse_qs(url.query)
        if url.path == "/novita/gpus/v2/products":
            if auth != "Bearer " + KEYS["NOVITA_API_KEY"]:
                return self.reply(401, {"error": "unauthorised"})
            return self.reply(200, NOVITA_PAGE_2 if q.get("cursor") == ["page-2"] else NOVITA_PAGE_1)
        if url.path == "/deepinfra/v1/containers/gpu_availability":
            if auth != "Bearer " + KEYS["DEEPINFRA_API_KEY"]:
                return self.reply(401, {"detail": "unauthorised"})
            # A reply that echoes the key, to prove it is removed before saving.
            return self.reply(200, dict(DEEPINFRA, debug={"token": KEYS["DEEPINFRA_API_KEY"]}))
        if url.path == "/runpod/v2/catalog/gpus":
            return self.reply(200, RUNPOD)
        if url.path == "/lambda/api/v1/instance-types":
            return self.reply(Mock.lambda_status, {"error": {"message": "something broke"}})
        return self.reply(404, {"error": "no such path"})


def sources(base, runpod_enabled=False):
    return {
        "about": "test",
        "gpus_of_interest": ["H100", "H200", "B200"],
        "sources": [
            {"id": "novita", "provider": "Novita", "in_panel": True, "enabled": True, "parser": "novita",
             "key_env": "NOVITA_API_KEY",
             "requests": [{"name": "instances", "url": f"{base}/novita/gpus/v2/products?type=gpu&category=instance",
                           "paginate": "cursor"}]},
            {"id": "deepinfra", "provider": "DeepInfra", "in_panel": True, "enabled": True, "parser": "deepinfra",
             "key_env": "DEEPINFRA_API_KEY",
             "requests": [{"name": "gpu-availability", "url": f"{base}/deepinfra/v1/containers/gpu_availability"}]},
            {"id": "runpod", "provider": "RunPod", "in_panel": False, "enabled": runpod_enabled, "parser": "runpod",
             "key_env": "RUNPOD_API_KEY",
             "requests": [{"name": "secure", "url": f"{base}/runpod/v2/catalog/gpus?cloud=SECURE"}]},
            {"id": "lambda", "provider": "Lambda", "in_panel": False, "enabled": True, "parser": "lambda",
             "key_env": "LAMBDA_API_KEY",
             "requests": [{"name": "instance-types", "url": f"{base}/lambda/api/v1/instance-types"}]},
        ],
    }


class GpuPriceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Mock.seen = []
        Mock.lambda_status = 500
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "repo")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(self.repo, "scripts"))
        os.makedirs(self.home)
        shutil.copy(os.path.join(ROOT, "scripts", "gpuprices.py"), os.path.join(self.repo, "scripts"))
        self.write_sources()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_sources(self, **kw):
        with open(os.path.join(self.repo, "gpu_sources.json"), "w") as f:
            json.dump(sources(self.base, **kw), f)

    def run_gpu(self, *args, now="2026-10-24T06:20:00", keys=None, keys_file=None):
        env = {k: v for k, v in os.environ.items() if k not in KEYS}
        env.update(GPU_NOW=now, GPU_RETRY_PAUSE="0", RUNNER_HOME=self.home)
        env.update(keys if keys is not None else {k: v for k, v in KEYS.items() if k != "RUNPOD_API_KEY"})
        if keys_file is not None:
            with open(os.path.join(self.home, "keys.env"), "w") as f:
                f.write("".join(f"{k}={v}\n" for k, v in keys_file.items()))
        return subprocess.run([sys.executable, os.path.join(self.repo, "scripts", "gpuprices.py")] + list(args),
                              cwd=self.tmp, env=env, capture_output=True, text=True, timeout=120)

    def gpu_dir(self, *parts):
        return os.path.join(self.repo, "data", "gpu", *parts)

    def manifest(self, name):
        with open(self.gpu_dir(name, "manifest.json")) as f:
            return json.load(f)

    def test_reading_saves_each_reply_and_records_every_source(self):
        r = self.run_gpu("--slot", "morning")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(os.listdir(self.gpu_dir())), ["2026-10-24-0620"])
        files = sorted(os.listdir(self.gpu_dir("2026-10-24-0620")))
        self.assertEqual(files, ["deepinfra-gpu-availability.json", "lambda-instance-types.json",
                                 "manifest.json", "novita-instances-p2.json", "novita-instances.json"])
        m = self.manifest("2026-10-24-0620")
        self.assertEqual(m["slot"], "morning")
        status = {(e["source"], e["request"]): e["status"] for e in m["requests"]}
        self.assertEqual(status, {("novita", "instances"): "ok", ("deepinfra", "gpu-availability"): "ok",
                                  ("runpod", "secure"): "skipped: no key",
                                  ("lambda", "instance-types"): "failed"})
        novita = next(e for e in m["requests"] if e["source"] == "novita")
        self.assertEqual(len(novita["pages"]), 2, "the second page must be followed by its cursor")
        with open(self.gpu_dir("2026-10-24-0620", "novita-instances.json")) as f:
            self.assertEqual(json.load(f), NOVITA_PAGE_1, "a reply must be saved exactly as received")
        lam = next(e for e in m["requests"] if e["source"] == "lambda")
        self.assertEqual(lam["error"], "HTTP 500")
        self.assertEqual(len([p for p, _ in Mock.seen if p.startswith("/lambda")]), 3, "a broken service is retried")
        self.assertFalse([n for n in os.listdir(self.gpu_dir()) if n.startswith(".")], "no partial folder is left")

    def test_a_key_is_never_saved_or_printed(self):
        r = self.run_gpu("--slot", "morning", keys=KEYS)
        everything = r.stdout + r.stderr
        for dirpath, _, names in os.walk(self.gpu_dir()):
            for n in names:
                with open(os.path.join(dirpath, n)) as f:
                    everything += f.read()
        for key in KEYS.values():
            self.assertNotIn(key, everything)
        with open(self.gpu_dir("2026-10-24-0620", "deepinfra-gpu-availability.json")) as f:
            self.assertEqual(json.load(f)["debug"]["token"], "[key]")

    def test_one_reading_per_slot_per_day_and_no_folder_reused(self):
        self.run_gpu("--slot", "morning")
        again = self.run_gpu("--slot", "morning", now="2026-10-24T09:00:00")
        self.assertIn("already in data/gpu", again.stdout)
        window = self.run_gpu("--slot", "window", now="2026-10-24T14:41:00")
        self.assertEqual(window.returncode, 0, window.stdout + window.stderr)
        self.assertEqual(sorted(os.listdir(self.gpu_dir())), ["2026-10-24-0620", "2026-10-24-1441"])
        same_minute = self.run_gpu(now="2026-10-24T14:41:30")
        self.assertIn("never overwritten", same_minute.stdout)
        tomorrow = self.run_gpu("--slot", "morning", now="2026-10-25T06:20:00")
        self.assertEqual(tomorrow.returncode, 0)
        self.assertIn("2026-10-25-0620", os.listdir(self.gpu_dir()))

    def test_test_mode_writes_nothing_and_tries_a_source_not_yet_enabled(self):
        Mock.lambda_status = 200
        r = self.run_gpu("--test", keys=KEYS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.gpu_dir()))
        self.assertIn("RunPod secure (not enabled)", r.stdout)
        self.assertIn("H200   on demand    $3.59", r.stdout)
        self.assertIn("H100   on demand    $3.39  spot    $1.70  stock normal", r.stdout)
        self.assertIn("H100   on demand    $2.49", r.stdout)
        self.assertIn("shape: {data: [1 x {", r.stdout)
        for key in KEYS.values():
            self.assertNotIn(key, r.stdout + r.stderr)

    def test_a_source_not_enabled_is_never_read_in_a_reading(self):
        self.run_gpu("--slot", "morning", keys=KEYS)
        self.assertFalse([p for p, _ in Mock.seen if p.startswith("/runpod")])
        m = self.manifest("2026-10-24-0620")
        self.assertIn(("runpod", "skipped: not enabled"), [(e["source"], e["status"]) for e in m["requests"]])

    def test_keys_are_read_from_keys_env_when_not_in_the_environment(self):
        r = self.run_gpu("--slot", "morning", keys={}, keys_file={"NOVITA_API_KEY": KEYS["NOVITA_API_KEY"]})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        status = {e["source"]: e["status"] for e in self.manifest("2026-10-24-0620")["requests"]}
        self.assertEqual(status["novita"], "ok")
        self.assertEqual(status["deepinfra"], "skipped: no key")

    def test_no_reading_when_no_source_has_a_key(self):
        r = self.run_gpu("--slot", "morning", keys={})
        self.assertEqual(r.returncode, 1)
        self.assertIn("No source can be read", r.stdout)
        self.assertFalse(os.path.exists(self.gpu_dir("2026-10-24-0620")))

    def test_report_gives_prices_per_gpu_hour(self):
        self.run_gpu("--slot", "morning")
        r = self.run_gpu("--report", "2026-10-24-0620")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("H100     Novita          $3.39    $1.70  normal", r.stdout)
        self.assertIn("H100     DeepInfra       $2.49        -  available", r.stdout)
        self.assertIn("B200     DeepInfra       $4.49        -  not available", r.stdout)
        self.assertNotIn("RTX 4090", r.stdout)
        everything = self.run_gpu("--report", "2026-10-24-0620", "--all")
        self.assertIn("RTX 4090 Novita          $0.35", everything.stdout)

    def test_a_reply_in_a_changed_format_is_reported_not_fatal(self):
        self.run_gpu("--slot", "morning")
        with open(self.gpu_dir("2026-10-24-0620", "novita-instances.json"), "w") as f:
            json.dump({"data": "changed"}, f)
        r = self.run_gpu("--report", "2026-10-24-0620")
        self.assertEqual(r.returncode, 1)
        self.assertIn("PROBLEM: novita-instances.json", r.stdout)
        self.assertIn("H100     DeepInfra", r.stdout, "the other sources are still reported")
        # Missing or odd values are not a changed format: they are shown as no price.
        with open(self.gpu_dir("2026-10-24-0620", "deepinfra-gpu-availability.json"), "w") as f:
            json.dump({"gpus": [{"gpu_config": None, "usd_per_hour": "n/a"}]}, f)
        r2 = self.run_gpu("--report", "2026-10-24-0620", "--all")
        self.assertNotIn("PROBLEM: deepinfra", r2.stdout)
        self.assertIn("DeepInfra", r2.stdout)

    def test_the_real_sources_file_is_well_formed(self):
        with open(os.path.join(ROOT, "gpu_sources.json")) as f:
            cfg = json.load(f)
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import gpuprices
        ids = [s["id"] for s in cfg["sources"]]
        self.assertEqual(len(ids), len(set(ids)))
        for s in cfg["sources"]:
            self.assertIn(s["parser"], gpuprices.PARSERS)
            self.assertTrue(s["key_env"].endswith("_API_KEY"))
            self.assertTrue(all(r["url"].startswith("https://") for r in s["requests"]))
            if s["enabled"]:
                self.assertTrue(s["terms"]["read"], f"{s['id']} is enabled without its terms having been read")


if __name__ == "__main__":
    unittest.main(verbosity=2)
