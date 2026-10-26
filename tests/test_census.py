"""
Tests for scripts/census.py: the model list, the one request that can stop the
census, is tried three times on a failure worth repeating, and only then.
Run with: python3 -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import census  # noqa: E402

MODELS = {"data": [{"id": "lab/a"}, {"id": "lab/b"}]}


class Mock(BaseHTTPRequestHandler):
    break_list = 0          # how many model-list requests to break before answering
    break_with = "cut"      # "cut": a reply cut off partway; "503": a server error
    seen = []

    def log_message(self, *args):
        pass

    def send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        Mock.seen.append(self.path)
        if self.path == "/api/v1/models":
            if Mock.break_list > 0:
                Mock.break_list -= 1
                if Mock.break_with == "503":
                    return self.send(503, {"error": "busy"})
                body = json.dumps(MODELS).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body[: len(body) // 2])
                self.close_connection = True
                return
            return self.send(200, MODELS)
        if self.path == "/api/v1/models/lab/a/endpoints":
            return self.send(200, {"data": {"endpoints": [{"provider_name": "P", "quantization": "fp8"}]}})
        self.send(404, {"error": "not found"})


class CensusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d/api/v1" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Mock.break_list, Mock.break_with, Mock.seen = 0, "cut", []
        self.slept = []

    def get(self, path, waits=(15, 45)):
        return census.get_json_retrying(self.base + path, waits, sleep=self.slept.append)

    def test_a_reply_cut_off_is_tried_again(self):
        Mock.break_list = 1
        reply, tries = self.get("/models")
        self.assertEqual(reply, MODELS)
        self.assertEqual(tries, 2)
        self.assertEqual(self.slept, [15])

    def test_a_server_error_is_tried_again_twice_at_most(self):
        Mock.break_list, Mock.break_with = 2, "503"
        reply, tries = self.get("/models")
        self.assertEqual((reply, tries, self.slept), (MODELS, 3, [15, 45]))

    def test_three_failures_stop_the_census(self):
        Mock.break_list = 5
        with self.assertRaises(Exception):
            self.get("/models")
        self.assertEqual(Mock.seen.count("/api/v1/models"), 3)
        self.assertEqual(self.slept, [15, 45])

    def test_a_refusal_is_not_repeated(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.get("/no-such-thing")
        self.assertEqual(len(Mock.seen), 1)
        self.assertEqual(self.slept, [])

    def test_retryable(self):
        def http_error(code):
            return urllib.error.HTTPError("u", code, "m", {}, None)
        self.assertTrue(census.retryable(TimeoutError("The read operation timed out")))
        self.assertTrue(census.retryable(ConnectionResetError()))
        self.assertTrue(census.retryable(json.JSONDecodeError("cut", "{", 1)))
        self.assertTrue(census.retryable(http_error(429)))
        self.assertTrue(census.retryable(http_error(502)))
        self.assertFalse(census.retryable(http_error(404)))
        self.assertFalse(census.retryable(KeyError("x")))

    def run_census(self, tmp):
        """census.main() in a scratch folder, against the mock, with no waiting."""
        here = os.getcwd()
        saved = census.BASE, census.LIST_WAITS
        census.BASE, census.LIST_WAITS = self.base, (0, 0)
        os.chdir(tmp)
        try:
            return census.main()
        finally:
            os.chdir(here)
            census.BASE, census.LIST_WAITS = saved

    def test_a_whole_census_records_its_tries(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        Mock.break_list = 1
        self.assertEqual(self.run_census(tmp), 0)
        days = os.listdir(os.path.join(tmp, "data", "census"))
        self.assertEqual(len(days), 1)
        day = os.path.join(tmp, "data", "census", days[0])
        with open(os.path.join(day, "meta.json")) as f:
            meta = json.load(f)
        self.assertEqual(meta["models_list_tries"], 2)
        self.assertEqual(meta["models"], 2)
        self.assertEqual(meta["errors"], 1, "a failed per-model request is recorded, not retried")
        self.assertTrue(os.path.exists(os.path.join(day, "endpoints", "lab__a.json")))
        self.assertTrue(os.path.exists(os.path.join(day, "endpoints", "lab__b.ERROR.txt")))
        self.assertEqual(Mock.seen.count("/api/v1/models/lab/b/endpoints"), 1)
        # Written once: a second run the same day changes nothing.
        before = Mock.seen[:]
        self.assertEqual(self.run_census(tmp), 0)
        self.assertEqual(Mock.seen, before)

    def test_the_script_still_runs_from_the_command_line(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        env = dict(os.environ, OPENROUTER_BASE=self.base)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "census.py")], cwd=tmp, env=env,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Census complete", r.stdout)
        day = os.listdir(os.path.join(tmp, "data", "census"))[0]
        with open(os.path.join(tmp, "data", "census", day, "meta.json")) as f:
            self.assertEqual(json.load(f)["models_list_tries"], 1)


if __name__ == "__main__":
    unittest.main()
