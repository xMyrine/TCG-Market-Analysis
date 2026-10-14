"""Research question 4. Which generation (era) of Pokemon cards is most expensive?

Run:  python -m analysis.q4_generation   (prints the answer that the dashboard shows)

This is a cross-sectional analysis. It needs one price snapshot, so it runs before any price
history exists.
1. Median and geometric-mean price per era show what a typical card of each era costs.
2. A hedonic regression of log price estimates the era premium with rarity, printing and
   card type held fixed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import altair as alt
import polars as pl

from pipeline.common import setup_logging

from .data import Silver, load_silver
from .results import Answer, Table

# Era = Pokemon TCG series, starting at the US release of its first set (checked against dim_group).
ERAS = [
    (date(1999, 1, 9), "01 WotC"), (date(2003, 6, 1), "02 EX"), (date(2007, 5, 23), "03 DP/Pt"),
    (date(2010, 2, 10), "04 HGSS"), (date(2011, 4, 25), "05 BW"), (date(2014, 2, 5), "06 XY"),
    (date(2017, 2, 3), "07 SM"), (date(2020, 2, 7), "08 SWSH"), (date(2023, 3, 31), "09 SV"),
    (date(2025, 9, 26), "10 ME"),
]


def load(silver: Silver, day: date | None = None) -> pl.DataFrame:
    """Return one row per price series (productId x printing) for Pokemon singles with a market
    price on `day` (default: the latest date in fact_price)."""
    fact = silver.fact_price
    day = day or silver.last_day
    products = silver.dim_product.filter(game="pokemon", product_kind="single")
    groups = silver.dim_group.select("groupId", "group_name", "release_date")
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


@dataclass(frozen=True)
class Fit:
    terms: pl.DataFrame  # era and first-edition coefficients with price ratios and 95% intervals
    n: int
    sets: int  # clusters
    r2: float


def hedonic(df: pl.DataFrame, like_for_like: bool = False) -> Fit:
    """OLS of log price on era + rarity + printing + 1st edition + card class.

    For an era coefficient b, exp(b) is the price ratio to Scarlet & Violet for an
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
    terms = (out.filter(pl.col("term").str.starts_with("era=") | (pl.col("term") == "first_edition"))
                .select("term", "b", "se", pl.col("b").exp().alias("ratio"),
                        pl.col("lo").exp().alias("ci95_lo"), pl.col("hi").exp().alias("ci95_hi")))
    return Fit(terms, n=int(fit.nobs), sets=df["groupId"].n_unique(), r2=fit.rsquared)


CAVEATS = [
    "One snapshot cannot separate age from print run. Age and era are the same variable here, so "
    "this shows that older eras are priced higher, not that cards appreciate. Small print runs "
    "(EX, HGSS) and the record printing of 2020-21 fit the uneven ratios equally well. Separating "
    "them needs the same cohorts observed over time.",
    "Era varies only between sets, so the effective sample size is the number of sets, not the "
    "number of cards. That is why the intervals are wide for eras with few sets.",
    "A rarity label is assumed to mean the same in every era. A Holo Rare was the top pull in "
    "1999 and is mid-tier today.",
    "Condition and survival of old physical cards are not controlled.",
    "Series without a market price are excluded. They are mostly expensive, illiquid cards.",
]
INK = "#2a78d6"
REFERENCE_LINE = "#8a8a85"


def era_ratios(fit: Fit) -> pl.DataFrame:
    """Era coefficients as price ratios vs the reference era, oldest first (terms are sorted by era)."""
    return (fit.terms.filter(pl.col("term").str.starts_with("era="))
            .select(pl.col("term").str.replace(r"^era=\d+ ", "").alias("era"),
                    "ratio", pl.col("ci95_lo").alias("lo"), pl.col("ci95_hi").alias("hi")))


def times(x: float) -> str:
    return f"{x:.0f}x" if x >= 10 else f"{x:.1f}x"


