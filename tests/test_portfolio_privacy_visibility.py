import pathlib
import unittest


HTML = (pathlib.Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")


class PortfolioPrivacyVisibilityTests(unittest.TestCase):
    def test_stock_cost_remains_visible_in_privacy_mode(self):
        table = HTML.split("function renderPortfolioTable", 1)[1].split(
            "function portfolioValuationVersions", 1
        )[0]
        self.assertIn('${formatPortfolioCost(position.averageCost)}</td>', table)
        self.assertNotIn('${portfolioPrivate(formatPortfolioCost(position.averageCost))}</td>', table)

    def test_stock_holding_profit_remains_visible_in_privacy_mode(self):
        table = HTML.split("function renderPortfolioTable", 1)[1].split(
            "function portfolioValuationVersions", 1
        )[0]
        self.assertIn("const holdingProfitCell = `${holdingProfitText}", table)
        self.assertNotIn('state.portfolioPrivacyMode\n              ? "****"', table)
        self.assertNotIn('const holdingProfitClass = state.portfolioPrivacyMode', table)

    def test_option_cost_and_holding_profit_also_remain_visible(self):
        table = HTML.split("function renderPortfolioTable", 1)[1].split(
            "function portfolioValuationVersions", 1
        )[0]
        option_row = table.split('if(position.assetType==="option")', 1)[1].split(
            "const pendingPlans", 1
        )[0]
        self.assertIn('${formatPortfolioCost(cost)}</td>', option_row)
        self.assertNotIn('portfolioPrivate(formatPortfolioCost(cost))', option_row)
        self.assertNotIn('portfolioPrivate(`${holdingProfit', option_row)


if __name__ == "__main__":
    unittest.main()
