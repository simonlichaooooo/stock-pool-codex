import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]
HTML = (ROOT / "index.html").read_text()
UPDATER = (ROOT / "scripts" / "update-market-overview.mjs").read_text()


class MarketInsightFastLoadTests(unittest.TestCase):
    def test_snapshot_contains_current_table_metrics(self):
        self.assertIn("snapshot.currentUniverse", UPDATER)
        self.assertIn("CURRENT_UNIVERSE_FIELDS", UPDATER)
        self.assertIn("excess_five_week_return_pct", UPDATER)
        self.assertIn("connect_change_5w_pct", UPDATER)

    def test_snapshot_is_loaded_before_metric_lookup(self):
        refresh = HTML.split("async function refreshMarketInsight", 1)[1].split("function journalStorageKey", 1)[0]
        self.assertLess(
            refresh.index("await loadMarketInsightSnapshot"),
            refresh.index("fetchPersistedMarketInsightUniverse(index.code"),
        )
        self.assertIn("marketInsightSnapshotUniverse", HTML)

    def test_large_live_refresh_uses_bounded_parallel_batches(self):
        loader = HTML.split("async function fetchMarketInsightUniverseBatches", 1)[1].split(
            "async function fetchPersistedMarketInsightUniverse", 1
        )[0]
        self.assertIn("start += 40", loader)
        self.assertIn("Math.min(4, batches.length)", loader)
        self.assertIn("stock_code=in.", loader)

    def test_login_does_not_prefetch_the_full_universe(self):
        startup = HTML.split("async function afterProfileReady", 1)[1].split("async function init", 1)[0]
        self.assertNotIn('fetchPersistedMarketInsightUniverse("ALL")', startup)


if __name__ == "__main__":
    unittest.main()
