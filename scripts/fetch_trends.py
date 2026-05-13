"""CLI: fetch cross-segment Google Trends data and persist to parquet + DuckDB.

Usage:
    python scripts/fetch_trends.py                       # WW, 5y
    python scripts/fetch_trends.py --geo US --timeframe "today 5-y"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gits.collectors.trends import fetch_cross_segment_trends, save_trends_parquet
from gits.config import RAW_DIR, SEGMENTS_CSV
from gits.storage.duckdb_io import get_conn, init_schema, upsert_trends

console = Console()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geo", default="", help="'' = worldwide, 'US' = US, 'TW' = Taiwan")
    ap.add_argument("--timeframe", default="today 5-y")
    args = ap.parse_args()

    if not SEGMENTS_CSV.exists():
        console.print(f"[red]Missing {SEGMENTS_CSV}[/red]")
        return 1
    segments = pd.read_csv(SEGMENTS_CSV)
    console.print(f"Loaded {len(segments)} segments from {SEGMENTS_CSV.name}")

    df = fetch_cross_segment_trends(segments, timeframe=args.timeframe, geo=args.geo)
    geo_tag = args.geo or "WW"
    parquet_path = save_trends_parquet(df, RAW_DIR, f"trends_{geo_tag}")
    console.print(f"[green]Saved {len(df)} rows -> {parquet_path}[/green]")

    with get_conn() as conn:
        init_schema(conn)
        n = upsert_trends(conn, df)
        console.print(f"[green]Upserted {n} rows into DuckDB trends table[/green]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
