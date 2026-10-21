"""
Tests for scripts/hashes.py and scripts/mirror.sh.
Run from the repository root:  python3 tests/test_hashes.py
Uses temporary folders only.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import hashes  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class HashTests(unittest.TestCase):
    def setUp(self):
        self.src = tempfile.mkdtemp()
        self.dst = tempfile.mkdtemp()
        write(os.path.join(self.src, "data/census/2026-10-01/models.json"), '{"data": []}')
        write(os.path.join(self.src, "data/census/2026-10-01/endpoints/a__b.json"), '{"x": 1}')
        write(os.path.join(self.src, "data/probes/2026-10-15/manifest.json"), "{}")
        write(os.path.join(self.src, "data/probes/2026-10-15/listing/m.json"), "{}")
        # Incomplete days are not fingerprinted.
        write(os.path.join(self.src, "data/census/2026-10-02/endpoints/a__b.json"), "{}")
        write(os.path.join(self.src, "data/probes/2026-10-16/listing/m.json"), "{}")

    def tearDown(self):
        shutil.rmtree(self.src)
        shutil.rmtree(self.dst)

    def test_writes_one_manifest_per_complete_day(self):
        self.assertEqual(hashes.run(self.src, self.dst), 0)
        out = os.path.join(self.dst, "data/hashes")
        self.assertTrue(os.path.exists(os.path.join(out, "census/2026-10-01.sha256")))
        self.assertTrue(os.path.exists(os.path.join(out, "probes/2026-10-15.sha256")))
        self.assertFalse(os.path.exists(os.path.join(out, "census/2026-10-02.sha256")))
        self.assertFalse(os.path.exists(os.path.join(out, "probes/2026-10-16.sha256")))

    def test_manifest_checks_with_sha256sum(self):
        hashes.run(self.src, self.dst)
        manifest = os.path.join(self.dst, "data/hashes/census/2026-10-01.sha256")
        result = subprocess.run(["sha256sum", "-c", manifest], cwd=self.src, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rerun_changes_nothing(self):
        hashes.run(self.src, self.dst)
        manifest = os.path.join(self.dst, "data/hashes/census/2026-10-01.sha256")
        before = open(manifest).read()
        self.assertEqual(hashes.run(self.src, self.dst), 0)
        self.assertEqual(open(manifest).read(), before)

    def test_changed_raw_file_is_an_error_and_manifest_is_kept(self):
        hashes.run(self.src, self.dst)
        manifest = os.path.join(self.dst, "data/hashes/census/2026-10-01.sha256")
        before = open(manifest).read()
        write(os.path.join(self.src, "data/census/2026-10-01/models.json"), '{"data": ["changed"]}')
        self.assertEqual(hashes.run(self.src, self.dst), 1)
        self.assertEqual(open(manifest).read(), before)

    def test_mirror_never_copies_raw_files_or_workflows(self):
        write(os.path.join(self.src, "README.md"), "readme")
        write(os.path.join(self.src, "notes/selection.md"), "notes")
        write(os.path.join(self.src, ".github/workflows/main.yml"), "on: schedule")
        write(os.path.join(self.src, "scripts/hashes.py"), open(os.path.join(ROOT, "scripts/hashes.py")).read())
        write(os.path.join(self.dst, "data/census/old/models.json"), "{}")
        subprocess.run(["bash", os.path.join(ROOT, "scripts/mirror.sh"), self.src, self.dst], check=True,
                       capture_output=True)
        self.assertTrue(os.path.exists(os.path.join(self.dst, "README.md")))
        self.assertTrue(os.path.exists(os.path.join(self.dst, "notes/selection.md")))
        self.assertTrue(os.path.exists(os.path.join(self.dst, "data/hashes/census/2026-10-01.sha256")))
        self.assertFalse(os.path.exists(os.path.join(self.dst, ".github")))
        self.assertFalse(os.path.exists(os.path.join(self.dst, "data/census")))
        self.assertFalse(os.path.exists(os.path.join(self.dst, "data/probes")))

    def test_each_assessment_file_gets_its_own_fingerprint(self):
        write(os.path.join(self.src, "data/assessments/2026-10-27/deepseek-v4.1-flash.json"), '{"a": 1}')
        write(os.path.join(self.src, "data/assessments/2026-10-27/deepseek-v4.1-flash.json.tmp"), "partial")
        self.assertEqual(hashes.run(self.src, self.dst), 0)
        out = os.path.join(self.dst, "data/hashes/assessments/2026-10-27")
        self.assertEqual(os.listdir(out), ["deepseek-v4.1-flash.sha256"])
        result = subprocess.run(["sha256sum", "-c", os.path.join(out, "deepseek-v4.1-flash.sha256")],
                                cwd=self.src, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_an_assessment_added_to_an_earlier_day_is_a_new_fingerprint(self):
        write(os.path.join(self.src, "data/assessments/2026-10-27/deepseek-v4.1-flash.json"), '{"a": 1}')
        hashes.run(self.src, self.dst)
        write(os.path.join(self.src, "data/assessments/2026-10-27/deepseek-v4.1-flash-1017.json"), '{"b": 2}')
        self.assertEqual(hashes.run(self.src, self.dst), 0)
        out = os.path.join(self.dst, "data/hashes/assessments/2026-10-27")
        self.assertEqual(sorted(os.listdir(out)),
                         ["deepseek-v4.1-flash-1017.sha256", "deepseek-v4.1-flash.sha256"])

    def test_a_changed_assessment_is_an_error_and_its_fingerprint_is_kept(self):
        path = os.path.join(self.src, "data/assessments/2026-10-27/deepseek-v4.1-flash.json")
        write(path, '{"a": 1}')
        hashes.run(self.src, self.dst)
        fp = os.path.join(self.dst, "data/hashes/assessments/2026-10-27/deepseek-v4.1-flash.sha256")
        with open(fp) as f:
            before = f.read()
        write(path, '{"a": 2}')
        self.assertEqual(hashes.run(self.src, self.dst), 1)
        with open(fp) as f:
            self.assertEqual(f.read(), before)

    def test_offwindow_readings_are_fingerprinted_and_never_copied(self):
        write(os.path.join(self.src, "data/offwindow/2026-10-24-1405/manifest.json"), "{}")
        write(os.path.join(self.src, "data/offwindow/2026-10-24-1405/requests/a.json"), "{}")
        write(os.path.join(self.src, "data/offwindow/2026-10-25-0917/requests/a.json"), "{}")   # unfinished
        write(os.path.join(self.src, "data/assessments/2026-10-27/deepseek-v4.1-flash.json"), "{}")
        write(os.path.join(self.src, "launch/publish.py"), "")
        write(os.path.join(self.src, "server/crontab"), "")
        write(os.path.join(self.src, "scripts/hashes.py"), open(os.path.join(ROOT, "scripts/hashes.py")).read())
        for stray in ("data/offwindow/x/manifest.json", "data/assessments/x.json", "launch/x", "server/x"):
            write(os.path.join(self.dst, stray), "{}")
        subprocess.run(["bash", os.path.join(ROOT, "scripts/mirror.sh"), self.src, self.dst], check=True,
                       capture_output=True)
        out = os.path.join(self.dst, "data/hashes/offwindow")
        self.assertEqual(os.listdir(out), ["2026-10-24-1405.sha256"])
        for private in ("data/offwindow", "data/assessments", "launch", "server"):
            self.assertFalse(os.path.exists(os.path.join(self.dst, private)), private + " must never be public")


if __name__ == "__main__":
    unittest.main(verbosity=2)
