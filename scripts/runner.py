"""
The server's runner. Every job on the London server goes through this one
script, started by cron from server/crontab, so that each job is logged in one
place and no job can be stopped by another's failure, or by GitHub's.

    python3 scripts/runner.py census    06:15 UTC every day: the census, pushed
                                        to Hunterson-raw, then the census alarm
    python3 scripts/runner.py window    14:05 UTC Monday to Friday: the
                                        assessed window, pushed as soon as the
                                        probe finishes
    python3 scripts/runner.py weekend   14:05 UTC Saturday and Sunday: the same
                                        procedure, for research only (D28)
    python3 scripts/runner.py random    five past every hour: runs the
                                        procedure once a day, at an hour chosen
                                        at random each day, for research only
                                        (D28); every other hour it does nothing
    python3 scripts/runner.py gpu       a reading of GPU-hour prices by hand,
                                        pushed to Hunterson-raw (D36). The
                                        census and window jobs each take one
                                        a day themselves, after their own work
    python3 scripts/runner.py market    a reading of OpenRouter's market data
                                        by hand, pushed (D38). The census job
                                        takes one a day itself, last of all
    python3 scripts/runner.py market-backfill
                                        once only: the market data history the
                                        Data API still serves, from 1 January
                                        2025, pushed. Takes about 20 minutes
    python3 scripts/runner.py check     checks the set-up and says what it
                                        finds, including that the server may
                                        push to Hunterson-raw; changes nothing
                                        but git's record of the remote

What it guarantees.

- The probe runs even if `git pull` fails: a GitHub fault at 14:05 no longer
  cancels the window. It runs with the code already on the server.
- The probe's files are pushed when it finishes, not at a fixed 15:00, with up
  to four attempts. A commit that still cannot be pushed stays on the server
  and goes with the next push.
- The probe is stopped after 58 minutes, whatever happens, and whatever it
  wrote is pushed. Each request also has its own time limit (scripts/probe.py).
- Git is used by one job at a time (a lock file), so an hourly reading can
  never collide with the census.
- The census is labelled "server" in its record, and the census alarm is
  pinged from here once the day's census is safely in Hunterson-raw, so the
  alarm no longer depends on GitHub's run.
- Readings outside the window go to data/offwindow/DATE-HHMM/, which the
  assessor never reads. The random hour is never 13:00 or 14:00 UTC, so a
  reading cannot overlap the window.
- GPU-hour prices (scripts/gpuprices.py, decision D36) are read after the
  census, as the "morning" reading, and after the window's files are pushed,
  as the "window" reading, into data/gpu/DATE-HHMM/, and pushed separately.
  They come last on purpose: whatever happens to them, the census, its alarm
  and the window are already done, and their exit codes are unchanged.
- OpenRouter's market data (scripts/marketdata.py, decision D38) is read once
  a day after the census and its GPU reading, into data/market/DATE-HHMM/,
  and pushed separately, on the same terms: it never changes the census job's
  exit code.

Files on the server, under /root unless RUNNER_HOME says otherwise:

    keys.env              API keys and the census alarm address, one NAME=value
                          a line. Never in the repository
    logs/runner-YYYY-MM.log   everything every job did, with times in UTC
    state/random-hour.json    today's random hour; private to the server
    runner.lock           the git lock

Uses only the Python standard library.
"""
import datetime as dt
import fcntl
import json
import os
import random
import subprocess
import sys
import time
import urllib.request

REPO = os.environ.get("RUNNER_REPO") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.environ.get("RUNNER_HOME", "/root")
KEYS = os.path.join(HOME, "keys.env")
LOGS = os.path.join(HOME, "logs")
STATE = os.path.join(HOME, "state")
LOCK = os.path.join(HOME, "runner.lock")
PY = sys.executable or "python3"

PROBE_LIMIT = 58 * 60          # seconds; the probe itself stops starting requests at 50 minutes
CENSUS_LIMIT = 40 * 60
GPU_LIMIT = 10 * 60
MARKET_LIMIT = 15 * 60
BACKFILL_LIMIT = 45 * 60
STEP_LIMIT = 10 * 60
PUSH_ATTEMPTS = 4
RANDOM_EXCLUDED_HOURS = (13, 14)   # never overlap the 14:00 to 15:00 window
RANDOM_START_MINUTES = (5, 25)     # start between five and twenty-five past the hour
EXCLUDED_DAYS = {(12, 25), (1, 1)}

