"""Smoke test: hit XQAPI for 2330 TSMC and convert to gits row format."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))

from lib.xqapi import (
    get_basic_info,
    get_quarterly_financial_report,
    quarterly_revenue_to_rows,
)

print("=== 2330 basic info ===")
bi = get_basic_info("2330")
for f in bi.get("fields", [])[:6]:
    cname = f.get("cName", "")
    val = f.get("values", [{}])[0].get("value", "")
    print(f"  {cname}: {val}")

print("\n=== 2330 quarterly revenue (last 8 quarters) ===")
fin = get_quarterly_financial_report("2330", count=8)
rows = quarterly_revenue_to_rows(fin, "2330")
for r in rows[:8]:
    print(f"  {r['fiscal_quarter']:>12} {r['quarter_end_date']}  revenue: {r['revenue_usd_m']:>12,.0f} M (TWD)")

print(f"\nTotal rows: {len(rows)}")
