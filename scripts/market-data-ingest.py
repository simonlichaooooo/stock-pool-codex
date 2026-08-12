#!/usr/bin/env python3
"""Ingest market constituents, positions, holdings and insight metrics into Supabase."""

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
import http.cookiejar
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from statistics import median
from xml.etree import ElementTree


HSCI_URL = "https://www.hsi.com.hk/data/eng/rt/index-series/hsci/constituents.do"
SFC_PAGE_URL = "https://www.sfc.hk/en/Regulatory-functions/Market/Short-position-reporting/Aggregated-reportable-short-positions-of-specified-shares"
SSE_PAGE_URL = "https://star.sse.com.cn/services/hkexsc/ggtscsj/ggtzqcysl/"
SSE_API_URL = "https://query.sse.com.cn/sseQuery/commonSoaQuery.do"
SZSE_PAGE_URL = "https://www.szse.cn/szhk/szhkshareholding/hkholdamount/index.html"
SZSE_XLSX_URL = "https://www.szse.cn/api/report/ShowReport"
HKEX_SOUTHBOUND_URL = "https://www3.hkexnews.hk/sdw/search/mutualmarket.aspx?t=hk"
SSE_PUBLIC_START = date(2024, 8, 19)
USER_AGENT = "Mozilla/5.0 (compatible; stock-pool-market-data/1.0)"
XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
MARKET_INSIGHTS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "market-insights.json")
METRIC_START = date(2023, 1, 1)
BIAS_PERIODS = (5, 10, 20, 30, 40, 50)
PERCENTILE_WINDOWS = {"1y": 52, "2y": 104}
RETURN_PERIODS = (1, 5)
HONG_KONG_TZ = timezone(timedelta(hours=8))


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


def latest_completed_week_date(now: datetime | None = None) -> date:
    hong_kong_now = now.astimezone(HONG_KONG_TZ) if now else datetime.now(HONG_KONG_TZ)
    days_since_friday = (hong_kong_now.weekday() - 4) % 7
    cutoff = hong_kong_now.date() - timedelta(days=days_since_friday)
    if hong_kong_now.weekday() == 4 and hong_kong_now.hour < 16:
        cutoff -= timedelta(days=7)
    return cutoff


def completed_weekly_prices(prices: list[tuple[str, float]], cutoff: date) -> list[tuple[str, float]]:
    return [(day, close) for day, close in prices if day <= cutoff.isoformat()]


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

    def rpc(self, function: str, payload: dict | None = None):
        return self._request("POST", f"rpc/{function}", payload or {}, prefer="return=representation")


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


def hidden_input(page: str, name: str) -> str:
    match = re.search(r'name="' + re.escape(name) + r'"[^>]*value="([^"]*)"', page, re.I)
    return html.unescape(match.group(1)) if match else ""


def parse_hkex_southbound_page(page: str) -> tuple[date, dict[str, dict]]:
    alert = hidden_input(page, "alertMsg")
    if alert:
        raise ValueError(f"HKEX Southbound date unavailable: {alert}")
    shown = hidden_input(page, "originalShareholdingDate")
    if not shown:
        raise ValueError("HKEX Southbound response date not found")
    actual_date = datetime.strptime(shown, "%Y/%m/%d").date()
    result: dict[str, dict] = {}
    for block in re.findall(r"<tr>(.*?)</tr>", page, re.I | re.S):
        def cell(class_name: str) -> str:
            match = re.search(
                r'<td[^>]*class="[^"]*' + re.escape(class_name) + r'[^"]*"[^>]*>.*?'
                r'<div[^>]*class="mobile-list-body"[^>]*>(.*?)</div>', block, re.I | re.S,
            )
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(match.group(1)))).strip() if match else ""
        raw_code = cell("col-stock-code")
        raw_shares = cell("col-shareholding")
        if not raw_code or not raw_shares:
            continue
        code = normalize_code(raw_code)
        raw_ratio = cell("col-shareholding-percent").rstrip("%").strip()
        result[code] = {
            "shares": integer(raw_shares),
            "name_en": cell("col-stock-name") or None,
            "source_ratio_pct": float(raw_ratio) if raw_ratio else None,
        }
    if len(result) < 500:
        raise ValueError(f"HKEX Southbound returned too few securities: {len(result)}")
    return actual_date, result


