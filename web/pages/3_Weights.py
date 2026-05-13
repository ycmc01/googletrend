"""Weights page — view / import / edit quarterly revenue per company."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "web"))

import pandas as pd
import streamlit as st

from gits.reference import load_companies, load_weights, save_weights
from lib.xqapi import get_quarterly_financial_report, quarterly_revenue_to_rows

st.set_page_config(page_title="GITS — Weights", page_icon="💰", layout="wide")
st.title("💰 Revenue Weights")
st.caption("Quarterly segment revenue (in millions of the company's reporting currency).")

companies = load_companies()
if companies.empty:
    st.warning("Register a company first.")
    st.stop()

ticker = st.selectbox("Ticker", companies["ticker"].tolist())

all_weights = load_weights()
w = all_weights[all_weights["ticker"].str.upper() == ticker.upper()].copy()

# -------- XQAPI import section --------
st.subheader("Import from XQAPI")
c1, c2, c3 = st.columns([1, 1, 3])
count = c1.number_input("Quarters to fetch", min_value=4, max_value=40, value=16, step=1)
import_btn = c2.button("📥 Import revenue", type="primary", use_container_width=True)
c3.caption("Uses /datamatrix/finance with metrics=financial-report, period=Q. Best for Taiwan stocks.")

if import_btn:
    try:
        with st.spinner(f"Fetching {count} quarters of {ticker}…"):
            payload = get_quarterly_financial_report(ticker, count=int(count))
        rows = quarterly_revenue_to_rows(payload, ticker)
    except Exception as e:
        st.error(f"XQAPI import failed: {e}")
        rows = []

    if not rows:
        st.warning("XQAPI returned no quarterly revenue. The ticker may be unsupported or the symbol format wrong.")
    else:
        new_df = pd.DataFrame(rows)
        # remove same ticker's existing 'Total' segment rows (no double-counting)
        keep = all_weights[~(
            (all_weights["ticker"].str.upper() == ticker.upper())
            & (all_weights["segment"] == "Total")
        )]
        save_weights(pd.concat([keep, new_df], ignore_index=True))
        st.success(f"Imported {len(new_df)} quarters into the **Total** segment for {ticker}")
        st.rerun()

st.divider()

# -------- Existing weights table editor --------
st.subheader(f"{ticker} revenue rows")
if w.empty:
    st.info("No revenue data yet. Import via XQAPI above or edit the CSV directly.")
else:
    # show wide pivot for readability
    wide = w.pivot_table(
        index=["fiscal_quarter", "quarter_end_date"],
        columns="segment",
        values="revenue_usd_m",
        aggfunc="first",
    ).reset_index().sort_values("quarter_end_date")
    totals = w.drop_duplicates("quarter_end_date").set_index("quarter_end_date")["total_revenue_usd_m"]
    wide["__total__"] = wide["quarter_end_date"].map(totals)
    st.dataframe(wide, use_container_width=True, hide_index=True)

    st.caption(f"{w['quarter_end_date'].nunique()} quarters loaded ({w['quarter_end_date'].min().date()} → {w['quarter_end_date'].max().date()})")

    with st.expander("✏️ Edit raw rows"):
        editable = w[["fiscal_quarter", "quarter_end_date", "segment", "revenue_usd_m", "total_revenue_usd_m", "source_filing"]].copy()
        editable["quarter_end_date"] = pd.to_datetime(editable["quarter_end_date"])
        edited = st.data_editor(
            editable,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "quarter_end_date": st.column_config.DateColumn("Quarter end"),
                "revenue_usd_m": st.column_config.NumberColumn("Segment revenue (M)"),
                "total_revenue_usd_m": st.column_config.NumberColumn("Total revenue (M)"),
            },
            key=f"weight_editor_{ticker}",
        )
        if st.button("💾 Save edits", type="primary"):
            edited = edited.dropna(subset=["quarter_end_date", "segment"]).copy()
            edited["ticker"] = ticker.upper()
            other = all_weights[all_weights["ticker"].str.upper() != ticker.upper()]
            save_weights(pd.concat([other, edited], ignore_index=True))
            st.success(f"Saved {len(edited)} rows for {ticker}")
            st.rerun()
