import pathlib
import unittest


HTML = (pathlib.Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")


class OptionBackfillSettlementTests(unittest.TestCase):
    def test_expired_option_is_allowed_only_for_backfill(self):
        function = HTML.split("async function submitOptionTrade", 1)[1].split(
            "function beginPortfolioTradeSharesEdit", 1
        )[0]
        self.assertIn("expiryDate<today&&!backfillTrade", function)
        self.assertIn("补录交易时间不能晚于期权到期日", function)

    def test_expired_backfill_is_settled_immediately(self):
        function = HTML.split("async function submitOptionTrade", 1)[1].split(
            "function beginPortfolioTradeSharesEdit", 1
        )[0]
        self.assertIn('backfillTrade&&expiryDate<today&&modal.type!=="reduce"', function)
        self.assertIn("await fetchHistoricalCloses(option", function)
        self.assertIn("settleExpiredOptionsInPortfolio(updated", function)
        self.assertIn("positionIds:[newPositionId]", function)

    def test_targeted_settlement_records_underlying_price(self):
        function = HTML.split("function settleExpiredOptionsInPortfolio", 1)[1].split(
            "function settleExpiredOptions", 1
        )[0]
        self.assertIn("targetIds.has(position.id)", function)
        self.assertIn("settlementPrices[option.id]", function)
        self.assertIn("underlyingPrice", function)


if __name__ == "__main__":
    unittest.main()
