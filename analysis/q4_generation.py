"""Research question 4. Which generation (era) of Pokemon cards is most expensive?

Run:  python -m analysis.q4_generation

This is a cross-sectional analysis. It needs one price snapshot, so it runs before any price
history exists.
1. Median and geometric-mean price per era show what a typical card of each era costs.
2. A hedonic regression of log price estimates the era premium with rarity, printing and
   card type held fixed.
"""
from __future__ import annotations

from datetime import date

import polars as pl

from pipeline.common import SILVER_DIR, setup_logging

# Era = Pokemon TCG series, starting at the US release of its first set (checked against dim_group).
ERAS = [
    (date(1999, 1, 9), "01 WotC"), (date(2003, 6, 1), "02 EX"), (date(2007, 5, 23), "03 DP/Pt"),
    (date(2010, 2, 10), "04 HGSS"), (date(2011, 4, 25), "05 BW"), (date(2014, 2, 5), "06 XY"),
    (date(2017, 2, 3), "07 SM"), (date(2020, 2, 7), "08 SWSH"), (date(2023, 3, 31), "09 SV"),
    (date(2025, 9, 26), "10 ME"),
]


def load(day: date | None = None) -> pl.DataFrame:
    """Return one row per price series (productId x printing) for Pokemon singles with a market
    price on `day` (default: the latest date in fact_price)."""
    fact = pl.read_parquet(SILVER_DIR / "fact_price.parquet")
    day = day or fact["date"].max()
    products = pl.read_parquet(SILVER_DIR / "dim_product.parquet").filter(game="pokemon", product_kind="single")
    groups = pl.read_parquet(SILVER_DIR / "dim_group.parquet").select("groupId", "group_name", "release_date")
    eras = pl.DataFrame(ERAS, schema=["era_start", "era"], orient="row")
    card_type = pl.col("extended_json").str.json_path_match("$['Card Type']").fill_null("")
    return (
        fact.filter(pl.col("date") == day, pl.col("marketPrice") > 0)
        .join(products.select("productId", "name", "rarity", "extended_json"), on="productId")
        .join(groups, on="groupId")
        .drop_nulls("release_date")
        .sort("release_date")
        .join_asof(eras, left_on="release_date", right_on="era_start")  # the latest era that started on or before release
        .with_columns(
            pl.col("marketPrice").log().alias("log_p"),
            pl.when(card_type.str.contains("Energy")).then(pl.lit("energy"))
            .when(card_type.str.contains("Trainer|Supporter|Item|Stadium|Tool")).then(pl.lit("trainer"))
            .otherwise(pl.lit("pokemon")).alias("card_class"),
        )
        .drop("extended_json")
    )


def era_medians(df: pl.DataFrame) -> pl.DataFrame:
    return (df.group_by("era").agg(
                pl.len().alias("series"),
                pl.col("group_name").n_unique().alias("sets"),
                pl.col("marketPrice").median().alias("median_$"),
                pl.col("log_p").mean().exp().alias("geo_mean_$"),
                pl.col("marketPrice").quantile(0.9).alias("p90_$"),
                (pl.col("marketPrice") >= 10).mean().alias("share_ge_10$"))
            .sort("era"))


SHARED_RARITIES = ["Common", "Uncommon", "Rare", "Holo Rare"]
REFERENCE = {"era": "09 SV", "rarity": "Common", "printing": "normal", "card_class": "pokemon"}


def dummies(df: pl.DataFrame, col: str) -> list[pl.Expr]:
    """One 0/1 column per level except the reference level (which the intercept absorbs)."""
    levels = sorted(set(df[col].unique().to_list()) - {REFERENCE[col]})
    return [(pl.col(col) == lv).cast(pl.Float64).alias(f"{col}={lv}") for lv in levels]


def hedonic(df: pl.DataFrame, like_for_like: bool = False) -> pl.DataFrame:
    """OLS of log price on era + rarity + printing + 1st edition + card class.

    For an era coefficient b, exp(b) - 1 is the price premium over Scarlet & Violet for an
    otherwise identical card. It is a ratio of geometric means, not arithmetic means. Standard
    errors cluster by set, because era is a set-level variable and cards from one set are not
    independent draws.
    """
    import numpy as np
    import statsmodels.api as sm

    if like_for_like:
        df = df.filter(pl.col("rarity").is_in(SHARED_RARITIES))
    sub = pl.col("subTypeName")
    df = df.with_columns(
        pl.when(sub.str.contains("Reverse")).then(pl.lit("reverse"))
        .when(sub.str.contains("Holofoil")).then(pl.lit("holo"))
        .otherwise(pl.lit("normal")).alias("printing"),
        sub.str.starts_with("1st Edition").cast(pl.Float64).alias("first_edition"),
    )
    X = df.select(*[e for c in REFERENCE for e in dummies(df, c)], "first_edition")
    X = sm.add_constant(X.to_pandas())
    fit = sm.OLS(df["log_p"].to_numpy(), X).fit(cov_type="cluster", cov_kwds={"groups": df["groupId"].to_numpy()})
    lo, hi = fit.conf_int().T.values
    out = pl.DataFrame({"term": X.columns, "b": fit.params.values, "se": fit.bse.values, "lo": lo, "hi": hi})
    print(f"  n={int(fit.nobs)}  sets(clusters)={df['groupId'].n_unique()}  R2={fit.rsquared:.3f}")
    return (out.filter(pl.col("term").str.starts_with("era=") | (pl.col("term") == "first_edition"))
               .with_columns((pl.col(c).exp() - 1).alias(f"premium_{c}") for c in ["b", "lo", "hi"])
               .select("term", "b", "se", pl.col("premium_b").alias("premium"),
                       pl.col("premium_lo").alias("ci95_lo"), pl.col("premium_hi").alias("ci95_hi")))


def main() -> None:
    setup_logging()
    pl.Config.set_tbl_rows(40)
    pl.Config.set_float_precision(2)
    df = load()
    print(f"{df.height} price series of Pokemon singles on {df['date'][0]}\n")
    print(era_medians(df))
    print("\nHedonic A: all rarities with rarity fixed effects, premium vs Scarlet & Violet")
    print(hedonic(df))
    print("\nHedonic B: like-for-like, shared rarities only", SHARED_RARITIES)
    print(hedonic(df, like_for_like=True))


if __name__ == "__main__":
    main()
