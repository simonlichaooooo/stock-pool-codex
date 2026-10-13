import importlib.util
import pathlib
import unittest
from unittest import mock
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location('hsi_ingest', ROOT / 'scripts/market-data-ingest.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

class HsiBenchmarkTests(unittest.TestCase):
    def test_same_stock_has_identical_excess_across_groups(self):
        prices = [((date(2026, 8, 21) + timedelta(weeks=i)).isoformat(), 100+i*2) for i in range(8)]
        hsi = [(day, 200+i) for i,(day,_) in enumerate(prices)]
        returns = {p: M.calendar_week_returns(hsi,p) for p in (1,5)}
        rows = [M.metric_rows(code,'00317',prices,returns,'official_hsi')[-1] for code in ('HSTECH','HSLI','HSMI','HSSI')]
        for row in rows:
            self.assertEqual(row['excess_five_week_return_pct'],rows[0]['excess_five_week_return_pct'])
            self.assertEqual(row['index_return_quality'],'official_hsi')
            self.assertIn('calculated_at',row)
        self.assertAlmostEqual(rows[0]['excess_five_week_return_pct'], (114/104-1)*100-(207/202-1)*100)

    def test_missing_weeks_do_not_extend_five_week_horizon(self):
        prices=[('2026-07-31',100),('2026-08-07',101),('2026-08-14',102),('2026-08-21',103),('2026-08-28',104),('2026-09-11',110)]
        self.assertAlmostEqual(M.calendar_week_returns(prices,5)['2026-09-11'],(110/101-1)*100)
        self.assertNotIn('2026-09-11',M.calendar_week_returns([p for p in prices if p[0]!='2026-08-07'],5))

    def test_holiday_dates_use_same_calendar_week(self):
        self.assertEqual(M.week_key('2026-10-01'), '2026-10-02')

    def test_ingestion_fetches_hsi_once_and_never_group_benchmarks(self):
        import json, tempfile
        prices=[((date(2026,8,21)+timedelta(weeks=i)).isoformat(),100+i) for i in range(8)]
        indexes={code:{'code':code,'quoteId':'must-not-fetch','members':[{'code':'00317'}]} for code in ('HSTECH','HSSI')}
        with tempfile.NamedTemporaryFile(mode='w',suffix='.json') as f:
            json.dump({'constituents':{'indexes':indexes}},f);f.flush()
            with mock.patch.object(M,'MARKET_INSIGHTS_FILE',f.name), mock.patch.object(M,'fetch_hsi_prices',return_value=prices) as hsi, mock.patch.object(M,'fetch_weekly_prices',return_value=prices), mock.patch.object(M,'fetch_index_weekly_prices',side_effect=AssertionError('old benchmark')):
                client=mock.Mock()
                client.upsert.side_effect=lambda table,rows,*a,**kw:len(rows)
                M.ingest_weekly_metrics(client)
                hsi.assert_called_once_with('week')
                rows=next(c.args[1] for c in client.upsert.call_args_list if c.args[0]=='hk_market_insight_metrics_weekly')
                self.assertTrue(all(r['index_return_quality']=='official_hsi' for r in rows))
                index_rows=next(c.args[1] for c in client.upsert.call_args_list if c.args[0]=='market_index_weekly_prices')
                self.assertEqual({r['index_code'] for r in index_rows},{'HSI'})
            with mock.patch.object(M,'MARKET_INSIGHTS_FILE',f.name), mock.patch.object(M,'fetch_hsi_prices',side_effect=RuntimeError('unavailable')), mock.patch.object(M,'fetch_weekly_prices') as stocks:
                with self.assertRaises(RuntimeError): M.ingest_weekly_metrics(mock.Mock())
                stocks.assert_not_called()

    def test_monthly_ingestion_uses_hsi_in_every_group(self):
        import json, tempfile
        prices=[('2026-08-31',100),('2026-09-30',110),('2026-10-13',120)]
        hsi_prices=[('2026-08-31',200),('2026-09-30',190),('2026-10-13',195)]
        indexes={code:{'code':code,'members':[{'code':'00317'}]} for code in ('HSLI','HSSI')}
        with tempfile.NamedTemporaryFile(mode='w',suffix='.json') as f:
            json.dump({'constituents':{'indexes':indexes}},f);f.flush()
            with mock.patch.object(M,'MARKET_INSIGHTS_FILE',f.name), mock.patch.object(M,'fetch_hsi_prices',return_value=hsi_prices) as hsi, mock.patch.object(M,'fetch_monthly_prices',return_value=prices):
                client=mock.Mock(); client.upsert.side_effect=lambda table,rows,*a,**kw:len(rows)
                M.ingest_monthly_metrics(client)
                hsi.assert_called_once_with('month')
                rows=next(c.args[1] for c in client.upsert.call_args_list if c.args[0]=='hk_market_insight_monthly_returns')
                self.assertTrue(all(r['index_return_quality']=='official_hsi' for r in rows))
                latest=[r for r in rows if r['month_start']=='2026-10-01']
                self.assertEqual(len(latest),2)
                self.assertAlmostEqual(latest[0]['excess_return_pct'],(120/110-1)*100-(195/190-1)*100)
                self.assertEqual(latest[0]['excess_return_pct'],latest[1]['excess_return_pct'])

    def test_hsi_loader_excludes_incomplete_week_and_rejects_stale(self):
        prices=[[(date(2026,8,21)+timedelta(weeks=i)).isoformat(),'0',str(100+i)] for i in range(8)]
        prices.append(['2026-10-13','0','110'])
        with mock.patch.object(M,'latest_completed_week_date',return_value=date(2026,10,9)), mock.patch.object(M,'json_request',return_value={'data':{'hkHSI':{'week':prices}}}):
            self.assertEqual(M.fetch_hsi_prices('week')[-1][0],'2026-10-09')
        with mock.patch.object(M,'latest_completed_week_date',return_value=date(2026,10,16)), mock.patch.object(M,'json_request',return_value={'data':{'hkHSI':{'week':prices[:-1]}}}), mock.patch.object(M.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'stale'): M.fetch_hsi_prices('week')

    def test_date_cell_and_old_benchmark_hidden(self):
        import subprocess
        html=(ROOT/'index.html').read_text()
        fn='function marketInsightExcessCell('+html.split('function marketInsightExcessCell(',1)[1].split('    const MARKET_INSIGHT_CUSTOM_METRICS',1)[0]
        subprocess.run(['node','-e', 'const escapeHtml=x=>x; const marketInsightRuleStar=()=>"";'+fn+';require("node:assert/strict").ok(marketInsightExcessCell(3,false,"2026-10-09").includes("截至 2026-10-09"));'],check=True)
        self.assertIn('metric.index_return_quality === "official_hsi"',html)
        self.assertNotIn('rows.find((row) => Number.isFinite(row.indexFiveWeekReturn))',html)

if __name__=='__main__': unittest.main()
