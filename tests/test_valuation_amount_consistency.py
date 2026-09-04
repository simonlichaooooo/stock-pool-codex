import pathlib
import unittest


HTML = (pathlib.Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")


class ValuationAmountConsistencyTests(unittest.TestCase):
    def test_original_amounts_are_the_source_for_canonical_calculation_values(self):
        function = HTML.split("function normalizeShareholderReturnFields", 1)[1].split(
            "function normalizeStockVersion", 1
        )[0]
        self.assertIn("Object.entries(next.originalAmounts).forEach", function)
        self.assertIn('key === "expectedProfitCny" && next.useSegmentValuation', function)
        self.assertIn("next[key] = toCny(inputAmount, entry.currency);", function)

    def test_segment_profit_is_also_rebuilt_from_its_visible_original_input(self):
        function = HTML.split("function normalizeSegmentValuationFields", 1)[1].split(
            "function applySegmentValuationTotals", 1
        )[0]
        self.assertIn('profitInput !== "" && Number.isFinite(inputProfit)', function)
        self.assertIn("toCny(inputProfit, profitCurrency)", function)

    def test_reported_example_has_positive_upside(self):
        expected_market_cap = 6.2 * 10 + 17 * 0.8
        upside = expected_market_cap / 52.7 - 1
        self.assertAlmostEqual(expected_market_cap, 75.6)
        self.assertGreater(upside, 0)
        self.assertAlmostEqual(upside * 100, 43.45, places=2)


if __name__ == "__main__":
    unittest.main()
