"""Offline end-to-end test: fake catalogue + fake PPMd archives -> prices -> audit.

Run:  TCG_DATA_DIR=/tmp/tcg-sim python -m tests.simulate
It never touches the network: prices.download() reuses archives already on disk.
"""
from __future__ import annotations

import json
import random
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import py7zr

from pipeline import audit, prices
from pipeline.common import RAW_DIR, SILVER_DIR, ensure_dirs
from pipeline.catalog import classify

random.seed(0)
ensure_dirs()

# --- fake dimensions: Pokemon (3) and a made-up Riftbound id, plus a game we must ignore (1)
pl.DataFrame({"game": ["pokemon", "riftbound"], "categoryId": [3, 89],
              "name": ["Pokemon", "Riftbound"], "displayName": ["Pokemon", "Riftbound"]}
             ).write_parquet(SILVER_DIR / "dim_category.parquet")
products = [
    ("pokemon", 3, 100, 1, "Charizard ex", {"Number": "199/165", "Rarity": "Special Illustration Rare"}),
    ("pokemon", 3, 100, 2, "Scarlet & Violet 151 Booster Bundle", {}),
    ("pokemon", 3, 100, 3, "Pikachu Card Sleeves", {}),
    ("pokemon", 3, 100, 4, "Mystery Thing", {}),
    ("riftbound", 89, 500, 10, "Jinx - Rebel", {"Number": "OGN-030", "Rarity": "Epic"}),
    ("riftbound", 89, 500, 11, "Origins Booster Display", {}),
]
pl.DataFrame([{"game": g, "categoryId": c, "groupId": gr, "productId": pid, "name": n, "clean_name": n,
               "number": e.get("Number"), "rarity": e.get("Rarity"), "product_kind": classify(n, e),
               "url": "", "extended_json": json.dumps(e)} for g, c, gr, pid, n, e in products]
             ).write_parquet(SILVER_DIR / "dim_product.parquet")
pl.DataFrame({"game": ["pokemon", "riftbound"], "categoryId": [3, 89], "groupId": [100, 500],
              "group_name": ["SV 151", "Origins"], "abbreviation": ["MEW", "OGN"],
              "is_supplemental": [False, False], "published_on": ["2023-09-22", "2025-10-31"],
              "release_date": [date(2023, 9, 22), date(2025, 10, 31)]}
             ).write_parquet(SILVER_DIR / "dim_group.parquet")

# --- fake archives mirroring the real layout <date>/<categoryId>/<groupId>/prices
days = [date(2024, 2, 8) + timedelta(days=7 * i) for i in range(5)]
(RAW_DIR / "archives").mkdir(parents=True, exist_ok=True)
for d in days:
    with tempfile.TemporaryDirectory() as tmp:
        for cid, gid, pids in [(3, 100, [1, 2, 3, 4]), (89, 500, [10, 11]), (1, 7, [999])]:
            folder = Path(tmp) / d.isoformat() / str(cid) / str(gid)
            folder.mkdir(parents=True)
            results = [{"productId": pid, "subTypeName": "Holofoil" if pid in (1, 10) else "Normal",
                        "lowPrice": 9.0, "midPrice": 11.0, "highPrice": 5000.0,  # parked listing
                        "marketPrice": round(10 * random.uniform(0.9, 1.2), 2), "directLowPrice": None}
                       for pid in pids]
            (folder / "prices").write_text(json.dumps({"success": True, "errors": [], "results": results}))
        with py7zr.SevenZipFile(RAW_DIR / "archives" / f"prices-{d.isoformat()}.ppmd.7z", "w",
                                filters=[{"id": py7zr.FILTER_PPMD}]) as z:
            z.writeall(Path(tmp) / d.isoformat(), arcname=d.isoformat())

sys.argv = ["prices", "--start", days[0].isoformat(), "--end", days[-1].isoformat(), "--step", "7"]
prices.main()
fact = pl.read_parquet(SILVER_DIR / "fact_price.parquet")
assert fact.height == 5 * 6, fact.height                # 5 days x 6 products; category 1 dropped
assert 999 not in fact["productId"].to_list()
print("prices OK:", fact.height, "rows")

sys.argv = ["prices", "--start", days[0].isoformat(), "--end", days[-1].isoformat(), "--step", "7"]
prices.main()                                            # second run must be a no-op
assert pl.read_parquet(SILVER_DIR / "fact_price.parquet").height == 30
print("idempotency OK")

audit.main()
