# Data

## Sources

| Source | What | Access |
|---|---|---|
| [TCGCSV](https://tcgcsv.com) | TCGplayer catalogue (games, sets, products) and daily prices | free, no key; please fetch each price file at most once per 24 h |
| Yahoo Finance (`yfinance`) | `^SP500TR` (S&P 500 total return), `^GSPC` (price index) | free |
| FRED | `DTB3` (3-month T-bill), `CPIAUCSL` (CPI), `DEXUSEU` (USD per EUR) | free, no key |

**Price history.** TCGCSV's daily price archive (2024-02-08 onwards) was taken offline in 2026
(HTTP 403 with a notice from the maintainer). History is therefore collected forward, one
snapshot per day from 2026-10-11, with `python -m pipeline.prices --live`. The archive code path
is kept in case it returns. A missed day cannot be recovered.

## Layers and tables

`data/raw` (as downloaded, disposable) → `data/bronze` (one Parquet file per day) →
`data/silver` (the analysis tables). A star schema: small dimension tables, one long fact table.

| Table | Grain (one row per…) | Key |
|---|---|---|
| `silver/dim_category` | game | `categoryId` |
| `silver/dim_group` | set | `groupId` |
| `silver/dim_product` | product (card, sealed, accessory, code card) | `productId` |
| `silver/fact_price` | product × printing × day | `(date, productId, subTypeName)` |
| `silver/benchmarks` | series × day | `(date, series)` |

A price series is `(productId, subTypeName)`: one card can have several printings (Normal,
Reverse Holofoil, 1st Edition, …). Use `marketPrice` (based on sales); `highPrice` and
`lowPrice` are listing-based and polluted (see below).

## Verified on real data (2026-10-12)

- Price files have the fields `productId, subTypeName, lowPrice, midPrice, highPrice, marketPrice, directLowPrice`.
- Game selection: Pokémon = category 3, Riftbound = 89. `Pokemon Japan` (85) is excluded by the
  anchored regex; `catalog` stops if a game ever matches more than one category.
- Snapshot of 2026-10-11: 47,515 price rows from 234 sets (220 Pokémon, 14 Riftbound).

## Product kinds

TCGplayer's `extendedData` decides card vs not-a-card; names only find the rare accessory:

1. `code_card` — `Rarity = "Code Card"` or "code card" in the name (digital redemption codes).
2. `single` — has `Number`, `Card Type` or `Rarity`.
3. `accessory` — names an accessory and nothing that implies booster packs inside.
4. `sealed` — everything else.

Why: in a 30-product sample per class, the original name-based rules had put 1,279 Code Cards
among singles, and 29/30 "accessories" and 30/30 "other" were sealed product ("Sleeved Booster
Pack", "Pin Collection", trainer kits). Within these two categories almost nothing is a pure
accessory; TCGplayer sells supplies in a separate category.

| | single | sealed | code_card | accessory |
|---|---|---|---|---|
| Pokémon | 28,647 | 2,932 | 1,282 | 4 |
| Riftbound | 1,716 | 76 | – | – |

## Known data issues and biases

- **Price parking.** Median `highPrice` is 20–25× `marketPrice` for singles; 55% of Pokémon singles
  list below half their market price. Only `marketPrice` is usable.
- **Missing `marketPrice` is not random.** 0.4% of Pokémon singles, 13% of sealed, 63% of
  presales. Singles without a market price have a median `lowPrice` of $91 vs $0.49 for the
  rest: it is the expensive, illiquid items that are missing.
- **Survivorship.** `catalog` rebuilds `dim_product` on every run, so a delisted product would
  drop out of the history. To fix before relying on long series.
- **Duplicate exposure.** 44% of Pokémon products have more than one printing; 698 Pokémon and
  139 Riftbound cards share a name and number across product ids (reprints, promos); cases,
  displays and "Set of N" bundles are 22% of Pokémon sealed and 50% of Riftbound sealed. An
  equal-weighted index would count the same exposure several times.
- **Presales** (set release date after the snapshot) trade thinly before release; exclude them
  using `dim_group.release_date`.
- **Benchmarks.** CPI for October 2025 was never published (US government shutdown);
  interpolate across it. FRED's EUR/USD lags about a week.
