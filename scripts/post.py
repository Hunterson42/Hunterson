"""
Posts the day's price to X, once, after the day's page and its image are live.

Run by the Post workflow in the private repository straight after the Publish
workflow, with backstops at 16:05 and 16:47 UTC on weekdays, from the launch
date in panel.json. For each grade
with a post written for today, docs/tweet/GRADE/DATE.txt, it waits until
https://SITE_HOST/GRADE/DATE/ and its image https://SITE_HOST/og/GRADE/DATE.png
are served, so that X shows the card under the post, then posts the text
through the X API and records the post in data/posts/DATE-GRADE.json. A post
already recorded is never made again. A notice that publication is suspended,
docs/tweet/notice/DATE.txt (decision D50), is posted the same way, once,
within a week of its date.

    python3 scripts/post.py [--today YYYY-MM-DD]
    python3 scripts/post.py --check

--check confirms that the secrets are set and that X accepts the credentials,
by reading the account's own name, and posts nothing. The dry run uses it.

Secrets, from the environment: X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN,
X_ACCESS_TOKEN_SECRET (OAuth 1.0a, user context) and SITE_HOST, such as
hunterson.org. None is ever printed. Uses only the Python standard library.
"""
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.x.com/2"
KEYS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
WAITS = [30] * 40                  # up to twenty minutes for the mirror and GitHub Pages
NOTICE_DAYS = 7
UA = "hunterson-post/1.0 (+https://hunterson.org/)"


def pct(s):
    return urllib.parse.quote(str(s), safe="~")


def oauth_header(method, url, keys, params=None, nonce=None, timestamp=None):
    """The OAuth 1.0a Authorization header, HMAC-SHA1. params are the query or
    form parameters; a JSON body is not part of the signature."""
    consumer_key, consumer_secret, token, token_secret = keys
    oauth = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(timestamp or int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    allp = dict(params or {}, **oauth)
    query = "&".join("%s=%s" % kv for kv in sorted((pct(k), pct(v)) for k, v in allp.items()))
    base = "&".join([method.upper(), pct(url), pct(query)])
    key = "%s&%s" % (pct(consumer_secret), pct(token_secret))
    oauth["oauth_signature"] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join('%s="%s"' % (pct(k), pct(v)) for k, v in sorted(oauth.items()))


def keys_from_env():
    missing = [k for k in KEYS + ("SITE_HOST",) if not os.environ.get(k)]
    if missing:
        raise SystemExit("Missing secrets: %s" % ", ".join(missing))
    return tuple(os.environ[k] for k in KEYS), os.environ["SITE_HOST"].strip().strip("/")


def call(method, url, keys, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", oauth_header(method, url, keys))
    req.add_header("User-Agent", UA)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as err:
        text = err.read().decode(errors="replace")[:500]
        return err.code, {"error": text}


def served(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def wait_until_served(urls, waits=None, sleep=time.sleep):
    for w in [0] + list(WAITS if waits is None else waits):
        sleep(w)
        if all(served(u) for u in urls):
            return True
    return False


def todo(root, today):
    """[(record name, text file, [urls that must be served first]), ...] for today."""
    with open(os.path.join(root, "panel.json")) as f:
        launch = json.load(f).get("launch_date")
    if not launch or today.isoformat() < launch:
        return []
    base = os.path.join(root, "docs", "tweet")
    out = []
    for g in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        folder = os.path.join(base, g)
        if g == "notice" or not os.path.isdir(folder):
            continue
        path = os.path.join(folder, today.isoformat() + ".txt")
        if os.path.exists(path):
            out.append(("%s-%s" % (today.isoformat(), g), path,
                        ["/%s/%s/" % (g, today.isoformat()), "/og/%s/%s.png" % (g, today.isoformat())]))
    notices = os.path.join(base, "notice")
    for fn in sorted(os.listdir(notices)) if os.path.isdir(notices) else []:
        d = fn[:-4]
        if fn.endswith(".txt") and 0 <= (today - dt.date.fromisoformat(d)).days <= NOTICE_DAYS:
            out.append(("notice-" + d, os.path.join(notices, fn), ["/"]))
    done = os.path.join(root, "data", "posts")
    return [t for t in out if not os.path.exists(os.path.join(done, t[0] + ".json"))]


def check():
    keys, host = keys_from_env()
    status, body = call("GET", API + "/users/me", keys)
    if status != 200:
        print("X did not accept the credentials: HTTP %d %s" % (status, body.get("error", "")))
        return 1
    print("The secrets are set; X accepts the credentials for @%s; SITE_HOST is %s. Nothing was posted."
          % (body.get("data", {}).get("username", "?"), host))
    return 0


def main(argv):
    if "--check" in argv:
        return check()
    today = dt.datetime.now(dt.timezone.utc).date()
    if "--today" in argv:
        today = dt.date.fromisoformat(argv[argv.index("--today") + 1])
    root = os.getcwd()
    jobs = todo(root, today)
    if not jobs:
        print("Nothing to post for %s." % today.isoformat())
        return 0
    keys, host = keys_from_env()
    failed = 0
    for name, path, paths in jobs:
        urls = ["https://%s%s" % (host, p) for p in paths]
        if not wait_until_served(urls):
            print("%s: not posted, because the page or its image is not yet served." % name)
            failed += 1
            continue
        with open(path) as f:
            text = f.read().strip()
        status, body = call("POST", API + "/tweets", keys, {"text": text})
        if status != 201 or "data" not in body:
            print("%s: X refused the post: HTTP %d %s" % (name, status, body.get("error", "")))
            failed += 1
            continue
        os.makedirs(os.path.join(root, "data", "posts"), exist_ok=True)
        with open(os.path.join(root, "data", "posts", name + ".json"), "w") as f:
            json.dump({"name": name, "id": body["data"]["id"], "text": text,
                       "posted_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}, f, indent=2)
            f.write("\n")
        print("%s: posted, id %s." % (name, body["data"]["id"]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
