import pathlib
import unittest


HTML = (pathlib.Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")


class OtcStockSearchTests(unittest.TestCase):
    def test_eastmoney_pink_sheet_market_is_accepted(self):
        search_filter = HTML.split("function isUsStockSearchItem", 1)[1].split(
            "function normalizeSearchItem", 1
        )[0]
        self.assertIn('item.Classify === "OTCBB"', search_filter)
        self.assertIn('marketNumber === "153"', search_filter)
        self.assertIn('item.SecurityTypeName === "粉单"', search_filter)
        self.assertIn('String(item.SecurityType || "") === "26"', search_filter)

    def test_pink_sheet_is_normalized_as_us_otc_stock(self):
        normalizer = HTML.split("function normalizeSearchItem", 1)[1].split(
            "async function fetchExchangeRates", 1
        )[0]
        self.assertIn('market = "US"', normalizer)
        self.assertIn('if (classify === "OTCBB") exchange = "OTC"', normalizer)

    def test_otc_quote_id_is_preserved_for_quote_and_history(self):
        normalizer = HTML.split("function normalizeSearchItem", 1)[1].split(
            "async function fetchExchangeRates", 1
        )[0]
        self.assertIn("const quoteId = item.QuoteID", normalizer)
        self.assertIn("quoteId,", normalizer)


if __name__ == "__main__":
    unittest.main()
