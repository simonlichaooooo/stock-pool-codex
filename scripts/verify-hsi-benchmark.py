#!/usr/bin/env python3
"""Read-only verification of persisted HSI benchmark returns."""
import importlib.util
from pathlib import Path
from datetime import date, timedelta

spec = importlib.util.spec_from_file_location('ingest', Path(__file__).with_name('market-data-ingest.py'))
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)
client = ingest.SupabaseRest()


def read(table, query):
    return client._request('GET', f'{table}?{query}')


def close(actual, expected):
    assert actual is not None and abs(float(actual) - expected) < 0.00001, (actual, expected)


weekly = 'hk_market_insight_metrics_weekly'
monthly = 'hk_market_insight_monthly_returns'
hsi = read('market_index_weekly_prices', 'index_code=eq.HSI&select=week_date,close_price&order=week_date.desc&limit=1')[0]
assert ingest.week_key(hsi['week_date']) == ingest.latest_completed_week_date().isoformat(), hsi
row = read(weekly, 'stock_code=eq.00317&select=*&order=week_date.desc&limit=1')[0]
assert row['week_date'] == hsi['week_date'] and row['index_return_quality'] == 'official_hsi', row
start = (date.fromisoformat(row['week_date']) - timedelta(weeks=5)).isoformat()
prior = read(weekly, f"stock_code=eq.00317&index_code=eq.{row['index_code']}&week_date=eq.{start}&select=close_price")[0]
prior_hsi = read('market_index_weekly_prices', f'index_code=eq.HSI&week_date=eq.{start}&select=close_price')[0]
stock_return = (float(row['close_price']) / float(prior['close_price']) - 1) * 100
index_return = (float(hsi['close_price']) / float(prior_hsi['close_price']) - 1) * 100
close(row['five_week_return_pct'], stock_return)
close(row['index_five_week_return_pct'], index_return)
close(row['excess_five_week_return_pct'], stock_return - index_return)
month = read(monthly, 'stock_code=eq.00317&select=*&order=month_start.desc&limit=1')[0]
assert month['month_start'][:7] == ingest.current_hong_kong_month(), month
assert month['index_return_quality'] == 'official_hsi', month
close(month['excess_return_pct'], float(month['stock_return_pct']) - float(month['index_return_pct']))
for table, field in [(weekly, 'excess_one_week_return_pct'), (weekly, 'excess_five_week_return_pct'), (monthly, 'excess_return_pct')]:
    assert not read(table, f'index_return_quality=neq.official_hsi&{field}=not.is.null&select=stock_code&limit=1'), (table, field)
print(f"::notice title=HSI benchmark verified::00317 date={row['week_date']}; stock5w={stock_return:.8f}%; HSI5w={index_return:.8f}%; excess5w={stock_return-index_return:.8f}%; month={month['month_start']}; monthlyExcess={month['excess_return_pct']}%; no legacy excess values remain")
