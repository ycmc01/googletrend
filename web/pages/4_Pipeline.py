"""Pipeline page — run fetch / compute / report for any ticker."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "web"))

import streamlit as st

from gits.reference import load_companies
from lib.utils import run_cli

st.set_page_config(page_title="GITS — Pipeline", page_icon="⚙", layout="wide")
st.title("⚙ Pipeline Runner")
st.caption("Trigger the data pipeline for any registered ticker. Each step is a subprocess call to the gits CLI.")

companies = load_companies()
if companies.empty:
    st.warning("Register a company first.")
    st.stop()

ticker = st.selectbox("Ticker", companies["ticker"].tolist())

st.divider()

# Step 1: Trends
st.subheader("Step 1 · Fetch Google Trends")
c1, c2 = st.columns([1, 1])
geo = c1.text_input("Geography", value="", help="Empty = worldwide; 'TW' for Taiwan-only; 'US' for US-only")
timeframe = c2.text_input("Timeframe", value="today 5-y")
if st.button("🌐 Fetch trends", type="primary"):
    with st.spinner("Calling pytrends…"):
        rc, out, err = run_cli("fetch", "trends", ticker, "--geo", geo, "--timeframe", timeframe)
    if rc == 0:
        st.success("Trends fetched")
    else:
        st.error(f"Failed (exit {rc})")
    st.code(out + ("\n--- STDERR ---\n" + err if err else ""), language=None)

st.divider()

# Step 2: Prices
st.subheader("Step 2 · Fetch stock prices")
start = st.text_input("Start date", value="2021-01-01")
if st.button("💹 Fetch prices", type="primary"):
    with st.spinner("Calling yfinance…"):
        rc, out, err = run_cli("fetch", "prices", ticker, "--start", start)
    if rc == 0:
        st.success("Prices fetched")
    else:
        st.error(f"Failed (exit {rc})")
    st.code(out + ("\n--- STDERR ---\n" + err if err else ""), language=None)

st.divider()

# Step 3: Compute
st.subheader("Step 3 · Compute GITS index")
geo2 = st.text_input("Geography for compute", value=(geo or "WW"))
if st.button("🧮 Compute GITS", type="primary"):
    with st.spinner("Computing weighted index…"):
        rc, out, err = run_cli("compute", ticker, "--geo", geo2)
    if rc == 0:
        st.success("GITS computed")
    else:
        st.error(f"Failed (exit {rc})")
    st.code(out + ("\n--- STDERR ---\n" + err if err else ""), language=None)

st.divider()

# Step 4: Report
st.subheader("Step 4 · Generate HTML report")
if st.button("📊 Generate report", type="primary"):
    with st.spinner("Executing notebook (this can take a minute)…"):
        rc, out, err = run_cli("report", ticker)
    if rc == 0:
        report_path = PROJECT_ROOT / "notebooks" / f"report_{ticker.upper()}.html"
        st.success(f"Report generated at {report_path}")
        st.markdown(f"Open in browser: `{report_path}`")
        if report_path.exists():
            with open(report_path, "rb") as f:
                st.download_button(
                    "⬇ Download HTML report", f, file_name=report_path.name, mime="text/html"
                )
    else:
        st.error(f"Failed (exit {rc})")
    st.code(out + ("\n--- STDERR ---\n" + err if err else ""), language=None)
