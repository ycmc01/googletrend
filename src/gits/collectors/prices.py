"""Stock price collector — XQAPI K-line (daily) for both TW and US tickers.

XQAPI returns adjusted daily K (freqType=11) for TW, regular daily (freqType=8)
for US. Both are stored with adj_close = close.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from rich.console import Console

from gits.xqapi import get_kline, kline_to_prices_df

console = Console()


def fetch_prices(ticker: str, count: int = 1500) -> pd.DataFrame:
    """Daily OHLCV for ticker via XQAPI. Returns the gits prices schema."""
    console.print(f"[cyan]Fetching prices for {ticker} via XQAPI (count={count})[/cyan]")
    payload = get_kline(ticker, count=count)
    df = kline_to_prices_df(payload, ticker)
    if df.empty:
        raise RuntimeError(
            f"XQAPI returned no kline data for {ticker}. "
            f"Title: {payload.get('title')}, total={payload.get('total')}"
        )
    return df


def save_parquet(df: pd.DataFrame, raw_dir: Path, name: str) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    path = raw_dir / f"{name}_{today}.parquet"
    df.to_parquet(path, index=False)
    return path
