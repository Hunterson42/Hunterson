"""
Timestamps for the fingerprints (decision D33).

Usage, from anywhere:

    python3 scripts/stamp.py PUBLIC_ROOT [--certs-from PRIVATE_ROOT]

PUBLIC_ROOT is the checkout that holds data/hashes, as written by hashes.py.
The mirror workflow runs this straight after the mirror, on the public copy.

For every fingerprint file, data/hashes/**/*.sha256, it makes sure two proofs
lie beside it:

  NAME.sha256.ots  an OpenTimestamps proof. The fingerprint file's hash is sent
                   to the public OpenTimestamps calendars, which anchor it in
                   the Bitcoin blockchain within a few hours. A new proof is
                   pending until then; a later run completes it.
  NAME.sha256.tsr  an RFC 3161 time-stamp token from FreeTSA, signed at once.
                   It is checked with openssl against FreeTSA's certificates
                   before it is written.

Only hashes leave the machine, never the records.

Each proof is written once. A pending OpenTimestamps proof is left exactly as
it is, byte for byte, until a run finds that its Bitcoin attestation is ready;
the completed proof then replaces it, once, and is never touched again. The
client's backup copy (NAME.sha256.ots.bak) is removed.

FreeTSA's certificates are kept in data/stamps/certs/. If they are missing from
the public copy, they are copied from the private checkout (--certs-from) or,
failing that, downloaded once, and their SHA-256 written beside them.

The first run that makes any proof writes data/hashes/stamping-began.txt, once.
Fingerprints written before that moment prove existence from it, not from the
day of their records.

A service that fails is reported, and tried again on the next run. The script
never exits with an error because of one, so the mirror always publishes.

Needs openssl, and the OpenTimestamps client (pip install
opentimestamps-client). Without the client, only the RFC 3161 proofs are made.
Otherwise uses only the Python standard library.
"""

import datetime as dt
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

OTS = os.environ.get("HUNTERSON_OTS", "ots")
TSA_URL = os.environ.get("HUNTERSON_TSA_URL", "https://freetsa.org/tsr")
CERT_URLS = {
    "tsa.crt": "https://freetsa.org/files/tsa.crt",
    "cacert.pem": "https://freetsa.org/files/cacert.pem",
}
NETWORK_TIMEOUT = 60


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def fingerprints(root):
    base = os.path.join(root, "data", "hashes")
    found = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames.sort()
        for name in sorted(filenames):
            if name.endswith(".sha256"):
                found.append(os.path.join(dirpath, name))
    return sorted(found)


def run(cmd, timeout):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# OpenTimestamps -------------------------------------------------------------

def ots_available():
    return shutil.which(OTS) is not None


def ots_info(proof):
    """The hash a proof commits to, and whether it carries a Bitcoin attestation."""
    try:
        r = run([OTS, "--no-cache", "info", proof], 60)
    except (OSError, subprocess.TimeoutExpired):
        return None, False
    digest = None
    for line in r.stdout.splitlines():
        if line.startswith("File sha256 hash:"):
            digest = line.split(":", 1)[1].strip()
    return digest, "BitcoinBlockHeaderAttestation" in r.stdout


def stamp_ots(files, counts):
    if not files:
        return
    try:
        r = run([OTS, "stamp", *files], 300)
        if r.returncode != 0:
            counts["notes"].append("OpenTimestamps: " + (r.stderr.strip() or r.stdout.strip())[:200])
    except (OSError, subprocess.TimeoutExpired) as e:
        counts["notes"].append(f"OpenTimestamps: {e}")
    for f in files:
        proof = f + ".ots"
        if not os.path.exists(proof):
            counts["failed"] += 1
            continue
        digest, _ = ots_info(proof)
        if digest != sha256_file(f):
            os.remove(proof)
            counts["failed"] += 1
            counts["notes"].append(f"OpenTimestamps: the proof for {f} did not match it, and was removed")
            continue
        counts["stamped"] += 1


def complete_ots(proofs, counts):
    """Try to complete pending proofs; leave each untouched unless it completes."""
    if not proofs:
        return
    originals = {}
    for proof in proofs:
        with open(proof, "rb") as f:
            originals[proof] = f.read()
    try:
        run([OTS, "upgrade", *proofs], 300)
    except (OSError, subprocess.TimeoutExpired) as e:
        counts["notes"].append(f"OpenTimestamps upgrade: {e}")
    for proof in proofs:
        complete = False
        if os.path.exists(proof):
            digest, complete = ots_info(proof)
            complete = complete and digest == sha256_file(proof[:-len(".ots")])
        if complete:
            counts["completed"] += 1
        else:
            write_atomic(proof, originals[proof])
            counts["pending"] += 1
        backup = proof + ".bak"
        if os.path.exists(backup):
            os.remove(backup)


# RFC 3161 -------------------------------------------------------------------

def download(url):
    with urllib.request.urlopen(url, timeout=NETWORK_TIMEOUT) as r:
        return r.read()


