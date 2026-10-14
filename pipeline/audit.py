"""Step 2. Audit the data before analysing it.

Run:  python -m pipeline.audit

Each check tests whether a table is fit for the research questions. The script only prints
results and changes no data. Cleaning rules come from reading its output.
"""
from __future__ import annotations

import duckdb
import polars as pl

from .common import SILVER_DIR, setup_logging

pl.Config.set_tbl_rows(30)
pl.Config.set_tbl_width_chars(140)


def section(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 70 - len(title)))


def main() -> None:
    setup_logging()
    con = duckdb.connect()
    for t in ["fact_price", "dim_product", "dim_group", "dim_category"]:
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM read_parquet('{SILVER_DIR / (t + '.parquet')}')")
    con.execute("""
        CREATE VIEW p AS
        SELECT f.*, d.game, d.product_kind, d.name, d.rarity
        FROM fact_price f
        LEFT JOIN dim_product d USING (productId)
    """)
    q = lambda sql: print(con.execute(sql).pl())  # noqa: E731

    section("1. Shape: rows, days and series per game")
    q("""SELECT game, count(*) AS rows, count(DISTINCT date) AS days,
                min(date) AS first_day, max(date) AS last_day,
                count(DISTINCT (productId, subTypeName)) AS series
         FROM p GROUP BY game ORDER BY game""")

    section("2. Primary key: (date, productId, subTypeName) must be unique")
    q("""SELECT count(*) AS duplicate_keys FROM (
           SELECT date, productId, subTypeName FROM fact_price
           GROUP BY ALL HAVING count(*) > 1)""")

    section("3. Referential integrity: priced products missing from dim_product")
    q("SELECT count(DISTINCT productId) AS orphan_products FROM p WHERE game IS NULL")

    section("4. Missingness of each price field")
    q("""SELECT game,
                avg((marketPrice IS NULL)::INT) AS market_null,
                avg((lowPrice IS NULL)::INT)    AS low_null,
                avg((midPrice IS NULL)::INT)    AS mid_null,
                avg((highPrice IS NULL)::INT)   AS high_null
         FROM p GROUP BY game ORDER BY game""")

    section("5. Product kinds: single / sealed / accessory / code_card")
    q("""SELECT game, product_kind, count(DISTINCT productId) AS products,
                count(DISTINCT productId) FILTER (WHERE marketPrice IS NOT NULL) AS with_market_price
         FROM p GROUP BY ALL ORDER BY game, products DESC""")
    print("Check these name-rule decisions by eye (accessories, and sealed products whose name mentions an accessory):")
    # USING SAMPLE runs before WHERE, so filter in a subquery first, then sample.
    q("""SELECT * FROM (SELECT game, product_kind, name FROM dim_product
                       WHERE product_kind = 'accessory'
                          OR (product_kind = 'sealed' AND regexp_matches(name, '(?i)sleeve|playmat|deck box|binder|dice|coin')))
         USING SAMPLE reservoir(15 ROWS) REPEATABLE (42)""")

    section("6. Price parking: highPrice far above marketPrice")
    q("""SELECT game,
                avg((highPrice > 20 * marketPrice)::INT) AS share_high_gt_20x_market,
                median(highPrice / marketPrice)          AS median_high_over_market
         FROM p WHERE marketPrice > 0 GROUP BY game ORDER BY game""")

    section("7. Impossible values: zero or negative prices")
    q("SELECT game, count(*) AS nonpositive_market FROM p WHERE marketPrice <= 0 GROUP BY game")

    section("8. Series length: how many observations each price series has")
    q("""WITH s AS (SELECT game, productId, subTypeName, count(marketPrice) AS n_obs
                    FROM p GROUP BY ALL)
         SELECT game, min(n_obs) AS min, quantile_cont(n_obs, 0.25) AS q25,
                median(n_obs) AS median, quantile_cont(n_obs, 0.75) AS q75, max(n_obs) AS max
         FROM s GROUP BY game ORDER BY game""")

    section("9. Price distribution (heavy tails, so use medians and logs)")
    q("""SELECT game, product_kind,
                quantile_cont(marketPrice, 0.5)  AS p50,
                quantile_cont(marketPrice, 0.9)  AS p90,
                quantile_cont(marketPrice, 0.99) AS p99,
                max(marketPrice) AS max,
                avg(marketPrice) AS mean
         FROM p WHERE date = (SELECT max(date) FROM fact_price) AND marketPrice > 0
         GROUP BY ALL ORDER BY game, product_kind""")


if __name__ == "__main__":
    main()
