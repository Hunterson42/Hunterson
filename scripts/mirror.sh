#!/usr/bin/env bash
# Copies the public parts of the private repository into a checkout of the
# public one, and adds the fingerprints of the raw files.
#
#   bash scripts/mirror.sh PRIVATE_CHECKOUT PUBLIC_CHECKOUT
#
# Only the paths listed below are copied. The raw files (data/census,
# data/probes, data/rehearsals, data/offwindow) and the workflows (.github) are
# never copied: the raw files are OpenRouter's material, and a workflow in the
# public repository would start collecting there again. The assessments
# (data/assessments) and the launch site (launch/) stay private until go-live.
# The register of benchmark uses (register/) is never public (decision D32).
set -euo pipefail

SRC="$1"
DST="$2"

FILES=(README.md LICENSE.md LICENCE-DATA.md METHODOLOGY.md candidates.json panel.json prompt.txt affiliations.json .gitignore data/track.md)
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
       "${DST:?}/data/offwindow" "${DST:?}/data/assessments" "${DST:?}/launch" "${DST:?}/server" \
       "${DST:?}/register"

python3 "$SRC/scripts/hashes.py" "$SRC" "$DST"
