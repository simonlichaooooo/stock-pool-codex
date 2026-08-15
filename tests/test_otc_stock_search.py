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

    def test_stock_pool_marks_pink_sheet_results(self):
        labeler = HTML.split("function stockMarketLabel", 1)[1].split(
            "function todayString", 1
        )[0]
        stock_pool_search = HTML.split("async function onStockSearch", 1)[1].split(
            "function applyCatalog", 1
        )[0]
        self.assertIn('stock?.exchange === "OTC"', labeler)
        self.assertIn("美股", HTML.split("function marketLabel", 1)[1].split("function stockMarketLabel", 1)[0])
        self.assertIn("stockMarketLabel(stock)", stock_pool_search)

    def test_stock_pool_preserves_otc_identity_when_selected_and_saved(self):
        apply_catalog = HTML.split("function applyCatalog", 1)[1].split(
            "async function saveStock", 1
        )[0]
        save_stock = HTML.split("async function saveStock", 1)[1].split(
            "function ", 1
        )[0]
        self.assertIn("state.form.exchange = stock.exchange", apply_catalog)
        self.assertIn('state.form.quoteId = stock.quoteId || ""', apply_catalog)
        self.assertIn("...normalizeShareholderReturnFields(state.form)", save_stock)
        self.assertIn("payloadForStockRecord(payload)", save_stock)


if __name__ == "__main__":
    unittest.main()