class HkexSouthboundSession:
    def __init__(self):
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.page = self._open()

    def _open(self, payload: bytes | None = None) -> str:
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
        if payload is not None:
            headers.update({"Content-Type": "application/x-www-form-urlencoded", "Referer": HKEX_SOUTHBOUND_URL})
        for attempt in range(5):
            request = urllib.request.Request(HKEX_SOUTHBOUND_URL, data=payload, headers=headers)
            try:
                with self.opener.open(request, timeout=90) as response:
                    return response.read().decode("utf-8", errors="replace")
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == 4:
                    raise
                time.sleep(min(20, 2 ** attempt))
        raise RuntimeError("HKEX Southbound retry loop ended unexpectedly")

    def fetch(self, day: date) -> tuple[date, dict[str, dict]]:
        payload = urllib.parse.urlencode({
            "__EVENTTARGET": "btnSearch", "__EVENTARGUMENT": "",
            "__VIEWSTATE": hidden_input(self.page, "__VIEWSTATE"),
            "__VIEWSTATEGENERATOR": hidden_input(self.page, "__VIEWSTATEGENERATOR"),
            "today": hidden_input(self.page, "today"), "sortBy": "stockcode", "sortDirection": "asc",
            "originalShareholdingDate": hidden_input(self.page, "originalShareholdingDate"),
            "alertMsg": "", "txtShareholdingDate": day.strftime("%Y/%m/%d"),
        }).encode()
        self.page = self._open(payload)
        return parse_hkex_southbound_page(self.page)


def hkex_stock_connect_rows(day: date, source: dict[str, dict]) -> tuple[list[dict], list[dict], str]:
    securities, holdings = [], []
    for code, item in source.items():
        securities.append({key: value for key, value in {
            "stock_code": code, "name_en": item.get("name_en"),
        }.items() if value is not None})
        holdings.append({
            "stock_code": code, "holding_date": day.isoformat(),
            "sh_holding_shares": None, "sz_holding_shares": None,
            "total_holding_shares": item["shares"], "completeness": "official_aggregate",
            "aggregate_source_url": HKEX_SOUTHBOUND_URL,
            "source_reported_ratio_pct": item.get("source_ratio_pct"),
        })
    return holdings, securities, "official_aggregate"


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
    hkex_online_start = date.today() - timedelta(days=364)
    hkex_session = HkexSouthboundSession() if any(day >= hkex_online_start for day in weekdays) else None
    for index, day in enumerate(weekdays, 1):
        try:
            if day >= hkex_online_start and hkex_session:
                actual_date, aggregate = hkex_session.fetch(day)
                holdings, securities, completeness = hkex_stock_connect_rows(actual_date, aggregate)
            else:
                sz = fetch_szse(day)
                sh = fetch_sse(day)
                holdings, securities, completeness = stock_connect_rows(day, sh, sz)
        except (urllib.error.HTTPError, urllib.error.URLError, zipfile.BadZipFile, json.JSONDecodeError, ValueError) as error:
            print(f"WARN {day}: source fetch failed: {error}", file=sys.stderr)
            missing_days += 1
            continue
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
            "hkex_online_start": hkex_online_start.isoformat(),
            "hkex_aggregate_source_url": HKEX_SOUTHBOUND_URL,
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
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    })
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            payload = json_request(
                f"https://push2his.eastmoney.com/api/qt/stock/kline/get?{params}",
                headers={"Referer": "https://quote.eastmoney.com/"},
            )
            result = []
            for line in ((payload.get("data") or {}).get("klines") or []):
                parts = str(line).split(",")
                if len(parts) >= 3 and float(parts[2]) > 0:
                    result.append((parts[0], float(parts[2])))
            if len(result) >= 6:
                return result
            last_error = RuntimeError(f"Index weekly prices returned too few rows for {quote_id}: {len(result)}")
        except Exception as error:
            last_error = error
        time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"Index weekly prices unavailable for {quote_id}: {last_error}")


