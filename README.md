# TCG market analysis: Pokémon & Riftbound vs the S&P 500

Are trading cards an asset class? This project collects daily TCGplayer prices for the
Pokémon and Riftbound trading card games and analyses them the way you would analyse a
financial market: returns against the S&P 500 total return index, risk, what drives prices,
and whether any of it can be predicted.

It is a learning project in data analysis and data science (Python, polars, DuckDB,
statsmodels). Methods, decisions and dead ends are documented in [`docs/`](docs/).

> **Status (2026-10):** the data pipeline collects one price snapshot per day since
> 2026-10-11. Cross-sectional questions can be answered now; the time-series questions are
> waiting for history to accumulate (TCGplayer's public price archive went offline, see
> [docs/data.md](docs/data.md)).

## Research questions

| # | Question | Method | Status |
|---|---|---|---|
| 1 | Did Pokémon and Riftbound grow more than the S&P 500 (total return, risk-adjusted)? | Chain-linked price indices vs `^SP500TR`, Sharpe ratio | waiting for data |
| 2 | Does the size of a game's player base affect prices? | Panel of ~10 games | not started |
| 3 | Is sealed product more stable than single cards? | Volatility after Geltner unsmoothing | waiting for data |
| 4 | Which generation of cards is most expensive? | Medians of log price, hedonic regression | **[first result](docs/findings/q4-generation.md)** |
| 5 | Will Riftbound keep outperforming? | Launch-cohort / event-time comparison | waiting for data |
| 6 | Can prices be predicted? | Walk-forward backtest vs random walk | waiting for data |

## Findings so far

**Q4 — older generations are far more expensive, but not in a straight line.** For an
otherwise identical card (same rarity, printing and card type), the price relative to
Scarlet & Violet (2023–25):

| Era | WotC 1999–03 | EX 2003–07 | DP/Pt 2007–10 | HGSS 2010–11 | BW 2011–14 | XY 2014–17 | SM 2017–20 | SWSH 2020–23 |
|---|---|---|---|---|---|---|---|---|
| Price ratio | **57×** | 36× | 13× | 17× | 5.7× | 3.3× | 3.5× | 1.0× |

One snapshot cannot separate *cards appreciate with age* from *older eras were printed in
smaller runs*; details and caveats in [docs/findings/q4-generation.md](docs/findings/q4-generation.md).

## Data

- **Prices and catalogue:** TCGplayer via [TCGCSV](https://tcgcsv.com) (daily snapshot, US market).
- **Benchmarks:** S&P 500 total return and price index (Yahoo Finance), 3-month T-bill,
  CPI and EUR/USD (FRED).

This repository contains **no price data**. Run the pipeline to fetch it. Only aggregated
results (medians, regression coefficients) are published here.

## Setup (once)

```bash
python -m venv .venv
source .venv/bin/activate          
pip install -r requirements.txt
```

## Run, in this order

Always as modules from the project root (`python -m pipeline.x`), never `python pipeline/x.py`:
the package uses relative imports. In PyCharm use the shared run configurations "1 catalog" .. "4 audit".

```bash
python -m pipeline.catalog          #  games, sets, products            (daily)
python -m pipeline.prices --live    #   today's price snapshot            (daily, after catalog)
python -m pipeline.benchmarks       #  S&P 500 TR, T-bill, CPI, EUR/USD    (any time)
python -m pipeline.audit            #   data quality report                      (whenever you look)
```

TCGCSV refreshes prices once a day (~20:00 UTC). A second `--live` run on the same snapshot
makes no price requests. The historical archive (`--step 7`, `--inspect`) is offline since 2026-10.

Data goes to `<project>/data` (override with `TCG_DATA_DIR=...`). Every step is safe to re-run.

Offline self-test (no network): `TCG_DATA_DIR=/tmp/tcg-sim python -m tests.simulate`

Analyses (one module per research question): `python -m analysis.q4_generation`

## Repository layout

```
pipeline/   data ingestion: catalog -> prices -> benchmarks -> audit (writes data/)
analysis/   one module per research question (reads data/silver/)
tests/      offline end-to-end test on simulated data
docs/       data notes, decision log, findings per question
data/       not in git: raw -> bronze (per-day Parquet) -> silver (analysis tables)
```

## Documentation

- [docs/data.md](docs/data.md) — sources, tables, data-quality audit, known biases
- [docs/decisions.md](docs/decisions.md) — decision log: what was decided, when, and why
- [docs/findings/](docs/findings/) — one write-up per research question

## Disclaimer

Not affiliated with TCGplayer, TCGCSV, The Pokémon Company or Riot Games. Pokémon and
Riftbound are trademarks of their respective owners. Nothing here is investment advice.
