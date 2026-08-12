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

    def test_custom_filter_controls_match_rating_filters(self):
        view = HTML.split("function renderMarketInsightView()", 1)[1].split(
            'section class="table-panel horizontal-data-table', 1
        )[0]
        self.assertIn("market-insight-custom-filter-list", view)
        self.assertIn('class="rating-rule ${state.marketInsightCustomActiveIds.includes(filter.id)', view)
        self.assertNotIn("<span>自定义筛选</span>", view)
        self.assertIn('data-action="openMarketInsightCustomFilter"', view)
        self.assertIn('data-action="openMarketInsightCustomManager"', view)

    def test_custom_filters_can_be_edited_and_require_delete_confirmation(self):
        self.assertIn("function renderMarketInsightCustomManagerModal()", HTML)
        self.assertIn('data-action="editMarketInsightCustomFilter"', HTML)
        self.assertIn('data-action="requestDeleteMarketInsightCustomFilter"', HTML)
        self.assertIn('data-action="confirmDeleteMarketInsightCustomFilter"', HTML)
        self.assertNotIn('data-action="deleteMarketInsightCustomFilter"', HTML)

    def test_rating_copy_and_motto_are_in_requested_rows(self):
        view = HTML.split("function renderMarketInsightView()", 1)[1].split(
            'section class="table-panel horizontal-data-table', 1
        )[0]
        refresh_index = view.index('data-action="refreshMarketInsight"')
        motto_index = view.index('class="market-insight-rating-motto"')
        score_row_index = view.index('class="market-insight-rating-filter-row market-insight-rating-score-row"')
        standard_index = view.index('class="market-insight-rating-standard"')
        self.assertLess(refresh_index, motto_index)
        self.assertLess(score_row_index, standard_index)


if __name__ == "__main__":
    unittest.main()