def fetch_monthly_prices(stock_code: str, count: int = 120) -> list[tuple[str, float]]:
    """Return adjusted monthly closes, including the latest month-to-date observation."""
    symbol = f"hk{normalize_code(stock_code)}"
    params = f"{symbol},month,,,{count}"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            payload = json_request(f"https://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={params}")
            data = (payload.get("data") or {}).get(symbol) or {}
            rows = data.get("qfqmonth") or data.get("month") or []
            result = []
            for row in rows:
                try:
                    close = float(row[2])
                except (IndexError, TypeError, ValueError):
                    continue
                if row[0] and close > 0:
                    result.append((str(row[0]), close))
            if len(result) >= 2:
                return normalized_monthly_prices(result)
            last_error = RuntimeError(f"Monthly prices returned too few rows for {stock_code}: {len(result)}")
        except Exception as error:
            last_error = error
        time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"Monthly prices unavailable for {stock_code}: {last_error}")


def fetch_index_monthly_prices(quote_id: str) -> list[tuple[str, float]]:
    """Return official index monthly closes, including the latest month-to-date close."""
    end = date.today().strftime("%Y%m%d")
    params = urllib.parse.urlencode({
        "secid": quote_id, "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "103", "fqt": "1", "beg": "20190101", "end": end,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
    })
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            payload = json_request(
                f"https://push2his.eastmoney.com/api/qt/stock/kline/get?{params}",
                headers={"Referer": "https://quote.eastmoney.com/"},
            )
            result = []
            for line in ((payload.get("data") or {}).get("klines") or []):
                parts = str(line).split(",")
                if len(parts) >= 3 and float(parts[2]) > 0:
                    result.append((parts[0], float(parts[2])))
            if len(result) >= 2:
                return normalized_monthly_prices(result)
            last_error = RuntimeError(f"Index monthly prices returned too few rows for {quote_id}: {len(result)}")
        except Exception as error:
            last_error = error
        time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"Index monthly prices unavailable for {quote_id}: {last_error}")


def fetch_issued_shares_history(stock_code: str, start: date, end: date) -> list[dict]:
    code = normalize_code(stock_code)
    source_url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = urllib.parse.urlencode({
        "secid": f"116.{code}", "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101", "fqt": "0", "beg": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"),
    })
    payload = None
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            payload = json_request(f"{source_url}?{params}", headers={"Referer": "https://quote.eastmoney.com/"})
            break
        except Exception as error:
            last_error = error
            time.sleep(0.8 * (attempt + 1))
    if payload is None:
        raise RuntimeError(f"Issued-share source unavailable for {code}: {last_error}")
    monthly: dict[str, list[tuple[date, float]]] = {}
    for line in ((payload.get("data") or {}).get("klines") or []):
        parts = str(line).split(",")
        if len(parts) < 11:
            continue
        try:
            day = datetime.strptime(parts[0], "%Y-%m-%d").date()
            volume = float(parts[5])
            turnover_pct = float(parts[10])
        except (TypeError, ValueError):
            continue
        if volume <= 0 or turnover_pct < 0.02:
            continue
        inferred = volume / (turnover_pct / 100)
        if inferred > 0:
            monthly.setdefault(day.strftime("%Y-%m"), []).append((day, inferred))
    rows = []
    for observations in monthly.values():
        period_end = max(day for day, _ in observations)
        values = [value for _, value in observations]
        rows.append({
            "stock_code": code,
            "period_end": period_end.isoformat(),
            "issued_shares": round(median(values)),
            "source_quality": "vendor_estimate",
            "source_url": source_url,
            "observations": len(values),
        })
    return rows


