import json
import pathlib
import subprocess
import unittest


HTML = (pathlib.Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")
SUBMIT = "async function submitPositionTrade" + HTML.split(
    "async function submitPositionTrade", 1
)[1].split("function submitOptionDirectionEdit", 1)[0]


class PositionEditCostTests(unittest.TestCase):
    def test_edit_input_accepts_negative_cost(self):
        edit = HTML.split('if (modal.type === "edit") return modalShell("编辑持仓"', 1)[1].split(
            'const stockMarket =', 1
        )[0]
        cost_input = edit.split('<span>摊薄成本</span>', 1)[1].split('</label>', 1)[0]
        self.assertIn('name="price" type="number"', cost_input)
        self.assertIn('${costInputAttrs()}', cost_input)
        self.assertNotIn('min="0"', cost_input)

    def test_edit_saves_negative_and_zero_cost_without_relaxing_trade_prices(self):
        script = """
const submit = SOURCE;
const position = {id: 'holding', shares: 2000, averageCost: -4.1401};
const portfolio = {positions: [position]};
const state = {portfolioModal: null};
let error = null;
let saved = null;
let closed = false;
const activePortfolio = () => portfolio;
const showPortfolioError = message => { error = message; };
const parsePositionTargetWeight = () => 3;
const normalizedPositionTradePlan = () => ({buy: [], sell: []});
const roundPortfolioCost = value => Number(Number(value).toFixed(4));
const updateActivePortfolio = updater => { saved = updater(portfolio); };
const closePortfolioModal = () => { closed = true; };
class FormData {
  constructor(form) { this.values = form.values; }
  get(name) { return this.values[name] ?? null; }
  has(name) { return name in this.values; }
}
async function check(type, price) {
  state.portfolioModal = {type, position, tags: []};
  error = null; saved = null; closed = false;
  const form = {values: {price, shares: '2000', targetWeight: '3'}, querySelectorAll: () => []};
  await submit({preventDefault() {}, currentTarget: form});
  return {error, cost: saved?.positions[0].averageCost ?? null, closed};
}
(async () => {
  const results = [];
  for (const [type, price] of [['edit', '-4.1401'], ['edit', '0'], ['edit', ''], ['add', '-1'], ['add', '0']]) {
    results.push(await check(type, price));
  }
  console.log(JSON.stringify(results));
})().catch(error => { console.error(error); process.exit(1); });
""".replace("SOURCE", SUBMIT)
        results = json.loads(subprocess.check_output(["node", "-e", script], text=True))
        self.assertEqual(results[:2], [
            {"error": None, "cost": -4.1401, "closed": True},
            {"error": None, "cost": 0, "closed": True},
        ])
        for result in results[2:]:
            self.assertEqual(result["error"], "请输入有效价格。")
            self.assertIsNone(result["cost"])
            self.assertFalse(result["closed"])


if __name__ == "__main__":
    unittest.main()
