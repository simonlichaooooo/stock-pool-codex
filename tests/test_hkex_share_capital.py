import importlib.util
import pathlib
import unittest
from unittest.mock import patch


SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "hkex-share-capital.py"
SPEC = importlib.util.spec_from_file_location("hkex_share_capital", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ParseOfficialShareCapitalTest(unittest.TestCase):
    def test_search_result_uses_hkex_headline_category(self):
        html = b'''<tr><td class="release-time">06/01/2023 18:50</td><td>
        <div class="headline">Monthly Returns<br/></div><div class="doc-link">
        <a href="/listedco/listconews/sehk/2023/0106/2023010601199.pdf">
        Monthly Return of Equity Issuer for December 2022</a></div></td></tr>'''
        with patch.object(MODULE, "request_bytes", return_value=html):
            rows = MODULE.search_filings(7609, MODULE.date(2023, 1, 1), MODULE.date(2023, 1, 31))
        self.assertEqual(rows[0]["document_id"], "2023010601199")
        self.assertIn("Monthly Returns", rows[0]["title"])

    def test_old_monthly_return(self):
        text = """
        Monthly Return of Equity Issuer
        For the month ended: 31 December 2022
        II. Movements in Issued Shares
        Type of shares Ordinary shares Class of shares Not applicable Listed on SEHK
        Stock code 00700
        Balance at close of the month 9,568,738,935
        III. Details of Movements
        """
        row = MODULE.parse_monthly(text, "00700")
        self.assertEqual(row["effective_date"].isoformat(), "2022-12-31")
        self.assertEqual(row["issued_shares"], 9568738935)
        self.assertEqual(row["treasury_shares"], 0)

    def test_new_monthly_return_with_treasury(self):
        text = """
        For the month ended: 31 July 2026
        II. Movements in Issued Shares and/or Treasury Shares
        Class of shares Ordinary shares Type of shares Not applicable Listed on SEHK
        Stock code (if listed) 00700
        Balance at close of the month 9,082,721,689 12,000 9,082,733,689
        III. Details of Movements
        """
        row = MODULE.parse_monthly(text, "00700")
        self.assertEqual(row["issued_shares_ex_treasury"], 9082721689)
        self.assertEqual(row["treasury_shares"], 12000)
        self.assertEqual(row["issued_shares"], 9082733689)

    def test_old_next_day_disclosure(self):
        text = """
        Type of shares Ordinary shares Class of shares Not applicable Listed on SEHK
        Stock code (if listed) 00700
        Closing balance as at (Note 8) 19 January 2023 9,568,209,666
        """
        row = MODULE.parse_next_day(text, "00700")
        self.assertEqual(row["effective_date"].isoformat(), "2023-01-19")
        self.assertEqual(row["issued_shares"], 9568209666)

    def test_new_next_day_disclosure_with_treasury(self):
        text = """
        Class of shares Ordinary shares Type of shares Not applicable Listed on SEHK
        Stock code (if listed) 00700
        Closing balance as at (Notes 5 and 6) 06 July 2026 9,092,370,719 0 9,092,370,719
        """
        row = MODULE.parse_next_day(text, "00700")
        self.assertEqual(row["effective_date"].isoformat(), "2026-07-06")
        self.assertEqual(row["issued_shares_ex_treasury"], 9092370719)

    def test_wvr_next_day_disclosure_with_long_event_table(self):
        text = """
        Class of shares WVR ordinary shares Type of shares B Listed on the Exchange Yes
        Stock code (if listed) 01024 Description
        """ + ("event details\n" * 450) + """
        Closing balance as at (Notes 5 and 6) 19 January 2026 3,658,873,609 0 3,658,873,609
        """
        row = MODULE.parse_next_day(text, "01024")
        self.assertEqual(row["effective_date"].isoformat(), "2026-01-19")
        self.assertEqual(row["issued_shares"], 3658873609)
        self.assertEqual(row["share_class"], "WVR ordinary shares")

    def test_rejects_inconsistent_totals(self):
        text = """
        For the month ended: 31 July 2026
        II. Movements in Issued Shares and/or Treasury Shares
        Class of shares Ordinary shares Listed on SEHK
        Stock code (if listed) 00700
        Balance at close of the month 100 20 999
        III. Details of Movements
        """
        with self.assertRaises(ValueError):
            MODULE.parse_monthly(text, "00700")


if __name__ == "__main__":
    unittest.main()