def ingest_issued_shares(client: SupabaseRest, start: date, end: date, *, dry_run: bool = False,
                         workers: int = 10) -> int:
    with open(MARKET_INSIGHTS_FILE, encoding="utf-8") as handle:
        indexes = json.load(handle)["constituents"]["indexes"]
    codes = sorted({normalize_code(member["code"]) for item in indexes.values() for member in item["members"]})
    all_rows: list[dict] = []
    failures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        source_start = start - timedelta(days=45)
        futures = {executor.submit(fetch_issued_shares_history, code, source_start, end): code for code in codes}
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            code = futures[future]
            try:
                all_rows.extend(future.result())
            except Exception as error:
                failures[code] = str(error)
            if completed % 50 == 0 or completed == len(futures):
                print(f"Issued shares: {completed}/{len(futures)}")
    if not all_rows:
        raise RuntimeError("No issued-share history was calculated")
    if not dry_run:
        client.upsert("hk_issued_shares_monthly", all_rows, "stock_code,period_end", chunk_size=500)
        result = client.rpc("refresh_hk_holding_ratios")
        print(f"Ratio backfill: {result}")
    print(f"Stored issued-share history: {len(all_rows)} rows; failed stocks: {len(failures)}")
    return len(all_rows)


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


def rolling_changes(values: list[float | None]) -> list[float | None]:
    result: list[float | None] = []
    previous: float | None = None
    for value in values:
        result.append(value - previous if value is not None and previous is not None else None)
        if value is not None:
            previous = value
    return result


def period_returns(prices: list[tuple[str, float]], weeks: int) -> dict[str, float]:
    return {
        day: (close / prices[index - weeks][1] - 1) * 100
        for index, (day, close) in enumerate(prices) if index >= weeks
    }


def five_week_returns(prices: list[tuple[str, float]]) -> dict[str, float]:
    return period_returns(prices, 5)