JOB = "runner"


def utc_now():
    fixed = os.environ.get("RUNNER_NOW")          # for the tests only
    if fixed:
        return dt.datetime.fromisoformat(fixed).replace(tzinfo=dt.timezone.utc)
    return dt.datetime.now(dt.timezone.utc)


def log(message):
    stamp = utc_now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} UTC [{JOB}] {message}"
    print(line, flush=True)
    try:
        os.makedirs(LOGS, exist_ok=True)
        with open(os.path.join(LOGS, utc_now().strftime("runner-%Y-%m.log")), "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def read_keys(path=KEYS):
    """NAME=value lines from keys.env. Blank lines and lines starting # are ignored."""
    keys = {}
    try:
        with open(path) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:]
                name, value = line.split("=", 1)
                keys[name.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        log(f"no keys file at {path}")
    return keys


def run(cmd, timeout=STEP_LIMIT, env=None, quiet=False):
    """Runs a command in the repository, logs what it printed, returns its exit code."""
    try:
        r = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True,
                           errors="replace", timeout=timeout)
        code, out = r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired as e:
        def text(b):
            return b.decode("utf-8", "replace") if isinstance(b, bytes) else (b or "")
        out = (text(e.stdout) + text(e.stderr)).strip()
        code = "stopped after %d seconds" % timeout
    except OSError as e:
        code, out = "could not start: %s" % e, ""
    name = " ".join(cmd[:3])
    if out and not quiet:
        for line in out.splitlines()[-60:]:
            if "warning: redirecting" in line:
                continue          # harmless, from the capitalisation of the stored address
            log(f"  {line}")
    if code != 0:
        log(f"{name}: exit {code}")
    return code


class GitLock:
    """One job at a time uses git. Waits up to `wait` seconds, then gives up."""

    def __init__(self, wait):
        self.wait, self.f, self.held = wait, None, False

    def __enter__(self):
        os.makedirs(os.path.dirname(LOCK), exist_ok=True)
        self.f = open(LOCK, "w")
        give_up = time.monotonic() + self.wait
        while True:
            try:
                fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.held = True
                return self
            except BlockingIOError:
                if time.monotonic() >= give_up:
                    return self
                time.sleep(2)

    def __exit__(self, *exc):
        if self.held:
            fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()
        return False


def pull_locked():
    if run(["git", "pull", "-q", "--rebase", "--autostash"]) == 0:
        return True
    run(["git", "rebase", "--abort"], quiet=True)
    log("git pull failed; carrying on with the code already here")
    return False


def pull(wait=60):
    with GitLock(wait) as lock:
        if not lock.held:
            log("git is busy with another job; carrying on without pulling")
            return False
        return pull_locked()


def commit_push_locked(paths, message):
    """Commits the given paths and pushes, retrying. True once the commit is in Hunterson-raw."""
    present = [p for p in paths if os.path.exists(os.path.join(REPO, p))]
    if present:
        run(["git", "add", "--"] + present)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO).returncode != 0
    if staged and run(["git", "commit", "-qm", message]) != 0:
        log("commit failed")
        return False
    for attempt in range(1, PUSH_ATTEMPTS + 1):
        pull_locked()
        if run(["git", "push", "-q"]) == 0:
            log(f"pushed: {message}" if staged else "nothing new to commit; branch pushed")
            return True
        if attempt < PUSH_ATTEMPTS:
            time.sleep(float(os.environ.get("RUNNER_PUSH_PAUSE", 15)) * attempt)
    log(f"PUSH FAILED after {PUSH_ATTEMPTS} attempts; the commit stays here and goes with the next push")
    return False


def commit_push(paths, message, wait=900):
    with GitLock(wait) as lock:
        if not lock.held:
            log("git stayed busy for %d seconds; committing anyway" % wait)
        return commit_push_locked(paths, message)


