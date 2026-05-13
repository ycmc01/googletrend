"""Thin client for Sysjust XQ API (https://mrtuat.xq.com.tw/SysjustMCP).

Documented in C:\\Users\\lee\\.claude\\skills\\XQAPI\\resources\\.
"""
from __future__ import annotations

import requests

BASE_URL = "https://mrtuat.xq.com.tw/SysjustMCP"
TIMEOUT = 20


def _norm_ticker(ticker: str) -> str:
    """'2330' -> '2330.TW'; 'AAPL' -> 'AAPL.US'; pass-through if already suffixed."""
    if "." in ticker:
        return ticker.upper()
    if ticker.isdigit():
        return f"{ticker}.TW"
    return f"{ticker.upper()}.US"


def get_basic_info(ticker: str, fields: str | None = None) -> dict:
    """GET /datamatrix/basic/information."""
    params = {"symbol": _norm_ticker(ticker)}
    if fields:
        params["fields"] = fields
    r = requests.get(f"{BASE_URL}/datamatrix/basic/information", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_quarterly_financial_report(ticker: str, count: int = 16) -> dict:
    """GET /datamatrix/finance?metrics=financial-report&period=Q.

    Returns dict with key 'financial-report' -> {ticker, period, fields[...]} where
    one of the fields has cName='營業收入淨額' (quarterly net revenue in TWD thousands).
    """
    params = {
        "symbol": _norm_ticker(ticker),
        "metrics": "financial-report",
        "count": count,
        "period": "Q",
    }
    r = requests.get(f"{BASE_URL}/datamatrix/finance", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_monthly_revenue(ticker: str, count: int = 36) -> dict:
    """GET /datamatrix/finance?metrics=revenue (台股月營收)."""
    params = {"symbol": _norm_ticker(ticker), "metrics": "revenue", "count": count}
    r = requests.get(f"{BASE_URL}/datamatrix/finance", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def extract_field(payload: dict, c_name: str) -> list[tuple[str, float]]:
    """Pull (date, value) pairs for the given cName out of an XQAPI response.

    Works for both shapes: {"financial-report": {...}} or basic-info {fields:[...]}.
    Returns empty list if not found. Values are coerced to float (NaN on failure).
    """
    nodes: list[dict] = []
    if "fields" in payload:
        nodes = payload["fields"]
    else:
        for v in payload.values():
            if isinstance(v, dict) and "fields" in v:
                nodes.extend(v["fields"])
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and "fields" in item:
                        nodes.extend(item["fields"])
    for field in nodes:
        if field.get("cName") == c_name:
            out = []
            for v in field.get("values", []):
                try:
                    out.append((v["date"], float(str(v["value"]).replace(",", ""))))
                except (ValueError, TypeError, KeyError):
                    continue
            return out
    return []


def quarterly_revenue_to_rows(payload: dict, ticker: str) -> list[dict]:
    """Convert financial-report Q response to gits revenue_weights row schema (Total segment).

    Values in XQAPI 'financial-report' are in 千元 (TWD thousands).
    We convert to millions USD-equivalent? NO — we keep TWD millions to stay aligned with
    the company's reported currency. Use TWD millions: value / 1000.
    """
    fields_iter = payload.get("financial-report", payload)
    raw_pairs = extract_field({"_": fields_iter} if "fields" in fields_iter else fields_iter, "營業收入淨額")
    if not raw_pairs:
        # fallback: try '營業收入'
        raw_pairs = extract_field({"_": fields_iter} if "fields" in fields_iter else fields_iter, "營業收入")

    rows = []
    for date_str, val in raw_pairs:
        # date format YYYYQn
        if "Q" in date_str:
            year, qn = date_str.split("Q")
            quarter_end = _quarter_end_date(int(year), int(qn))
            rows.append({
                "ticker": ticker.upper(),
                "fiscal_quarter": f"Q{qn} FY{year}",
                "quarter_end_date": quarter_end,
                "segment": "Total",
                "revenue_usd_m": val / 1000,  # 千元 → 百萬元
                "total_revenue_usd_m": val / 1000,
                "source_filing": f"XQAPI financial-report Q",
            })
    return rows


def _quarter_end_date(year: int, qn: int) -> str:
    """Calendar quarter end as YYYY-MM-DD. Taiwan firms use calendar quarters."""
    mm_dd = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[qn]
    return f"{year}-{mm_dd}"
