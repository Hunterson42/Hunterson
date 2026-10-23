"""
Tests for scripts/marketdata.py, OpenRouter's market data (decision D38).
Run from the repository root:  python3 tests/test_marketdata.py

A local web server stands in for OpenRouter's Data API, with replies in the
form its published SDK (openrouter 1.3.79) describes, so nothing touches
OpenRouter. Each test copies the script into a throwaway repository with its
own market_sources.json pointing at that server.
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
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "sk-or-test-secret-123"
YESTERDAY = "2026-10-23"          # the most recent completed day when the tests' clock reads 24 October


def days(start, end):
    d, last = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    while d <= last:
        yield d.isoformat()
        d += dt.timedelta(days=1)


class Mock(BaseHTTPRequestHandler):
    seen = []
    fail_after = None          # every request after this many is refused with 429
    broken = set()             # request windows (path, start_date) that answer 500

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
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        Mock.seen.append((url.path, q))
        if self.headers.get("Authorization") != "Bearer " + KEY:
            return self.reply(401, {"error": {"code": 401, "message": "No auth credentials found"}})
        if Mock.fail_after is not None and len(Mock.seen) > Mock.fail_after:
            return self.reply(429, {"error": {"code": 429, "message": "Rate limit exceeded: 500 requests per day"}})
        if (url.path, q.get("start_date")) in Mock.broken:
            return self.reply(500, {"error": {"code": 500, "message": "Internal error"}})
        meta = {"as_of": "2026-10-24T06:00:00Z", "version": "v1"}
        if url.path == "/api/v1/datasets/rankings-daily":
            end = q.get("end_date", YESTERDAY)
            start = q.get("start_date") or (dt.date.fromisoformat(end) - dt.timedelta(days=30)).isoformat()
            start = max(start, "2025-01-01")
            if (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days > 365:
                return self.reply(400, {"error": {"code": 400, "message": "window longer than 366 days"}})
            scale = 1 if q.get("modality") != "tool_calling" else 0.4
            rows = []
            for d in days(start, end):
                rows += [{"date": d, "model_permaslug": "deepseek/deepseek-v4.1-flash",
                          "total_tokens": str(int(600e9 * scale))},
                         {"date": d, "model_permaslug": "zai-org/glm-5.3", "total_tokens": str(int(300e9 * scale))},
                         {"date": d, "model_permaslug": "other", "total_tokens": str(int(100e9 * scale))}]
            return self.reply(200, {"data": rows, "meta": dict(meta, start_date=start, end_date=end)})
        if url.path == "/api/v1/classifications/task":
            return self.reply(200, {"data": {
                "as_of": "2026-10-24T05:00:00Z", "window_days": 7,
                "classifications": [{"tag": "code-generation", "display_name": "Code generation",
                                     "macro_category": "code", "usage_share": 0.3, "token_share": 0.5,
                                     "category_usage_share": 0.6, "category_token_share": 0.7,
                                     "models": [{"id": "deepseek/deepseek-v4.1-flash", "tag_usage_share": 0.2,
                                                 "tag_token_share": 0.25}]}],
                "macro_categories": [{"key": "code", "label": "Code", "usage_share": 0.4, "token_share": 0.6},
                                     {"key": "agent", "label": "Agent", "usage_share": 0.2, "token_share": 0.25}]}})
        if url.path == "/api/v1/datasets/app-rankings":
            limit, offset = int(q.get("limit", 50)), int(q.get("offset", 0))
            if not 1 <= limit <= 100 or not 0 <= offset <= 100:
                return self.reply(400, {"error": {"code": 400, "message": "limit or offset out of range"}})
            count = 5 if q.get("subcategory") else (limit if offset == 0 else 30)
            rows = [{"rank": offset + i + 1, "app_id": 1000 + offset + i, "app_name": f"App {offset + i + 1}",
                     "total_tokens": str(int(1e12 / (offset + i + 1))), "total_requests": 5000}
                    for i in range(count)]
            return self.reply(200, {"data": rows, "meta": dict(meta, start_date=q.get("start_date"),
                                                               end_date=q.get("end_date"))})
        if url.path == "/api/v1/datasets/session-cost":
            limit, offset = int(q.get("limit", 100)), int(q.get("offset", 0))
            if not 1 <= limit <= 500 or not 0 <= offset <= 5000:
                return self.reply(400, {"error": {"code": 400, "message": "limit or offset out of range"}})
            count = limit if offset < 1000 else 120
            ranges = ["1-turn", "2-9-turns", "10-49-turns", "50-plus-turns"]
            rows = [{"app_name": "Harness", "app_slug": "harness", "model_permaslug": "deepseek/deepseek-v4.1-flash",
                     "turn_range": ranges[i % 4], "median_session_cost_usd": 0.05 * (i % 4 + 1)} for i in range(count)]
            return self.reply(200, {"data": rows, "meta": dict(meta, window_days=7, window_end_date="2026-10-18")})
        if url.path == "/api/v1/benchmarks":
            # A reply that echoes the key, to prove it is removed before saving.
            return self.reply(200, {"data": [
                {"source": "artificial-analysis", "model_permaslug": "deepseek/deepseek-v4.1-flash",
                 "display_name": "DeepSeek V4.1 Flash", "intelligence_index": 61.2, "coding_index": 55.0,
                 "agentic_index": 48.1, "pricing": {"prompt": "0.00000021", "completion": "0.00000084"}},
                {"source": "design-arena", "model_permaslug": "zai-org/glm-5.3", "elo": 1210}],
                "meta": dict(meta, citation=None, model_count=2, source=None, source_url=None, task_type=None),
                "debug": {"auth": KEY}})
        return self.reply(404, {"error": {"code": 404, "message": "Not found"}})


def config(base):
    with open(os.path.join(ROOT, "market_sources.json")) as f:
        cfg = json.load(f)
    cfg["sources"][0]["base_url"] = base + "/api/v1"
    return cfg


class MarketDataTests(unittest.TestCase):
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
        Mock.seen, Mock.fail_after, Mock.broken = [], None, set()
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "repo")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(os.path.join(self.repo, "scripts"))
        os.makedirs(self.home)
        shutil.copy(os.path.join(ROOT, "scripts", "marketdata.py"), os.path.join(self.repo, "scripts"))
        with open(os.path.join(self.repo, "market_sources.json"), "w") as f:
            json.dump(config(self.base), f)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_market(self, *args, now="2026-10-24T06:21:00", keys=None, keys_file=None):
        env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
        env.update(MARKET_NOW=now, MARKET_PACE="0", MARKET_RETRY_PAUSE="0", RUNNER_HOME=self.home)
        env.update({"OPENROUTER_API_KEY": KEY} if keys is None else keys)
        if keys_file is not None:
            with open(os.path.join(self.home, "keys.env"), "w") as f:
                f.write("".join(f"{k}={v}\n" for k, v in keys_file.items()))
        return subprocess.run([sys.executable, os.path.join(self.repo, "scripts", "marketdata.py")] + list(args),
                              cwd=self.tmp, env=env, capture_output=True, text=True, timeout=300)

    def market_dir(self, *parts):
        return os.path.join(self.repo, "data", "market", *parts)

    def manifest(self, name):
        with open(self.market_dir(name, "manifest.json")) as f:
            return json.load(f)

    def requests(self, path):
        return [q for p, q in Mock.seen if p == path]

    def test_first_reading_of_the_week_takes_the_daily_and_weekly_data(self):
        r = self.run_market("--slot", "morning")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.listdir(self.market_dir()), ["2026-10-24-0621"])
        m = self.manifest("2026-10-24-0621")
        self.assertEqual((m["slot"], m["kinds"]), ("morning", ["daily", "weekly"]))
        self.assertEqual(len(m["requests"]), 26)
        self.assertTrue(all(e["status"] == "ok" for e in m["requests"]), r.stdout)
        by_name = {e["request"]: e for e in m["requests"]}
        self.assertEqual(by_name["rankings"]["window"], {"start_date": "2026-10-20", "end_date": None},
                         "the last four completed days, ending where the server says")
        self.assertEqual(by_name["apps"]["window"], {"start_date": "2026-10-12", "end_date": "2026-10-18"},
                         "the previous week, Monday to Sunday")
        self.assertEqual(len(by_name["apps"]["pages"]), 2, "the top 200 apps take two pages")
        self.assertEqual(len(by_name["session-cost"]["pages"]), 3, "every page of session costs is read")
        self.assertEqual([p["rows"] for p in by_name["session-cost"]["pages"]], [500, 500, 120])
        self.assertIn("apps-cli-agent", by_name)
        self.assertIn({"modality": "tool_calling", "start_date": "2026-10-20"},
                      self.requests("/api/v1/datasets/rankings-daily"))
        self.assertIn("rankings-context-100K.json", os.listdir(self.market_dir("2026-10-24-0621")))
        with open(self.market_dir("2026-10-24-0621", "session-cost-p3.json")) as f:
            self.assertEqual(len(json.load(f)["data"]), 120, "a reply is saved exactly as received")
        self.assertFalse([n for n in os.listdir(self.market_dir()) if n.startswith(".")], "no partial folder is left")

    def test_later_readings_that_week_take_the_daily_data_only(self):
        self.run_market("--slot", "morning")
        sunday = self.run_market("--slot", "morning", now="2026-10-25T06:21:00")
        self.assertEqual(sunday.returncode, 0, sunday.stdout + sunday.stderr)
        m = self.manifest("2026-10-25-0621")
        self.assertEqual(m["kinds"], ["daily"])
        self.assertEqual(len(m["requests"]), 8)
        monday = self.run_market("--slot", "morning", now="2026-10-26T06:21:00")
        self.assertEqual(monday.returncode, 0)
        m = self.manifest("2026-10-26-0621")
        self.assertEqual(m["kinds"], ["daily", "weekly"], "a new week takes the weekly data again")
        apps = next(e for e in m["requests"] if e["request"] == "apps")
        self.assertEqual(apps["window"], {"start_date": "2026-10-19", "end_date": "2026-10-25"})

    def test_one_morning_reading_a_day_and_no_folder_reused(self):
        self.run_market("--slot", "morning")
        again = self.run_market("--slot", "morning", now="2026-10-24T09:00:00")
        self.assertIn("already in data/market", again.stdout)
        same_minute = self.run_market(now="2026-10-24T06:21:30")
        self.assertIn("never overwritten", same_minute.stdout)
        by_hand = self.run_market(now="2026-10-24T11:00:00")
        self.assertEqual(by_hand.returncode, 0)
        self.assertEqual(self.manifest("2026-10-24-1100")["kinds"], ["daily"])
        self.assertEqual(sorted(os.listdir(self.market_dir())), ["2026-10-24-0621", "2026-10-24-1100"])

    def test_the_key_is_never_saved_or_printed(self):
        r = self.run_market("--slot", "morning")
        everything = r.stdout + r.stderr
        for dirpath, _, names in os.walk(self.market_dir()):
            for n in names:
                with open(os.path.join(dirpath, n)) as f:
                    everything += f.read()
        self.assertNotIn(KEY, everything)
        with open(self.market_dir("2026-10-24-0621", "benchmarks.json")) as f:
            self.assertEqual(json.load(f)["debug"]["auth"], "[key]")

    def test_test_mode_reads_one_page_of_each_kind_and_writes_nothing(self):
        r = self.run_market("--test")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self.market_dir()))
        self.assertEqual(len(Mock.seen), 8)
        self.assertEqual(len(self.requests("/api/v1/datasets/session-cost")), 1)
        self.assertIn("8 of 8 requests answered. Nothing was written.", r.stdout)
        self.assertIn("4 days to 2026-10-23; 2026-10-23: 1.00T tokens, 3 rows", r.stdout)
        self.assertIn("top: deepseek/deepseek-v4.1-flash 60.0%; zai-org/glm-5.3 30.0%", r.stdout)
        self.assertIn("token share: Code 60.0%; Agent 25.0%", r.stdout)
        self.assertIn("500 cells, 7 days to 2026-10-18", r.stdout)
        self.assertIn("2 items (as of 2026-10-24T06:00:00Z): artificial-analysis 1; design-arena 1", r.stdout)
        self.assertIn("shape: {data: [", r.stdout)
        self.assertNotIn(KEY, r.stdout + r.stderr)

    def test_backfill_takes_the_served_history_once_and_finishes_what_it_missed(self):
        Mock.broken = {("/api/v1/datasets/app-rankings", "2025-03-01")}
        r = self.run_market("--backfill", now="2026-10-24T19:00:00")
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr)
        m = self.manifest("2026-10-24-1900")
        self.assertEqual((m["slot"], m["kinds"]), ("backfill", ["backfill"]))
        self.assertEqual(len(m["requests"]), 350)
        rankings = {e["request"]: e["window"] for e in m["requests"] if e["dataset"] == "/datasets/rankings-daily"}
        self.assertEqual(rankings["rankings-2025-01-01"], {"start_date": "2025-01-01", "end_date": "2025-12-31"})
        self.assertEqual(rankings["rankings-2026-01-01"], {"start_date": "2026-01-01", "end_date": None})
        self.assertEqual(len(rankings), 14)
        months = sorted({e["window"]["start_date"] for e in m["requests"] if e["request"].startswith("apps")})
        self.assertEqual((months[0], months[-1], len(months)), ("2025-01-01", "2026-09-01", 21))
        failed = [e["request"] for e in m["requests"] if e["status"] != "ok"]
        self.assertEqual(len(failed), 16, "the overall and fifteen subcategory requests for March 2025")
        self.assertFalse([q for p, q in Mock.seen if p in ("/api/v1/datasets/session-cost", "/api/v1/benchmarks",
                                                          "/api/v1/classifications/task")],
                         "only the rankings history is served, so only it is backfilled")
        Mock.broken, Mock.seen = set(), []
        again = self.run_market("--backfill", now="2026-10-24T19:30:00")
        self.assertIn("taking the 16 it did not", again.stdout)
        self.assertEqual(len(self.manifest("2026-10-24-1930")["requests"]), 16)
        done = self.run_market("--backfill", now="2026-10-24T20:00:00")
        self.assertIn("nothing is left to take", done.stdout)
        self.assertEqual(sorted(os.listdir(self.market_dir())), ["2026-10-24-1900", "2026-10-24-1930"])

    def test_a_reading_stops_early_when_the_service_keeps_refusing(self):
        Mock.fail_after = 3
        r = self.run_market("--slot", "morning")
        self.assertEqual(r.returncode, 1)
        m = self.manifest("2026-10-24-0621")
        statuses = [e["status"] for e in m["requests"]]
        self.assertEqual(statuses[:3], ["ok"] * 3)
        self.assertEqual(statuses[3:8], ["failed"] * 5)
        self.assertTrue(all(s.startswith("not tried: the reading stopped after 5 refusals") for s in statuses[8:]))
        self.assertEqual(len(Mock.seen), 3 + 5 * 3, "each refusal is tried three times, then the reading stops")

    def test_report_summarises_a_saved_reading(self):
        self.run_market("--slot", "morning")
        r = self.run_market("--report", "2026-10-24-0621")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Market data in 2026-10-24-0621: morning, daily, weekly; 26 of 26 requests answered", r.stdout)
        self.assertIn("rankings-tool-calling: 4 days to 2026-10-23; 2026-10-23: 400.00B tokens", r.stdout)
        self.assertIn("40.0% of all tokens on 2026-10-23", r.stdout)
        self.assertIn("tokens by length of request, 2026-10-23: 1K 20.0%; 10K 20.0%; 100K 20.0%", r.stdout)
        self.assertIn("apps, 2 pages: 130 apps, 2026-10-12 to 2026-10-18", r.stdout, "every page is counted")
        self.assertIn("apps by subcategory, tokens in the listed apps: cli-agent 2.28T (5); ", r.stdout)
        self.assertIn("session-cost, 3 pages: 1,120 cells", r.stdout)
        self.assertIn("1-turn $0.05; 2-9-turns $0.10; 10-49-turns $0.15; 50-plus-turns $0.20", r.stdout)
        self.assertNotIn("PROBLEM", r.stdout)

    def test_report_flags_a_reply_in_a_changed_format(self):
        self.run_market("--slot", "morning")
        with open(self.market_dir("2026-10-24-0621", "tasks.json"), "w") as f:
            json.dump({"data": "changed"}, f)
        r = self.run_market("--report", "2026-10-24-0621")
        self.assertEqual(r.returncode, 1)
        self.assertIn("PROBLEM: tasks.json", r.stdout)
        self.assertIn("rankings:", r.stdout, "the other datasets are still reported")

    def test_no_reading_without_a_key(self):
        r = self.run_market("--slot", "morning", keys={})
        self.assertEqual(r.returncode, 1)
        self.assertIn("No source can be read", r.stdout)
        self.assertFalse(os.path.exists(self.market_dir()))
        self.assertEqual(Mock.seen, [])

    def test_the_key_is_read_from_keys_env_when_not_in_the_environment(self):
        r = self.run_market("--slot", "morning", keys={}, keys_file={"OPENROUTER_API_KEY": KEY})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(all(e["status"] == "ok" for e in self.manifest("2026-10-24-0621")["requests"]))

    def test_the_real_sources_file_is_well_formed(self):
        with open(os.path.join(ROOT, "market_sources.json")) as f:
            cfg = json.load(f)
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import marketdata
        dt.date.fromisoformat(cfg["data_start"])
        for s in cfg["sources"]:
            self.assertTrue(s["base_url"].startswith("https://"))
            self.assertTrue(s["key_env"].endswith("_API_KEY"))
            if s["enabled"]:
                self.assertTrue(s["terms"]["read"], f"{s['id']} is enabled without its terms having been read")
            for ds in s["datasets"]:
                self.assertTrue(ds["path"].startswith("/"))
                self.assertIn(ds.get("every"), ("day", "week"))
                self.assertIn(ds.get("dates"), (None, "recent", "last-week"))
                self.assertIn(ds.get("backfill"), (None, "years", "months"))
                self.assertLessEqual(len(ds.get("each") or {}), 1)
                self.assertTrue(ds.get("why"))
        names = [n for ds in cfg["sources"][0]["datasets"] for n, _ in marketdata.expand(ds)]
        self.assertEqual(len(names), len(set(names)), "every request needs its own file name")
        plan = marketdata.plan_reading(cfg, dt.date(2026, 10, 26), ["daily", "weekly"])
        extra_pages = 1 + 10          # the second page of apps, and up to ten more of session costs
        self.assertLess(len(plan) + extra_pages, 100, "the heaviest daily reading stays far inside 500 requests a day")


if __name__ == "__main__":
    unittest.main(verbosity=2)
