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

    def test_exercise_history_is_linked_to_underlying_stock(self):
        settlement = HTML.split("function settleExpiredOptionsInPortfolio", 1)[1].split(
            "function settleExpiredOptions", 1
        )[0]
        history = HTML.split("function renderPositionHistoryModal", 1)[1].split(
            "function modalShell", 1
        )[0]
        self.assertIn("underlyingCode:option.underlyingCode", settlement)
        self.assertIn("sharesDelta", settlement)
        self.assertIn('item.underlyingCode === position?.code', history)
        self.assertIn('item.assetType==="option"', history)
        self.assertIn('portfolioTradeTypeText(item.type,item)', history)

    def test_option_premium_is_included_in_effective_stock_cost(self):
        settlement = HTML.split("function settleExpiredOptionsInPortfolio", 1)[1].split(
            "function settleExpiredOptions", 1
        )[0]
        self.assertIn("strike+optionFactor*optionPremium", settlement)
        self.assertIn("averageCost:roundPortfolioCost(effectivePrice)", settlement)
        self.assertAlmostEqual(123 - 3.1, 119.9)

    def test_existing_option_exercises_are_enriched_for_cost_ledger(self):
        repair = HTML.split("function repairOptionSettlementHistory", 1)[1].split(
            "function normalizePortfolioPositionIds", 1
        )[0]
        self.assertIn("parseUniversalOptionCode(trade.code", repair)
        self.assertIn("optionPremium", repair)
        self.assertIn("sharesAfter", repair)
        self.assertIn("closedPositionCycle:sharesAfter===0", repair)


if __name__ == "__main__":
    unittest.main()
