import pathlib
import unittest


HTML = (pathlib.Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")


class MarketInsightConnectMissingRatioTests(unittest.TestCase):
    def test_missing_ratio_is_not_recomputed_with_a_fallback_denominator(self):
        helper = HTML.split("function marketInsightStoredConnectRatio", 1)[1].split(
            "function marketInsightTrendAnalysis", 1
        )[0]
        self.assertIn('rawRatio === null', helper)
        self.assertIn('rawRatio === undefined', helper)
        self.assertIn('rawRatio === ""', helper)
        self.assertIn('row.ratio_quality === "missing_denominator"', helper)

    def test_only_complete_quality_checked_rows_are_plotted(self):
        helper = HTML.split("function marketInsightStoredConnectRatio", 1)[1].split(
            "function marketInsightTrendAnalysis", 1
        )[0]
        loader = HTML.split("async function openMarketInsightDetail", 1)[1].split(
            "function marketInsightConstituents", 1
        )[0]
        self.assertIn('["complete", "official_aggregate"].includes(row.completeness)', helper)
        self.assertIn("completeness,ratio_quality", loader)
        self.assertIn("marketInsightStoredConnectRatio(row)", loader)
        connect_mapping = loader.split("const connectHistory", 1)[1].split(
            "const currentConnectRatio", 1
        )[0]
        self.assertNotIn("ratioValue(", connect_mapping)

    def test_single_point_fallback_also_requires_an_explicit_stored_ratio(self):
        loader = HTML.split("async function openMarketInsightDetail", 1)[1].split(
            "function marketInsightConstituents", 1
        )[0]
        current_ratio = loader.split("const currentConnectRatio", 1)[1].split(
            "const priceHistory", 1
        )[0]
        self.assertIn("stock?.stockConnectRatio === null", current_ratio)
        self.assertNotIn("marketInsightConnectRatio(stock)", current_ratio)


if __name__ == "__main__":
    unittest.main()
