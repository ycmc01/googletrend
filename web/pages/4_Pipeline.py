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
GEO_OPTIONS = {
    "Worldwide": "",
    "Taiwan (TW)": "TW",
    "United States (US)": "US",
    "Japan (JP)": "JP",
    "Hong Kong (HK)": "HK",
    "Korea (KR)": "KR",
    "Mainland China (CN)": "CN",
    "Singapore (SG)": "SG",
    "United Kingdom (GB)": "GB",
}
geo_label = c1.selectbox("Geography", list(GEO_OPTIONS.keys()), index=0)
geo = GEO_OPTIONS[geo_label]
timeframe = c2.text_input("Timeframe", value="today 5-y", help="e.g. 'today 5-y', 'today 12-m', '2020-01-01 2025-12-31'")
if st.button("🌐 Fetch trends", type="primary"):
    with st.spinner("Calling pytrends…"):
        cli_args = ["fetch", "trends", ticker, "--timeframe", timeframe]
        if geo:
            cli_args.extend(["--geo", geo])
        rc, out, err = run_cli(*cli_args)
    if rc == 0:
        st.success("Trends fetched")
    else:
        st.error(f"Failed (exit {rc})")
    st.code(out + ("\n--- STDERR ---\n" + err if err else ""), language=None)

st.divider()

# Step 2: Prices
st.subheader("Step 2 · Fetch stock prices")
count = st.number_input("Daily bars to fetch", min_value=100, max_value=5000, value=1500, step=100,
                        help="XQAPI K-line: 1500 bars ≈ 6 years for TW (3y for US, fewer trading days)")
if st.button("💹 Fetch prices", type="primary"):
    with st.spinner("Calling XQAPI K-line…"):
        rc, out, err = run_cli("fetch", "prices", ticker, "--count", str(count))
    if rc == 0:
        st.success("Prices fetched")
    else:
        st.error(f"Failed (exit {rc})")
    st.code(out + ("\n--- STDERR ---\n" + err if err else ""), language=None)

st.divider()

# Step 3: Compute
st.subheader("Step 3 · Compute GITS index")
# DuckDB stores geo as 'WW' for worldwide
geo_for_compute = geo if geo else "WW"
st.caption(f"Will read trends with geo = `{geo_for_compute}` (matches Step 1 selection)")
if st.button("🧮 Compute GITS", type="primary"):
    with st.spinner("Computing weighted index…"):
        rc, out, err = run_cli("compute", ticker, "--geo", geo_for_compute)
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