def ping(url, what):
    if not url:
        log(f"no {what} address in keys.env; no ping")
        return False
    err = "no reply"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hunterson-runner/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
            log(f"{what} pinged")
            return True
        except Exception as e:
            err = type(e).__name__
            time.sleep(5 * (attempt + 1))
    log(f"{what} ping failed ({err})")
    return False


# Jobs ---------------------------------------------------------------------

def gpu_folders():
    base = os.path.join(REPO, "data", "gpu")
    return {n for n in os.listdir(base) if not n.startswith(".")} if os.path.isdir(base) else set()


def job_gpu(keys, slot="manual"):
    """A reading of GPU-hour prices (D36), pushed on its own."""
    before = gpu_folders()
    env = dict(os.environ)
    env.update(keys)
    env["GPU_TRIGGER"] = "server"
    code = run([PY, "scripts/gpuprices.py", "--slot", slot], GPU_LIMIT, env)
    new = sorted(gpu_folders() - before)
    if not new:
        if code != 0:
            log("GPU prices: no reading written")
        return 0 if code == 0 else 1
    ok = commit_push([os.path.join("data", "gpu", n) for n in new],
                     f"GPU prices {', '.join(new)}, {slot} (server)")
    return 0 if ok and code == 0 else 1


def gpu_after(keys, slot):
    """Takes the slot's GPU price reading after another job's work is done.
    Never raises, and never changes that job's exit code."""
    try:
        job_gpu(keys, slot)
    except Exception as e:
        log(f"GPU prices FAILED: {type(e).__name__}: {e}")


def market_folders():
    base = os.path.join(REPO, "data", "market")
    return {n for n in os.listdir(base) if not n.startswith(".")} if os.path.isdir(base) else set()


def job_market(keys, slot="manual", backfill=False):
    """A reading of OpenRouter's market data (D38), pushed on its own."""
    before = market_folders()
    env = dict(os.environ)
    env.update(keys)
    env["MARKET_TRIGGER"] = "server"
    args = ["--backfill"] if backfill else ["--slot", slot]
    code = run([PY, "scripts/marketdata.py"] + args, BACKFILL_LIMIT if backfill else MARKET_LIMIT, env)
    new = sorted(market_folders() - before)
    if not new:
        if code != 0:
            log("market data: no reading written")
        return 0 if code == 0 else 1
    label = "backfill" if backfill else slot
    ok = commit_push([os.path.join("data", "market", n) for n in new],
                     f"Market data {', '.join(new)}, {label} (server)")
    return 0 if ok and code == 0 else 1


def job_market_backfill(keys):
    return job_market(keys, backfill=True)


def market_after(keys):
    """Takes the day's market data reading after the census and its GPU
    reading. Never raises, and never changes the census job's exit code."""
    try:
        job_market(keys, "morning")
    except Exception as e:
        log(f"market data FAILED: {type(e).__name__}: {e}")


def job_census(keys):
    code = census_only(keys)
    gpu_after(keys, "morning")
    market_after(keys)
    return code


def census_only(keys):
    day = utc_now().strftime("%Y-%m-%d")
    folder = os.path.join("data", "census", day)
    marker = os.path.join(REPO, folder, "models.json")
    with GitLock(600) as lock:
        if not lock.held:
            log("git stayed busy for ten minutes; taking the census anyway")
        pull_locked()
        if os.path.exists(marker):
            log(f"the census for {day} is already in the repository; nothing to take")
            pushed = True
        else:
            env = dict(os.environ, CENSUS_TRIGGER="server")
            code = run([PY, "scripts/census.py"], CENSUS_LIMIT, env)
            if code != 0 or not os.path.exists(os.path.join(REPO, folder, "meta.json")):
                # An unfinished census is set aside on the server, never committed, so that
                # GitHub's backup run can take a complete one.
                if os.path.isdir(os.path.join(REPO, folder)):
                    aside = os.path.join(STATE, f"failed-census-{day}-{utc_now().strftime('%H%M%S')}")
                    os.makedirs(STATE, exist_ok=True)
                    os.rename(os.path.join(REPO, folder), aside)
                    log(f"the census did not finish; set aside in {aside}")
                log("CENSUS FAILED; GitHub's backup run takes it from 06:41")
                return 1
            run([PY, "scripts/rank.py"])
            run([PY, "scripts/track.py"])
            pushed = commit_push_locked([folder, "data/rank", "data/site", "data/track.md"],
                                        f"Census {day} (server)")
    if pushed and os.path.exists(marker):
        ping(keys.get("HEALTHCHECK_CENSUS"), "census alarm")
        return 0
    return 1


