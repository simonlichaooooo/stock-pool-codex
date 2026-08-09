#!/usr/bin/env python3
"""Backfill official HKEX issued-share history from disclosure PDFs."""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_FILE = ROOT / "data" / "market-insights.json"
USER_AGENT = "Mozilla/5.0 (compatible; stock-pool-hkex-official-capital/1.0)"
PARSER_VERSION = "hkex-share-capital-v1"
HK_TZ = timezone(timedelta(hours=8))


def normalize_code(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        raise ValueError(f"Invalid HK stock code: {value!r}")
    return digits[-5:].zfill(5)


def request_bytes(url: str, timeout: int = 60, attempts: int = 5) -> bytes:
    for attempt in range(attempts):
        request = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        })
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt + 1 == attempts:
                raise
            time.sleep(min(20, 2 ** attempt))
    raise RuntimeError("request retry loop ended unexpectedly")


class SupabaseRest:
    def __init__(self, required: bool = True):
        self.base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if required and (not self.base_url or not self.key):
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

    def request(self, method: str, path: str, payload=None, prefer: str | None = None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        if prefer:
            headers["Prefer"] = prefer
        req = urllib.request.Request(f"{self.base_url}/rest/v1/{path}", data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RuntimeError(f"Supabase {method} {path} failed: {error.code} {detail}") from error

    def upsert(self, table: str, rows: list[dict], conflict: str):
        if rows:
            path = f"{table}?on_conflict={urllib.parse.quote(conflict)}"
            self.request("POST", path, rows, "resolution=merge-duplicates,return=minimal")

    def parsed_documents(self, code: str, start: date, end: date) -> set[str]:
        query = urllib.parse.urlencode({
            "select": "document_id", "stock_code": f"eq.{code}",
            "parse_status": "in.(parsed,no_listed_class)",
            "release_at": f"gte.{start.isoformat()}T00:00:00+08:00",
            "order": "release_at.asc", "limit": "10000",
        })
        rows = self.request("GET", f"hkex_share_capital_filings?{query}") or []
        return {row["document_id"] for row in rows}

    def rpc(self, name: str):
        return self.request("POST", f"rpc/{name}", {}, "return=representation")

    def insert_run(self, started_at: str, start: date, end: date, status: str, rows: int, details: dict):
        self.request("POST", "market_data_ingestion_runs", [{
            "dataset": "hkex_share_capital", "range_start": start.isoformat(), "range_end": end.isoformat(),
            "status": status, "rows_written": rows, "details": details, "started_at": started_at,
        }], "return=minimal")


def universe_codes() -> list[str]:
    data = json.loads(UNIVERSE_FILE.read_text())
    codes: set[str] = set()
    for index in data["constituents"]["indexes"].values():
        for member in index["members"]:
            codes.add(normalize_code(member["code"]))
    return sorted(codes)


def stock_id(code: str) -> int:
    url = "https://www1.hkexnews.hk/search/prefix.do?" + urllib.parse.urlencode({
        "callback": "callback", "lang": "EN", "type": "A", "name": code,
    })
    raw = request_bytes(url).decode("utf-8-sig")
    match = re.search(r"callback\((.*)\)\s*;?", raw, re.S)
    if not match:
        raise ValueError("HKEX prefix response is invalid")
    records = json.loads(match.group(1)).get("stockInfo", [])
    exact = next((row for row in records if str(row.get("code") or "").zfill(5) == code), None)
    if not exact:
        raise ValueError(f"HKEX stock id not found for {code}")
    return int(exact["stockId"])


def month_ranges(start: date, end: date):
    current = start.replace(day=1)
    while current <= end:
        last = date(current.year, current.month, calendar.monthrange(current.year, current.month)[1])
        yield max(start, current), min(end, last)
        current = last + timedelta(days=1)


def search_filings(hkex_stock_id: int, start: date, end: date) -> list[dict]:
    url = "https://www1.hkexnews.hk/search/titlesearch.xhtml?" + urllib.parse.urlencode({
        "lang": "EN", "market": "SEHK", "searchType": 0, "category": 0,
        "stockId": hkex_stock_id, "from": start.strftime("%Y%m%d"), "to": end.strftime("%Y%m%d"),
    })
    html = request_bytes(url).decode("utf-8-sig", errors="replace")
    rows = []
    link_pattern = re.compile(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', re.I | re.S)
    for link in link_pattern.finditer(html):
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(link.group(2)))).strip()
        context = html[max(0, link.start() - 2000):link.start()]
        categories = re.findall(r'<div[^>]+class="headline"[^>]*>\s*([^<]+)', context, re.I)
        category = categories[-1].strip() if categories else ""
        if not re.search(r"Monthly Returns|Next Day Disclosure Returns", category + " " + title, re.I):
            continue
        timestamps = re.findall(r"(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})", context)
        if not timestamps:
            continue
        href = urllib.parse.urljoin("https://www1.hkexnews.hk", unescape(link.group(1)))
        released = datetime.strptime(timestamps[-1], "%d/%m/%Y %H:%M").replace(tzinfo=HK_TZ)
        rows.append({"document_id": Path(urllib.parse.urlparse(href).path).stem,
                     "source_url": href, "title": category + " — " + title, "release_at": released})
    return rows


def pdf_text(content: bytes) -> str:
    import io
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)


