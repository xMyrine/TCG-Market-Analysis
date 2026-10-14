"""Run:  python -m unittest tests.test_questions"""
import unittest
from datetime import date

import polars as pl

from analysis.data import Silver
from analysis.questions import QUESTIONS, Status, status
from analysis.results import Question


def silver_with(days: int) -> Silver:
    empty = pl.DataFrame()
    return Silver(empty, empty, empty, empty, None, days=days, last_day=date(2026, 10, 13))


def question(min_days, answer) -> Question:
    return Question(1, "title", "method", min_days=min_days, answer=answer)


class StatusTest(unittest.TestCase):
    def test_question_without_code_is_not_started_however_much_history_exists(self):
        self.assertIs(status(question(180, None), silver_with(500)), Status.NOT_STARTED)

    def test_question_with_code_waits_until_it_has_min_days(self):
        q = question(180, lambda silver: None)
        self.assertIs(status(q, silver_with(179)), Status.WAITING)
        self.assertIs(status(q, silver_with(180)), Status.READY)

    def test_question_with_code_and_no_minimum_is_ready(self):
        self.assertIs(status(question(None, lambda silver: None), silver_with(0)), Status.READY)

    def test_registry_after_one_snapshot(self):
        by_id = {q.id: status(q, silver_with(1)) for q in QUESTIONS}
        self.assertEqual(by_id[4], Status.READY)
        self.assertEqual({i for i, s in by_id.items() if s is Status.NOT_STARTED}, {1, 2, 3, 5, 6})


if __name__ == "__main__":
    unittest.main()
