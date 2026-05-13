"""One-time migration: add ticker col to old AAPL parquet files and re-ingest into the
new DuckDB schema. Safe to run multiple times.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
from rich.console import Console

from gits.config import RAW_DIR
from gits.storage.duckdb_io import (
    get_conn,
    init_schema,
    upsert_prices,
    upsert_quarterly_revenue,
    upsert_trends,
)

console = Console()


def _add_ticker(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if "ticker" not in df.columns:
        df = df.copy()
        df["ticker"] = ticker
    return df


def main() -> int:
    with get_conn() as conn:
        init_schema(conn)

        # trends_WW_*.parquet was AAPL — old schema lacks ticker
        for f in sorted(RAW_DIR.glob("trends_WW_*.parquet")):
            df = pd.read_parquet(f)
            if "ticker" not in df.columns:
                df = _add_ticker(df, "AAPL")
            df = df[["ticker", "date", "segment", "rsv", "geo", "timeframe"]]
            n = upsert_trends(conn, df)
            console.print(f"[green]trends[/green] {f.name}: ingested {n} rows")

        # prices already had ticker col but re-ingest to be safe
        for f in sorted(RAW_DIR.glob("prices_*.parquet")):
            df = pd.read_parquet(f)
            n = upsert_prices(conn, df)
            console.print(f"[green]prices[/green] {f.name}: ingested {n} rows")

        # quarterly_rev parquet
        for f in sorted(RAW_DIR.glob("quarterly_rev_*.parquet")):
            df = pd.read_parquet(f).rename(columns={"quarter_end": "quarter_end"})
            if "ticker" not in df.columns:
                df["ticker"] = "AAPL"
            df = df[["ticker", "quarter_end", "total_revenue_usd_m"]]
            n = upsert_quarterly_revenue(conn, df)
            console.print(f"[green]q_rev[/green] {f.name}: ingested {n} rows")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
