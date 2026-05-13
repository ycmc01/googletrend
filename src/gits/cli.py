"""Unified CLI for the GITS Scanner — `gits <command> ...`.

Run via:
    python scripts/gits.py <command> ...

Sub-commands:
    company   add | list | show | remove
    segment   add | list | show | remove
    weight    add | import | list
    fetch     trends | prices
    compute
    report
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from gits.reference import (
    COMPANY_COLS,
    SEGMENT_COLS,
    WEIGHT_COLS,
    get_company,
    list_tickers,
    load_companies,
    load_segments,
    load_weights,
    save_companies,
    save_segments,
    save_weights,
)

console = Console()


# ---------------- company commands ----------------

def cmd_company_add(args) -> int:
    ticker = args.ticker.upper()
    name = args.name or Prompt.ask("Company name")
    fy_end = args.fy_end_month or int(Prompt.ask("Fiscal year-end month (1-12)", default="12"))
    notes = args.notes or Prompt.ask("Notes (optional)", default="")

    df = load_companies()
    if (df["ticker"].str.upper() == ticker).any():
        if not Confirm.ask(f"[yellow]{ticker} already exists. Overwrite?[/yellow]", default=False):
            console.print("[yellow]Aborted.[/yellow]")
            return 1
        df = df[df["ticker"].str.upper() != ticker]

    new_row = pd.DataFrame([{
        "ticker": ticker, "name": name,
        "fiscal_year_end_month": fy_end, "notes": notes,
    }])
    save_companies(pd.concat([df, new_row], ignore_index=True))
    console.print(f"[green]OK[/green] Added {ticker} ({name}) to companies.csv")
    return 0


def cmd_company_list(args) -> int:
    df = load_companies()
    if df.empty:
        console.print("[yellow]No companies registered. Use `gits company add TICKER`.[/yellow]")
        return 0
    t = Table(title="Registered Companies", show_header=True)
    for col in COMPANY_COLS:
        t.add_column(col)
    for _, row in df.iterrows():
        t.add_row(*[str(row[c]) if pd.notna(row[c]) else "" for c in COMPANY_COLS])
    console.print(t)
    return 0


def cmd_company_show(args) -> int:
    ticker = args.ticker.upper()
    row = get_company(ticker)
    if row is None:
        console.print(f"[red]{ticker} not found.[/red]")
        return 1
    console.print(f"[bold]{ticker}[/bold] — {row['name']}")
    console.print(f"  FY end month: {row['fiscal_year_end_month']}")
    if pd.notna(row.get("notes")) and row["notes"]:
        console.print(f"  Notes: {row['notes']}")

    segs = load_segments(ticker)
    console.print(f"\n[bold]Segments[/bold] ({len(segs)}):")
    for _, s in segs.iterrows():
        kw_count = len(str(s["trends_keywords"]).split("|")) if pd.notna(s["trends_keywords"]) else 0
        console.print(f"  • {s['segment_name']}: {kw_count} keywords")

    wts = load_weights(ticker)
    if not wts.empty:
        n_q = wts["quarter_end_date"].nunique()
        latest = wts["quarter_end_date"].max()
        console.print(f"\n[bold]Revenue weights[/bold]: {n_q} quarters loaded (latest: {latest.date()})")
    return 0


def cmd_company_remove(args) -> int:
    ticker = args.ticker.upper()
    if not Confirm.ask(f"[red]Remove {ticker} (and its segments + weights)?[/red]", default=False):
        return 1
    save_companies(load_companies().query("ticker.str.upper() != @ticker"))
    save_segments(load_segments().query("ticker.str.upper() != @ticker"))
    save_weights(load_weights().query("ticker.str.upper() != @ticker"))
    console.print(f"[green]OK[/green] Removed {ticker} and all associated data")
    return 0


# ---------------- segment commands ----------------

def _multi_line_prompt(label: str, terminator: str = "(blank line to finish)") -> list[str]:
    console.print(f"[cyan]{label}[/cyan] {terminator}:")
    items: list[str] = []
    while True:
        line = console.input(f"  {len(items) + 1}> ").strip()
        if not line:
            break
        items.append(line)
    return items


def cmd_segment_add(args) -> int:
    ticker = args.ticker.upper()
    if get_company(ticker) is None:
        console.print(f"[red]{ticker} not registered. Run `gits company add {ticker}` first.[/red]")
        return 1

    segments_df = load_segments(ticker)
    if len(segments_df) >= 5:
        console.print(
            f"[yellow]Warning: {ticker} already has {len(segments_df)} segments. "
            "pytrends only allows 5 per query for cross-segment calibration. "
            "Adding more means you'll need to split queries.[/yellow]"
        )

    segment_name = args.name or Prompt.ask("Segment name (e.g. 'iPhone', 'Data Center')")

    existing = segments_df[segments_df["segment_name"].str.lower() == segment_name.lower()]
    if not existing.empty:
        if not Confirm.ask(f"[yellow]'{segment_name}' already exists for {ticker}. Overwrite?[/yellow]", default=False):
            return 1

    console.print()
    keywords = _multi_line_prompt("Keywords (one per line)")
    if not keywords:
        console.print("[red]At least one keyword required.[/red]")
        return 1

    console.print()
    excludes = _multi_line_prompt("Exclude terms (one per line, blank to skip)")
    topic_id = Prompt.ask("\nTopic ID (e.g. /m/04ck9_, blank to skip)", default="").strip()
    notes = Prompt.ask("Notes (optional)", default="")

    new_row = pd.DataFrame([{
        "ticker": ticker,
        "segment_name": segment_name,
        "trends_topic_id": topic_id,
        "trends_keywords": "|".join(keywords),
        "exclude_terms": "|".join(excludes),
        "notes": notes,
    }])
    all_segments = load_segments()
    all_segments = all_segments[
        ~((all_segments["ticker"].str.upper() == ticker) & (all_segments["segment_name"].str.lower() == segment_name.lower()))
    ]
    save_segments(pd.concat([all_segments, new_row], ignore_index=True))

    console.print(f"\n[green]OK[/green] Added segment [bold]{segment_name}[/bold] to {ticker}")
    console.print(f"  Keywords ({len(keywords)}): {' | '.join(keywords)}")
    if excludes:
        console.print(f"  Excludes ({len(excludes)}): {' | '.join(excludes)}")
    return 0


def cmd_segment_list(args) -> int:
    ticker = args.ticker.upper()
    segs = load_segments(ticker)
    if segs.empty:
        console.print(f"[yellow]No segments for {ticker}.[/yellow]")
        return 0

    t = Table(title=f"{ticker} Segments", show_header=True)
    t.add_column("#", style="cyan", width=3)
    t.add_column("Segment", style="bold")
    t.add_column("Keywords")
    t.add_column("Excludes")
    t.add_column("Topic ID")
    for i, (_, row) in enumerate(segs.iterrows(), 1):
        kws = str(row["trends_keywords"] or "").replace("|", ", ")
        excl = str(row["exclude_terms"] or "").replace("|", ", ") if pd.notna(row["exclude_terms"]) else ""
        topic = str(row["trends_topic_id"] or "") if pd.notna(row["trends_topic_id"]) else ""
        t.add_row(str(i), str(row["segment_name"]), kws, excl, topic)
    console.print(t)
    return 0


def cmd_segment_show(args) -> int:
    ticker = args.ticker.upper()
    segs = load_segments(ticker)
    match = segs[segs["segment_name"].str.lower() == args.name.lower()]
    if match.empty:
        console.print(f"[red]{ticker}/{args.name} not found.[/red]")
        return 1
    s = match.iloc[0]
    console.print(f"[bold]{ticker} — {s['segment_name']}[/bold]")
    for col in ["trends_topic_id", "trends_keywords", "exclude_terms", "notes"]:
        val = s[col] if pd.notna(s[col]) else "(empty)"
        console.print(f"  {col}: {val}")
    return 0


def cmd_segment_remove(args) -> int:
    ticker = args.ticker.upper()
    if not Confirm.ask(f"[red]Remove {ticker}/{args.name}?[/red]", default=False):
        return 1
    all_segs = load_segments()
    mask = (all_segs["ticker"].str.upper() == ticker) & (all_segs["segment_name"].str.lower() == args.name.lower())
    if not mask.any():
        console.print(f"[red]{ticker}/{args.name} not found.[/red]")
        return 1
    save_segments(all_segs[~mask])
    console.print(f"[green]OK[/green] Removed {ticker}/{args.name}")
    return 0


# ---------------- weight commands ----------------

def cmd_weight_import(args) -> int:
    ticker = args.ticker.upper()
    if get_company(ticker) is None:
        console.print(f"[red]{ticker} not registered.[/red]")
        return 1

    src = pd.read_csv(args.csv, parse_dates=["quarter_end_date"])
    if "ticker" not in src.columns:
        src["ticker"] = ticker

    missing = set(WEIGHT_COLS) - set(src.columns)
    if missing:
        console.print(f"[red]CSV missing columns: {missing}[/red]")
        console.print(f"Expected: {WEIGHT_COLS}")
        return 1

    src = src[src["ticker"].str.upper() == ticker]
    if src.empty:
        console.print(f"[yellow]No rows for {ticker} in CSV.[/yellow]")
        return 1

    all_wts = load_weights()
    keep_mask = ~all_wts.apply(
        lambda r: r["ticker"].upper() == ticker
        and (r["quarter_end_date"], r["segment"]) in zip(src["quarter_end_date"], src["segment"], strict=False),
        axis=1,
    ) if not all_wts.empty else pd.Series([], dtype=bool)
    if not all_wts.empty:
        all_wts = all_wts[keep_mask]

    save_weights(pd.concat([all_wts, src], ignore_index=True))
    n_q = src["quarter_end_date"].nunique()
    console.print(f"[green]OK[/green] Imported {len(src)} rows ({n_q} quarters) for {ticker}")
    return 0


def cmd_weight_list(args) -> int:
    ticker = args.ticker.upper()
    wts = load_weights(ticker)
    if wts.empty:
        console.print(f"[yellow]No weights for {ticker}.[/yellow]")
        return 0

    wide = wts.pivot_table(
        index=["fiscal_quarter", "quarter_end_date"],
        columns="segment",
        values="revenue_usd_m",
        aggfunc="first",
    ).reset_index().sort_values("quarter_end_date")
    totals = wts.drop_duplicates("quarter_end_date").set_index("quarter_end_date")["total_revenue_usd_m"]
    wide["total"] = wide["quarter_end_date"].map(totals)

    t = Table(title=f"{ticker} Revenue by Segment (USD millions)", show_header=True)
    t.add_column("Quarter")
    t.add_column("Q-End")
    seg_cols = [c for c in wide.columns if c not in ("fiscal_quarter", "quarter_end_date", "total")]
    for c in seg_cols:
        t.add_column(c, justify="right")
    t.add_column("Total", justify="right", style="bold")
    for _, row in wide.iterrows():
        t.add_row(
            str(row["fiscal_quarter"]),
            str(pd.Timestamp(row["quarter_end_date"]).date()),
            *[f"{row[c]:,.0f}" if pd.notna(row[c]) else "—" for c in seg_cols],
            f"{row['total']:,.0f}" if pd.notna(row["total"]) else "—",
        )
    console.print(t)
    return 0


# ---------------- pipeline commands ----------------

def cmd_fetch_trends(args) -> int:
    from gits.collectors.trends import fetch_cross_segment_trends, save_trends_parquet
    from gits.config import RAW_DIR
    from gits.storage.duckdb_io import get_conn, init_schema, upsert_trends

    ticker = args.ticker.upper()
    segments = load_segments(ticker)
    if segments.empty:
        console.print(f"[red]No segments defined for {ticker}. Run `gits segment add {ticker}` first.[/red]")
        return 1

    df = fetch_cross_segment_trends(segments, timeframe=args.timeframe, geo=args.geo or "", ticker=ticker)
    geo_tag = args.geo or "WW"
    path = save_trends_parquet(df, RAW_DIR, f"trends_{ticker}_{geo_tag}")
    console.print(f"[green]OK[/green] Saved {len(df)} rows ->{path}")

    with get_conn() as conn:
        init_schema(conn)
        n = upsert_trends(conn, df)
        console.print(f"[green]OK[/green] Upserted {n} rows into DuckDB")
    return 0


def cmd_fetch_prices(args) -> int:
    from gits.collectors.prices import fetch_prices, fetch_quarterly_financials, save_parquet
    from gits.config import RAW_DIR
    from gits.storage.duckdb_io import get_conn, init_schema, upsert_prices, upsert_quarterly_revenue

    ticker = args.ticker.upper()
    prices = fetch_prices(ticker, start=args.start)
    save_parquet(prices, RAW_DIR, f"prices_{ticker}")
    qf = fetch_quarterly_financials(ticker)
    save_parquet(qf, RAW_DIR, f"quarterly_rev_{ticker}")

    with get_conn() as conn:
        init_schema(conn)
        upsert_prices(conn, prices)
        upsert_quarterly_revenue(conn, qf)
    console.print(f"[green]OK[/green] {ticker}: {len(prices)} price rows, {len(qf)} quarterly rev rows persisted")
    return 0


def cmd_compute(args) -> int:
    from gits.engine.normalize import pivot_trends_wide
    from gits.engine.weighting import compute_gits_index, load_weights_long
    from gits.storage.duckdb_io import get_conn, init_schema, read_trends, upsert_segment_weights

    ticker = args.ticker.upper()
    weights_long = load_weights_long(ticker)
    if weights_long.empty:
        console.print(f"[red]No revenue weights for {ticker}. Fill reference/revenue_weights.csv.[/red]")
        return 1

    weights_for_db = weights_long.assign(ticker=ticker)[["ticker", "quarter_end", "segment", "revenue_usd_m", "weight_pct"]]
    with get_conn() as conn:
        init_schema(conn)
        upsert_segment_weights(conn, weights_for_db)
        trends_long = read_trends(conn, ticker=ticker, geo=args.geo)

    if trends_long.empty:
        console.print(f"[red]No trends for {ticker}/{args.geo}. Run `gits fetch trends {ticker}` first.[/red]")
        return 1

    traffic_wide = pivot_trends_wide(trends_long)
    gits = compute_gits_index(traffic_wide, weights_long)
    console.print(f"[green]OK[/green] GITS computed for {ticker}: {len(gits)} time points")

    out_dir = Path(__file__).resolve().parents[2] / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"gits_{ticker}_{args.geo}.parquet"
    gits.to_parquet(out_path)
    console.print(f"[green]OK[/green] Saved ->{out_path}")

    t = Table(title=f"GITS — last 8 periods ({ticker}, {args.geo})", show_header=True)
    t.add_column("Date")
    for col in gits.columns:
        t.add_column(col, justify="right")
    for idx, row in gits.tail(8).iterrows():
        t.add_row(str(idx.date()), *[f"{v:.2f}" if pd.notna(v) else "—" for v in row])
    console.print(t)
    return 0


def cmd_report(args) -> int:
    """Execute the parameterized notebook with the chosen ticker ->HTML."""
    import os
    import subprocess

    from gits.config import NOTEBOOKS_DIR

    ticker = args.ticker.upper()
    nb_in = NOTEBOOKS_DIR / "01_poc_template.ipynb"
    nb_alt = NOTEBOOKS_DIR / "01_apple_poc.ipynb"
    nb_path = nb_in if nb_in.exists() else nb_alt
    if not nb_path.exists():
        console.print(f"[red]No notebook found at {nb_in} or {nb_alt}.[/red]")
        return 1

    out_html = NOTEBOOKS_DIR / f"report_{ticker}.html"
    env = os.environ.copy()
    env["GITS_TICKER"] = ticker

    console.print(f"[cyan]Executing notebook for {ticker} ->{out_html.name}[/cyan]")
    result = subprocess.run(
        [
            sys.executable, "-m", "jupyter", "nbconvert",
            "--to", "html", "--execute", str(nb_path),
            "--output", out_html.name,
        ],
        cwd=str(NOTEBOOKS_DIR),
        env=env,
    )
    if result.returncode == 0:
        console.print(f"[green]OK[/green] Report ->{out_html}")
    return result.returncode


# ---------------- argparse wiring ----------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gits", description="GITS Scanner CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    # company
    pc = sub.add_parser("company", help="Manage company registry")
    pcs = pc.add_subparsers(dest="action", required=True)
    pca = pcs.add_parser("add"); pca.add_argument("ticker"); pca.add_argument("name", nargs="?")
    pca.add_argument("--fy-end-month", type=int); pca.add_argument("--notes", default=""); pca.set_defaults(func=cmd_company_add)
    pcl = pcs.add_parser("list"); pcl.set_defaults(func=cmd_company_list)
    pcsh = pcs.add_parser("show"); pcsh.add_argument("ticker"); pcsh.set_defaults(func=cmd_company_show)
    pcr = pcs.add_parser("remove"); pcr.add_argument("ticker"); pcr.set_defaults(func=cmd_company_remove)

    # segment
    ps = sub.add_parser("segment", help="Manage segment keyword groups (the main key-in tool)")
    pss = ps.add_subparsers(dest="action", required=True)
    psa = pss.add_parser("add", help="Interactively add a new segment + keywords"); psa.add_argument("ticker")
    psa.add_argument("--name", help="Segment name (skipped prompt if given)")
    psa.set_defaults(func=cmd_segment_add)
    psl = pss.add_parser("list"); psl.add_argument("ticker"); psl.set_defaults(func=cmd_segment_list)
    pssh = pss.add_parser("show"); pssh.add_argument("ticker"); pssh.add_argument("name"); pssh.set_defaults(func=cmd_segment_show)
    psr = pss.add_parser("remove"); psr.add_argument("ticker"); psr.add_argument("name"); psr.set_defaults(func=cmd_segment_remove)

    # weight
    pw = sub.add_parser("weight", help="Manage revenue weights")
    pws = pw.add_subparsers(dest="action", required=True)
    pwi = pws.add_parser("import", help="Bulk import from a CSV file"); pwi.add_argument("ticker"); pwi.add_argument("--csv", required=True); pwi.set_defaults(func=cmd_weight_import)
    pwl = pws.add_parser("list"); pwl.add_argument("ticker"); pwl.set_defaults(func=cmd_weight_list)

    # fetch
    pf = sub.add_parser("fetch", help="Fetch raw data")
    pfs = pf.add_subparsers(dest="action", required=True)
    pft = pfs.add_parser("trends"); pft.add_argument("ticker"); pft.add_argument("--geo", default=""); pft.add_argument("--timeframe", default="today 5-y"); pft.set_defaults(func=cmd_fetch_trends)
    pfp = pfs.add_parser("prices"); pfp.add_argument("ticker"); pfp.add_argument("--start", default="2020-01-01"); pfp.set_defaults(func=cmd_fetch_prices)

    # compute
    pco = sub.add_parser("compute"); pco.add_argument("ticker"); pco.add_argument("--geo", default="WW"); pco.set_defaults(func=cmd_compute)

    # report
    pr = sub.add_parser("report", help="Generate HTML notebook report"); pr.add_argument("ticker"); pr.set_defaults(func=cmd_report)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
