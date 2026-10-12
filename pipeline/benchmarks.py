"""Step 1c - the benchmarks the card markets are compared against.

Run:  python -m pipeline.benchmarks

Outputs data/silver/benchmarks.parquet in long format: (date, series, value)
    SP500TR   S&P 500 total return index (dividends reinvested)  <- the fair benchmark
    SP500     S&P 500 price index (no dividends)                 <- kept to show the difference
    DTB3      3-month US T-bill rate, % per year                 <- risk-free rate for Sharpe ratios
    CPIAUCSL  US consumer price index                            <- for inflation-adjusted returns
    DEXUSEU   USD per 1 EUR                                      <- to convert Cardmarket EUR prices
"""
from __future__ import annotations

import io

import polars as pl
import yfinance as yf

from .common import SILVER_DIR, ensure_dirs, http_get, log, setup_logging

START = "2015-01-01"
YAHOO = {"SP500TR": "^SP500TR", "SP500": "^GSPC"}
FRED = ["DTB3", "CPIAUCSL", "DEXUSEU"]


def from_yahoo(name: str, ticker: str) -> pl.DataFrame:
    df = yf.download(ticker, start=START, auto_adjust=False, progress=False)
    close = df["Close"].squeeze()  # newer yfinance returns a column MultiIndex
    out = pl.DataFrame({"date": close.index.date, "value": close.to_numpy()})
    return out.with_columns(pl.lit(name).alias("series"))


def from_fred(series_id: str) -> pl.DataFrame:
    # The public graph CSV needs no API key. FRED writes missing values as "." or blank.
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={START}"
    raw = pl.read_csv(io.BytesIO(http_get(url).content), infer_schema_length=0)
    date_col, value_col = raw.columns[0], raw.columns[1]
    return raw.select(
        pl.col(date_col).str.to_date().alias("date"),
        pl.col(value_col).cast(pl.Float64, strict=False).alias("value"),
        pl.lit(series_id).alias("series"),
    ).drop_nulls("value")


def main() -> None:
    setup_logging()
    ensure_dirs()
    frames = [from_yahoo(n, t) for n, t in YAHOO.items()] + [from_fred(s) for s in FRED]
    df = pl.concat([f.select("date", "series", "value") for f in frames]).sort("series", "date")
    df.write_parquet(SILVER_DIR / "benchmarks.parquet")
    print(df.group_by("series").agg(pl.len().alias("rows"), pl.col("date").min().alias("first"),
                                     pl.col("date").max().alias("last")).sort("series"))


if __name__ == "__main__":
    main()
