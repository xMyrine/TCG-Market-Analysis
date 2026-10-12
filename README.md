# TCG market analysis: Pokémon & Riftbound vs the S&P 500

Step 1 of the project: get trustworthy data onto disk.

## Setup (once)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run, in this order

```bash
python -m pipeline.catalog                       # ~5-15 min: games, sets, products
python -m pipeline.prices --inspect 2024-02-08   # sanity check: archive layout
python -m pipeline.prices --step 7               # weekly sample since 2024-02-08
python -m pipeline.benchmarks                    # S&P 500 TR, T-bill, CPI, EUR/USD
python -m pipeline.audit                         # data quality report
```

Data goes to `./data` (override with `TCG_DATA_DIR=...`). Every step is safe to re-run.

Offline self-test (no network): `TCG_DATA_DIR=/tmp/tcg-sim python -m tests.simulate`

## Tables

| Table | Grain (one row per…) | Key |
|---|---|---|
| `silver/dim_category` | game | `categoryId` |
| `silver/dim_group` | set | `groupId` |
| `silver/dim_product` | product (card, box, accessory) | `productId` |
| `silver/fact_price` | product × printing × day | `(date, productId, subTypeName)` |
| `silver/benchmarks` | series × day | `(date, series)` |

## Assumptions to verify on the first real run

- Archive members are laid out as `<date>/<categoryId>/<groupId>/prices`. `--inspect` prints the layout; if it differs, adjust `parse_member()` in `pipeline/prices.py`.
- The Riftbound category name matches the regex in `pipeline/common.py` (`catalog` logs what it selected).
- Product kind: extendedData decides card vs not-a-card (`Rarity = "Code Card"` -> `code_card`; `Number`/`Card Type`/`Rarity` -> `single`); non-cards default to `sealed`, and a narrow name rule finds the rare `accessory`. Audit section 5 lists the name-rule decisions.
