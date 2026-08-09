import importlib.util
import pathlib
import unittest


SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "market-data-ingest.py"
SPEC = importlib.util.spec_from_file_location("market_data_ingest", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def row(code, shares, ratio="1.25%"):
    return f'''<tr>
      <td class="col-stock-code"><div class="mobile-list-body">{code}</div></td>
      <td class="col-stock-name"><div class="mobile-list-body">Stock {code}</div></td>
      <td class="col-shareholding"><div class="mobile-list-body">{shares}</div></td>
      <td class="col-shareholding-percent"><div class="mobile-list-body">{ratio}</div></td>
    </tr>'''


class HkexSouthboundTest(unittest.TestCase):
    def test_parse_and_build_official_aggregate_rows(self):
        page = '''
          <input name="originalShareholdingDate" value="2026/08/07" />
          <input name="alertMsg" value="" />
        ''' + "".join(row(code, f"{code * 1000:,}") for code in range(1, 501))
        actual_date, source = MODULE.parse_hkex_southbound_page(page)
        self.assertEqual(actual_date.isoformat(), "2026-08-07")
        self.assertEqual(source["00257"]["shares"], 257000)
        holdings, securities, completeness = MODULE.hkex_stock_connect_rows(actual_date, source)
        item = next(value for value in holdings if value["stock_code"] == "00257")
        self.assertEqual(completeness, "official_aggregate")
        self.assertEqual(item["total_holding_shares"], 257000)
        self.assertIsNone(item["sh_holding_shares"])
        self.assertIsNone(item["sz_holding_shares"])
        self.assertEqual(len(securities), 500)

    def test_rejects_unavailable_date(self):
        page = '''
          <input name="originalShareholdingDate" value="2024/08/16" />
          <input name="alertMsg" value="Your input date is invalid. Please re-enter." />
        '''
        with self.assertRaisesRegex(ValueError, "date unavailable"):
            MODULE.parse_hkex_southbound_page(page)


if __name__ == "__main__":
    unittest.main()
