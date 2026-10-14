"""Shared configuration and helpers for the TCG market pipeline.

Storage layout (a small "medallion" layout):
    data/raw/      files exactly as downloaded (archives, JSON), safe to delete and download again
    data/bronze/   parsed but unmodified rows, one Parquet file per source day
    data/silver/   cleaned, typed, joined tables that analysis code reads
"""
from __future__ import annotations

import logging
import os
import re
import sys
import time
from pathlib import Path

import requests

# Anchored to the project root, not the working directory, so IDE runs can't scatter data/.
DATA_DIR = Path(os.environ.get("TCG_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
RAW_DIR = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"

TCGCSV = "https://tcgcsv.com"

# Games to ingest. Each key maps to a regex matched against the TCGplayer category name or
# displayName. Pokemon and Riftbound answer the core questions. The commented-out games are
# for the player-base question later, which needs more than two games to compare.
GAMES: dict[str, str] = {
    "pokemon": r"^pok[eé]mon$",
    "riftbound": r"riftbound",
    # "one_piece": r"one piece card game",
    # "lorcana": r"lorcana",
    # "star_wars_unlimited": r"star wars.*unlimited",
}

USER_AGENT = "tcg-market-analysis/0.1 (personal learning project)"

log = logging.getLogger("tcg")


def setup_logging() -> None:
    # Windows encodes redirected/piped output with the legacy code page (e.g. cp1250), which
    # can't represent Polars' box-drawing table borders or card names like "Pokémon δ ☆".
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def ensure_dirs() -> None:
    for d in (RAW_DIR, BRONZE_DIR, SILVER_DIR):
        d.mkdir(parents=True, exist_ok=True)


_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


def http_get(url: str, *, retries: int = 4, timeout: int = 60, stream: bool = False) -> requests.Response:
    """GET with exponential backoff. TCGCSV is a free community service, so keep the request rate low."""
    for attempt in range(retries):
        try:
            r = _session.get(url, timeout=timeout, stream=stream)
            if r.status_code == 404:
                return r  # the caller handles it, e.g. a missing archive day
            if 400 <= r.status_code < 500 and r.status_code != 429:
                # a client error repeats on every attempt, so retrying only adds load to the server
                raise RuntimeError(f"GET {url} -> HTTP {r.status_code}:\n{r.text[:1000]}")
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            wait = 2 ** attempt
            log.warning("GET %s failed (%s), retrying in %ss", url, e, wait)
            time.sleep(wait)
    raise RuntimeError(f"giving up on {url}")


def get_results(url: str) -> list[dict]:
    """TCGCSV endpoints wrap rows as {"success": ..., "results": [...]}."""
    payload = http_get(url).json()
    if isinstance(payload, dict):
        return payload.get("results", [])
    return payload


def match_game(name: str) -> str | None:
    for key, pattern in GAMES.items():
        if re.search(pattern, name or "", flags=re.IGNORECASE):
            return key
    return None
