#!/usr/bin/env bash
# Copies the public parts of the private repository into a checkout of the
# public one, and adds the fingerprints of the raw files.
#
#   bash scripts/mirror.sh PRIVATE_CHECKOUT PUBLIC_CHECKOUT
#
# Only the paths listed below are copied. The raw files (data/census,
# data/probes, data/rehearsals, data/offwindow, data/gpu, data/market) and the
# workflows (.github) are never copied: the raw files are OpenRouter's and the
# GPU clouds' material, and a workflow in the public repository would start
# collecting there again. The assessments (data/assessments) are copied only
# from the launch date in panel.json, a day at a time, as scripts/site/gate.py
# allows: a day after the launch date once its page is built, and never a day on
# which publication was suspended (decision D50). The illustrative files and
# their tests (launch/), the oversight record (data/oversight.json) and the
# register of benchmark uses (register/, decision D32) are never public.
set -euo pipefail

SRC="$1"
DST="$2"

FILES=(README.md LICENSE.md LICENSE-APACHE-2.0.txt NOTICE LICENCE-DATA.md METHODOLOGY.md IOSCO.md CONFLICTS.md CONTINUITY.md candidates.json panel.json prompt.txt affiliations.json gpu_sources.json market_sources.json .gitignore data/track.md)
DIRS=(notes scripts tests docs data/rank data/site)

for f in "${FILES[@]}"; do
  if [ -f "$SRC/$f" ]; then
    mkdir -p "$DST/$(dirname "$f")"
    cp "$SRC/$f" "$DST/$f"
  else
    rm -f "$DST/$f"
  fi
done

for d in "${DIRS[@]}"; do
  if [ -d "$SRC/$d" ]; then
    rm -rf "${DST:?}/$d"
    mkdir -p "$(dirname "$DST/$d")"
    cp -R "$SRC/$d" "$DST/$d"
    find "$DST/$d" \( -name '__pycache__' -o -name '.github' \) -prune -exec rm -rf {} +
  else
    rm -rf "${DST:?}/$d"
  fi
done

# Defensive: the public repository must never hold workflows or raw files.
rm -rf "${DST:?}/.github" "${DST:?}/data/census" "${DST:?}/data/probes" "${DST:?}/data/rehearsals" \
       "${DST:?}/data/offwindow" "${DST:?}/data/gpu" "${DST:?}/data/market" "${DST:?}/data/assessments" \
       "${DST:?}/launch" "${DST:?}/server" "${DST:?}/register" "${DST:?}/data/oversight.json"

# The assessments, from the launch date, a day at a time.
# Without the gate, or without panel.json, no assessment is copied.
if [ -f "$SRC/scripts/site/gate.py" ]; then
  python3 "$SRC/scripts/site/gate.py" "$SRC" > "$DST/.public-days"
else
  : > "$DST/.public-days"
fi
while read -r day; do
  mkdir -p "$DST/data/assessments"
  cp -R "$SRC/data/assessments/$day" "$DST/data/assessments/$day"
done < "$DST/.public-days"
rm -f "$DST/.public-days"

python3 "$SRC/scripts/hashes.py" "$SRC" "$DST"
