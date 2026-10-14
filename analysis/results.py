"""What an analysis hands to the dashboard: an Answer per research question."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import altair as alt
import polars as pl

from .data import Silver


@dataclass(frozen=True)
class Table:
    title: str
    df: pl.DataFrame
    note: str = ""
    formats: dict[str, str] = field(default_factory=dict)  # column -> Streamlit number format, e.g. "$%.2f"


@dataclass(frozen=True)
class Answer:
    headline: str
    tables: list[Table]
    chart: alt.Chart | None
    caveats: list[str]
    as_of: date


@dataclass(frozen=True)
class Question:
    id: int
    title: str
    method: str
    min_days: int | None  # days of price history needed; None when no amount is defined yet
    answer: Callable[[Silver], Answer] | None  # None until the analysis is written
