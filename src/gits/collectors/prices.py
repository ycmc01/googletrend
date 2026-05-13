"""Stock price and quarterly financials via yfinance."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf
from rich.console import Console

console = Console()


def fetch_prices(ticker: str, start: str = "2020-01-01", end: str | None = None) -> pd.DataFrame:
    """Daily OHLCV for ticker. Returns columns: date, open, high, low, close, adj_close, volume."""
    console.print(f"[cyan]Fetching prices for {ticker} from {start}[/cyan]")
    end = end or pd.Timestamp.now().strftime("%Y-%m-%d")
    df = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    if df.empty:
        raise RuntimeError(f"yfinance returned empty for {ticker}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    ).reset_index().rename(columns={"Date": "date"})
    df["ticker"] = ticker
    return df[["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]]


def fetch_quarterly_financials(ticker: str) -> pd.DataFrame:
    """Quarterly total revenue from yfinance. Returns: quarter_end, total_revenue_usd_m.

    Note: yfinance only has ~5 most recent quarters. For longer history, you must
    fill apple_revenue_weights.csv manually from 10-Q filings.
    """
    console.print(f"[cyan]Fetching quarterly financials for {ticker}[/cyan]")
    t = yf.Ticker(ticker)
    qf = t.quarterly_income_stmt
    if qf is None or qf.empty:
        return pd.DataFrame(columns=["quarter_end", "total_revenue_usd_m"])

    if "Total Revenue" in qf.index:
        rev = qf.loc["Total Revenue"]
    else:
        candidates = [i for i in qf.index if "revenue" in str(i).lower()]
        if not candidates:
            raise RuntimeError(f"No revenue row found for {ticker}; rows: {list(qf.index)[:10]}")
        rev = qf.loc[candidates[0]]

    df = rev.reset_index()
    df.columns = ["quarter_end", "total_revenue"]
    df["quarter_end"] = pd.to_datetime(df["quarter_end"]).dt.date
    df["total_revenue_usd_m"] = df["total_revenue"].astype(float) / 1_000_000
    df["ticker"] = ticker
    return df[["quarter_end", "ticker", "total_revenue_usd_m"]].sort_values("quarter_end")


def save_parquet(df: pd.DataFrame, raw_dir: Path, name: str) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    path = raw_dir / f"{name}_{today}.parquet"
    df.to_parquet(path, index=False)
    return path
