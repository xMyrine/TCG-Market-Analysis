"""Dashboard tests against the real silver tables. They are skipped when data/silver has no
fact_price.

Run:  python -m unittest tests.test_app
"""
import re
import shutil
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

import polars as pl
from streamlit.testing.v1 import AppTest

from analysis import data

APP = Path(__file__).resolve().parent.parent / "app.py"
HEADLINE = r"For an otherwise identical card, WotC-era cards cost \d+x Scarlet & Violet cards \(95% CI \d+x to \d+x\)\."


def run_app() -> AppTest:
    return AppTest.from_file(str(APP), default_timeout=120).run()


@unittest.skipUnless((data.SILVER_DIR / "fact_price.parquet").exists(), "no data/silver/fact_price.parquet")
class DashboardTest(unittest.TestCase):
    def test_q4_headline_chart_and_tables_render(self):
        at = run_app()
        self.assertEqual([e.value for e in at.exception], [])
        self.assertEqual([e.value for e in at.error], [])
        self.assertRegex(at.subheader[0].value, HEADLINE)
        overview = " ".join(m.value for m in at.markdown)
        self.assertRegex(overview, HEADLINE)
        self.assertEqual(len(at.get("vega_lite_chart")), 1)
        self.assertEqual(len(at.dataframe), 1 + 3)  # rows per game in the sidebar, then the three Q4 tables

    def test_a_pipeline_run_shows_after_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            silver_dir = Path(tmp)
            shutil.copytree(data.SILVER_DIR, silver_dir, dirs_exist_ok=True)
            with mock.patch.object(data, "SILVER_DIR", silver_dir):
                before = {m.label: m.value for m in run_app().metric}

                fact = pl.read_parquet(silver_dir / "fact_price.parquet")
                last_day = fact["date"].max()
                next_day = last_day + timedelta(days=1)
                pl.concat([fact, fact.filter(pl.col("date") == last_day).with_columns(date=next_day)]
                          ).write_parquet(silver_dir / "fact_price.parquet")

                at = run_app()
                after = {m.label: m.value for m in at.metric}
                self.assertEqual(int(after["Days collected"]), int(before["Days collected"]) + 1)
                self.assertEqual(after["Last snapshot"], str(next_day))
                self.assertIn(f"Snapshot of {next_day}", [c.value for c in at.caption])
                self.assertEqual([e.value for e in at.exception], [])


if __name__ == "__main__":
    unittest.main()
