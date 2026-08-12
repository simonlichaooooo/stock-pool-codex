import importlib.util
import pathlib
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock


SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "market-data-ingest.py"
SPEC = importlib.util.spec_from_file_location("market_data_ingest_filter_metrics", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MarketInsightFilterMetricsTest(unittest.TestCase):
    def test_incomplete_week_is_excluded(self):
        wednesday = datetime(2026, 8, 12, 10, tzinfo=timezone.utc)
        cutoff = MODULE.latest_completed_week_date(wednesday)
        self.assertEqual(cutoff.isoformat(), "2026-08-07")
        prices = [("2026-08-07", 100), ("2026-08-12", 101)]
        self.assertEqual(MODULE.completed_weekly_prices(prices, cutoff), [("2026-08-07", 100)])

    def test_index_weekly_prices_retry_transient_failure(self):
        payload = {"data": {"klines": [f"2026-0{month}-01,0,{100 + month}" for month in range(1, 7)]}}
        with mock.patch.object(MODULE, "json_request", side_effect=[ConnectionError("reset"), payload]), \
                mock.patch.object(MODULE.time, "sleep"):
            prices = MODULE.fetch_index_weekly_prices("124.HSTECH")
        self.assertEqual(len(prices), 6)
        self.assertEqual(prices[-1][1], 106)

    def test_percentile_and_speed_calculations(self):
        values = [float(value) for value in range(104)]
        percentiles = MODULE.rolling_percentiles(values, 104)
        self.assertIsNone(percentiles[-2])
        self.assertEqual(percentiles[-1], 100)
        self.assertEqual(MODULE.rolling_changes([None, 1.0, 1.5, 0.5]), [None, None, 0.5, -1.0])

    def test_metric_rows_include_every_filter_period(self):
        start = date(2022, 1, 7)
        prices = [
            ((start + timedelta(days=7 * offset)).isoformat(), 100 + offset * 0.4)
            for offset in range(180)
        ]
        index_returns = {
            period: MODULE.period_returns(prices, period)
            for period in MODULE.RETURN_PERIODS
        }
        rows = MODULE.metric_rows("HSTECH", "00700", prices, index_returns, "official_index")
        latest = rows[-1]
        for period in MODULE.BIAS_PERIODS:
            self.assertIsNotNone(latest[f"bias_{period}w_pct"])
            self.assertIsNotNone(latest[f"bias_speed_{period}w_pct"])
            self.assertIsNotNone(latest[f"percentile_{period}w_1y"])
            self.assertIsNotNone(latest[f"percentile_{period}w_2y"])
        self.assertAlmostEqual(latest["excess_one_week_return_pct"], 0)
        self.assertAlmostEqual(latest["excess_five_week_return_pct"], 0)

    def test_coverage_reports_database_ready_rows(self):
        start = date(2022, 1, 7)
        prices = [
            ((start + timedelta(days=7 * offset)).isoformat(), 80 + offset * 0.25)
            for offset in range(180)
        ]
        index_returns = {
            period: MODULE.period_returns(prices, period)
            for period in MODULE.RETURN_PERIODS
        }
        rows = MODULE.metric_rows("HSTECH", "00700", prices, index_returns, "official_index")
        indexes = {
            "hstech": {
                "code": "HSTECH",
                "members": [{"code": "00700"}],
            }
        }
        coverage = MODULE.metric_coverage(rows, indexes)["HSTECH"]
        self.assertEqual(coverage["stocks_expected"], 1)
        self.assertEqual(coverage["stocks_calculated"], 1)
        self.assertEqual(coverage["all_2y_percentiles_coverage_pct"], 100)
        self.assertEqual(coverage["standard_excess_returns_coverage_pct"], 100)


if __name__ == "__main__":
    unittest.main()
