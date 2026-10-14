import pathlib
import unittest
from unittest import mock
import importlib.util
import json
import tempfile


ROOT = pathlib.Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("stock_connect_ingest", ROOT / "scripts" / "market-data-ingest.py")
INGEST = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INGEST)


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

    def test_share_ratio_refresh_is_batched(self):
        indexes = {"stockconnect": {"code": "STOCK_CONNECT", "members": [
            {"code": str(code)} for code in range(1, 24)
        ]}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as source:
            json.dump({"constituents": {"indexes": indexes}}, source)
            source.flush()
            client = mock.Mock()
            with mock.patch.object(INGEST, "MARKET_INSIGHTS_FILE", source.name), mock.patch.object(
                INGEST, "fetch_issued_shares_history",
                side_effect=lambda code, *_: [{"stock_code": code, "period_end": "2026-09-30", "issued_shares": 1}],
            ):
                INGEST.ingest_issued_shares(client, INGEST.date(2026, 1, 1), INGEST.date(2026, 10, 14), workers=2)
        batches = [call.args[1]["p_stock_codes"] for call in client.rpc.call_args_list]
        self.assertEqual([len(batch) for batch in batches], [10, 10, 3])
        self.assertEqual(len({code for batch in batches for code in batch}), 23)


if __name__ == "__main__":
    unittest.main()