def offwindow_folders():
    base = os.path.join(REPO, "data", "offwindow")
    return set(os.listdir(base)) if os.path.isdir(base) else set()


def run_probe(keys, args):
    env = dict(os.environ)
    env.update(keys)
    if not env.get("OPENROUTER_API_KEY"):
        log("OPENROUTER_API_KEY is not set in keys.env; the probe cannot buy anything")
    start = time.monotonic()
    code = run([PY, "scripts/probe.py"] + args, PROBE_LIMIT, env)
    log(f"probe finished in {int(time.monotonic() - start)} seconds, exit {code}")
    return code


def job_window(keys):
    now = utc_now()
    day = now.strftime("%Y-%m-%d")
    if now.weekday() >= 5 or (now.month, now.day) in EXCLUDED_DAYS:
        log(f"{day} has no window")
        return 0
    pull(wait=60)
    code = run_probe(keys, [])
    folder = os.path.join("data", "probes", day)
    if not os.path.isdir(os.path.join(REPO, folder)):
        log("PROBE WROTE NOTHING")
        return 1
    if not os.path.exists(os.path.join(REPO, folder, "manifest.json")):
        log("the probe did not finish (no manifest); pushing what it wrote")
    ok = commit_push([folder], f"Probes {day} (server)")
    gpu_after(keys, "window")
    return 0 if ok and code == 0 else 1


def job_offwindow(keys, kind):
    before = offwindow_folders()
    pull(wait=60)
    code = run_probe(keys, ["--offwindow", kind])
    new = sorted(offwindow_folders() - before)
    if not new:
        log("the off-window reading wrote nothing")
        return 1
    ok = commit_push([os.path.join("data", "offwindow", n) for n in new],
                     f"Off-window {', '.join(new)}, {kind} (server)")
    return 0 if ok and code == 0 else 1


def job_weekend(keys):
    if utc_now().weekday() < 5:
        log("not a weekend day; nothing to do")
        return 0
    return job_offwindow(keys, "weekend")


def choose_random(now, rng=None):
    """Today's hour and starting minute. Never 13:00 or 14:00 UTC. If chosen after
    midnight, as when the server restarts, only hours still to come are used."""
    rng = rng or random.SystemRandom()
    hours = [h for h in range(24) if h not in RANDOM_EXCLUDED_HOURS and h >= now.hour]
    if not hours:
        return None
    return {"date": now.strftime("%Y-%m-%d"), "hour": rng.choice(hours),
            "minute": rng.randint(*RANDOM_START_MINUTES), "done": False}


def read_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, path)


def job_random(keys):
    path = os.path.join(STATE, "random-hour.json")
    now = utc_now()
    state = read_state(path)
    if not state or state.get("date") != now.strftime("%Y-%m-%d"):
        state = choose_random(now)
        if not state:
            return 0
        write_state(path, state)
        log("today's random hour has been chosen")
    if state.get("done") or state["hour"] != now.hour:
        return 0
    wait = (now.replace(minute=state["minute"], second=0, microsecond=0) - now).total_seconds()
    if wait > 0:
        time.sleep(wait)
    state["done"] = True                  # before the run, so a crash never repeats it
    write_state(path, state)
    log("start: today's random-hour reading")
    code = job_offwindow(keys, "random")
    log(f"end, exit {code}")
    return code


