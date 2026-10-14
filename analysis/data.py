"""The silver tables as one object, and the one place that reads them from disk."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl

from pipeline.common import SILVER_DIR

REQUIRED = ["fact_price", "dim_category", "dim_group", "dim_product"]


@dataclass(frozen=True)
class Silver:
    fact_price: pl.DataFrame
    dim_category: pl.DataFrame
    dim_group: pl.DataFrame
    dim_product: pl.DataFrame
    benchmarks: pl.DataFrame | None  # written by a separate step, so it can be absent
    days: int
    last_day: date


def load_silver() -> Silver:
    missing = [t for t in REQUIRED if not (SILVER_DIR / f"{t}.parquet").exists()]
    if missing:
        raise FileNotFoundError(
            f"No {', '.join(missing)} in {SILVER_DIR}. Build the tables first: run "
            "`python -m pipeline.catalog`, then `python -m pipeline.prices --live`.")
    frames = {t: pl.read_parquet(SILVER_DIR / f"{t}.parquet") for t in REQUIRED}
    bench = SILVER_DIR / "benchmarks.parquet"
    fact = frames["fact_price"]
    return Silver(**frames,
                  benchmarks=pl.read_parquet(bench) if bench.exists() else None,
                  days=fact["date"].n_unique(), last_day=fact["date"].max())


def silver_stamp() -> tuple[int, ...]:
    """Modification times of the silver files. It changes whenever a pipeline run rewrites one,
    so it works as a cache key."""
    return tuple(p.stat().st_mtime_ns for p in sorted(SILVER_DIR.glob("*.parquet")))


def rows_per_game(silver: Silver) -> pl.DataFrame:
    """Rows in fact_price per game, in total and on the latest day."""
    return (silver.fact_price
            .group_by("categoryId")
            .agg(pl.len().alias("rows"), (pl.col("date") == silver.last_day).sum().alias("rows_last_day"))
            .join(silver.dim_category.select("categoryId", "game"), on="categoryId")
            .select("game", "rows", "rows_last_day")
            .sort("game"))