def normalized_monthly_prices(prices: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Keep the latest valid observation in each calendar month."""
    by_month: dict[str, tuple[str, float]] = {}
    for day, close in prices:
        month = str(day)[:7]
        if len(month) != 7 or close <= 0:
            continue
        previous = by_month.get(month)
        if previous is None or day > previous[0]:
            by_month[month] = (day, close)
    return sorted(by_month.values())


def monthly_returns(prices: list[tuple[str, float]]) -> dict[str, float]:
    """Map YYYY-MM-01 to the return from the prior month's close."""
    normalized = normalized_monthly_prices(prices)
    return {
        f"{day[:7]}-01": (close / normalized[index - 1][1] - 1) * 100
        for index, (day, close) in enumerate(normalized) if index >= 1
    }


def monthly_return_rows(index_code: str, stock_code: str,
                        prices: list[tuple[str, float]],
                        index_returns: dict[str, float], quality: str) -> list[dict]:
    normalized = normalized_monthly_prices(prices)
    stock_returns = monthly_returns(normalized)
    rows = []
    for day, close in normalized:
        month_start = f"{day[:7]}-01"
        if month_start < METRIC_START.replace(day=1).isoformat():
            continue
        stock_return = stock_returns.get(month_start)
        index_return = index_returns.get(month_start)
        rows.append({
            "index_code": index_code,
            "stock_code": normalize_code(stock_code),
            "month_start": month_start,
            "period_end": day,
            "close_price": close,
            "stock_return_pct": stock_return,
            "index_return_pct": index_return,
            "excess_return_pct": (
                stock_return - index_return
                if stock_return is not None and index_return is not None else None
            ),
            "index_return_quality": quality,
            "price_source": "tencent_monthly",
        })
    return rows


def monthly_metric_coverage(rows: list[dict], indexes: dict) -> dict[str, dict]:
    latest_month = max((row["month_start"] for row in rows), default=None)
    summary: dict[str, dict] = {}
    for item in indexes.values():
        index_code = item["code"]
        index_rows = [row for row in rows if row["index_code"] == index_code]
        current_rows = [row for row in index_rows if row["month_start"] == latest_month]
        expected = len(item["members"])
        covered = sum(row.get("excess_return_pct") is not None for row in current_rows)
        official = sum(row.get("index_return_quality") == "official_index" for row in current_rows)
        summary[index_code] = {
            "stocks_expected": expected,
            "stocks_in_latest_month": len(current_rows),
            "latest_month": latest_month,
            "stocks_with_excess_return": covered,
            "excess_return_coverage_pct": round(covered / expected * 100, 2) if expected else 0,
            "stocks_with_official_index_return": official,
        }
    return summary


def metric_rows(index_code: str, stock_code: str, prices: list[tuple[str, float]],
                index_returns: dict[int, dict[str, float]], quality: str) -> list[dict]:
    biases = {period: rolling_biases(prices, period) for period in BIAS_PERIODS}
    speeds = {period: rolling_changes(biases[period]) for period in BIAS_PERIODS}
    percentiles = {
        (period, label): rolling_percentiles(biases[period], window)
        for period in BIAS_PERIODS for label, window in PERCENTILE_WINDOWS.items()
    }
    stock_returns = {period: period_returns(prices, period) for period in RETURN_PERIODS}
    rows = []
    for offset, (day, close) in enumerate(prices):
        if day < METRIC_START.isoformat():
            continue
        row = {
            "index_code": index_code, "stock_code": normalize_code(stock_code), "week_date": day,
            "close_price": close,
            "index_return_quality": quality, "price_source": "tencent_weekly",
        }
        for period in BIAS_PERIODS:
            row[f"bias_{period}w_pct"] = biases[period][offset]
            row[f"bias_speed_{period}w_pct"] = speeds[period][offset]
            for label in PERCENTILE_WINDOWS:
                row[f"percentile_{period}w_{label}"] = percentiles[(period, label)][offset]
        for period, prefix in ((1, "one"), (5, "five")):
            stock_return = stock_returns[period].get(day)
            index_return = index_returns[period].get(day)
            row[f"{prefix}_week_return_pct"] = stock_return
            row[f"index_{prefix}_week_return_pct"] = index_return
            row[f"excess_{prefix}_week_return_pct"] = (
                stock_return - index_return
                if stock_return is not None and index_return is not None else None
            )
        rows.append(row)
    return rows


def metric_coverage(rows: list[dict], indexes: dict) -> dict[str, dict]:
    latest_by_key: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["index_code"], row["stock_code"])
        if key not in latest_by_key or row["week_date"] > latest_by_key[key]["week_date"]:
            latest_by_key[key] = row
    summary: dict[str, dict] = {}
    for item in indexes.values():
        index_code = item["code"]
        latest = [row for (code, _), row in latest_by_key.items() if code == index_code]
        expected = len(item["members"])
        field_groups = {
            "all_biases": [f"bias_{period}w_pct" for period in BIAS_PERIODS],
            "all_speeds": [f"bias_speed_{period}w_pct" for period in BIAS_PERIODS],
            "all_1y_percentiles": [f"percentile_{period}w_1y" for period in BIAS_PERIODS],
            "all_2y_percentiles": [f"percentile_{period}w_2y" for period in BIAS_PERIODS],
            "standard_excess_returns": ["excess_one_week_return_pct", "excess_five_week_return_pct"],
        }
        counts = {
            label: sum(all(row.get(field) is not None for field in fields) for row in latest)
            for label, fields in field_groups.items()
        }
        summary[index_code] = {
            "stocks_expected": expected,
            "stocks_calculated": len(latest),
            "latest_week": max((row["week_date"] for row in latest), default=None),
            **{f"stocks_with_{label}": count for label, count in counts.items()},
            **{
                f"{label}_coverage_pct": round(count / expected * 100, 2) if expected else 0
                for label, count in counts.items()
            },
        }
    return summary


