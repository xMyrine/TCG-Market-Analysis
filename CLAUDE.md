# TCG market analysis: Pokémon & Riftbound vs the S&P 500

Learning project in Data Analysis / Data Science. The owner is a Java backend developer
with good fundamentals in statistics and ML, learning the data-science toolchain.

## How to work with me
- Explain the methods in depth: why a technique is chosen, its assumptions, and what
  breaks when they fail. Assume solid stats/ML knowledge; skip the basics.
- Prefer running things and showing real output over describing what would happen.
- Python stack: polars, DuckDB, statsmodels, LightGBM. Plain scripts in `pipeline/`;
  notebooks only for exploration.

## Research questions
1. Did the Pokémon and Riftbound markets grow more than the S&P 500 (total return, same window, risk-adjusted)?
2. Does the size of a TCG's player base affect prices? (Needs a panel of ~10 games, not 2.)
3. Is sealed product more stable than single cards? (Unsmooth TCGplayer market prices first: Geltner.)
4. Which generation of cards is most expensive? (Medians of log price, then a hedonic regression.)
5. Will Riftbound keep outperforming? (Launch-cohort / event-time comparison with other TCGs.)
6. Can we make predictions? (Beat a random-walk baseline with walk-forward validation; rank IC.)

## Data
- TCGCSV (TCGplayer mirror): catalogue + daily price archives from 2024-02-08.
- Benchmarks: ^SP500TR, ^GSPC (yfinance); FRED DTB3, CPIAUCSL, DEXUSEU.
- Later: Limitless tournament attendance and Google Trends as player-base proxies.

## Pipeline (see README.md)
`pipeline.catalog` -> `pipeline.prices` -> `pipeline.benchmarks` -> `pipeline.audit`
Layers: data/raw (disposable) -> data/bronze (per-day Parquet) -> data/silver (analysis tables).
Price series key: (productId, subTypeName). Fact table key: (date, productId, subTypeName).
Use `marketPrice`; `highPrice` is polluted by price parking.

## Forecasting plan (question 6, after the indices exist)
- Walk-forward backtest, expanding window, horizons 4/8/13 weeks, on log prices.
- Models: naive (last value), drift, ETS (statsforecast), LightGBM on lagged returns +
  card features, Google TimesFM zero-shot, TimesFM + XReg covariates.
- Evaluate on both raw and Geltner-unsmoothed prices: TCGplayer market prices are
  smoothed, so "skill" on raw prices may only be the lag catching up.
- Metrics: MASE vs naive, pinball loss + interval coverage, rank IC, Diebold–Mariano.

## Status
- Step 1 (ingestion + audit) written and tested on simulated data only.
- Not yet verified against live data: archive layout (`--inspect`), Riftbound category
  match, benchmarks download.
- Next: run the pipeline on real data, review the audit, then build chain-linked
  equal- and value-weighted indices and compare with the S&P 500 total return.