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

    def test_index_monthly_prices_retry_and_normalize_current_month(self):
        payload = {"data": {"klines": [
            "2026-06-30,0,100", "2026-07-31,0,110", "2026-08-12,0,121",
        ]}}
        with mock.patch.object(MODULE, "json_request", side_effect=[ConnectionError("reset"), payload]), \
                mock.patch.object(MODULE.time, "sleep"):
            prices = MODULE.fetch_index_monthly_prices("124.HSTECH")
        self.assertEqual(prices[-1], ("2026-08-12", 121))
        self.assertAlmostEqual(MODULE.monthly_returns(prices)["2026-08-01"], 10)

    def test_monthly_prices_backfill_current_month_from_daily_when_omitted(self):
        monthly_payload = {"data": {"hk00700": {"qfqmonth": [
            ["2026-06-30", "0", "100"], ["2026-07-31", "0", "110"],
        ]}}}
        with mock.patch.object(MODULE, "json_request", return_value=monthly_payload), \
                mock.patch.object(MODULE, "fetch_current_month_price", return_value=("2026-08-12", 121)), \
                mock.patch.object(MODULE, "current_hong_kong_month", return_value="2026-08"):
            prices = MODULE.fetch_monthly_prices("00700")
        self.assertEqual(prices[-1], ("2026-08-12", 121))

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

    def test_monthly_return_rows_align_stock_and_index_by_calendar_month(self):
        prices = [
            ("2022-12-30", 90),
            ("2023-01-31", 99),
            ("2023-02-28", 108.9),
        ]
        index_prices = [
            ("2022-12-30", 100),
            ("2023-01-30", 105),
            ("2023-02-27", 107.1),
        ]
        rows = MODULE.monthly_return_rows(
            "HSTECH", "00700", prices, MODULE.monthly_returns(index_prices), "official_index"
        )
        self.assertEqual([row["month_start"] for row in rows], ["2023-01-01", "2023-02-01"])
        self.assertEqual(rows[0]["period_end"], "2023-01-31")
        self.assertAlmostEqual(rows[0]["stock_return_pct"], 10)
        self.assertAlmostEqual(rows[0]["index_return_pct"], 5)
        self.assertAlmostEqual(rows[0]["excess_return_pct"], 5)
        self.assertAlmostEqual(rows[1]["excess_return_pct"], 8)

    def test_monthly_return_quality_can_fall_back_for_only_current_month(self):
        prices = [("2026-06-30", 100), ("2026-07-31", 110), ("2026-08-12", 121)]
        index_returns = {"2026-07-01": 5, "2026-08-01": 4}
        rows = MODULE.monthly_return_rows("HSTECH", "00700", prices, index_returns, {
            "2026-07-01": "official_index",
            "2026-08-01": "constituent_equal_weight",
        })
        self.assertEqual(rows[-2]["index_return_quality"], "official_index")
        self.assertEqual(rows[-1]["index_return_quality"], "constituent_equal_weight")
        self.assertAlmostEqual(rows[-1]["excess_return_pct"], 6)


if __name__ == "__main__":
    unittest.main()
