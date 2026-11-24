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



class LateScheduleTest(unittest.TestCase):
    """A backup run that GitHub starts after midnight for a schedule set the day before does nothing, so it
    cannot take the new day's census hours before the server (24 November 2026, taken at 00:04 UTC)."""

    def at(self, hh, mm):
        import datetime
        return datetime.datetime(2026, 11, 24, hh, mm, tzinfo=datetime.timezone.utc)

    def test_a_run_that_starts_before_its_scheduled_time_was_set_for_an_earlier_day(self):
        late = census.scheduled_for_an_earlier_day
        self.assertTrue(late("23 12 * * *", self.at(0, 4)))       # 24 November 2026
        self.assertTrue(late("41 6 * * *", self.at(5, 59)))
        self.assertTrue(late("41 9 * * *", self.at(9, 40)))

    def test_a_run_on_time_or_late_the_same_day_is_due(self):
        late = census.scheduled_for_an_earlier_day
        for schedule, hh, mm in (("41 6 * * *", 6, 41), ("41 6 * * *", 11, 57), ("23 12 * * *", 21, 38),
                                 ("41 9 * * *", 23, 59)):
            self.assertFalse(late(schedule, self.at(hh, mm)), (schedule, hh, mm))

    def test_a_run_by_hand_or_an_odd_schedule_is_never_late(self):
        late = census.scheduled_for_an_earlier_day
        for schedule in ("", None, "*/30 * * * *", "41"):
            self.assertFalse(late(schedule, self.at(0, 4)), schedule)

    def test_the_command_line_check(self):
        def check(*args):
            r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "census.py"), "--schedule-check", *args],
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout.strip()
        self.assertEqual(check("23 12 * * *", "--now", "00:04"), "late")
        self.assertEqual(check("41 6 * * *", "--now", "06:41"), "due")
        self.assertEqual(check("", "--now", "00:04"), "due")

    def test_the_workflow_asks_before_doing_anything(self):
        with open(os.path.join(ROOT, ".github", "workflows", "main.yml")) as f:
            wf = f.read()
        self.assertIn("SCHEDULE: ${{ github.event.schedule }}", wf)
        self.assertIn('census.py --schedule-check "$SCHEDULE")" = "late"', wf)
        self.assertIn('echo "done=late"', wf)
        self.assertEqual(wf.count("steps.check.outputs.done == 'false' || github.event_name == 'workflow_dispatch'"), 2)
        self.assertNotIn("steps.check.outputs.done != 'true'", wf, "a late run would otherwise run the census")
        self.assertLess(wf.index("--schedule-check"), wf.index("python scripts/census.py\n"))


if __name__ == "__main__":
    unittest.main()
