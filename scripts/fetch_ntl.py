"""CLI: 從 Google Earth Engine 抓取所有 ROI 的月度夜間燈光資料。

前置：
    1. 已 pip install earthengine-api（pyproject 已含）
    2. 已執行 `python -m ee authenticate` 完成 Google 認證

使用：
    python scripts/fetch_ntl.py
    python scripts/fetch_ntl.py --start 2018-01-01
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rich.console import Console

from gits.nightlights import fetch_all_rois, load_rois, save_cached

console = Console()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2014-01-01", help="起始日期 YYYY-MM-DD")
    args = ap.parse_args()

    rois = load_rois()
    console.print(f"[cyan]從 GEE 抓取 {len(rois)} 個 ROI 的夜間燈光時序…[/cyan]")
    console.print(f"  ROIs: {rois['roi_name'].tolist()}")
    console.print(f"  起始日: {args.start}")
    console.print()

    try:
        df = fetch_all_rois(start=args.start)
    except RuntimeError as e:
        console.print(f"[red]GEE 認證失敗：[/red]\n{e}")
        return 1

    if df.empty:
        console.print("[yellow]沒抓到任何資料[/yellow]")
        return 1

    path = save_cached(df)
    console.print(f"[green]OK[/green] 已存 {len(df)} 列 -> {path}")
    console.print(f"  ROIs: {df['roi_name'].nunique()}")
    console.print(f"  期間: {df['date'].min().date()} ~ {df['date'].max().date()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
