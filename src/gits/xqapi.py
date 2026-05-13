"""Sysjust XQ API client — REST wrapper around https://mrtuat.xq.com.tw/SysjustMCP.

Supports both Taiwan (`.TW`) and US (`.US`) symbols. K-line uses adjusted daily
(freqType=11) for TW where available, and regular daily (freqType=8) for US
where adjusted is not supported.
"""
from __future__ import annotations

import pandas as pd
import requests

BASE_URL = "https://mrtuat.xq.com.tw/SysjustMCP"
TIMEOUT = 30


def norm_ticker(ticker: str) -> str:
    """'2330' -> '2330.TW'; 'AAPL' -> 'AAPL.US'; pass-through if already suffixed."""
    if "." in ticker:
        return ticker.upper()
    if ticker.isdigit():
        return f"{ticker}.TW"
    return f"{ticker.upper()}.US"


def market_of(ticker: str) -> str:
    """Return market suffix (TW, US, HK, ...)."""
    return norm_ticker(ticker).split(".", 1)[1]


# ---------------- basic info & financials ----------------

def get_basic_info(ticker: str, fields: str | None = None) -> dict:
    """GET /datamatrix/basic/information."""
    params = {"symbol": norm_ticker(ticker)}
    if fields:
        params["fields"] = fields
    r = requests.get(f"{BASE_URL}/datamatrix/basic/information", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_quarterly_financial_report(ticker: str, count: int = 16) -> dict:
    """GET /datamatrix/finance?metrics=financial-report&period=Q."""
    params = {
        "symbol": norm_ticker(ticker),
        "metrics": "financial-report",
        "count": count,
        "period": "Q",
    }
    r = requests.get(f"{BASE_URL}/datamatrix/finance", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def get_monthly_revenue(ticker: str, count: int = 36) -> dict:
    """GET /datamatrix/finance?metrics=revenue (台股月營收)."""
    params = {"symbol": norm_ticker(ticker), "metrics": "revenue", "count": count}
    r = requests.get(f"{BASE_URL}/datamatrix/finance", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# ---------------- K-line (prices) ----------------

def get_kline(ticker: str, count: int = 1500, freq_type: int | None = None) -> dict:
    """GET /symbolinfo/kline.

    `freq_type`: 8 = daily, 11 = adjusted daily. If None, auto-pick 11 for TW,
    8 for everything else (XQAPI returns total=0 for US on freqType=11).

    Note: returned data is in REVERSE chronological order (newest first).
    """
    sym = norm_ticker(ticker)
    if freq_type is None:
        freq_type = 11 if sym.endswith(".TW") else 8
    params = {"stockID": sym, "freqType": freq_type, "count": count, "baseDate": "0"}
    r = requests.get(f"{BASE_URL}/symbolinfo/kline", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def kline_to_prices_df(payload: dict, ticker: str) -> pd.DataFrame:
    """Convert /symbolinfo/kline response to the gits prices schema.

    Output columns: date, ticker, open, high, low, close, adj_close, volume.
    For TW with freqType=11 the close IS adjusted (we set adj_close=close).
    For US with freqType=8 the prices are NOT adjusted; adj_close=close anyway.
    """
    rows = payload.get("data", [])
    if not rows:
        return pd.DataFrame(columns=["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"])

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.date
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    df["adj_close"] = df["close"]
    bare = norm_ticker(ticker).split(".", 1)[0]
    df["ticker"] = bare
    return df.sort_values("date").reset_index(drop=True)[
        ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]
    ]


# ---------------- field extraction helpers ----------------

def extract_field(payload: dict, c_name: str) -> list[tuple[str, float]]:
    """Pull (date, value) pairs for the given cName out of an XQAPI payload."""
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
    """Convert financial-report Q response to revenue_weights row schema.

    Single 'Total' segment per quarter. Handles XQAPI's two quirks:
      * Unit is per-market: TW returns '1000' (千元) → divide by 1000 to get millions.
                            US returns '1000000' (millions) → no division.
      * Date format is per-market: TW returns 'YYYYQn', US returns 'YYYY/Qn'.
    """
    fields_iter = payload.get("financial-report", payload)
    nodes = fields_iter.get("fields", []) if "fields" in fields_iter else []
    target = None
    for f in nodes:
        if f.get("cName") in ("營業收入淨額", "營業收入"):
            target = f
            break
    if target is None:
        return []

    unit = str(target.get("unit", "")).strip()
    if unit in ("1000", "千元"):
        divisor = 1000.0
    elif unit in ("1000000", "百萬"):
        divisor = 1.0
    else:
        divisor = 1000.0  # conservative default for unknown units

    bare = norm_ticker(ticker).split(".", 1)[0]
    rows = []
    for v in target.get("values", []):
        date_str = str(v.get("date", "")).replace("/", "")  # '2026/Q2' → '2026Q2'
        try:
            raw = float(str(v["value"]).replace(",", ""))
        except (ValueError, KeyError, TypeError):
            continue
        if "Q" not in date_str:
            continue
        try:
            year, qn = date_str.split("Q")
            qn_int = int(qn)
        except (ValueError, IndexError):
            continue
        mm_dd = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}.get(qn_int)
        if not mm_dd:
            continue
        revenue_m = raw / divisor
        rows.append({
            "ticker": bare,
            "fiscal_quarter": f"Q{qn} FY{year}",
            "quarter_end_date": f"{year}-{mm_dd}",
            "segment": "Total",
            "revenue_usd_m": revenue_m,
            "total_revenue_usd_m": revenue_m,
            "source_filing": "XQAPI financial-report Q",
        })
    return rows