def post_query(body):
    req = urllib.request.Request(TSA_URL, data=body, headers={"Content-Type": "application/timestamp-query"})
    with urllib.request.urlopen(req, timeout=NETWORK_TIMEOUT) as r:
        return r.read()


def ensure_certs(public_root, private_root, counts):
    """FreeTSA's certificates in the public copy, or None if they cannot be had."""
    certs = os.path.join(public_root, "data", "stamps", "certs")
    os.makedirs(certs, exist_ok=True)
    fetched = False
    for name, url in CERT_URLS.items():
        target = os.path.join(certs, name)
        if os.path.exists(target):
            continue
        source = os.path.join(private_root, "data", "stamps", "certs", name) if private_root else None
        if source and os.path.exists(source):
            shutil.copyfile(source, target)
            continue
        try:
            write_atomic(target, download(url))
            fetched = True
        except Exception as e:      # any network failure: try again next run
            counts["notes"].append(f"FreeTSA certificate {name}: {e}")
            return None
    sums = os.path.join(certs, "SHA256SUMS")
    if fetched or not os.path.exists(sums):
        lines = [f"{sha256_file(os.path.join(certs, n))}  data/stamps/certs/{n}" for n in sorted(CERT_URLS)]
        write_atomic(sums, ("\n".join(lines) + "\n").encode())
    return certs


def verify_tsr(fingerprint, reply, certs):
    try:
        r = run(["openssl", "ts", "-verify", "-data", fingerprint, "-in", reply,
                 "-CAfile", os.path.join(certs, "cacert.pem"),
                 "-untrusted", os.path.join(certs, "tsa.crt")], 60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and "Verification: OK" in r.stdout


def sign_tsr(fingerprint, certs, counts):
    with tempfile.TemporaryDirectory() as tmp:
        query = os.path.join(tmp, "q.tsq")
        reply = os.path.join(tmp, "r.tsr")
        try:
            r = run(["openssl", "ts", "-query", "-data", fingerprint, "-no_nonce", "-sha256", "-cert",
                     "-out", query], 60)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip()[:200])
            with open(query, "rb") as f:
                body = f.read()
            with open(reply, "wb") as f:
                f.write(post_query(body))
        except Exception as e:      # any network or openssl failure: try again next run
            counts["failed"] += 1
            counts["notes"].append(f"RFC 3161, {os.path.basename(fingerprint)}: {e}")
            return
        if not verify_tsr(fingerprint, reply, certs):
            counts["failed"] += 1
            counts["notes"].append(f"RFC 3161, {os.path.basename(fingerprint)}: the reply did not verify, "
                                   "so it was not written")
            return
        with open(reply, "rb") as f:
            write_atomic(fingerprint + ".tsr", f.read())
        counts["signed"] += 1


# The run --------------------------------------------------------------------

def mark_start(public_root, now):
    path = os.path.join(public_root, "data", "hashes", "stamping-began.txt")
    if os.path.exists(path):
        return
    text = (f"Timestamping began at {now:%Y-%m-%d %H:%M} UTC (decision D33).\n"
            "Each fingerprint written before then was stamped at that moment, and its proofs show that\n"
            "it existed from then, not from the day of its records. Each fingerprint written since was\n"
            "stamped when it was written.\n")
    write_atomic(path, text.encode())


def stamp_all(public_root, private_root=None, now=None):
    counts = {"stamped": 0, "signed": 0, "completed": 0, "pending": 0, "failed": 0, "notes": []}
    files = fingerprints(public_root)

    if ots_available():
        earlier = [f + ".ots" for f in files if os.path.exists(f + ".ots")]
        stamp_ots([f for f in files if not os.path.exists(f + ".ots")], counts)
        # Proofs made in this run cannot be complete yet, so only earlier ones are tried.
        complete_ots([p for p in earlier if not ots_info(p)[1]], counts)
    else:
        counts["notes"].append(f"The OpenTimestamps client ({OTS}) is not installed; no OpenTimestamps proofs")

    missing = [f for f in files if not os.path.exists(f + ".tsr")]
    if missing:
        certs = ensure_certs(public_root, private_root, counts)
        if certs:
            for f in missing:
                sign_tsr(f, certs, counts)
        else:
            counts["failed"] += len(missing)

    if counts["stamped"] or counts["signed"]:
        mark_start(public_root, now or dt.datetime.now(dt.timezone.utc))

    print(f"Timestamps: {counts['stamped']} stamped with OpenTimestamps, {counts['signed']} signed under "
          f"RFC 3161, {counts['completed']} completed in Bitcoin, {counts['pending']} still pending, "
          f"{counts['failed']} failed and to be tried again.")
    for note in counts["notes"]:
        print("NOTE: " + note)
    return counts


def main(argv):
    args = argv[1:]
    private_root = None
    if "--certs-from" in args:
        i = args.index("--certs-from")
        if i + 1 >= len(args):
            print(__doc__)
            return 2
        private_root = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        print(__doc__)
        return 2
    stamp_all(args[0], private_root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
