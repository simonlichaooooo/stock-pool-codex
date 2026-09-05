import pathlib
import unittest


HTML = (pathlib.Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")


class PortfolioCostCycleTests(unittest.TestCase):
    def test_option_premium_flows_into_stock_cost_ledger_once(self):
        entry = HTML.split("function portfolioCostLedgerEntry", 1)[1].split(
            "function portfolioCostLedger", 1
        )[0]
        self.assertIn("cashOutflowSign", entry)
        self.assertIn("contracts*multiplier*premium", entry)
        self.assertIn("sharesDelta*Number(trade.strikePrice", entry)

    def test_futu_example_keeps_premiums_separate_from_both_assignments(self):
        diluted_cost = (
            111.35 * 300
            - 3.45 * 300
            - 123 * 300
            - 3.10 * 300
            + 123 * 300
        ) / 300
        self.assertAlmostEqual(diluted_cost, 104.80)

    def test_cost_continues_across_zero_until_user_completes_cycle(self):
        ledger = HTML.split("function portfolioCostLedger(portfolio", 1)[1].split(
            "function recalculatePortfolioCostBases", 1
        )[0]
        self.assertIn("netInvested+=entry.costDelta", ledger)
        self.assertIn("if(trade.completesCycle){shares=0;netInvested=0", ledger)
        self.assertNotIn("if(!shares)", ledger)

    def test_manual_full_sale_asks_whether_to_complete_cycle(self):
        submit = HTML.split("async function submitPositionTrade", 1)[1].split(
            "function submitOptionDirectionEdit", 1
        )[0]
        self.assertIn('fullySold=modal.type==="reduce"&&shares===Number(stock.shares)', submit)
        self.assertIn("是否同时完结当前成本周期", submit)
        self.assertIn("completesCycle", submit)

    def test_called_away_history_offers_complete_cycle_action(self):
        history = HTML.split("function renderPositionHistoryModal", 1)[1].split(
            "function modalShell", 1
        )[0]
        self.assertIn('data-action="completePositionCycle"', history)
        self.assertIn("完结周期", history)
        self.assertIn("周期已完结", history)

    def test_futu_cycle_start_is_migrated_for_every_portfolio(self):
        migration = HTML.split("function migrateFutuCostCycleStart", 1)[1].split(
            "function normalizePortfolioPositionIds", 1
        )[0]
        self.assertIn('portfolioCostCycleKey("US","FUTU")', migration)
        self.assertIn('costCycleStarts[key]="2026-08-19"', migration)


if __name__ == "__main__":
    unittest.main()
