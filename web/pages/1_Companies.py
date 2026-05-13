"""Companies page — register a ticker, with XQAPI auto-fill for TW stocks."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "web"))

import pandas as pd
import streamlit as st

from gits.reference import load_companies, load_segments, load_weights, save_companies
from lib.xqapi import extract_field, get_basic_info

st.set_page_config(page_title="GITS — Companies", page_icon="🏢", layout="wide")
st.title("🏢 Companies")

# -------- XQAPI auto-fill section --------
st.subheader("Add company")

with st.form("add_company", clear_on_submit=False):
    col1, col2 = st.columns([2, 3])
    ticker_input = col1.text_input(
        "Ticker", placeholder="e.g. 2330 (TW) or AAPL (US)",
        help="Bare digits are interpreted as Taiwan stocks; bare letters as US stocks."
    )
    name_input = col2.text_input("Company name", placeholder="Auto-filled if you click Lookup")
    fy_end = col1.number_input("Fiscal year-end month", min_value=1, max_value=12, value=12, step=1)
    notes = col2.text_input("Notes (optional)", value="")

    bcol1, bcol2 = st.columns([1, 4])
    lookup = bcol1.form_submit_button("🔍 Lookup via XQAPI", use_container_width=True)
    submit = bcol2.form_submit_button("✅ Save company", type="primary", use_container_width=True)

if lookup:
    if not ticker_input.strip():
        st.warning("Enter a ticker first.")
    else:
        try:
            with st.spinner(f"Querying XQAPI for {ticker_input}…"):
                payload = get_basic_info(
                    ticker_input,
                    fields="公司全名,交易所產業分類,所屬產業,掛牌交易所",
                )
        except Exception as e:
            st.error(f"XQAPI lookup failed: {e}")
        else:
            name_pairs = extract_field(payload, "公司全名")
            industry_pairs = extract_field(payload, "交易所產業分類")
            sector_pairs = extract_field(payload, "所屬產業")
            exchange_pairs = extract_field(payload, "掛牌交易所")

            name = name_pairs[0][1] if name_pairs else None
            industry = industry_pairs[0][1] if industry_pairs else None
            sector = sector_pairs[0][1] if sector_pairs else None
            exchange = exchange_pairs[0][1] if exchange_pairs else None

            # extract_field coerces values to float; for company name we need raw string
            name_raw = None
            for f in payload.get("fields", []):
                if f.get("cName") == "公司全名":
                    name_raw = f["values"][0]["value"]
                if f.get("cName") == "交易所產業分類":
                    industry = f["values"][0]["value"]
                if f.get("cName") == "所屬產業":
                    sector = f["values"][0]["value"]
                if f.get("cName") == "掛牌交易所":
                    exchange = f["values"][0]["value"]

            st.success(f"Found: **{name_raw}**  ·  exchange: {exchange}  ·  industry: {industry}")
            if sector:
                st.caption(f"所屬產業: {sector}")
            st.info("Copy these into the form fields above and click **Save company**:")
            st.code(
                f"Company name: {name_raw}\nNotes: {industry or ''} / {sector or ''}",
                language=None,
            )

if submit:
    ticker = ticker_input.strip().upper()
    if "." not in ticker:
        ticker = (ticker + ".TW") if ticker.isdigit() else (ticker + ".US")
    # store the bare ticker without market suffix (e.g. "2330") so it matches user expectation
    bare_ticker = ticker.split(".")[0]

    if not name_input.strip():
        st.error("Company name required.")
    else:
        df = load_companies()
        df = df[df["ticker"].str.upper() != bare_ticker]
        new_row = pd.DataFrame([{
            "ticker": bare_ticker,
            "name": name_input.strip(),
            "fiscal_year_end_month": int(fy_end),
            "notes": notes,
        }])
        save_companies(pd.concat([df, new_row], ignore_index=True))
        st.success(f"Saved {bare_ticker} ({name_input.strip()})")
        st.balloons()

st.divider()

# -------- Existing companies table --------
st.subheader("Registered companies")
companies = load_companies()
if companies.empty:
    st.info("No companies registered yet.")
else:
    segments = load_segments()
    weights = load_weights()
    rows = []
    for _, c in companies.iterrows():
        ticker = c["ticker"]
        seg_count = (segments["ticker"].str.upper() == ticker).sum() if not segments.empty else 0
        if not weights.empty:
            w = weights[weights["ticker"].str.upper() == ticker]
            q_count = w["quarter_end_date"].nunique()
        else:
            q_count = 0
        rows.append({
            "Ticker": ticker, "Name": c["name"],
            "FY end month": int(c["fiscal_year_end_month"]) if str(c["fiscal_year_end_month"]).strip() else "",
            "Notes": c.get("notes", "") or "",
            "Segments": seg_count, "Quarters": q_count,
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # delete
    with st.expander("⚠ Delete a company"):
        ticker_to_del = st.selectbox("Select ticker", [""] + companies["ticker"].tolist())
        if ticker_to_del and st.button("Delete this company AND its segments + weights", type="primary"):
            from gits.reference import save_segments, save_weights
            save_companies(companies[companies["ticker"].str.upper() != ticker_to_del.upper()])
            if not segments.empty:
                save_segments(segments[segments["ticker"].str.upper() != ticker_to_del.upper()])
            if not weights.empty:
                save_weights(weights[weights["ticker"].str.upper() != ticker_to_del.upper()])
            st.success(f"Removed {ticker_to_del}")
            st.rerun()