def ingest_weekly_metrics(client: SupabaseRest, *, dry_run: bool = False, workers: int = 10) -> int:
    started = datetime.now(timezone.utc).isoformat()
    completed_week = latest_completed_week_date()
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
                prices_by_code[code] = completed_weekly_prices(future.result(), completed_week)
            except Exception as error:  # individual source failures must not discard the whole weekly snapshot
                failures[code] = str(error)
            if completed % 50 == 0 or completed == len(futures):
                print(f"Weekly prices: {completed}/{len(futures)}")
    all_rows = []
    all_index_price_rows = []
    index_failures = {}
    for index_id, item in indexes.items():
        index_code = item["code"]
        quality = "official_index"
        try:
            index_prices = completed_weekly_prices(fetch_index_weekly_prices(item["quoteId"]), completed_week)
            index_returns = {period: period_returns(index_prices, period) for period in RETURN_PERIODS}
            all_index_price_rows.extend({
                "index_code": index_code, "week_date": day, "close_price": close,
                "price_source": "eastmoney_index_weekly",
            } for day, close in index_prices)
        except Exception as error:
            print(f"WARN {index_code}: official index prices unavailable, using equal-weight constituents: {error}", file=sys.stderr)
            quality = "constituent_equal_weight"
            index_failures[index_code] = str(error)
            index_returns = {}
            for period in RETURN_PERIODS:
                grouped: dict[str, list[float]] = {}
                for member in item["members"]:
                    prices = prices_by_code.get(normalize_code(member["code"]))
                    if not prices:
                        continue
                    for day, value in period_returns(prices, period).items():
                        grouped.setdefault(day, []).append(value)
                index_returns[period] = {
                    day: sum(values) / len(values) for day, values in grouped.items() if values
                }
        for member in item["members"]:
            code = normalize_code(member["code"])
            prices = prices_by_code.get(code)
            if prices:
                all_rows.extend(metric_rows(index_code, code, prices, index_returns, quality))
    if not all_rows:
        raise RuntimeError("No weekly metric rows were calculated")
    coverage = metric_coverage(all_rows, indexes)
    if dry_run:
        written = len(all_rows)
        index_prices_written = len(all_index_price_rows)
    else:
        index_prices_written = client.upsert(
            "market_index_weekly_prices", all_index_price_rows,
            "index_code,week_date", chunk_size=500) if all_index_price_rows else 0
        written = client.upsert(
            "hk_market_insight_metrics_weekly", all_rows,
            "index_code,stock_code,week_date", chunk_size=500)
    if not dry_run:
        client.insert_run("weekly_metrics", started, METRIC_START, date.today(),
                          "partial" if failures or index_failures else "success", written,
                          {"stocks_requested": len(codes), "stocks_loaded": len(prices_by_code),
                           "failed_stocks": failures, "indexes": list(indexes),
                           "index_price_rows": index_prices_written,
                           "failed_index_prices": index_failures,
                           "filter_metric_coverage": coverage})
    print(f"Stored index weekly prices: {index_prices_written} rows; failed indexes: {len(index_failures)}")
    print(f"Stored weekly market insight metrics: {written} rows; failed stocks: {len(failures)}")
    print("Filter metric coverage: " + json.dumps(coverage, ensure_ascii=False, sort_keys=True))
    return written


