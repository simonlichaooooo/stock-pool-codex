#!/usr/bin/env python3
"""Ingest official HSCI, SFC short-position and Southbound holding data into Supabase."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from xml.etree import ElementTree


HSCI_URL = "https://www.hsi.com.hk/data/eng/rt/index-series/hsci/constituents.do"
SFC_PAGE_URL = "https://www.sfc.hk/en/Regulatory-functions/Market/Short-position-reporting/Aggregated-reportable-short-positions-of-specified-shares"
SSE_PAGE_URL = "https://star.sse.com.cn/services/hkexsc/ggtscsj/ggtzqcysl/"
SSE_API_URL = "https://query.sse.com.cn/sseQuery/commonSoaQuery.do"
SZSE_PAGE_URL = "https://www.szse.cn/szhk/szhkshareholding/hkholdamount/index.html"
SZSE_XLSX_URL = "https://www.szse.cn/api/report/ShowReport"
SSE_PUBLIC_START = date(2024, 8, 19)
USER_AGENT = "Mozilla/5.0 (compatible; stock-pool-market-data/1.0)"
XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
MARKET_INSIGHTS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "market-insights.json")
METRIC_START = date(2023, 1, 1)


def http_request(url: str, *, headers: dict[str, str] | None = None, timeout: int = 45) -> bytes:
    request_headers = {"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def json_request(url: str, **kwargs):
    return json.loads(http_request(url, **kwargs).decode("utf-8-sig"))


def normalize_code(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        raise ValueError(f"Invalid HK stock code: {value!r}")
    return digits[-5:].zfill(5)


def integer(value: object) -> int:
    cleaned = str(value or "").replace(",", "").strip()
    if not cleaned:
        return 0
    return int(Decimal(cleaned))


def date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


class SupabaseRest:
    def __init__(self, *, required: bool = True):
        self.base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if required and (not self.base_url or not self.key):
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

    def _request(self, method: str, path: str, payload=None, *, prefer: str | None = None):
        url = f"{self.base_url}/rest/v1/{path}"
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
                return json.loads(data) if data else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase {method} {path} failed: {error.code} {detail}") from error

    def upsert(self, table: str, rows: list[dict], conflict: str, chunk_size: int = 500) -> int:
        written = 0
        # PostgREST requires every object in one bulk request to expose the same keys.
        # Exchange rows can legitimately have only a Chinese name or both names, so
        # group them by shape before chunking and preserve omitted fields on upsert.
        groups: dict[tuple[str, ...], list[dict]] = {}
        for row in rows:
            groups.setdefault(tuple(sorted(row)), []).append(row)
        for group in groups.values():
            for offset in range(0, len(group), chunk_size):
                chunk = group[offset : offset + chunk_size]
                path = f"{table}?on_conflict={urllib.parse.quote(conflict)}"
                self._request("POST", path, chunk, prefer="resolution=merge-duplicates,return=minimal")
                written += len(chunk)
        return written

    def insert_run(self, dataset: str, started_at: str, start: date | None, end: date | None,
                   status: str, rows_written: int, details: dict):
        payload = [{
            "dataset": dataset,
            "range_start": start.isoformat() if start else None,
            "range_end": end.isoformat() if end else None,
            "status": status,
            "rows_written": rows_written,
            "details": details,
            "started_at": started_at,
        }]
        self._request("POST", "market_data_ingestion_runs", payload, prefer="return=minimal")


def fetch_hsci() -> tuple[date, list[dict]]:
    payload = json_request(HSCI_URL)
    series = next(item for item in payload["indexSeriesList"] if item["seriesCode"] == "hsci")
    index = next(item for item in series["indexList"] if item["indexName"] == "Hang Seng Composite Index")
    snapshot = datetime.strptime(series["constituentsDate"][:10], "%Y-%m-%d").date()
    constituents = []
    for row in index["constituentContent"]:
        if row.get("isDummy") == "Y":
            continue
        constituents.append({
            "stock_code": normalize_code(row["code"]),
            "name_en": row.get("constituentName") or None,
        })
    if len(constituents) < 400:
        raise RuntimeError(f"HSCI source returned too few constituents: {len(constituents)}")
    return snapshot, constituents


def sync_hsci(client: SupabaseRest, *, dry_run: bool = False) -> int:
    started = datetime.now(timezone.utc).isoformat()
    snapshot, constituents = fetch_hsci()
    if dry_run:
        print(f"HSCI {snapshot}: {len(constituents)} constituents")
        return len(constituents)
    securities = [{"stock_code": row["stock_code"], "name_en": row["name_en"]} for row in constituents]
    client.upsert("market_securities", securities, "stock_code")
    rows = [{
        "index_code": "HSCI",
        "snapshot_date": snapshot.isoformat(),
        "stock_code": row["stock_code"],
        "constituent_name": row["name_en"],
        "source_url": HSCI_URL,
    } for row in constituents]
    written = client.upsert("market_index_constituents", rows, "index_code,snapshot_date,stock_code")
    client.insert_run("hsci_constituents", started, snapshot, snapshot, "success", written,
                      {"constituent_count": len(rows), "source_url": HSCI_URL})
    print(f"Stored HSCI {snapshot}: {written} constituents")
    return written


def sfc_csv_links() -> list[tuple[date, str]]:
    page = http_request(SFC_PAGE_URL).decode("utf-8", errors="replace")
    pattern = re.compile(r'''href=["']([^"']*Short_Position_Reporting_Aggregated_Data_(\d{8})\.csv[^"']*)["']''', re.I)
    links: dict[date, str] = {}
    for raw_url, yyyymmdd in pattern.findall(page):
        report_date = datetime.strptime(yyyymmdd, "%Y%m%d").date()
        links[report_date] = urllib.parse.urljoin(SFC_PAGE_URL, html.unescape(raw_url))
    if not links:
        raise RuntimeError("SFC page did not expose historical CSV links")
    return sorted(links.items())


def parse_sfc_csv(content: bytes, fallback_date: date, source_url: str) -> tuple[list[dict], list[dict]]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    next(reader, None)
    positions: list[dict] = []
    securities: dict[str, dict] = {}
    for values in reader:
        if len(values) < 5 or not any(value.strip() for value in values):
            continue
        code = normalize_code(values[1])
        name = values[2].strip() or None
        try:
            report_date = datetime.strptime(values[0].strip(), "%Y-%m-%d").date()
        except ValueError:
            report_date = fallback_date
        securities[code] = {"stock_code": code, "name_en": name}
        positions.append({
            "stock_code": code,
            "report_date": report_date.isoformat(),
            "short_shares": integer(values[3]),
            "short_value_hkd": str(Decimal(values[4].replace(",", "").strip() or "0")),
            "ratio_quality": "missing_denominator",
            "source_url": source_url,
        })
    return positions, list(securities.values())


def ingest_short_positions(client: SupabaseRest, start: date, end: date, *, latest_only: bool,
                           pause: float, dry_run: bool = False) -> int:
    started = datetime.now(timezone.utc).isoformat()
    selected = [(d, u) for d, u in sfc_csv_links() if start <= d <= end]
    if latest_only and selected:
        selected = [selected[-1]]
    if not selected:
        raise RuntimeError(f"No SFC reports found from {start} through {end}")
    total = 0
    report_counts: dict[str, int] = {}
    for index, (report_date, url) in enumerate(selected, 1):
        positions, securities = parse_sfc_csv(http_request(url), report_date, url)
        if len(positions) < 100:
            raise RuntimeError(f"SFC {report_date} returned too few rows: {len(positions)}")
        if not dry_run:
            client.upsert("market_securities", securities, "stock_code")
            total += client.upsert("hk_short_positions_weekly", positions, "stock_code,report_date")
        else:
            total += len(positions)
        report_counts[report_date.isoformat()] = len(positions)
        print(f"SFC {report_date}: {len(positions)} rows ({index}/{len(selected)})")
        if pause and index < len(selected):
            time.sleep(pause)
    if not dry_run:
        client.insert_run("short_positions", started, selected[0][0], selected[-1][0], "success", total,
                          {"reports": len(selected), "report_counts": report_counts, "source_url": SFC_PAGE_URL})
    return total


def xlsx_rows(content: bytes) -> list[list[str]]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{XLSX_NS}si"):
                shared.append("".join(node.text or "" for node in item.iter(f"{XLSX_NS}t")))
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet.iter(f"{XLSX_NS}row"):
            cells: dict[int, str] = {}
            for cell in row.findall(f"{XLSX_NS}c"):
                reference = cell.attrib.get("r", "A1")
                column_letters = re.match(r"[A-Z]+", reference).group(0)
                column = 0
                for letter in column_letters:
                    column = column * 26 + ord(letter) - ord("A") + 1
                value = ""
                inline = cell.find(f"{XLSX_NS}is/{XLSX_NS}t")
                raw = cell.find(f"{XLSX_NS}v")
                if inline is not None:
                    value = inline.text or ""
                elif raw is not None:
                    value = raw.text or ""
                    if cell.attrib.get("t") == "s":
                        value = shared[int(value)]
                cells[column - 1] = value
            if cells:
                width = max(cells) + 1
                rows.append([cells.get(index, "") for index in range(width)])
        return rows


def fetch_szse(day: date) -> dict[str, dict]:
    params = urllib.parse.urlencode({
        "SHOWTYPE": "xlsx",
        "CATALOGID": "SGT_GGTCGSL",
        "TABKEY": "tab1",
        "txtDate": day.isoformat(),
        "txtZqdm": "",
    })
    content = http_request(f"{SZSE_XLSX_URL}?{params}", headers={"Referer": SZSE_PAGE_URL})
    rows = xlsx_rows(content)
    result = {}
    for values in rows[1:]:
        if len(values) < 3 or not values[0].strip():
            continue
        code = normalize_code(values[0])
        result[code] = {"shares": integer(values[2]), "name_zh": values[1].strip() or None}
    return result


def fetch_sse(day: date) -> dict[str, dict]:
    if day < SSE_PUBLIC_START:
        return {}
    params = urllib.parse.urlencode({
        "sqlId": "FW_HGTZL_GGTSCSJ_GGTZQCYSL",
        "tradeDate": day.strftime("%Y%m%d"),
        "pageHelp.pageSize": "2000",
        "pageHelp.pageNo": "1",
        "pageHelp.beginPage": "1",
        "pageHelp.endPage": "1",
    })
    payload = json_request(f"{SSE_API_URL}?{params}", headers={"Referer": SSE_PAGE_URL})
    rows = (payload.get("pageHelp") or {}).get("data") or []
    result = {}
    for row in rows:
        code = normalize_code(row["secCode"])
        result[code] = {
            "shares": integer(row.get("totalHoldings")),
            "name_zh": row.get("cnAbbr") or None,
            "name_en": row.get("enAbbr") or None,
        }
    return result


def stock_connect_rows(day: date, sh: dict[str, dict], sz: dict[str, dict]) -> tuple[list[dict], list[dict], str | None]:
    sh_available = len(sh) >= 100
    sz_available = len(sz) >= 100
    if not sh_available and not sz_available:
        return [], [], None
    # 自上交所逐股数据公开起点后，只有两侧都到齐才落库，避免源站短暂迟发
    # 时把已经完整的记录降级覆盖成 partial。滚动回看会在下一次自动补齐。
    if day >= SSE_PUBLIC_START and not (sh_available and sz_available):
        return [], [], None
    if sh_available and sz_available:
        completeness = "complete"
    elif sh_available:
        completeness = "partial_sh"
    else:
        completeness = "partial_sz"
    securities = {}
    holdings = []
    for code in sorted(set(sh) | set(sz)):
        sh_row = sh.get(code) or {}
        sz_row = sz.get(code) or {}
        name_zh = sh_row.get("name_zh") or sz_row.get("name_zh")
        name_en = sh_row.get("name_en") or sz_row.get("name_en")
        securities[code] = {key: value for key, value in {
            "stock_code": code, "name_zh": name_zh, "name_en": name_en,
        }.items() if value is not None}
        row = {
            "stock_code": code,
            "holding_date": day.isoformat(),
            "sh_holding_shares": sh_row.get("shares") if sh_available else None,
            "sz_holding_shares": sz_row.get("shares") if sz_available else None,
            "total_holding_shares": None,
            "completeness": completeness,
            "ratio_quality": "missing_denominator",
            "sh_source_url": SSE_PAGE_URL if sh_available else None,
            "sz_source_url": SZSE_PAGE_URL if sz_available else None,
        }
        if sh_available and sz_available:
            row["sh_holding_shares"] = sh_row.get("shares", 0)
            row["sz_holding_shares"] = sz_row.get("shares", 0)
            row["total_holding_shares"] = row["sh_holding_shares"] + row["sz_holding_shares"]
        holdings.append(row)
    return holdings, list(securities.values()), completeness


def ingest_stock_connect(client: SupabaseRest, start: date, end: date, *, pause: float,
                         dry_run: bool = False) -> int:
    started = datetime.now(timezone.utc).isoformat()
    total = 0
    complete_days = 0
    partial_days = 0
    missing_days = 0
    weekdays = [day for day in date_range(start, end) if day.weekday() < 5]
    for index, day in enumerate(weekdays, 1):
        try:
            sz = fetch_szse(day)
            sh = fetch_sse(day)
        except (urllib.error.HTTPError, urllib.error.URLError, zipfile.BadZipFile, json.JSONDecodeError) as error:
            print(f"WARN {day}: source fetch failed: {error}", file=sys.stderr)
            missing_days += 1
            continue
        holdings, securities, completeness = stock_connect_rows(day, sh, sz)
        if not holdings:
            missing_days += 1
            print(f"Stock Connect {day}: no published data ({index}/{len(weekdays)})")
        else:
            if completeness == "complete":
                complete_days += 1
            else:
                partial_days += 1
            if not dry_run:
                client.upsert("market_securities", securities, "stock_code")
                total += client.upsert("hk_stock_connect_holdings_daily", holdings, "stock_code,holding_date")
            else:
                total += len(holdings)
            print(f"Stock Connect {day}: {len(holdings)} rows, {completeness} ({index}/{len(weekdays)})")
        if pause and index < len(weekdays):
            time.sleep(pause)
    status = "success" if partial_days == 0 and missing_days == 0 else "partial"
    if not dry_run:
        client.insert_run("stock_connect", started, start, end, status, total, {
            "complete_days": complete_days,
            "partial_days": partial_days,
            "missing_days": missing_days,
            "sse_public_start": SSE_PUBLIC_START.isoformat(),
            "sse_source_url": SSE_PAGE_URL,
            "szse_source_url": SZSE_PAGE_URL,
        })
    return total


def fetch_weekly_prices(stock_code: str, count: int = 320) -> list[tuple[str, float]]:
    symbol = f"hk{normalize_code(stock_code)}"
    params = f"{symbol},week,,,{count}"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            payload = json_request(f"https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={params}")
            data = (payload.get("data") or {}).get(symbol) or {}
            rows = data.get("qfqweek") or data.get("week") or []
            result = []
            for row in rows:
                try:
                    close = float(row[2])
                except (IndexError, TypeError, ValueError):
                    continue
                if row[0] and close > 0:
                    result.append((str(row[0]), close))
            if len(result) >= 6:
                return result
            last_error = RuntimeError(f"Weekly prices returned too few rows for {stock_code}: {len(result)}")
        except Exception as error:
            last_error = error
        time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"Weekly prices unavailable for {stock_code}: {last_error}")


def fetch_index_weekly_prices(quote_id: str) -> list[tuple[str, float]]:
    end = date.today().strftime("%Y%m%d")
    params = urllib.parse.urlencode({
        "secid": quote_id, "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "102", "fqt": "1", "beg": "20190101", "end": end,
    })
    payload = json_request(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?{params}")
    result = []
    for line in ((payload.get("data") or {}).get("klines") or []):
        parts = str(line).split(",")
        if len(parts) >= 3 and float(parts[2]) > 0:
            result.append((parts[0], float(parts[2])))
    if len(result) < 6:
        raise RuntimeError(f"Index weekly prices unavailable for {quote_id}")
    return result


def rolling_biases(prices: list[tuple[str, float]], period: int) -> list[float | None]:
    values = [close for _, close in prices]
    result: list[float | None] = []
    rolling_sum = 0.0
    for index, close in enumerate(values):
        rolling_sum += close
        if index >= period:
            rolling_sum -= values[index - period]
        result.append((close / (rolling_sum / period) - 1) * 100 if index >= period - 1 else None)
    return result


def rolling_percentiles(values: list[float | None], window: int = 104) -> list[float | None]:
    result: list[float | None] = []
    valid: list[float] = []
    for value in values:
        if value is None:
            result.append(None)
            continue
        valid.append(value)
        observations = valid[-window:]
        if len(observations) < window:
            result.append(None)
            continue
        lower = sum(item < value for item in observations)
        equal = sum(item == value for item in observations)
        result.append((lower + 0.5 * (equal - 1)) / (len(observations) - 1) * 100)
    return result


def five_week_returns(prices: list[tuple[str, float]]) -> dict[str, float]:
    return {
        day: (close / prices[index - 5][1] - 1) * 100
        for index, (day, close) in enumerate(prices) if index >= 5
    }


def metric_rows(index_code: str, stock_code: str, prices: list[tuple[str, float]],
                index_returns: dict[str, float], quality: str) -> list[dict]:
    biases = {period: rolling_biases(prices, period) for period in (5, 30, 40, 50)}
    percentiles = {period: rolling_percentiles(biases[period]) for period in (5, 30, 40, 50)}
    stock_returns = five_week_returns(prices)
    rows = []
    for offset, (day, close) in enumerate(prices):
        if day < METRIC_START.isoformat():
            continue
        stock_return = stock_returns.get(day)
        index_return = index_returns.get(day)
        rows.append({
            "index_code": index_code, "stock_code": normalize_code(stock_code), "week_date": day,
            "close_price": close,
            "bias_5w_pct": biases[5][offset], "bias_30w_pct": biases[30][offset],
            "bias_40w_pct": biases[40][offset], "bias_50w_pct": biases[50][offset],
            "percentile_5w_2y": percentiles[5][offset], "percentile_30w_2y": percentiles[30][offset],
            "percentile_40w_2y": percentiles[40][offset], "percentile_50w_2y": percentiles[50][offset],
            "five_week_return_pct": stock_return, "index_five_week_return_pct": index_return,
            "excess_five_week_return_pct": stock_return - index_return if stock_return is not None and index_return is not None else None,
            "index_return_quality": quality, "price_source": "tencent_weekly",
        })
    return rows


def ingest_weekly_metrics(client: SupabaseRest, *, dry_run: bool = False, workers: int = 10) -> int:
    started = datetime.now(timezone.utc).isoformat()
    with open(MARKET_INSIGHTS_FILE, encoding="utf-8") as handle:
        indexes = json.load(handle)["constituents"]["indexes"]
    codes = sorted({normalize_code(member["code"]) for item in indexes.values() for member in item["members"]})
    prices_by_code: dict[str, list[tuple[str, float]]] = {}
    failures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_weekly_prices, code): code for code in codes}
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            code = futures[future]
            try:
                prices_by_code[code] = future.result()
            except Exception as error:  # individual source failures must not discard the whole weekly snapshot
                failures[code] = str(error)
            if completed % 50 == 0 or completed == len(futures):
                print(f"Weekly prices: {completed}/{len(futures)}")
    all_rows = []
    for index_id, item in indexes.items():
        index_code = item["code"]
        quality = "official_index"
        try:
            index_returns = five_week_returns(fetch_index_weekly_prices(item["quoteId"]))
        except Exception as error:
            print(f"WARN {index_code}: official index prices unavailable, using equal-weight constituents: {error}", file=sys.stderr)
            quality = "constituent_equal_weight"
            grouped: dict[str, list[float]] = {}
            for member in item["members"]:
                prices = prices_by_code.get(normalize_code(member["code"]))
                if not prices:
                    continue
                for day, value in five_week_returns(prices).items():
                    grouped.setdefault(day, []).append(value)
            index_returns = {day: sum(values) / len(values) for day, values in grouped.items() if values}
        for member in item["members"]:
            code = normalize_code(member["code"])
            prices = prices_by_code.get(code)
            if prices:
                all_rows.extend(metric_rows(index_code, code, prices, index_returns, quality))
    if not all_rows:
        raise RuntimeError("No weekly metric rows were calculated")
    written = len(all_rows) if dry_run else client.upsert(
        "hk_market_insight_metrics_weekly", all_rows, "index_code,stock_code,week_date", chunk_size=500)
    if not dry_run:
        client.insert_run("weekly_metrics", started, METRIC_START, date.today(),
                          "partial" if failures else "success", written,
                          {"stocks_requested": len(codes), "stocks_loaded": len(prices_by_code),
                           "failed_stocks": failures, "indexes": list(indexes)})
    print(f"Stored weekly market insight metrics: {written} rows; failed stocks: {len(failures)}")
    return written


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Fetch and validate without writing to Supabase")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sync-hsci")

    short = subparsers.add_parser("short")
    short.add_argument("--start", type=parse_date, default=date(2023, 1, 1))
    short.add_argument("--end", type=parse_date, default=date.today())
    short.add_argument("--latest-only", action="store_true")
    short.add_argument("--pause", type=float, default=0.15)

    connect = subparsers.add_parser("stock-connect")
    connect.add_argument("--start", type=parse_date)
    connect.add_argument("--end", type=parse_date, default=date.today())
    connect.add_argument("--lookback-days", type=int, default=10)
    connect.add_argument("--pause", type=float, default=0.15)

    metrics = subparsers.add_parser("metrics")
    metrics.add_argument("--workers", type=int, default=10)

    args = parser.parse_args()
    client = SupabaseRest(required=not args.dry_run)
    if args.command == "sync-hsci":
        sync_hsci(client, dry_run=args.dry_run)
    elif args.command == "short":
        ingest_short_positions(client, args.start, args.end, latest_only=args.latest_only,
                               pause=args.pause, dry_run=args.dry_run)
    elif args.command == "stock-connect":
        start = args.start or (args.end - timedelta(days=max(0, args.lookback_days - 1)))
        ingest_stock_connect(client, start, args.end, pause=args.pause, dry_run=args.dry_run)
    elif args.command == "metrics":
        ingest_weekly_metrics(client, dry_run=args.dry_run, workers=args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