def number(value: str) -> int:
    return int(value.replace(",", ""))


def share_class_near(text: str, position: int) -> str:
    nearby = text[max(0, position - 700):position]
    values = []
    for label in ("Class of shares", "Type of shares"):
        matches = list(re.finditer(label + r"\s+([^\n]+)", nearby, re.I))
        if matches:
            value = re.sub(r"\s+", " ", matches[-1].group(1)).strip()
            value = re.split(r"\s+(?:Type|Class) of shares|\s+Listed on SEHK", value, flags=re.I)[0]
            if value.lower() not in {"not applicable", "n/a"}:
                values.append(value)
    return values[0] if values else "listed shares"


def validate_shares(ex_treasury: int, treasury: int, total: int):
    if min(ex_treasury, total) <= 0 or treasury < 0 or ex_treasury + treasury != total:
        raise ValueError(f"invalid share totals: {ex_treasury}+{treasury}!={total}")


def parse_monthly(text: str, code: str) -> dict:
    period_match = re.search(r"For the month ended:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})", text, re.I)
    if not period_match:
        raise ValueError("monthly period end not found")
    section_match = re.search(r"II\.\s+Movements in Issued Shares.*?(?=\n\s*III\.)", text, re.I | re.S)
    if not section_match:
        raise ValueError("issued-shares section not found")
    section = section_match.group(0)
    code_match = re.search(r"(?<!Multi-counter )Stock code(?: \(if listed(?: on SEHK)?\))?[^\n\d]{0,80}" + re.escape(code) + r"\b", section, re.I)
    if not code_match:
        raise LookupError("listed share class not found")
    following = section[code_match.end():code_match.end() + 3000]
    balance = re.search(r"Balance at close of the month\s+([\d,]+)(?:\s+([\d,]+)\s+([\d,]+))?", following, re.I)
    if not balance:
        raise ValueError("monthly closing balance not found")
    if balance.group(3):
        ex_treasury, treasury, total = map(number, balance.groups())
    else:
        total = ex_treasury = number(balance.group(1)); treasury = 0
    validate_shares(ex_treasury, treasury, total)
    return {"effective_date": datetime.strptime(period_match.group(1), "%d %B %Y").date(),
            "share_class": share_class_near(section, code_match.start()), "issued_shares": total,
            "treasury_shares": treasury, "issued_shares_ex_treasury": ex_treasury}


def parse_next_day(text: str, code: str) -> dict:
    code_match = re.search(r"(?<!Multi-counter )Stock code(?: \(if listed(?: on SEHK)?\))?[^\n\d]{0,80}" + re.escape(code) + r"\b", text, re.I)
    if not code_match:
        raise LookupError("listed share class not found")
    following = text[code_match.end():code_match.end() + 5000]
    balance = re.search(r"Closing balance as at(?:\s*\([^)]*\))?\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})\s+([\d,]+)(?:\s+([\d,]+)\s+([\d,]+))?", following, re.I)
    if not balance:
        raise ValueError("next-day closing balance not found")
    if balance.group(4):
        ex_treasury, treasury, total = map(number, balance.groups()[1:])
    else:
        total = ex_treasury = number(balance.group(2)); treasury = 0
    validate_shares(ex_treasury, treasury, total)
    return {"effective_date": datetime.strptime(balance.group(1), "%d %B %Y").date(),
            "share_class": share_class_near(text, code_match.start()), "issued_shares": total,
            "treasury_shares": treasury, "issued_shares_ex_treasury": ex_treasury}


