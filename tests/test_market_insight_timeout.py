import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).parents[1]
HTML = (ROOT / 'index.html').read_text()
BLOCK = HTML.split('    function marketInsightCustomMetricField(', 1)[1].split('    const MARKET_OVERVIEW_METRIC_ORDER', 1)[0]
BLOCK = 'function marketInsightCustomMetricField(' + BLOCK


class TimeoutTests(unittest.TestCase):
    def test_timeout_fallback_preserves_filter_semantics_and_atomicity(self):
        script = r'''
const assert = require('node:assert/strict');
const MARKET_INSIGHT_BASE_INDEXES = [{id:'large',code:'HSLI'}];
const conditions = [
  {metric:'speed',span:'30',operator:'gt',value:'0'},
  {metric:'percentile',span:'30',percentileWindow:'2y',operator:'lt',value:'20'},
  {metric:'shortChange',span:'5w',operator:'lt',value:'0'}
];
const state = {marketInsightCustomRequestId:0, marketInsightCustomFilters:[{id:'a',conditions}],marketInsightCustomActiveIds:['a'],marketInsightRows: Array.from({length:85},(_,i)=>({primaryIndexId:'large',rawCode:String(i+1)}))};
const render = () => {};
let calls = [], failBatch = false, cancel = false;
async function supabaseRequest(path, options) {
  calls.push(path);
  if (path.includes('/rpc/')) {
    assert.deepEqual(JSON.parse(options.body).p_index_codes, ['HSLI']);
    throw new Error('{"code":"57014","message":"canceling statement due to statement timeout"}');
  }
  assert.ok(path.includes('current_hk_market_insight_filter_universe'));
  assert.ok(path.includes('limit=40'));
  if (failBatch && calls.length === 3) throw new Error('network failure');
  const codes = path.match(/stock_code=in\.\(([^)]+)\)/)[1].split(',');
  assert.ok(codes.length <= 40);
  if (cancel) state.marketInsightCustomRequestId++;
  return codes.map(stock_code=>({index_code:'HSLI',stock_code,bias_speed_30w_pct:1,percentile_30w_2y:10,short_change_5w_pct:stock_code==='00002'?null:stock_code==='00003'?1:-1}));
}
BLOCK
(async()=>{
  await loadMarketInsightCustomMetrics();
  assert.equal(calls.length,4);
  assert.equal(state.marketInsightCustomHistory,true);
  assert.equal(state.marketInsightRows.filter(r=>r.customFilterMatch).length,83);
  assert.equal(state.marketInsightRows[1].customFilterMissingConditions,1);
  assert.equal(state.marketInsightRows[2].customFilterMissingConditions,0);
  assert.equal(state.marketInsightCustomError,'');
  const before = state.marketInsightRows;
  state.marketInsightCustomHistory=null; calls=[]; failBatch=true;
  await loadMarketInsightCustomMetrics();
  assert.equal(state.marketInsightRows,before);
  assert.equal(state.marketInsightCustomHistory,null);
  assert.ok(state.marketInsightCustomError.includes('network failure'));
  failBatch=false; cancel=true; calls=[];
  await loadMarketInsightCustomMetrics();
  assert.equal(state.marketInsightRows,before);
  assert.equal(state.marketInsightCustomHistory,null);
  const row={index_code:'HSLI',stock_code:'00001',bias_10w_pct:0};
  const monthly=new Map([['HSLI:00001:2026-09-01',5]]);
  const extra=[{metric:'bias',span:'10',operator:'eq',value:'0.004'}, {metric:'excess',span:'specific',month:'2026-09',operator:'gt',value:'4'}];
  assert.equal(evaluateMarketInsightCustomConditions(row,extra,monthly,extra.map(marketInsightCustomMonth)).matches,true);
  extra[0].value='0.006';
  assert.equal(evaluateMarketInsightCustomConditions(row,extra,monthly,extra.map(marketInsightCustomMonth)).matches,false);
  extra[0].value='';
  assert.equal(evaluateMarketInsightCustomConditions(row,extra,monthly,extra.map(marketInsightCustomMonth)).missing_condition_count,1);
  assert.equal(marketInsightCustomMonth({metric:'excess',span:'specific',month:'2026-13'}),null);
})().catch(error=>{console.error(error);process.exitCode=1});
'''.replace('BLOCK', BLOCK)
        subprocess.run(['node', '-e', script], check=True)

    def test_all_inline_scripts_parse(self):
        import re
        for script in re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>', HTML, re.S):
            subprocess.run(['node', '--check'], input=script, text=True, check=True)


if __name__ == '__main__':
    unittest.main()
