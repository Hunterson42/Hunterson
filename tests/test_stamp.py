"""
Tests for scripts/stamp.py.
Run from the repository root:  python3 tests/test_stamp.py

Neither service is contacted. OpenTimestamps is replaced by a small stand-in
for the `ots` command, and FreeTSA by a real RFC 3161 authority run locally
with openssl, with its own test certificates, so that the openssl checks are
the real ones. Uses temporary folders only.
"""
import datetime as dt
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import stamp  # noqa: E402

FAKE_OTS = textwrap.dedent('''\
    #!/usr/bin/env python3
    # Stand-in for the OpenTimestamps client: stamp, info and upgrade only.
    import hashlib, os, shutil, sys
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cmd, files = args[0], args[1:]
    def digest(path):
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    if cmd == "stamp":
        if os.environ.get("FAKE_OTS_DOWN"):
            sys.exit(1)
        for f in files:
            open(f + ".ots", "w").write("PENDING " + digest(f))
    elif cmd == "info":
        kind, h = open(files[0]).read().split()[:2]
        print("File sha256 hash: " + h)
        print("Timestamp:")
        if kind == "COMPLETE":
            print("verify BitcoinBlockHeaderAttestation(900000)")
        else:
            print("verify PendingAttestation('https://a.pool.opentimestamps.org')")
    elif cmd == "upgrade":
        for p in files:
            h = open(p).read().split()[1]
            shutil.move(p, p + ".bak")
            if os.environ.get("FAKE_OTS_CONFIRMED"):
                open(p, "w").write("COMPLETE " + h)
            else:
                open(p, "w").write("PENDING " + h + " rewritten")
''')

TSA_CONF = textwrap.dedent('''\
    [ tsa ]
    default_tsa = tsa_config1
    [ tsa_config1 ]
    serial = {dir}/serial
    crypto_device = builtin
    signer_cert = {dir}/tsa.crt
    certs = {dir}/cacert.pem
    signer_key = {dir}/tsa.key
    signer_digest = sha256
    default_policy = 1.2.3.4.1
    digests = sha256, sha512
    accuracy = secs:1
    ordering = yes
    tsa_name = yes
    ess_cert_id_chain = no
    ess_cert_id_alg = sha256
''')


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def read(path, mode="r"):
    with open(path, mode) as f:
        return f.read()


def openssl(*args, cwd):
    subprocess.run(["openssl", *args], cwd=cwd, check=True, capture_output=True)


def make_authority(folder, name):
    """A test CA and a time-stamping certificate signed by it."""
    os.makedirs(folder)
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "cacert.pem",
            "-subj", f"/CN={name} test CA", "-days", "2",
            "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign",
            cwd=folder)
    openssl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", "tsa.key", "-out", "tsa.csr",
            "-subj", f"/CN={name} test TSA", cwd=folder)
    write(os.path.join(folder, "ext.cnf"),
          "extendedKeyUsage=critical,timeStamping\nkeyUsage=critical,digitalSignature,nonRepudiation\n")
    openssl("x509", "-req", "-in", "tsa.csr", "-CA", "cacert.pem", "-CAkey", "ca.key", "-CAcreateserial",
            "-out", "tsa.crt", "-days", "2", "-extfile", "ext.cnf", cwd=folder)
    write(os.path.join(folder, "serial"), "01\n")
    write(os.path.join(folder, "tsa.cnf"), TSA_CONF.format(dir=folder))


def local_tsa(folder):
    """A function that answers an RFC 3161 query as the authority in folder would."""
    def answer(body):
        with tempfile.TemporaryDirectory() as tmp:
            q, r = os.path.join(tmp, "q.tsq"), os.path.join(tmp, "r.tsr")
            with open(q, "wb") as f:
                f.write(body)
            openssl("ts", "-reply", "-config", os.path.join(folder, "tsa.cnf"), "-queryfile", q,
                    "-out", r, cwd=folder)
            return read(r, "rb")
    return answer


class StampTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.keys = tempfile.mkdtemp()
        make_authority(os.path.join(cls.keys, "good"), "Good")
        make_authority(os.path.join(cls.keys, "other"), "Other")
        cls.ots = os.path.join(cls.keys, "ots")
        write(cls.ots, FAKE_OTS)
        os.chmod(cls.ots, os.stat(cls.ots).st_mode | stat.S_IEXEC)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.keys)

    def setUp(self):
        self.pub = tempfile.mkdtemp()
        self.priv = tempfile.mkdtemp()
        self.fp_census = os.path.join(self.pub, "data/hashes/census/2026-10-01.sha256")
        self.fp_assess = os.path.join(self.pub, "data/hashes/assessments/2026-10-27/deepseek-v4.1-flash.sha256")
        write(self.fp_census, "aa  data/census/2026-10-01/models.json\n")
        write(self.fp_assess, "bb  data/assessments/2026-10-27/deepseek-v4.1-flash.json\n")
        good = os.path.join(self.keys, "good")
        for name in ("tsa.crt", "cacert.pem"):
            write(os.path.join(self.priv, "data/stamps/certs", name), read(os.path.join(good, name)))
        self.saved = (stamp.OTS, stamp.post_query, stamp.download)
        stamp.OTS = self.ots
        stamp.post_query = local_tsa(good)
        stamp.download = self.no_network
        for var in ("FAKE_OTS_DOWN", "FAKE_OTS_CONFIRMED"):
            os.environ.pop(var, None)

    def tearDown(self):
        stamp.OTS, stamp.post_query, stamp.download = self.saved
        shutil.rmtree(self.pub)
        shutil.rmtree(self.priv)

    @staticmethod
    def no_network(url):
        raise OSError("no network in tests")

    def run_quietly(self, **kw):
        devnull = open(os.devnull, "w")
        old, sys.stdout = sys.stdout, devnull
        try:
            return stamp.stamp_all(self.pub, self.priv, now=dt.datetime(2026, 10, 21, 15, 0), **kw)
        finally:
            sys.stdout = old
            devnull.close()

    def test_every_fingerprint_gets_both_proofs(self):
        c = self.run_quietly()
        self.assertEqual((c["stamped"], c["signed"], c["failed"]), (2, 2, 0))
        for fp in (self.fp_census, self.fp_assess):
            self.assertTrue(os.path.exists(fp + ".ots"))
            self.assertTrue(os.path.exists(fp + ".tsr"))

    def test_token_verifies_with_openssl_as_the_readme_says(self):
        self.run_quietly()
        certs = os.path.join(self.pub, "data/stamps/certs")
        r = subprocess.run(["openssl", "ts", "-verify", "-data", self.fp_census, "-in", self.fp_census + ".tsr",
                            "-CAfile", os.path.join(certs, "cacert.pem"),
                            "-untrusted", os.path.join(certs, "tsa.crt")], capture_output=True, text=True)
        self.assertIn("Verification: OK", r.stdout, r.stderr)

    def test_certificates_copied_from_private_with_their_sums(self):
        self.run_quietly()
        certs = os.path.join(self.pub, "data/stamps/certs")
        sums = read(os.path.join(certs, "SHA256SUMS"))
        for name in ("tsa.crt", "cacert.pem"):
            h = hashlib.sha256(read(os.path.join(certs, name), "rb")).hexdigest()
            self.assertIn(f"{h}  data/stamps/certs/{name}", sums)

    def test_a_reply_that_does_not_verify_is_not_written(self):
        stamp.post_query = local_tsa(os.path.join(self.keys, "other"))
        c = self.run_quietly()
        self.assertEqual((c["signed"], c["failed"]), (0, 2))
        self.assertFalse(os.path.exists(self.fp_census + ".tsr"))

    def test_without_certificates_nothing_is_signed_and_nothing_breaks(self):
        shutil.rmtree(os.path.join(self.priv, "data/stamps"))
        c = self.run_quietly()
        self.assertEqual(c["signed"], 0)
        self.assertEqual(c["stamped"], 2)
        self.assertFalse(os.path.exists(self.fp_census + ".tsr"))

    def test_proofs_are_written_once(self):
        self.run_quietly()
        before = {p: read(p, "rb") for p in (self.fp_census + ".ots", self.fp_census + ".tsr")}
        c = self.run_quietly()
        self.assertEqual((c["stamped"], c["signed"]), (0, 0))
        for p, data in before.items():
            self.assertEqual(read(p, "rb"), data)

    def test_pending_proof_is_left_exactly_as_it_was(self):
        self.run_quietly()
        proof = self.fp_census + ".ots"
        before = read(proof, "rb")
        c = self.run_quietly()
        self.assertEqual(c["pending"], 2)
        self.assertEqual(read(proof, "rb"), before)
        self.assertFalse(os.path.exists(proof + ".bak"))

    def test_pending_proof_is_completed_once_then_never_touched(self):
        self.run_quietly()
        os.environ["FAKE_OTS_CONFIRMED"] = "1"
        c = self.run_quietly()
        self.assertEqual(c["completed"], 2)
        proof = self.fp_census + ".ots"
        self.assertTrue(read(proof).startswith("COMPLETE"))
        self.assertFalse(os.path.exists(proof + ".bak"))
        done = read(proof, "rb")
        c = self.run_quietly()
        self.assertEqual((c["completed"], c["pending"]), (0, 0))
        self.assertEqual(read(proof, "rb"), done)

    def test_calendar_down_is_retried_next_run(self):
        os.environ["FAKE_OTS_DOWN"] = "1"
        c = self.run_quietly()
        self.assertEqual((c["stamped"], c["signed"]), (0, 2))
        self.assertFalse(os.path.exists(self.fp_census + ".ots"))
        os.environ.pop("FAKE_OTS_DOWN")
        c = self.run_quietly()
        self.assertEqual(c["stamped"], 2)

    def test_without_the_client_only_rfc3161_proofs_are_made(self):
        stamp.OTS = os.path.join(self.keys, "no-such-ots")
        c = self.run_quietly()
        self.assertEqual((c["stamped"], c["signed"]), (0, 2))

    def test_start_is_recorded_once(self):
        self.run_quietly()
        path = os.path.join(self.pub, "data/hashes/stamping-began.txt")
        first = read(path)
        self.assertIn("2026-10-21 15:00 UTC", first)
        write(os.path.join(self.pub, "data/hashes/census/2026-10-02.sha256"), "cc  x\n")
        devnull = open(os.devnull, "w")
        old, sys.stdout = sys.stdout, devnull
        try:
            stamp.stamp_all(self.pub, self.priv, now=dt.datetime(2026, 10, 22, 6, 30))
        finally:
            sys.stdout = old
            devnull.close()
        self.assertEqual(read(path), first)

    def test_main_never_fails_because_of_a_service(self):
        stamp.post_query = self.no_network
        os.environ["FAKE_OTS_DOWN"] = "1"
        devnull = open(os.devnull, "w")
        old, sys.stdout = sys.stdout, devnull
        try:
            self.assertEqual(stamp.main(["stamp.py", self.pub, "--certs-from", self.priv]), 0)
        finally:
            sys.stdout = old
            devnull.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
