"""
Tests for scripts/runner.py, the server's runner.
Run from the repository root:  python3 tests/test_runner.py

Each test builds a throwaway repository with a throwaway remote, and stand-ins
for the census and the probe, so nothing touches GitHub, OpenRouter or the
server. The census alarm is a local web server that counts pings.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import runner  # noqa: E402

STUB_PROBE = r'''
import datetime as dt, json, os, sys
now = dt.datetime.fromisoformat(os.environ["RUNNER_NOW"])
if "--offwindow" in sys.argv:
    out = os.path.join("data", "offwindow", now.strftime("%Y-%m-%d-%H%M"))
else:
    out = os.path.join("data", "probes", now.strftime("%Y-%m-%d"))
os.makedirs(os.path.join(out, "requests"), exist_ok=True)
with open(os.path.join(out, "requests", "a.json"), "w") as f:
    f.write("{}")
if os.environ.get("STUB_PROBE_CRASH"):
    sys.exit(3)
with open(os.path.join(out, "manifest.json"), "w") as f:
    json.dump({"key_seen": bool(os.environ.get("OPENROUTER_API_KEY"))}, f)
print("stub probe done")
'''

STUB_CENSUS = r'''
import datetime as dt, json, os, sys
day = dt.datetime.fromisoformat(os.environ["RUNNER_NOW"]).strftime("%Y-%m-%d")
out = os.path.join("data", "census", day)
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "models.json"), "w") as f:
    f.write('{"data": []}')
if os.environ.get("STUB_CENSUS_CRASH"):
    sys.exit(1)
with open(os.path.join(out, "meta.json"), "w") as f:
    json.dump({"trigger": os.environ.get("GITHUB_EVENT_NAME") or os.environ.get("CENSUS_TRIGGER") or "manual"}, f)
'''

STUB_GPU = r'''
import datetime as dt, json, os, sys
now = dt.datetime.fromisoformat(os.environ["RUNNER_NOW"])
if os.environ.get("STUB_GPU_CRASH"):
    print("stub gpu broke")
    sys.exit(1)
slot = sys.argv[sys.argv.index("--slot") + 1]
base = os.path.join("data", "gpu")
day = now.strftime("%Y-%m-%d")
for name in (os.listdir(base) if os.path.isdir(base) else []):
    if name.startswith(day) and json.load(open(os.path.join(base, name, "manifest.json")))["slot"] == slot != "manual":
        print("already taken")
        sys.exit(0)
out = os.path.join(base, now.strftime("%Y-%m-%d-%H%M"))
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "manifest.json"), "w") as f:
    json.dump({"slot": slot, "trigger": os.environ.get("GPU_TRIGGER"),
               "key_seen": bool(os.environ.get("NOVITA_API_KEY"))}, f)
'''

STUB_TRACK = r'''
import os
os.makedirs(os.path.join("data", "site"), exist_ok=True)
open(os.path.join("data", "track.md"), "a").write("tracked\n")
open(os.path.join("data", "site", "track.json"), "w").write("{}")
'''


class Pings(BaseHTTPRequestHandler):
    count = 0

    def log_message(self, *args):
        pass

    def do_GET(self):
        Pings.count += 1
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


def load(path):
    with open(path) as f:
        return json.load(f)


def git(cwd, *args):
    return subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, check=True).stdout


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Pings)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.ping_url = f"http://127.0.0.1:{cls.server.server_address[1]}/ping"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Pings.count = 0
        self.tmp = tempfile.mkdtemp()
        self.remote = os.path.join(self.tmp, "remote.git")
        self.repo = os.path.join(self.tmp, "repo")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.remote], check=True)
        subprocess.run(["git", "clone", "-q", self.remote, self.repo], check=True, capture_output=True)
        git(self.repo, "config", "user.name", "test")
        git(self.repo, "config", "user.email", "test@example.invalid")
        os.makedirs(os.path.join(self.repo, "scripts"))
        shutil.copy(os.path.join(ROOT, "scripts", "runner.py"), os.path.join(self.repo, "scripts"))
        for name, text in (("probe.py", STUB_PROBE), ("census.py", STUB_CENSUS),
                           ("rank.py", "print('ranked')\n"), ("track.py", STUB_TRACK),
                           ("gpuprices.py", STUB_GPU)):
            with open(os.path.join(self.repo, "scripts", name), "w") as f:
                f.write(text)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "start")
        git(self.repo, "push", "-q", "origin", "HEAD:main")
        git(self.repo, "branch", "-q", "--set-upstream-to=origin/main")
        with open(os.path.join(self.home, "keys.env"), "w") as f:
            f.write("# keys\nOPENROUTER_API_KEY=test-key\nexport HEALTHCHECK_CENSUS='%s'\n"
                    "NOVITA_API_KEY=novita-test-key\n" % self.ping_url)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_job(self, job, now, **env):
        e = dict(os.environ, RUNNER_HOME=self.home, RUNNER_NOW=now, RUNNER_PUSH_PAUSE="0", **env)
        e.pop("GITHUB_EVENT_NAME", None)
        return subprocess.run([sys.executable, os.path.join(self.repo, "scripts", "runner.py"), job],
                              cwd=self.tmp, env=e, capture_output=True, text=True, timeout=120)

    def remote_log(self):
        return git(self.remote, "log", "--format=%s", "main")

    def remote_has(self, path):
        return subprocess.run(["git", "cat-file", "-e", "main:" + path], cwd=self.remote,
                              capture_output=True).returncode == 0

    def test_census_is_labelled_pushed_and_pings_the_alarm(self):
        r = self.run_job("census", "2026-10-20T06:15:00")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Census 2026-10-20 (server)", self.remote_log())
        meta = json.loads(git(self.remote, "show", "main:data/census/2026-10-20/meta.json"))
        self.assertEqual(meta["trigger"], "server")
        self.assertTrue(self.remote_has("data/track.md") and self.remote_has("data/site/track.json"))
        self.assertEqual(Pings.count, 1)
        with open(os.path.join(self.home, "logs", "runner-2026-10.log")) as f:
            self.assertNotIn(self.ping_url, f.read(), "the alarm address must never be written to the log")
        again = self.run_job("census", "2026-10-20T09:00:00")
        self.assertEqual(again.returncode, 0)
        self.assertIn("already in the repository", again.stdout)
        self.assertEqual(self.remote_log().count("Census 2026-10-20"), 1)
        self.assertEqual(Pings.count, 2)

    def test_unfinished_census_is_set_aside_not_committed(self):
        r = self.run_job("census", "2026-10-20T06:15:00", STUB_CENSUS_CRASH="1")
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Census", self.remote_log())
        self.assertFalse(os.path.exists(os.path.join(self.repo, "data", "census", "2026-10-20")))
        self.assertTrue([n for n in os.listdir(os.path.join(self.home, "state")) if n.startswith("failed-census")])
        self.assertEqual(Pings.count, 0)

    def test_window_is_pushed_when_the_probe_finishes(self):
        r = self.run_job("window", "2026-10-20T14:05:00")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Probes 2026-10-20 (server)", self.remote_log())
        manifest = json.loads(git(self.remote, "show", "main:data/probes/2026-10-20/manifest.json"))
        self.assertTrue(manifest["key_seen"], "the probe must get the keys from keys.env")

    def test_window_runs_even_when_github_cannot_be_reached(self):
        git(self.repo, "remote", "set-url", "origin", os.path.join(self.tmp, "missing.git"))
        r = self.run_job("window", "2026-10-20T14:05:00")
        self.assertEqual(r.returncode, 1)
        self.assertIn("git pull failed; carrying on", r.stdout)
        self.assertIn("PUSH FAILED", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "data", "probes", "2026-10-20", "manifest.json")))
        self.assertIn("Probes 2026-10-20 (server)", git(self.repo, "log", "--format=%s"))
        # GitHub comes back: the next job's push carries the stranded commit.
        git(self.repo, "remote", "set-url", "origin", self.remote)
        self.run_job("census", "2026-10-21T06:15:00")
        self.assertIn("Probes 2026-10-20 (server)", self.remote_log())

    def test_unfinished_probe_is_still_pushed(self):
        r = self.run_job("window", "2026-10-20T14:05:00", STUB_PROBE_CRASH="1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no manifest", r.stdout)
        self.assertTrue(self.remote_has("data/probes/2026-10-20/requests/a.json"))

    def test_no_window_at_the_weekend(self):
        r = self.run_job("window", "2026-10-24T14:05:00")
        self.assertEqual(r.returncode, 0)
        self.assertIn("has no window", r.stdout)
        self.assertNotIn("Probes", self.remote_log())

    def test_weekend_reading_goes_to_offwindow(self):
        r = self.run_job("weekend", "2026-10-24T14:05:00")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Off-window 2026-10-24-1405, weekend (server)", self.remote_log())
        self.assertTrue(self.remote_has("data/offwindow/2026-10-24-1405/manifest.json"))
        self.assertFalse(self.remote_has("data/probes"))
        weekday = self.run_job("weekend", "2026-10-26T14:05:00")
        self.assertIn("not a weekend day", weekday.stdout)

    def test_random_hour_runs_once_at_its_hour(self):
        state = os.path.join(self.home, "state", "random-hour.json")
        os.makedirs(os.path.dirname(state))
        with open(state, "w") as f:
            json.dump({"date": "2026-10-20", "hour": 9, "minute": 5, "done": False}, f)
        other = self.run_job("random", "2026-10-20T08:05:00")
        self.assertEqual(other.returncode, 0)
        self.assertEqual(self.remote_log().count("Off-window"), 0)
        r = self.run_job("random", "2026-10-20T09:06:00")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Off-window 2026-10-20-0906, random (server)", self.remote_log())
        self.assertTrue(load(state)["done"])
        self.run_job("random", "2026-10-20T09:30:00")
        self.assertEqual(self.remote_log().count("Off-window"), 1)
        # A new day chooses a new hour.
        self.run_job("random", "2026-10-21T00:05:00")
        self.assertEqual(load(state)["date"], "2026-10-21")

    def test_random_hour_never_overlaps_the_window(self):
        import random
        rng = random.Random(1)
        seen = set()
        for _ in range(2000):
            c = runner.choose_random(dt.datetime(2026, 10, 20, 0, 5), rng)
            seen.add(c["hour"])
            self.assertTrue(5 <= c["minute"] <= 25)
        self.assertEqual(seen, set(range(24)) - {13, 14})
        late = runner.choose_random(dt.datetime(2026, 10, 20, 17, 30), rng)
        self.assertGreaterEqual(late["hour"], 17)
        self.assertEqual(runner.choose_random(dt.datetime(2026, 10, 20, 23, 30), rng)["hour"], 23)

    def test_census_is_followed_by_the_morning_gpu_reading(self):
        r = self.run_job("census", "2026-10-20T06:15:00")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        log = self.remote_log().splitlines()
        self.assertIn("GPU prices 2026-10-20-0615, morning (server)", log)
        self.assertLess(log.index("GPU prices 2026-10-20-0615, morning (server)"),
                        log.index("Census 2026-10-20 (server)"), "the census is pushed first")
        m = json.loads(git(self.remote, "show", "main:data/gpu/2026-10-20-0615/manifest.json"))
        self.assertEqual((m["slot"], m["trigger"], m["key_seen"]), ("morning", "server", True))
        self.assertEqual(Pings.count, 1)
        again = self.run_job("census", "2026-10-20T09:00:00")
        self.assertEqual(again.returncode, 0)
        self.assertEqual(self.remote_log().count("GPU prices"), 1, "one morning reading a day")

    def test_a_gpu_failure_changes_nothing_for_the_census(self):
        r = self.run_job("census", "2026-10-20T06:15:00", STUB_GPU_CRASH="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Census 2026-10-20 (server)", self.remote_log())
        self.assertNotIn("GPU prices", self.remote_log())
        self.assertIn("GPU prices: no reading written", r.stdout)
        self.assertEqual(Pings.count, 1)

    def test_a_failed_census_still_takes_the_gpu_reading(self):
        r = self.run_job("census", "2026-10-20T06:15:00", STUB_CENSUS_CRASH="1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("GPU prices 2026-10-20-0615, morning (server)", self.remote_log())
        self.assertEqual(Pings.count, 0)

    def test_window_is_followed_by_the_window_gpu_reading(self):
        r = self.run_job("window", "2026-10-20T14:05:00")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        log = self.remote_log().splitlines()
        self.assertLess(log.index("GPU prices 2026-10-20-1405, window (server)"),
                        log.index("Probes 2026-10-20 (server)"), "the probe's files are pushed first")
        crash = self.run_job("window", "2026-10-21T14:05:00", STUB_GPU_CRASH="1")
        self.assertEqual(crash.returncode, 0, "a GPU failure never fails the window")
        self.assertIn("Probes 2026-10-21 (server)", self.remote_log())

    def test_gpu_reading_by_hand(self):
        r = self.run_job("gpu", "2026-10-20T11:30:00")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("GPU prices 2026-10-20-1130, manual (server)", self.remote_log())

    def test_keys_file_is_read_without_quotes_or_export(self):
        keys = runner.read_keys(os.path.join(self.home, "keys.env"))
        self.assertEqual(keys["OPENROUTER_API_KEY"], "test-key")
        self.assertEqual(keys["HEALTHCHECK_CENSUS"], self.ping_url)

    def test_check_changes_nothing(self):
        before = git(self.repo, "status", "--porcelain")
        r = self.run_job("check", "2026-10-20T10:00:00")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OPENROUTER_API_KEY: set", r.stdout)
        self.assertIn("HEALTHCHECK_CENSUS: set", r.stdout)
        self.assertIn("Permission to push: yes", r.stdout)
        self.assertIn("Commits here not yet pushed: 0", r.stdout)
        self.assertNotIn("test-key", r.stdout)
        self.assertEqual(git(self.repo, "status", "--porcelain"), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
