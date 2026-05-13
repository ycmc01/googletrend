"""CLI: fetch AAPL prices and quarterly total revenue.

Usage:
    python scripts/fetch_prices.py
    python scripts/fetch_prices.py --ticker AAPL --start 2019-01-01
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gits.collectors.prices import fetch_prices, fetch_quarterly_financials, save_parquet
from gits.config import RAW_DIR
from gits.storage.duckdb_io import (
    get_conn,
    init_schema,
    upsert_prices,
    upsert_quarterly_revenue,
)

console = Console()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="AAPL")
    ap.add_argument("--start", default="2020-01-01")
    args = ap.parse_args()

    prices = fetch_prices(args.ticker, start=args.start)
    p_path = save_parquet(prices, RAW_DIR, f"prices_{args.ticker}")
    console.print(f"[green]Saved {len(prices)} price rows -> {p_path}[/green]")

    qf = fetch_quarterly_financials(args.ticker)
    q_path = save_parquet(qf, RAW_DIR, f"quarterly_rev_{args.ticker}")
    console.print(f"[green]Saved {len(qf)} quarterly revenue rows -> {q_path}[/green]")

    with get_conn() as conn:
        init_schema(conn)
        upsert_prices(conn, prices)
        upsert_quarterly_revenue(conn, qf)
        console.print("[green]Prices + quarterly revenue persisted to DuckDB[/green]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