def headline(ratios: pl.DataFrame) -> str:
    top = ratios.sort("ratio").row(-1, named=True)
    text = (f"For an otherwise identical card, {top['era']}-era cards cost {times(top['ratio'])} "
            f"Scarlet & Violet cards (95% CI {times(top['lo'])} to {times(top['hi'])}).")
    same = ratios.filter((pl.col("lo") <= 1) & (pl.col("hi") >= 1))["era"].to_list()
    if same:
        text += f" The 95% CI includes 1x for {', '.join(same)}."
    return text


def ratio_chart(ratios: pl.DataFrame) -> alt.Chart:
    low, high = ratios["lo"].min() / 1.2, ratios["hi"].max() * 1.2
    log = alt.Scale(type="log", domain=[low, high], nice=False)
    ticks = [t for t in (0.25, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500) if low <= t <= high]
    y_axis = alt.Axis(values=ticks, format="~g", labelExpr="datum.label + 'x'",
                      title="Price ratio vs Scarlet & Violet (log scale)")
    base = alt.Chart(ratios).encode(x=alt.X("era:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)))
    interval = base.mark_rule(color=INK, strokeWidth=2).encode(
        y=alt.Y("lo:Q", scale=log, axis=y_axis), y2="hi:Q")
    dots = base.mark_point(color=INK, filled=True, opacity=1, size=64).encode(
        y=alt.Y("ratio:Q", scale=log, axis=y_axis),
        tooltip=[alt.Tooltip("era:N"), alt.Tooltip("ratio:Q", format=".1f", title="ratio"),
                 alt.Tooltip("lo:Q", format=".1f", title="95% CI low"),
                 alt.Tooltip("hi:Q", format=".1f", title="95% CI high")])
    extremes = (ratios.filter(pl.col("ratio").is_in([ratios["ratio"].max(), ratios["ratio"].min()]))
                .with_columns(pl.col("ratio").map_elements(times, return_dtype=pl.String).alias("label")))
    labels = (alt.Chart(extremes).mark_text(align="left", dx=8, color=INK)
              .encode(x=alt.X("era:N", sort=None), y=alt.Y("ratio:Q", scale=log),
                      text="label:N"))
    one = (alt.Chart(pl.DataFrame({"ratio": [1.0]})).mark_rule(color=REFERENCE_LINE, strokeWidth=1)
           .encode(y=alt.Y("ratio:Q", scale=log)))
    return (one + interval + dots + labels).properties(height=320)


def answer(silver: Silver) -> Answer:
    df = load(silver)
    medians = era_medians(df)
    all_rarities = hedonic(df)
    like_for_like = hedonic(df, like_for_like=True)
    ratios = era_ratios(like_for_like)
    ratio_formats = {"b": "%.2f", "se": "%.2f", "ratio": "%.1fx", "ci95_lo": "%.1fx", "ci95_hi": "%.1fx"}
    note = "ratio = exp(b), the price of an otherwise identical card relative to Scarlet & Violet. "
    return Answer(
        headline=headline(ratios),
        tables=[
            Table("Price per era", medians,
                  note=f"{df.height:,} price series of Pokemon singles on {silver.last_day}",
                  formats={"median_$": "$%.2f", "geo_mean_$": "$%.2f", "p90_$": "$%.2f", "share_ge_10$": "percent"}),
            Table("Hedonic A: all rarities with rarity fixed effects, price ratio vs Scarlet & Violet", all_rarities.terms,
                  note=note + f"n={all_rarities.n:,}, sets (clusters)={all_rarities.sets}, R2={all_rarities.r2:.3f}",
                  formats=ratio_formats),
            Table(f"Hedonic B: like-for-like, shared rarities only ({', '.join(SHARED_RARITIES)})", like_for_like.terms,
                  note=note + f"n={like_for_like.n:,}, sets (clusters)={like_for_like.sets}, R2={like_for_like.r2:.3f}",
                  formats=ratio_formats),
        ],
        chart=ratio_chart(ratios),
        caveats=CAVEATS,
        as_of=silver.last_day,
    )


def main() -> None:
    setup_logging()
    pl.Config.set_tbl_rows(40)
    pl.Config.set_float_precision(2)
    result = answer(load_silver())
    print(f"{result.headline}  (snapshot {result.as_of})")
    for t in result.tables:
        print(f"\n{t.title}\n  {t.note}")
        print(t.df)


if __name__ == "__main__":
    main()
