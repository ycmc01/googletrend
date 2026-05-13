"""Report page — view the GITS index + charts interactively (without notebook)."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import streamlit as st

from gits.analysis.backtest import deseasonalize_fiscal
from gits.analysis.plots import (
    lead_lag_chart,
    segment_contribution_chart,
    three_axis_chart,
)
from gits.engine.normalize import align_to_apple_fiscal_quarters, pivot_trends_wide
from gits.engine.weighting import compute_gits_index, load_total_revenue, load_weights_long
from gits.reference import load_companies
from gits.storage.duckdb_io import get_conn, init_schema, read_prices, read_trends

st.set_page_config(page_title="GITS — Report", page_icon="📈", layout="wide")
st.title("📈 GITS Report")

companies = load_companies()
if companies.empty:
    st.warning("Register a company first.")
    st.stop()

ticker = st.selectbox("Ticker", companies["ticker"].tolist())
geo = st.selectbox("Geography", ["WW", "US", "TW"], index=0)

conn = get_conn()
init_schema(conn)

trends_long = read_trends(conn, ticker=ticker, geo=geo)
prices_df = read_prices(conn, ticker=ticker)
weights_long = load_weights_long(ticker)
csv_revenue = load_total_revenue(ticker)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Trend rows", len(trends_long))
c2.metric("Price days", len(prices_df))
c3.metric("Segments", trends_long["segment"].nunique() if not trends_long.empty else 0)
c4.metric("Revenue quarters", len(csv_revenue))

if trends_long.empty:
    st.error("No trends data. Run **⚙ Pipeline → Step 1** first.")
    st.stop()
if weights_long.empty:
    st.error("No revenue weights. Add via **💰 Weights** page first.")
    st.stop()

prices = prices_df.set_index("date")
traffic_wide = pivot_trends_wide(trends_long)
gits = compute_gits_index(traffic_wide, weights_long)

st.subheader("Segment contribution to GITS (weighted)")
st.plotly_chart(segment_contribution_chart(gits, title=f"{ticker} weighted segment contribution"), use_container_width=True)

if not csv_revenue.empty and not prices.empty:
    st.subheader("Three-axis overlay")
    fig = three_axis_chart(
        gits=gits["gits"].resample("QS").mean(),
        revenue=csv_revenue,
        price=prices["adj_close"].resample("W").last(),
        title=f"{ticker} — GITS vs Revenue vs Price",
    )
    st.plotly_chart(fig, use_container_width=True)

# Lead-lag analysis
fiscal_ends = list(csv_revenue.index)
traffic_at_fq = align_to_apple_fiscal_quarters(traffic_wide, fiscal_ends)
gits_fq = compute_gits_index(traffic_at_fq, weights_long)["gits"].dropna()

st.subheader("GITS at fiscal quarter-ends")
side_by_side = gits_fq.to_frame("GITS").join(csv_revenue.rename("Revenue (M)")).round(2)
st.dataframe(side_by_side, use_container_width=True)

# Deseasonalized lead-lag (the main analytical output)
if len(gits_fq) >= 4:
    import numpy as np
    from scipy.stats import pearsonr

    def fq_lead_lag(leading, target, max_lead=2):
        aligned = pd.concat([leading.rename("lead"), target.rename("tgt")], axis=1, join="inner").sort_index()
        rows = []
        for k in range(-max_lead, max_lead + 1):
            shifted = aligned["tgt"].shift(-k)
            valid = pd.concat([aligned["lead"], shifted], axis=1).dropna()
            if len(valid) < 3 or valid.iloc[:, 0].std() == 0 or valid.iloc[:, 1].std() == 0:
                rows.append({"lead": k, "n": len(valid), "pearson_r": np.nan, "p_value": np.nan})
                continue
            r, p = pearsonr(valid.iloc[:, 0], valid.iloc[:, 1])
            rows.append({"lead": k, "n": len(valid), "pearson_r": r, "p_value": p})
        return pd.DataFrame(rows)

    st.subheader("Deseasonalized lead-lag (publication-lag adjusted)")
    st.caption("Lead = 0 with high r ⇒ nowcasting signal worth ~30-45 days vs the official earnings release.")

    gits_des = deseasonalize_fiscal(gits_fq)
    rev_des = deseasonalize_fiscal(csv_revenue)
    corr_rev = fq_lead_lag(gits_des, rev_des, max_lead=2)
    st.dataframe(corr_rev, use_container_width=True, hide_index=True)
    st.plotly_chart(lead_lag_chart(corr_rev, title=f"Deseasoned GITS → {ticker} Revenue"), use_container_width=True)

    if not prices.empty:
        price_at_fq = pd.Series({d: prices["adj_close"].asof(d) for d in fiscal_ends}).sort_index().astype(float)
        price_des = deseasonalize_fiscal(price_at_fq)
        corr_px = fq_lead_lag(gits_des, price_des, max_lead=2)
        st.dataframe(corr_px, use_container_width=True, hide_index=True)
        st.plotly_chart(lead_lag_chart(corr_px, title=f"Deseasoned GITS → {ticker} Price"), use_container_width=True)
else:
    st.info(f"Need ≥ 4 fiscal quarters of overlap to compute lead-lag; currently have {len(gits_fq)}.")