def process(client: SupabaseRest, code: str, start: date, end: date, pause: float, dry_run: bool) -> tuple[int, int]:
    sid = stock_id(code)
    existing = set() if dry_run else client.parsed_documents(code, start, end + timedelta(days=40))
    documents: dict[str, dict] = {}
    for month_start, month_end in month_ranges(start, end):
        for item in search_filings(sid, month_start, month_end):
            documents[item["document_id"]] = item
        time.sleep(pause)
    written = failed = stock_failures = 0
    for item in sorted(documents.values(), key=lambda row: row["release_at"]):
        if item["document_id"] in existing:
            continue
        filing_type = "monthly_return" if re.search("Monthly Returns", item["title"], re.I) else "next_day_disclosure"
        filing = {"document_id": item["document_id"], "stock_code": code, "filing_type": filing_type,
                  "release_at": item["release_at"].isoformat(), "title": item["title"],
                  "source_url": item["source_url"], "parser_version": PARSER_VERSION}
        try:
            text = pdf_text(request_bytes(item["source_url"], timeout=90))
            values = parse_monthly(text, code) if filing_type == "monthly_return" else parse_next_day(text, code)
            filing.update(parse_status="parsed", parse_error=None)
            capital = {"stock_code": code, **values,
                       "effective_date": values["effective_date"].isoformat(),
                       "source_type": "hkex_monthly_return" if filing_type == "monthly_return" else "hkex_next_day_disclosure",
                       "source_priority": 80 if filing_type == "monthly_return" else 100,
                       "source_url": item["source_url"], "document_id": item["document_id"],
                       "release_at": item["release_at"].isoformat(), "parser_version": PARSER_VERSION}
            if dry_run:
                print(json.dumps(capital, ensure_ascii=False, default=str))
            else:
                client.upsert("hkex_share_capital_filings", [filing], "document_id")
                client.upsert("hk_issued_shares_official", [capital], "stock_code,effective_date,share_class")
            written += 1
        except LookupError as error:
            filing.update(parse_status="no_listed_class", parse_error=str(error)); failed += 1
            if not dry_run: client.upsert("hkex_share_capital_filings", [filing], "document_id")
        except Exception as error:
            filing.update(parse_status="failed", parse_error=str(error)[:1000]); failed += 1
            if not dry_run: client.upsert("hkex_share_capital_filings", [filing], "document_id")
            print(f"WARN {code} {item['document_id']}: {error}", flush=True)
        time.sleep(pause)
    return written, failed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--batch-start", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=50, help="0 processes all remaining stocks")
    parser.add_argument("--codes", help="comma-separated HK codes (testing/repair)")
    parser.add_argument("--pause", type=float, default=0.4)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    codes = [normalize_code(code) for code in args.codes.split(",")] if args.codes else universe_codes()
    stop = None if args.batch_size == 0 else args.batch_start + args.batch_size
    codes = codes[args.batch_start:stop]
    client = SupabaseRest(required=not args.dry_run)
    started = datetime.now(timezone.utc).isoformat()
    written = failed = stock_failures = 0
    try:
        for position, code in enumerate(codes, 1):
            print(f"[{position}/{len(codes)}] {code}", flush=True)
            try:
                added, errors = process(client, code, start, end, args.pause, args.dry_run)
                written += added; failed += errors
            except Exception as error:
                stock_failures += 1
                print(f"WARN {code}: stock processing failed after retries: {error}", flush=True)
        ratios = None if args.dry_run else client.rpc("refresh_hk_holding_ratios")
        if not args.dry_run:
            client.insert_run(started, start, end, "success" if failed == 0 and stock_failures == 0 else "partial", written,
                              {"stocks": len(codes), "documents_failed": failed, "stocks_failed": stock_failures,
                               "ratio_refresh": ratios,
                               "batch_start": args.batch_start, "parser_version": PARSER_VERSION})
    except Exception as error:
        if not args.dry_run:
            client.insert_run(started, start, end, "failed", written, {"error": str(error), "documents_failed": failed})
        raise
    print(json.dumps({"stocks": len(codes), "rows_written": written, "documents_failed": failed,
                      "stocks_failed": stock_failures}, ensure_ascii=False))
    return 1 if stock_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
