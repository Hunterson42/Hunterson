# Hunterson Standard Inference, Europe

A daily price assessment for delivered open-weight AI inference: what a defined AI model actually costs per million tokens, bought, timed and receipted every weekday, with written rules for when the model changes.

**Site:** https://hunterson.org/

## Where it stands

The census has run every day since 11 September 2026. It records which providers serve which open-weight models, at what declared precision and listed price, from OpenRouter's public listings. The probe that buys the daily test job runs on weekdays from 15 October 2026, in a shadow period. No price is published yet; the first published assessment follows the shadow period. The methodology, version 0.9, is in [`METHODOLOGY.md`](METHODOLOGY.md) and open for comment.

## Raw files and fingerprints

The raw files, meaning the census, the probe's listing snapshots and test records, and the rehearsals, are OpenRouter's responses. They are kept in a private repository and are not published here.

Each day's raw files are fingerprinted with SHA-256, and the fingerprints are published in `data/hashes/`, one file per day, in the format of `sha256sum`. A fingerprint file is written once. Anyone later shown a raw file can check, with `sha256sum -c` from the repository root, that it existed on that day and has not changed since.

Everything else is kept here and updated automatically from the private repository.

## What is here

| Path | What it is |
|---|---|
| `data/hashes/` | The fingerprints of the raw files, one file per day, written once |
| `data/track.md` | The current tracking page: qualifying providers per candidate per day, the challenger streaks, and the watchlist |
| `data/rank/` | A daily ranking of the most widely served models |
| `data/site/` | Small data files the site reads |
| `candidates.json` | The grades, the candidate models, their accepted precision tags, and which is the reference |
| `affiliations.json` | The register of provider groups: providers that resell one source or share an owner count as one. Each group with its public evidence and the day it applies from |
| `METHODOLOGY.md` | How the number is produced, step by step. Version 0.9, open for comment |
| `notes/selection.md` | Every rule and decision, dated, with the reasons |
| `panel.json` | Settings for the probe, and the assessment's limits |
| `prompt.txt` | The frozen test piece |
| `scripts/` | The census, ranking, tracker, probe, assessor, fingerprints and mirror. Python standard library only |
| `tests/` | Tests for the probe against a mock of OpenRouter, which need the raw census and so run in the private repository, and for the assessor, on made-up windows |
| `docs/` | The site |

## Licence

The derived data and the written material in this repository are licensed under Creative Commons Attribution 4.0 International. OpenRouter's raw responses are not in this repository and are not licensed by it. See `LICENSE.md`. The site includes Chart.js, under the MIT licence, and the IBM Plex Mono font, under the SIL Open Font License; their licences are in `docs/vendor/`.
