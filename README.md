# Hunterson Standard Inference, Europe

A daily price assessment for delivered open-weight AI inference: what a defined AI model actually costs per million tokens, bought, timed and receipted every weekday, with written rules for when the model changes.

**Site:** https://hunterson42.github.io/Hunterson/

## Where it stands

The census has run every day since 11 September 2026. It records which providers serve which open-weight models, at what declared precision and listed price, from OpenRouter's public listings. No price is being assessed yet. The probe that buys the daily test job is built and waiting for its server; the first published assessment follows a shadow period and a published methodology.

## What is here

| Path | What it is |
|---|---|
| `data/census/` | One folder per day, written once and never overwritten. Raw listings as fetched, plus `meta.json` with the collection time from 14 October 2026 |
| `data/track.md` | The current tracking page: qualifying providers per candidate per day, the challenger streaks, and the watchlist |
| `data/rank/` | A daily ranking of the most widely served models |
| `data/site/` | Small data files the site reads |
| `candidates.json` | The grades, the candidate models, their accepted precision tags, and which is the reference |
| `notes/selection.md` | Every rule and decision, dated, with the reasons |
| `panel.json` | Settings for the probe |
| `scripts/` | The census, ranking, tracker and probe. Python standard library only |
| `tests/` | Tests for the probe against a mock of OpenRouter. Run `python3 tests/test_probe.py` |
| `docs/` | The site |

## Licence

The derived data and the written material in this repository are licensed under Creative Commons Attribution 4.0 International. The raw OpenRouter responses in `data/census/` are not; they remain OpenRouter's, under its terms. See `LICENSE.md`. The site includes Chart.js, under the MIT licence, and the IBM Plex Mono font, under the SIL Open Font License; their licences are in `docs/vendor/`.