def ingest_monthly_metrics(client: SupabaseRest, *, dry_run: bool = False, workers: int = 10) -> int:
    """Persist calendar-month stock/index/excess returns for database filtering."""
    started = datetime.now(timezone.utc).isoformat()
    with open(MARKET_INSIGHTS_FILE, encoding="utf-8") as handle:
        indexes = json.load(handle)["constituents"]["indexes"]
    codes = sorted({normalize_code(member["code"]) for item in indexes.values() for member in item["members"]})
    prices_by_code: dict[str, list[tuple[str, float]]] = {}
    failures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_monthly_prices, code): code for code in codes}
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            code = futures[future]
            try:
                prices_by_code[code] = future.result()
            except Exception as error:  # one suspended/new listing must not discard the monthly snapshot
                failures[code] = str(error)
            if completed % 50 == 0 or completed == len(futures):
                print(f"Monthly prices: {completed}/{len(futures)}")

    all_rows = []
    all_index_price_rows = []
    index_failures = {}
    for item in indexes.values():
        index_code = item["code"]
        quality = "official_index"
        try:
            index_prices = fetch_index_monthly_prices(item["quoteId"])
            index_returns = monthly_returns(index_prices)
            all_index_price_rows.extend({
                "index_code": index_code,
                "month_start": f"{day[:7]}-01",
                "period_end": day,
                "close_price": close,
                "price_source": "eastmoney_index_monthly",
            } for day, close in index_prices)
        except Exception as error:
            print(f"WARN {index_code}: official index monthly prices unavailable, "
                  f"using equal-weight constituents: {error}", file=sys.stderr)
            quality = "constituent_equal_weight"
            index_failures[index_code] = str(error)
            grouped: dict[str, list[float]] = {}
            for member in item["members"]:
                prices = prices_by_code.get(normalize_code(member["code"]))
                if not prices:
                    continue
                for month_start, value in monthly_returns(prices).items():
                    grouped.setdefault(month_start, []).append(value)
            index_returns = {
                month_start: sum(values) / len(values)
                for month_start, values in grouped.items() if values
            }
        for member in item["members"]:
            code = normalize_code(member["code"])
            prices = prices_by_code.get(code)
            if prices:
                all_rows.extend(monthly_return_rows(index_code, code, prices, index_returns, quality))

    if not all_rows:
        raise RuntimeError("No monthly market insight rows were calculated")
    coverage = monthly_metric_coverage(all_rows, indexes)
    if dry_run:
        written = len(all_rows)
        index_prices_written = len(all_index_price_rows)
    else:
        index_prices_written = client.upsert(
            "market_index_monthly_prices", all_index_price_rows,
            "index_code,month_start", chunk_size=500) if all_index_price_rows else 0
        written = client.upsert(
            "hk_market_insight_monthly_returns", all_rows,
            "index_code,stock_code,month_start", chunk_size=500)
        client.insert_run(
            "monthly_metrics", started, METRIC_START.replace(day=1), date.today(),
            "partial" if failures or index_failures else "success", written,
            {"stocks_requested": len(codes), "stocks_loaded": len(prices_by_code),
             "failed_stocks": failures, "indexes": list(indexes),
             "index_price_rows": index_prices_written,
             "failed_index_prices": index_failures,
             "monthly_metric_coverage": coverage},
        )
    print(f"Stored index monthly prices: {index_prices_written} rows; failed indexes: {len(index_failures)}")
    print(f"Stored monthly market insight returns: {written} rows; failed stocks: {len(failures)}")
    print("Monthly metric coverage: " + json.dumps(coverage, ensure_ascii=False, sort_keys=True))
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

    monthly_metrics = subparsers.add_parser("monthly-metrics")
    monthly_metrics.add_argument("--workers", type=int, default=10)

    shares = subparsers.add_parser("issued-shares")
    shares.add_argument("--start", type=parse_date, default=date(2023, 1, 1))
    shares.add_argument("--end", type=parse_date, default=date.today())
    shares.add_argument("--workers", type=int, default=10)

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
    elif args.command == "monthly-metrics":
        ingest_monthly_metrics(client, dry_run=args.dry_run, workers=args.workers)
    elif args.command == "issued-shares":
        ingest_issued_shares(client, args.start, args.end, dry_run=args.dry_run, workers=args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