def job_check(keys):
    """Says what is set up. Changes nothing."""
    print(f"Repository: {REPO}")
    print(f"Python: {sys.version.split()[0]} at {PY}")
    head = subprocess.run(["git", "log", "-1", "--format=%h %cd %s", "--date=format:%Y-%m-%d %H:%M"],
                          cwd=REPO, capture_output=True, text=True).stdout.strip()
    print(f"Latest commit here: {head}")
    fetch = subprocess.run(["git", "fetch", "-q", "origin"], cwd=REPO, capture_output=True, text=True, timeout=120)
    print("Hunterson-raw: " + ("reachable" if fetch.returncode == 0 else "NOT reachable: " + fetch.stderr.strip()[-200:]))
    # A push of the remote's own latest commit changes nothing, but GitHub still checks
    # that this server may write, so this proves the push will work.
    push = subprocess.run(["git", "push", "--dry-run", "-q", "origin", "refs/remotes/origin/main:refs/heads/main"],
                          cwd=REPO, capture_output=True, text=True, timeout=120)
    print("Permission to push: " + ("yes" if push.returncode == 0 else "NO: " + push.stderr.strip()[-200:]))
    behind = subprocess.run(["git", "rev-list", "--count", "HEAD..origin/main"], cwd=REPO,
                            capture_output=True, text=True).stdout.strip()
    ahead = subprocess.run(["git", "rev-list", "--count", "origin/main..HEAD"], cwd=REPO,
                           capture_output=True, text=True).stdout.strip()
    print(f"Commits here not yet pushed: {ahead or '?'}; commits in Hunterson-raw not yet here: {behind or '?'}")
    print(f"Keys file: {KEYS} " + ("found" if os.path.exists(KEYS) else "NOT FOUND"))
    for name in ("OPENROUTER_API_KEY", "HEALTHCHECK_CENSUS"):
        print(f"  {name}: " + ("set" if keys.get(name) else "NOT SET"))
    others = sorted(k for k in keys if k not in ("OPENROUTER_API_KEY", "HEALTHCHECK_CENSUS"))
    if others:
        print("  also set: " + ", ".join(others))
    try:
        os.makedirs(LOGS, exist_ok=True)
        print(f"Log folder: {LOGS} writable")
    except OSError as e:
        print(f"Log folder: {LOGS} NOT writable ({e})")
    try:
        cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except OSError:
        cron = ""
    jobs = [j for j in ("census", "window", "weekend", "random") if f"runner.py {j}" in cron]
    print("Crontab: runner jobs " + (", ".join(jobs) if jobs else "NONE") +
          ("; old lines still present" if "probe.py >>" in cron or "census.py &&" in cron else ""))
    state = read_state(os.path.join(STATE, "random-hour.json"))
    print("Random hour: " + ("chosen for " + state["date"] + (", done" if state.get("done") else ", not yet run")
                             if state else "not yet chosen"))
    try:
        with open(os.path.join(REPO, "gpu_sources.json")) as f:
            sources = json.load(f)["sources"]
        print("GPU prices (D36): " + "; ".join(
            f"{s['provider']} " + ("enabled" if s.get("enabled") else "not enabled") +
            (", key set" if keys.get(s.get("key_env")) else ", no key") for s in sources))
    except (OSError, ValueError, KeyError):
        print("GPU prices (D36): gpu_sources.json not found")
    try:
        with open(os.path.join(REPO, "market_sources.json")) as f:
            sources = json.load(f)["sources"]
        latest = max(market_folders(), default=None)
        print("Market data (D38): " + "; ".join(
            f"{s['provider']} " + ("enabled" if s.get("enabled") else "not enabled") +
            (", key set" if keys.get(s.get("key_env")) else ", no key") for s in sources) +
            f"; latest reading {latest or 'none yet'}")
    except (OSError, ValueError, KeyError):
        print("Market data (D38): market_sources.json not found")
    return 0


JOBS = {"census": job_census, "window": job_window, "weekend": job_weekend,
        "random": job_random, "gpu": job_gpu, "market": job_market,
        "market-backfill": job_market_backfill, "check": job_check}


def main(argv):
    global JOB
    if len(argv) != 1 or argv[0] not in JOBS:
        print(__doc__)
        return 2
    JOB = argv[0]
    keys = read_keys()
    if JOB == "check":
        return job_check(keys)
    if JOB != "random":
        log("start")
    try:
        code = JOBS[JOB](keys)
    except Exception as e:  # never die silently
        log(f"FAILED: {type(e).__name__}: {e}")
        return 1
    if JOB != "random":
        log(f"end, exit {code}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
