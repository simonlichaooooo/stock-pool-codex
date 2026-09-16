import json
import pathlib
import subprocess
import unittest


HTML = (pathlib.Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")
# Execute the actual stock-row calculations and formatting, including privacy mode.
BLOCK = HTML.split('            const averageCost = position.averageCost == null', 1)[1].split('            return `<tr', 1)[0]
BLOCK = 'const averageCost = position.averageCost == null' + BLOCK


def render(cost, price=20, shares=100, privacy=False, fx=1):
    script = '''
const position = INPUT;
const state = {portfolioPrivacyMode: PRIVACY};
const base = "USD";
const portfolioFx = () => FX;
const formatPortfolioNumber = value => value.toFixed(2);
const formatWan = value => value.toFixed(2);
BLOCK
console.log(JSON.stringify({profit: holdingProfit, cell: holdingProfitCell, className: holdingProfitClass}));
'''.replace('INPUT', json.dumps(dict(averageCost=cost, latestPrice=price, shares=shares, currency='USD'))).replace('PRIVACY', json.dumps(privacy)).replace('FX', str(fx)).replace('BLOCK', BLOCK)
    return json.loads(subprocess.check_output(['node', '-e', script], text=True))


class PortfolioHoldingProfitTests(unittest.TestCase):
    def test_partial_sale_recovers_more_than_original_cost(self):
        # Buy 200 at 10, then sell 100 at 30: remaining cost = -10.
        cost = (200 * 10 - 100 * 30) / 100
        result = render(cost)
        self.assertEqual(result['profit'], 3000)
        self.assertIn('+3000.00', result['cell'])
        self.assertIn('本金已收回', result['cell'])
        self.assertNotIn('%', result['cell'])
        self.assertEqual(result['className'], 'gain')

    def test_zero_cost_and_currency_conversion(self):
        self.assertEqual(render(0)['profit'], 2000)
        self.assertEqual(render(-10, fx=7)['profit'], 21000)

    def test_privacy_does_not_expose_amount(self):
        for cost in [-10, 0]:
            self.assertEqual(render(cost, privacy=True)['cell'], '本金已收回')
        self.assertEqual(render(10, privacy=True)['cell'], '+100.00%')

    def test_positive_cost_gain_loss_and_flat(self):
        for cost, profit, rate, color in [(10, 1000, '+100.00%', 'gain'), (25, -500, '-20.00%', 'loss'), (20, 0, '0.00%', '')]:
            result = render(cost)
            self.assertEqual(result['profit'], profit)
            self.assertIn(rate, result['cell'])
            self.assertEqual(result['className'], color)

    def test_missing_and_invalid_inputs_still_show_placeholder(self):
        for cost in [None, '', 'invalid']:
            self.assertEqual(render(cost)['cell'], '--')
        for price in [None, 0, 'invalid']:
            self.assertEqual(render(-10, price=price)['cell'], '--')


if __name__ == '__main__':
    unittest.main()
