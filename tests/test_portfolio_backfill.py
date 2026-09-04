import pathlib
import unittest


HTML = (pathlib.Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")


class PortfolioBackfillTests(unittest.TestCase):
    def test_historical_closes_prefers_cors_enabled_tencent_with_jsonp_fallback(self):
        function = HTML.split("async function fetchHistoricalCloses", 1)[1].split(
            "async function revisedNavForTrades", 1
        )[0]
        self.assertIn("tencentHistorySymbol(stock)", function)
        self.assertIn("web.ifzq.gtimg.cn/appstock/app/fqkline/get", function)
        self.assertIn("data?.qfqday || data?.day || []", function)
        self.assertIn("if (closes.length) return closes;", function)
        self.assertIn("const json = await jsonp(url);", function)
        self.assertLess(function.index("web.ifzq.gtimg.cn"), function.index("push2his.eastmoney.com"))

    def test_current_or_future_nav_trade_skips_history_request(self):
        function = HTML.split("async function revisedNavForTrades", 1)[1].split(
            "async function submitPositionTrade", 1
        )[0]
        self.assertIn("const firstDate = applicableDates.sort()[0];", function)
        self.assertNotIn("[...applicableDates, rows[0].nav_date]", function)
        self.assertIn("firstDate >= todayString() || firstDate > lastDate", function)
        boundary_check = function.index("if (firstDate >= todayString()")
        history_request = function.index("await fetchHistoricalCloses")
        self.assertLess(boundary_check, history_request)

    def test_history_provider_failure_does_not_block_trade_save(self):
        function = HTML.split("async function submitPositionTrade", 1)[1].split(
            "function submitOptionDirectionEdit", 1
        )[0]
        backfill = function.split('if (form.has("backfillTrade"))', 1)[1].split(
            "updateActivePortfolio", 1
        )[0]
        self.assertIn("trade.navRevisionPending = true;", backfill)
        self.assertNotIn("return showPortfolioError", backfill)


if __name__ == "__main__":
    unittest.main()
