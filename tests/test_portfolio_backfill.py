import pathlib
import unittest


HTML = (pathlib.Path(__file__).parents[1] / "index.html").read_text(encoding="utf-8")


class PortfolioBackfillTests(unittest.TestCase):
    def test_historical_closes_uses_cross_origin_compatible_jsonp(self):
        function = HTML.split("async function fetchHistoricalCloses", 1)[1].split(
            "async function revisedNavForTrades", 1
        )[0]
        self.assertIn("const json = await jsonp(url);", function)
        self.assertNotIn("fetchWithTimeout(url", function)
        self.assertNotIn("response.json()", function)


if __name__ == "__main__":
    unittest.main()
