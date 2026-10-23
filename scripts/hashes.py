"""
Fingerprints of the raw files and of the assessments.

The raw files are the census, the probe's listing snapshots and request
records, the rehearsals, the readings taken outside the window for research
(decision D28), and the GPU-hour price readings (decision D36). They are
OpenRouter's and the GPU clouds' responses, so they are kept in the private
repository and not published. This script writes one SHA-256
manifest per day into the public record, so that anyone shown a raw file later
can check that it existed on that day and has not changed since.

Usage, from anywhere:
    python3 scripts/hashes.py SOURCE_ROOT TARGET_ROOT

SOURCE_ROOT is a checkout holding data/census, data/probes, data/rehearsals,
data/offwindow and data/gpu.
TARGET_ROOT is the checkout that receives data/hashes. They can be the same.

Each manifest uses the format of `sha256sum`, with paths relative to the
repository root, so the files can be checked with `sha256sum -c` from there.

A manifest is written once. If one already exists and no longer matches the
files, the script reports it and exits with an error, and the mirror then
publishes nothing, because a raw file has changed and that must never happen
silently.

A day is fingerprinted only once it is complete: a census day once its
models.json exists, a probe day, rehearsal, off-window reading or GPU price
reading once its manifest.json exists. Hidden folders, such as a GPU price
reading still being assembled, are never fingerprinted.

The assessments in data/assessments are fingerprinted one file at a time, into
data/hashes/assessments/DATE/SLUG.sha256 (decision D33). The assessor writes
each checkpoint's file once, but can add a file to an earlier day, for example
when a checkpoint is placed after its windows ran; one fingerprint per file
means such an addition is a new fingerprint, never a changed one. The
assessments stay private until go-live; only their fingerprints are public.
Uses only the Python standard library.
"""
import hashlib
import os
import sys

CLASSES = [
    # (folder under data/, file that marks the day as complete)
    ("census", "models.json"),
    ("probes", "manifest.json"),
    ("rehearsals", "manifest.json"),
    ("offwindow", "manifest.json"),
    ("gpu", "manifest.json"),          # GPU-hour price readings, from October 2026 (D36)
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def manifest_for(source_root, day_dir):
    """The manifest text for one day folder, files in sorted order."""
    lines = []
    for dirpath, dirnames, filenames in os.walk(day_dir):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, source_root).replace(os.sep, "/")
            lines.append(f"{sha256(full)}  {rel}")
    lines.sort(key=lambda line: line.split("  ", 1)[1])
    return "\n".join(lines) + "\n"


def write_once(out, text, label, counts):
    """Write a fingerprint file once; a different existing one is a problem."""
    if os.path.exists(out):
        with open(out) as f:
            if f.read() == text:
                counts["unchanged"] += 1
                return
        counts["problems"].append(f"{label}: the files no longer match the published fingerprints")
        return
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(text)
    counts["written"] += 1


def assessments(source_root, target_root, counts):
    """One fingerprint per assessment file (decision D33)."""
    base = os.path.join(source_root, "data", "assessments")
    if not os.path.isdir(base):
        return
    out_base = os.path.join(target_root, "data", "hashes", "assessments")
    for day in sorted(os.listdir(base)):
        day_dir = os.path.join(base, day)
        if not os.path.isdir(day_dir):
            continue
        for name in sorted(os.listdir(day_dir)):
            full = os.path.join(day_dir, name)
            if not name.endswith(".json") or not os.path.isfile(full):
                continue
            text = f"{sha256(full)}  data/assessments/{day}/{name}\n"
            out = os.path.join(out_base, day, name[:-len(".json")] + ".sha256")
            write_once(out, text, f"assessments/{day}/{name}", counts)


def run(source_root, target_root):
    counts = {"written": 0, "unchanged": 0, "problems": []}
    for folder, marker in CLASSES:
        base = os.path.join(source_root, "data", folder)
        if not os.path.isdir(base):
            continue
        out_base = os.path.join(target_root, "data", "hashes", folder)
        for day in sorted(os.listdir(base)):
            day_dir = os.path.join(base, day)
            if day.startswith(".") or not os.path.isdir(day_dir) or not os.path.exists(os.path.join(day_dir, marker)):
                continue
            text = manifest_for(source_root, day_dir)
            out = os.path.join(out_base, day + ".sha256")
            write_once(out, text, f"{folder}/{day}", counts)
    assessments(source_root, target_root, counts)
    problems = counts["problems"]
    print(f"Fingerprints: {counts['written']} written, {counts['unchanged']} unchanged, "
          f"{len(problems)} problems.")
    for p in problems:
        print("PROBLEM: " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(run(sys.argv[1], sys.argv[2]))
