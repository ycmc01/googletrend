"""CLI: compute the GITS index from collected trends + manual segment weights.

Pre-requisites:
    1. reference/apple_revenue_weights.csv has been filled out
    2. python scripts/fetch_trends.py has been run
    3. python scripts/fetch_prices.py has been run

Usage:
    python scripts/compute_gits.py
    python scripts/compute_gits.py --geo US
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gits.config import WEIGHTS_CSV
from gits.engine.normalize import pivot_trends_wide
from gits.engine.weighting import compute_gits_index, load_weights_from_csv
from gits.storage.duckdb_io import (
    get_conn,
    init_schema,
    read_trends,
    upsert_segment_weights,
)

console = Console()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geo", default="WW")
    args = ap.parse_args()

    if not WEIGHTS_CSV.exists():
        console.print(f"[red]Missing {WEIGHTS_CSV}[/red]")
        return 1

    weights_long = load_weights_from_csv(WEIGHTS_CSV)
    if weights_long.empty:
        console.print(
            f"[yellow]No revenue data in {WEIGHTS_CSV.name}. "
            f"Fill in at least one fiscal quarter to proceed.[/yellow]"
        )
        return 1

    n_quarters = weights_long["quarter_end"].nunique()
    console.print(f"Loaded {n_quarters} quarter(s) of segment weights")

    with get_conn() as conn:
        init_schema(conn)
        upsert_segment_weights(conn, weights_long)
        trends_long = read_trends(conn, geo=args.geo)

    if trends_long.empty:
        console.print(f"[red]No trends data for geo={args.geo!r}. Run fetch_trends.py first.[/red]")
        return 1

    traffic_wide = pivot_trends_wide(trends_long)
    console.print(
        f"Trends matrix: {len(traffic_wide)} time points x {len(traffic_wide.columns)} segments "
        f"({traffic_wide.index.min().date()} → {traffic_wide.index.max().date()})"
    )

    gits = compute_gits_index(traffic_wide, weights_long)

    t = Table(title=f"GITS Index — last 12 periods ({args.geo})")
    t.add_column("Date")
    for col in gits.columns:
        t.add_column(col, justify="right")
    for idx, row in gits.tail(12).iterrows():
        t.add_row(str(idx.date()), *[f"{row[c]:.2f}" if row[c] == row[c] else "—" for c in gits.columns])
    console.print(t)

    out_path = Path(WEIGHTS_CSV).parent.parent / "data" / "processed" / f"gits_{args.geo}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gits.to_parquet(out_path)
    console.print(f"[green]GITS index saved -> {out_path}[/green]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
