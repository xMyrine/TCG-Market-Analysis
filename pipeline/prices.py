"""Step 1b - download TCGCSV's daily price archives and keep only our games.

Run:
    python -m pipeline.prices --inspect 2024-02-08     # look inside one archive first
    python -m pipeline.prices --step 7                 # weekly sample, 2024-02-08 .. yesterday
    python -m pipeline.prices --step 1                 # later: fill in every day
    python -m pipeline.prices --live                   # current snapshot via the API (run daily)

NOTE (2026-10): TCGCSV has taken the archive offline (403 with a notice); --live is the
only working source until it returns. Both paths write the same bronze day files.

Each archive is a full snapshot of TCGplayer prices for every game on one day. We
extract only the selected categories, parse them into rows and write one Parquet file
per day under data/bronze/prices/date=YYYY-MM-DD/. Then all days are consolidated into
data/silver/fact_price.parquet.

Re-running is safe (idempotent): days that already have a Parquet file are skipped, so a
crash or Ctrl-C costs nothing, and `--step 1` after `--step 7` only fetches the gaps.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path, PurePosixPath

import duckdb
import polars as pl
import py7zr

from .common import (BRONZE_DIR, RAW_DIR, SILVER_DIR, TCGCSV, ensure_dirs, http_get, log,
                     setup_logging)

ARCHIVE_START = date(2024, 2, 8)  # first day TCGCSV archived
PRICE_FIELDS = ["lowPrice", "midPrice", "highPrice", "marketPrice", "directLowPrice"]
SCHEMA = {
    "date": pl.Date, "categoryId": pl.Int64, "groupId": pl.Int64, "productId": pl.Int64,
    "subTypeName": pl.Utf8, **{f: pl.Float64 for f in PRICE_FIELDS},
}


def archive_url(d: date) -> str:
    return f"{TCGCSV}/archive/tcgplayer/prices-{d.isoformat()}.ppmd.7z"


def day_path(d: date) -> Path:
    return BRONZE_DIR / "prices" / f"date={d.isoformat()}" / "part.parquet"


def download(d: date) -> Path | None:
    dest = RAW_DIR / "archives" / f"prices-{d.isoformat()}.ppmd.7z"
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = http_get(archive_url(d), stream=True, timeout=300)
    if r.status_code == 404:
        log.warning("%s: no archive (404), skipping", d)
        return None
    tmp = dest.with_suffix(".part")
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    tmp.rename(dest)  # atomic: a half-downloaded file never looks finished
    return dest


def parse_member(name: str) -> tuple[int, int] | None:
    """Archive members look like  <date>/<categoryId>/<groupId>/prices .
    Returns (categoryId, groupId), or None for anything that isn't a prices file."""
    parts = PurePosixPath(name).parts
    if len(parts) < 3 or parts[-1] != "prices":
        return None
    try:
        return int(parts[-3]), int(parts[-2])
    except ValueError:
        return None


def payload_rows(d: date, cid: int, gid: int, payload: dict | list) -> list[dict]:
    """One TCGCSV prices file (archive member or live API response) -> fact rows."""
    results = payload.get("results", []) if isinstance(payload, dict) else payload
    return [{"date": d, "categoryId": cid, "groupId": gid,
             "productId": r.get("productId"), "subTypeName": r.get("subTypeName"),
             **{f: r.get(f) for f in PRICE_FIELDS}} for r in results]


def extract_day(archive: Path, d: date, category_ids: set[int]) -> pl.DataFrame:
    rows = []
    with py7zr.SevenZipFile(archive, mode="r") as z:
        targets = [n for n in z.getnames()
                   if (m := parse_member(n)) and m[0] in category_ids]
        with tempfile.TemporaryDirectory() as tmpdir:
            z.extract(path=tmpdir, targets=targets)
            for name in targets:
                cid, gid = parse_member(name)
                payload = json.loads((Path(tmpdir) / name).read_text(encoding="utf-8"))
                rows += payload_rows(d, cid, gid, payload)
    return pl.DataFrame(rows, schema=SCHEMA)


