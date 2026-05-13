"""Read/write helpers for the three reference CSVs (companies, segments, revenue_weights).

All functions are ticker-aware. Each CSV holds data for ALL companies; functions
filter by ticker as needed.
"""
from __future__ import annotations

import pandas as pd

from gits.config import COMPANIES_CSV, REVENUE_WEIGHTS_CSV, SEGMENTS_CSV

COMPANY_COLS = ["ticker", "name", "fiscal_year_end_month", "notes"]
SEGMENT_COLS = ["ticker", "segment_name", "trends_topic_id", "trends_keywords", "exclude_terms", "notes"]
WEIGHT_COLS = ["ticker", "fiscal_quarter", "quarter_end_date", "segment", "revenue_usd_m", "total_revenue_usd_m", "source_filing"]


def load_companies() -> pd.DataFrame:
    if not COMPANIES_CSV.exists():
        return pd.DataFrame(columns=COMPANY_COLS)
    return pd.read_csv(COMPANIES_CSV, dtype={"ticker": str})


def save_companies(df: pd.DataFrame) -> None:
    df = df.copy()
    df["ticker"] = df["ticker"].astype(str)
    df = df[COMPANY_COLS].drop_duplicates(subset=["ticker"], keep="last")
    df.to_csv(COMPANIES_CSV, index=False)


def get_company(ticker: str) -> pd.Series | None:
    df = load_companies()
    matches = df[df["ticker"].str.upper() == ticker.upper()]
    return matches.iloc[0] if len(matches) else None


def load_segments(ticker: str | None = None) -> pd.DataFrame:
    if not SEGMENTS_CSV.exists():
        return pd.DataFrame(columns=SEGMENT_COLS)
    df = pd.read_csv(SEGMENTS_CSV, dtype={"ticker": str})
    if ticker is not None:
        df = df[df["ticker"].astype(str).str.upper() == ticker.upper()].reset_index(drop=True)
    return df


def save_segments(df: pd.DataFrame) -> None:
    df = df.copy()
    df["ticker"] = df["ticker"].astype(str)
    df = df[SEGMENT_COLS].drop_duplicates(subset=["ticker", "segment_name"], keep="last")
    df = df.sort_values(["ticker", "segment_name"]).reset_index(drop=True)
    df.to_csv(SEGMENTS_CSV, index=False)


def load_weights(ticker: str | None = None) -> pd.DataFrame:
    if not REVENUE_WEIGHTS_CSV.exists():
        return pd.DataFrame(columns=WEIGHT_COLS)
    df = pd.read_csv(REVENUE_WEIGHTS_CSV, dtype={"ticker": str})
    # robust parse with format='mixed' to handle YYYY-MM-DD and YYYY-MM-DD HH:MM:SS
    df["quarter_end_date"] = pd.to_datetime(df["quarter_end_date"], errors="coerce", format="mixed")
    if ticker is not None:
        df = df[df["ticker"].astype(str).str.upper() == ticker.upper()].reset_index(drop=True)
    return df


def save_weights(df: pd.DataFrame) -> None:
    df = df.copy()
    # Cast to string first so pd.to_datetime sees a uniform input (concat between
    # datetime64 and object columns is fragile in pandas 3.0).
    # CRITICAL: format='mixed' lets pandas infer per-row format. Without this,
    # pandas picks ONE format from the first row and silently fails on others —
    # e.g. '2024-06-29 00:00:00' wins, then '2026-12-31' becomes NaT.
    df["quarter_end_date"] = df["quarter_end_date"].astype(str)
    df["quarter_end_date"] = pd.to_datetime(
        df["quarter_end_date"], errors="coerce", format="mixed"
    ).dt.strftime("%Y-%m-%d")
    # Drop rows where the date couldn't be parsed
    df = df.dropna(subset=["quarter_end_date"])
    df = df[WEIGHT_COLS].drop_duplicates(subset=["ticker", "quarter_end_date", "segment"], keep="last")
    df = df.sort_values(["ticker", "quarter_end_date", "segment"]).reset_index(drop=True)
    df.to_csv(REVENUE_WEIGHTS_CSV, index=False)


def list_tickers() -> list[str]:
    return sorted(load_companies()["ticker"].dropna().astype(str).str.upper().unique().tolist())
