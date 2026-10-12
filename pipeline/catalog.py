"""Step 1a - build the dimension tables: which games, sets (groups) and products exist.

Run:  python -m pipeline.catalog

Outputs:
    data/silver/dim_category.parquet   the selected games and their TCGplayer categoryId
    data/silver/dim_group.parquet      one row per set (groupId), with release date
    data/silver/dim_product.parquet    one row per product, with card number, rarity and product_kind

Prices are NOT here - they live in a separate fact table (see prices.py). This is a
star schema: small descriptive dimension tables joined to one large, narrow fact table.
"""
from __future__ import annotations

import json
import re
import time

import polars as pl

from .common import (SILVER_DIR, TCGCSV, ensure_dirs, get_results, log, match_game,
                     setup_logging)

# Heuristics for products WITHOUT a card number. Checked in order: accessories first,
# because "Deck Box" or "Card Sleeves" would otherwise match the sealed patterns.
ACCESSORY_RE = re.compile(
    r"sleeve|playmat|play mat|deck box|binder|portfolio|code card|dice|coin|pin\b|"
    r"toploader|storage|album|figure|plush|poster|lanyard|counter",
    re.IGNORECASE,
)
SEALED_RE = re.compile(
    r"booster|elite trainer|display|bundle|collection|tin\b|blister|case\b|box|"
    r"premium|starter|theme deck|champion deck|battle deck|build & battle|pack|gift set",
    re.IGNORECASE,
)


def classify(name: str, ext: dict[str, str]) -> str:
    """single / sealed / accessory / other.

    TCGplayer stores card attributes in extendedData; a collector number is the most
    reliable signal that a product is an individual card. Everything else is decided by
    name patterns, which is a heuristic - the audit step reports how many fall in 'other'
    so we can refine the rules instead of trusting them blindly.
    """
    if ext.get("Number") or ext.get("Rarity"):
        return "single"
    if ACCESSORY_RE.search(name):
        return "accessory"
    if SEALED_RE.search(name):
        return "sealed"
    return "other"


def flatten_extended(items: list[dict] | None) -> dict[str, str]:
    return {i.get("name"): i.get("value") for i in (items or []) if i.get("name")}


def main() -> None:
    setup_logging()
    ensure_dirs()

    categories = get_results(f"{TCGCSV}/tcgplayer/categories")
    selected = []
    for c in categories:
        game = match_game(c.get("name", "")) or match_game(c.get("displayName", ""))
        if game:
            selected.append({"game": game, "categoryId": c["categoryId"], "name": c.get("name"),
                             "displayName": c.get("displayName")})
    if not selected:
        raise SystemExit("No categories matched GAMES in common.py - check the regexes.")
    games = [s["game"] for s in selected]
    if dupes := {g for g in games if games.count(g) > 1}:
        # e.g. a new "Riftbound Japan" category would silently mix markets into one index
        raise SystemExit(f"Games matched several categories: {dupes} - tighten the regexes in common.py.")
    for s in selected:
        log.info("Selected %-10s categoryId=%s (%s)", s["game"], s["categoryId"], s["displayName"])
    pl.DataFrame(selected).write_parquet(SILVER_DIR / "dim_category.parquet")

    group_rows, product_rows = [], []
    for cat in selected:
        cid = cat["categoryId"]
        groups = get_results(f"{TCGCSV}/tcgplayer/{cid}/groups")
        log.info("%s: %d groups", cat["game"], len(groups))
        for i, g in enumerate(groups, 1):
            group_rows.append({
                "game": cat["game"], "categoryId": cid, "groupId": g["groupId"],
                "group_name": g.get("name"), "abbreviation": g.get("abbreviation"),
                "is_supplemental": g.get("isSupplemental"), "published_on": g.get("publishedOn"),
            })
            for p in get_results(f"{TCGCSV}/tcgplayer/{cid}/{g['groupId']}/products"):
                ext = flatten_extended(p.get("extendedData"))
                product_rows.append({
                    "game": cat["game"], "categoryId": cid, "groupId": g["groupId"],
                    "productId": p["productId"], "name": p.get("name"), "clean_name": p.get("cleanName"),
                    "number": ext.get("Number"), "rarity": ext.get("Rarity"),
                    "product_kind": classify(p.get("name", ""), ext),
                    "url": p.get("url"), "extended_json": json.dumps(ext, ensure_ascii=False),
                })
            time.sleep(0.15)  # politeness: ~7 requests/second at most
            if i % 50 == 0:
                log.info("  %d/%d groups done", i, len(groups))

    groups_df = pl.DataFrame(group_rows).with_columns(
        pl.col("published_on").str.to_datetime(strict=False).dt.date().alias("release_date")
    )
    products_df = pl.DataFrame(product_rows)
    groups_df.write_parquet(SILVER_DIR / "dim_group.parquet")
    products_df.write_parquet(SILVER_DIR / "dim_product.parquet")

    log.info("Wrote %d groups and %d products", groups_df.height, products_df.height)
    print(products_df.group_by("game", "product_kind").len().sort("game", "len", descending=[False, True]))


if __name__ == "__main__":
    main()
