import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]
SQL = (ROOT / "supabase" / "market-insight-composite-filter.sql").read_text(encoding="utf-8")
HTML = (ROOT / "index.html").read_text(encoding="utf-8")


class MarketInsightCompositeFilterTest(unittest.TestCase):
    def test_every_supported_metric_is_mapped_in_database(self):
        for period in (5, 10, 20, 30, 40, 50):
            self.assertIn(f"u.bias_{period}w_pct", SQL)
            self.assertIn(f"u.bias_speed_{period}w_pct", SQL)
            self.assertIn(f"u.percentile_{period}w_1y", SQL)
            self.assertIn(f"u.percentile_{period}w_2y", SQL)
        for field in (
            "u.excess_one_week_return_pct",
            "u.excess_five_week_return_pct",
            "monthly.excess_return_pct",
            "u.connect_change_5w_pct",
            "u.short_change_5w_pct",
        ):
            self.assertIn(field, SQL)

    def test_database_function_combines_conditions_and_reports_missing_data(self):
        self.assertIn("bool_and(", SQL)
        self.assertIn("missing_condition_count", SQL)
        self.assertIn("abs(e.actual_value - e.expected_value) < 0.005", SQL)
        self.assertIn("current_timestamp at time zone 'Asia/Hong_Kong'", SQL)

    def test_frontend_calls_rpc_instead_of_downloading_weekly_history(self):
        custom_loader = HTML.split("async function loadMarketInsightCustomMetrics()", 1)[1].split(
            "function renderMarketInsightView()", 1
        )[0]
        self.assertIn('/rest/v1/rpc/filter_hk_market_insights', custom_loader)
        self.assertNotIn("hk_market_insight_metrics_weekly?", custom_loader)
        self.assertNotIn("fetchEastmoneyWeeklySeries", custom_loader)


if __name__ == "__main__":
    unittest.main()
