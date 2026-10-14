"""The six research questions, and whether the data collected so far can answer each."""
from __future__ import annotations

from enum import Enum

from . import q4_generation
from .data import Silver
from .results import Question


class Status(Enum):
    NOT_STARTED = "not started"
    WAITING = "waiting for data"
    READY = "ready"


QUESTIONS = [
    Question(1, "Did Pokémon and Riftbound grow more than the S&P 500 (total return, risk-adjusted)?",
             "Chain-linked price indices vs ^SP500TR, Sharpe ratio", min_days=180, answer=None),
    Question(2, "Does the size of a game's player base affect prices?",
             "Panel of ~10 games", min_days=None, answer=None),
    Question(3, "Is sealed product more stable than single cards?",
             "Volatility after Geltner unsmoothing", min_days=180, answer=None),
    Question(4, "Which generation of cards is most expensive?",
             "Medians of log price, hedonic regression", min_days=1, answer=q4_generation.answer),
    Question(5, "Will Riftbound keep outperforming?",
             "Launch-cohort / event-time comparison", min_days=90, answer=None),
    Question(6, "Can prices be predicted?",
             "Walk-forward backtest vs random walk", min_days=365, answer=None),
]


def status(q: Question, silver: Silver) -> Status:
    if q.answer is None:
        return Status.NOT_STARTED
    if q.min_days is not None and silver.days < q.min_days:
        return Status.WAITING
    return Status.READY
