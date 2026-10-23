# Hunterson Standard Inference, Europe

A daily price assessment for delivered open-weight AI inference: what a defined AI model actually costs per million tokens, bought, timed and receipted every weekday, with written rules for when the model changes.

**Site:** https://hunterson.org/

## Where it stands

The census has run every day since 11 September 2026. It records which providers serve which open-weight models, at what declared precision and listed price, from OpenRouter's public listings. The probe that buys the daily test job runs on weekdays from 15 October 2026, in a shadow period. No price is published yet; the first published assessment follows the shadow period. The methodology, version 0.9, is in [`METHODOLOGY.md`](METHODOLOGY.md) and open for comment.

## Raw files and fingerprints

The raw files, meaning the census, the probe's listing snapshots and test records, and the rehearsals, are OpenRouter's responses. They are kept in a private repository and are not published here. The same holds for the GPU-hour price readings taken twice a day since October 2026 for the derived series, which are GPU clouds' responses; their sources are listed in `gpu_sources.json`. It holds too for the market data read once a day since October 2026 from OpenRouter's Data API, listed in `market_sources.json`: the data is licensed under CC BY 4.0, but is kept privately like the census, and figures derived from it are published with OpenRouter's citation.

Each day's raw files are fingerprinted with SHA-256, and the fingerprints are published in `data/hashes/`, one file per day, in the format of `sha256sum`. A fingerprint file is written once. Anyone later shown a raw file can check, with `sha256sum -c` from the repository root, that it has not changed since its fingerprint was published.

Each assessment is fingerprinted the same way when it is made, one fingerprint per file, in `data/hashes/assessments/`. The assessments themselves stay private until the first publication.

**Timestamps.** Each fingerprint file is timestamped, when it is written, by two independent services: OpenTimestamps, which anchors it in the Bitcoin blockchain within a few hours, and FreeTSA, a timestamp authority that signs it within seconds under RFC 3161. The two proofs lie beside it, as `NAME.sha256.ots` and `NAME.sha256.tsr`. Only the fingerprint is sent to either service, never the records. FreeTSA's certificates are kept in `data/stamps/certs/`. Fingerprints already published when stamping began were stamped then; the moment is recorded in `data/hashes/stamping-began.txt`, and their proofs show existence from it.

Everything else is kept here and updated automatically from the private repository.

## How to check a fingerprint and its timestamps

**First, check a record against its fingerprint.** From the repository's root, `sha256sum -c data/hashes/probes/2026-10-20.sha256` checks every file the fingerprint lists. It needs the records themselves, which are private; anyone later shown a record can run it.

**Then, when the fingerprint existed: OpenTimestamps.** Download the fingerprint file and its `.ots` proof. Open https://opentimestamps.org in any browser and drop both files on the page. It names the Bitcoin block that holds the stamp, and that block's time. A proof less than a few hours old shows as pending. With a Bitcoin node, `ots verify NAME.sha256.ots` gives the same answer.

**And the signed time: RFC 3161.** With OpenSSL, from the repository's root:

```
openssl ts -verify -data data/hashes/probes/2026-10-20.sha256 -in data/hashes/probes/2026-10-20.sha256.tsr -CAfile data/stamps/certs/cacert.pem -untrusted data/stamps/certs/tsa.crt
```

It prints `Verification: OK`. OpenSSL may also warn that `tsa.crt` is not a CA certificate. That is expected: it is FreeTSA's signing certificate, passed with `-untrusted`, not the authority that vouches for it, which is `cacert.pem`. To see the time it records:

```
openssl ts -reply -in data/hashes/probes/2026-10-20.sha256.tsr -text
```

## What is here

| Path | What it is |
|---|---|
| `data/hashes/` | The fingerprints of the raw files, one file per day, and of each assessment, one per file; each written once, with its two timestamp proofs beside it |
| `data/stamps/certs/` | FreeTSA's certificates, kept so that a proof can be checked even if the service goes |
| `data/track.md` | The current tracking page: qualifying providers per candidate per day, the challenger streaks, and the watchlist |
| `data/rank/` | A daily ranking of the most widely served models |
| `data/site/` | Small data files the site reads |
| `candidates.json` | The grades, the candidate models, their accepted precision tags, and which is the reference |
| `affiliations.json` | The register of provider groups: providers that resell one source or share an owner count as one. Each group with its public evidence and the day it applies from |
| `gpu_sources.json` | The GPU clouds whose GPU-hour prices are read for the derived series, and why each may be read. Never an input to the assessment |
| `market_sources.json` | The market data read each day from OpenRouter's Data API (tokens by model, by app, by task and by length of request; the cost of an agent session; benchmark scores), why each dataset is read, and the licence it is read under. Never an input to the assessment |
| `METHODOLOGY.md` | How the number is produced, step by step. Version 0.9, open for comment |
| `LICENCE-DATA.md` | The Hunterson Data Licence: the terms on which the figures may be used |
| `notes/selection.md` | Every rule and decision, dated, with the reasons |
| `panel.json` | Settings for the probe, and the assessment's limits |
| `prompt.txt` | The frozen test piece |
| `scripts/` | The census, ranking, tracker, probe, assessor, fingerprints, timestamps and mirror. Python standard library only, except that the timestamps also use the OpenTimestamps client and OpenSSL |
| `tests/` | Tests for the probe against a mock of OpenRouter, which need the raw census and so run in the private repository, and for the assessor, on made-up windows |
| `docs/` | The site |

## Licence

**The figures,** meaning the price assessments, their history and any series calculated from them, are under the Hunterson Data Licence, [`LICENCE-DATA.md`](LICENCE-DATA.md), also at https://hunterson.org/licence/. They are free to view, copy, quote and use with credit. Using them to settle a contract, value a financial instrument, measure a fund or make up an index needs a free registration, so that everyone relying on them is told directly when the rules change. Distributing them as a data service needs an agreement.

**The fingerprints and timestamp proofs** are in the public domain, under CC0 1.0. **The derived census data and the written material** in this repository are licensed under Creative Commons Attribution 4.0 International. OpenRouter's raw responses are not in this repository and are not licensed by it. See `LICENSE.md`. The site includes Chart.js, under the MIT licence, and the IBM Plex Mono font, under the SIL Open Font License; their licences are in `docs/vendor/`.
