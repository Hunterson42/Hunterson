"""
Fingerprints of the raw files.

The raw files are the census, the probe's listing snapshots and request
records, the rehearsals, and the readings taken outside the window for
research (decision D28). They are OpenRouter's responses, so they are kept
in the private repository and not published. This script writes one SHA-256
manifest per day into the public record, so that anyone shown a raw file later
can check that it existed on that day and has not changed since.

Usage, from anywhere:
    python3 scripts/hashes.py SOURCE_ROOT TARGET_ROOT

SOURCE_ROOT is a checkout holding data/census, data/probes, data/rehearsals and
data/offwindow.
TARGET_ROOT is the checkout that receives data/hashes. They can be the same.

Each manifest uses the format of `sha256sum`, with paths relative to the
repository root, so the files can be checked with `sha256sum -c` from there.

A manifest is written once. If one already exists and no longer matches the
files, the script reports it and exits with an error, and the mirror then
publishes nothing, because a raw file has changed and that must never happen
silently.

A day is fingerprinted only once it is complete: a census day once its
models.json exists, a probe day, rehearsal or off-window reading once its
manifest.json exists.
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


def run(source_root, target_root):
    written, unchanged, problems = 0, 0, []
    for folder, marker in CLASSES:
        base = os.path.join(source_root, "data", folder)
        if not os.path.isdir(base):
            continue
        out_base = os.path.join(target_root, "data", "hashes", folder)
        for day in sorted(os.listdir(base)):
            day_dir = os.path.join(base, day)
            if not os.path.isdir(day_dir) or not os.path.exists(os.path.join(day_dir, marker)):
                continue
            text = manifest_for(source_root, day_dir)
            out = os.path.join(out_base, day + ".sha256")
            if os.path.exists(out):
                with open(out) as f:
                    if f.read() == text:
                        unchanged += 1
                        continue
                problems.append(f"{folder}/{day}: the files no longer match the published fingerprints")
                continue
            os.makedirs(out_base, exist_ok=True)
            with open(out, "w") as f:
                f.write(text)
            written += 1
    print(f"Fingerprints: {written} written, {unchanged} unchanged, {len(problems)} problems.")
    for p in problems:
        print("PROBLEM: " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(run(sys.argv[1], sys.argv[2]))
