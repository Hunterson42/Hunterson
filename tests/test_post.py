"""
Tests for scripts/post.py, the daily post, and for the launch documents beside it.
Nothing is sent anywhere: X and the site are replaced by stand-ins.
Run with: python3 -m unittest discover tests
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import post  # noqa: E402

KEYS = ("xvz1evFS4wEEPTGEFPHBog", "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
        "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb", "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE")


class PostTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.root)
        with open("panel.json", "w") as f:
            json.dump({"launch_date": "2026-11-03"}, f)
        os.makedirs(os.path.join("docs", "tweet", "standard"))
        for d in ("2026-11-03", "2026-11-04"):
            with open(os.path.join("docs", "tweet", "standard", d + ".txt"), "w") as f:
                f.write("Hunterson Standard Inference, Europe\n%s\n" % d)
        self.sent, self.ok = [], True
        self.saved = post.call, post.served, post.WAITS
        post.call = lambda method, url, keys, body=None: (self.sent.append(body) or (201, {"data": {"id": "1%d" % len(self.sent)}}))
        post.served = lambda url: self.ok
        post.WAITS = [0, 0]
        for k in post.KEYS + ("SITE_HOST",):
            os.environ[k] = "hunterson.org" if k == "SITE_HOST" else "test"

    def tearDown(self):
        post.call, post.served, post.WAITS = self.saved
        os.chdir(self.cwd)
        shutil.rmtree(self.root)

    def test_signature_matches_the_published_worked_example(self):
        # The worked example in X's documentation of OAuth 1.0a signing.
        h = post.oauth_header("POST", "https://api.twitter.com/1.1/statuses/update.json", KEYS,
                              params={"include_entities": "true",
                                      "status": "Hello Ladies + Gentlemen, a signed OAuth request!"},
                              nonce="kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg", timestamp=1318622958)
        self.assertIn('oauth_signature="hCtSmYh%2BiHYCEqBWrE7C7hYmtUk%3D"', h)
        self.assertTrue(h.startswith("OAuth "))

    def test_posts_once_and_records_it(self):
        self.assertEqual(post.main(["--today", "2026-11-03"]), 0)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("2026-11-03", self.sent[0]["text"])
        with open(os.path.join("data", "posts", "2026-11-03-standard.json")) as f:
            self.assertEqual(json.load(f)["id"], "11")
        self.assertEqual(post.main(["--today", "2026-11-03"]), 0)    # the second attempt finds it done
        self.assertEqual(len(self.sent), 1)

    def test_nothing_before_the_launch_date(self):
        self.assertEqual(post.main(["--today", "2026-11-02"]), 0)
        self.assertEqual(self.sent, [])

    def test_waits_for_the_page_and_image(self):
        self.ok = False
        self.assertEqual(post.main(["--today", "2026-11-04"]), 1)
        self.assertEqual(self.sent, [])
        self.assertFalse(os.path.exists(os.path.join("data", "posts", "2026-11-04-standard.json")))

    def test_a_refused_post_is_not_recorded(self):
        post.call = lambda method, url, keys, body=None: (403, {"error": "forbidden"})
        self.assertEqual(post.main(["--today", "2026-11-04"]), 1)
        self.assertFalse(os.path.exists(os.path.join("data", "posts")))

    def test_a_suspension_notice_is_posted_once_within_a_week(self):
        os.makedirs(os.path.join("docs", "tweet", "notice"))
        with open(os.path.join("docs", "tweet", "notice", "2026-12-18.txt"), "w") as f:
            f.write("Publication is suspended from 18 December 2026")
        self.assertEqual(post.main(["--today", "2026-12-21"]), 0)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(post.main(["--today", "2026-12-22"]), 0)
        self.assertEqual(len(self.sent), 1)
        shutil.rmtree(os.path.join("data", "posts"))
        self.assertEqual(post.main(["--today", "2027-01-04"]), 0)     # too old to post
        self.assertEqual(len(self.sent), 1)

    def test_missing_secrets_stop_before_anything_is_sent(self):
        del os.environ["X_ACCESS_TOKEN"]
        with self.assertRaises(SystemExit):
            post.main(["--today", "2026-11-03"])
        self.assertEqual(self.sent, [])


class LaunchDocumentTests(unittest.TestCase):
    def read(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return f.read()

    def test_no_dashes_and_no_brackets_left_to_choose(self):
        for rel in ("CONFLICTS.md", "CONTINUITY.md", "NOTICE", "LICENSE.md"):
            text = self.read(rel)
            self.assertNotRegex(text, "[–—]", rel)
            self.assertNotIn("CHOOSE", text, rel)
            self.assertNotIn("[date", text, rel)

    def test_continuity_states_the_lapse_the_code_uses(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts", "site"))
        import oversight
        with open(os.path.join(ROOT, "data", "oversight.json")) as f:
            record = json.load(f)
        self.assertEqual(record["lapse_days"], oversight.LAPSE_DAYS)
        self.assertIn("within the previous %d days" % oversight.LAPSE_DAYS, self.read("CONTINUITY.md"))

    def test_the_code_licence_is_apache_2(self):
        text = self.read("LICENSE-APACHE-2.0.txt")
        self.assertIn("Apache License\n                           Version 2.0, January 2004", text)
        self.assertIn("END OF TERMS AND CONDITIONS", text)
        self.assertIn("Apache License, Version 2.0", self.read("LICENSE.md"))
        self.assertNotIn("has not yet been chosen", self.read("LICENSE.md"))

    def test_launch_date_is_a_weekday(self):
        with open(os.path.join(ROOT, "panel.json")) as f:
            launch = json.load(f)["launch_date"]
        self.assertRegex(launch, r"^\d{4}-\d{2}-\d{2}$")
        self.assertLess(dt.date.fromisoformat(launch).weekday(), 5)


if __name__ == "__main__":
    unittest.main()
