#!/usr/bin/env python3
"""Verify the expanded Stock Connect market-insight universe after backfill."""
import importlib.util
import json
from pathlib import Path

root = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("ingest", root / "scripts" / "market-data-ingest.py")
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)
client = ingest.SupabaseRest()


def read(table, query):
    return client._request("GET", f"{table}?{query}")


snapshot = json.loads((root / "data" / "market-insights.json").read_text())
scope = snapshot["constituents"]["indexes"]["stockconnect"]
codes = {ingest.normalize_code(member["code"]) for member in scope["members"]}
assert len(codes) >= 100, len(codes)
assert "01330" in codes, "01330 missing from Stock Connect snapshot"

weekly = read(
    "hk_market_insight_metrics_weekly",
    "index_code=eq.STOCK_CONNECT&stock_code=eq.01330&select=week_date,index_return_quality,excess_five_week_return_pct&order=week_date.asc",
)
monthly = read(
    "hk_market_insight_monthly_returns",
    "index_code=eq.STOCK_CONNECT&stock_code=eq.01330&select=month_start,index_return_quality,excess_return_pct&order=month_start.asc",
)
holdings = read(
    "hk_stock_connect_holdings_daily",
    "stock_code=eq.01330&completeness=eq.official_aggregate&select=holding_date,total_holding_shares&order=holding_date.asc",
)
assert len(weekly) >= 100, len(weekly)
assert len(monthly) >= 24, len(monthly)
assert holdings, "01330 has no official Stock Connect history"
assert weekly[-1]["index_return_quality"] == "official_hsi"
assert monthly[-1]["index_return_quality"] == "official_hsi"
print(
    "::notice title=Stock Connect universe verified::"
    f"scope={len(codes)} stocks; 01330 weekly={len(weekly)} ({weekly[0]['week_date']}..{weekly[-1]['week_date']}); "
    f"monthly={len(monthly)} ({monthly[0]['month_start']}..{monthly[-1]['month_start']}); "
    f"holdings={len(holdings)} ({holdings[0]['holding_date']}..{holdings[-1]['holding_date']})"
)
