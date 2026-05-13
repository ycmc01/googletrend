"""GITS Scanner — Streamlit web UI entry point."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import streamlit as st

from gits.reference import load_companies, load_segments, load_weights

st.set_page_config(page_title="GITS Scanner", page_icon="📈", layout="wide")
st.title("📈 GITS Scanner")
st.caption("Revenue-weighted Google Trends nowcasting for any public company")

companies = load_companies()
segments = load_segments()
weights = load_weights()

c1, c2, c3 = st.columns(3)
c1.metric("Registered companies", len(companies))
c2.metric("Total segments", len(segments))
c3.metric(
    "Quarters of revenue data",
    weights["quarter_end_date"].nunique() if not weights.empty else 0,
)

st.divider()
st.subheader("Companies")

if companies.empty:
    st.info("No companies yet. Go to **🏢 Companies** in the sidebar to add one.")
else:
    rows = []
    for _, c in companies.iterrows():
        ticker = str(c["ticker"])
        seg_count = (segments["ticker"].astype(str).str.upper() == ticker.upper()).sum() if not segments.empty else 0
        if not weights.empty:
            w = weights[weights["ticker"].astype(str).str.upper() == ticker.upper()]
            q_count = w["quarter_end_date"].nunique()
            if q_count:
                latest = pd.to_datetime(w["quarter_end_date"]).max()
                latest_str = latest.date().isoformat() if pd.notna(latest) else "-"
            else:
                latest_str = "-"
        else:
            q_count, latest_str = 0, "-"
        rows.append({
            "Ticker": ticker,
            "Name": c["name"],
            "FY end": int(c["fiscal_year_end_month"]) if str(c["fiscal_year_end_month"]).strip() else "",
            "Segments": seg_count,
            "Quarters": q_count,
            "Latest data": latest_str,
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Workflow")
st.markdown("""
1. **🏢 Companies** — Register a new ticker. For Taiwan stocks (e.g. `2330`) the form auto-fills the company name via XQAPI.
2. **🏷 Segments** — Define keyword groups for each business unit. Default for TW stocks is a single `Total` segment using the company name; replace with finer breakdowns if data is available.
3. **💰 Weights** — Import quarterly revenue from XQAPI, or paste manually for segments not covered.
4. **⚙ Pipeline** — Run `fetch trends / fetch prices / compute` for the chosen ticker.
5. **📈 Report** — View the nowcasting analysis with interactive charts.
""")

with st.sidebar:
    st.markdown("### About")
    st.caption(
        "Project root: `" + str(PROJECT_ROOT) + "`\n\n"
        "Data sources: Google Trends (pytrends), XQAPI (prices + revenue), DuckDB"
    )