def snapshot_date() -> date:
    """Date of the prices the live API is serving now (refreshed daily ~20:00 UTC)."""
    stamp = http_get(f"{TCGCSV}/last-updated.txt").text.strip()  # e.g. 2026-10-11T20:05:45+0000
    return date.fromisoformat(stamp[:10])


def fetch_live() -> None:
    """Save the API's current snapshot as one bronze day, exactly like an archive day.

    The archive went offline in 2026; the maintainer asks clients to fetch prices per group
    and not to request the same file twice in 24h. The day_path() existence check enforces
    that: a second run on the same snapshot makes no price requests at all."""
    d = snapshot_date()
    out = day_path(d)
    if out.exists():
        log.info("%s: snapshot already saved, nothing to fetch", d)
        return
    groups = pl.read_parquet(SILVER_DIR / "dim_group.parquet").select("categoryId", "groupId").rows()
    rows = []
    for i, (cid, gid) in enumerate(groups, 1):
        rows += payload_rows(d, cid, gid, http_get(f"{TCGCSV}/tcgplayer/{cid}/{gid}/prices").json())
        time.sleep(0.15)
        if i % 50 == 0:
            log.info("  %d/%d groups fetched", i, len(groups))
    if snapshot_date() != d:  # TCGCSV refreshed mid-run: rows would mix two days
        raise SystemExit("Snapshot changed during the fetch - re-run to get a consistent day.")
    df = pl.DataFrame(rows, schema=SCHEMA)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out)
    log.info("%s: %d price rows from %d groups (live API)", d, df.height, len(groups))


def inspect(d: date) -> None:
    archive = download(d)
    if archive is None:
        return
    with py7zr.SevenZipFile(archive, mode="r") as z:
        names = z.getnames()
    print(f"{len(names)} members. First 15:")
    for n in names[:15]:
        print("  ", n, "->", parse_member(n))


def consolidate() -> None:
    """Union every daily file into one silver fact table, sorted for fast time-series reads."""
    pattern = str(BRONZE_DIR / "prices" / "*" / "part.parquet")
    out = SILVER_DIR / "fact_price.parquet"
    con = duckdb.connect()
    con.execute(f"""
        COPY (
            SELECT * FROM read_parquet('{pattern}')
            ORDER BY categoryId, productId, subTypeName, date
        ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
    """)
    n, days = con.execute(f"SELECT count(*), count(DISTINCT date) FROM read_parquet('{out}')").fetchone()
    log.info("fact_price: %d rows over %d days -> %s", n, days, out)


def main() -> None:
    setup_logging()
    ensure_dirs()
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat, default=ARCHIVE_START)
    ap.add_argument("--end", type=date.fromisoformat, default=date.today() - timedelta(days=1))
    ap.add_argument("--step", type=int, default=7, help="days between samples (7 = weekly)")
    ap.add_argument("--keep-archives", action="store_true", help="keep raw .7z files (large)")
    ap.add_argument("--inspect", type=date.fromisoformat, help="list the members of one archive and exit")
    ap.add_argument("--live", action="store_true", help="save today's snapshot from the API (archive is offline)")
    args = ap.parse_args()

    if args.inspect:
        inspect(args.inspect)
        return

    dim_cat = SILVER_DIR / "dim_category.parquet"
    if not dim_cat.exists():
        raise SystemExit("Run `python -m pipeline.catalog` first.")
    category_ids = set(pl.read_parquet(dim_cat)["categoryId"].to_list())

    if args.live:
        fetch_live()
        consolidate()
        return

    d = args.start
    while d <= args.end:
        out = day_path(d)
        if not out.exists():
            archive = download(d)
            if archive is not None:
                df = extract_day(archive, d, category_ids)
                out.parent.mkdir(parents=True, exist_ok=True)
                df.write_parquet(out)
                log.info("%s: %d price rows", d, df.height)
                if not args.keep_archives:
                    archive.unlink()
        d += timedelta(days=args.step)

    consolidate()
    if not args.keep_archives:
        shutil.rmtree(RAW_DIR / "archives", ignore_errors=True)


if __name__ == "__main__":
    main()
