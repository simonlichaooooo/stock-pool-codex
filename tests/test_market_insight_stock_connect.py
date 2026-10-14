import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]


class StockConnectUniverseTests(unittest.TestCase):
    def test_frontend_exposes_stock_connect_scope(self):
        html = (ROOT / "index.html").read_text()
        self.assertIn('{ id: "stockconnect", name: "港股通", code: "STOCK_CONNECT"', html)
        self.assertIn('["all", "watchlist", "stockconnect"].includes(indexId)', html)
        self.assertIn("港股通与四个指数范围", html)

    def test_overview_builds_scope_from_latest_official_holdings(self):
        source = (ROOT / "scripts" / "update-market-overview.mjs").read_text()
        self.assertIn('stockconnect:"STOCK_CONNECT"', source)
        self.assertIn('row.holding_date === latestConnectDate', source)
        self.assertIn('snapshot.constituents.indexes.stockconnect', source)
        self.assertIn('["all", "stockconnect", "hstech", "hsli", "hsmi", "hssi"]', source)

    def test_database_migration_allows_stock_connect_scope(self):
        migration = (ROOT / "supabase" / "market-insight-stock-connect-universe.sql").read_text()
        self.assertEqual(migration.count("'STOCK_CONNECT'"), 3)
        self.assertIn("hk_market_insight_metrics_weekly_index_code_check", migration)
        self.assertIn("hk_market_insight_monthly_returns_index_code_check", migration)


if __name__ == "__main__":
    unittest.main()
