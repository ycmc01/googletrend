"""Segments page — define and edit keyword groups for any ticker."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import streamlit as st

from gits.reference import load_companies, load_segments, save_segments

st.set_page_config(page_title="GITS — Segments", page_icon="🏷", layout="wide")
st.title("🏷 Segments — Keyword Group Manager")
st.caption("Each segment = one set of positive Google Trends keywords. Maximum 5 segments per ticker (pytrends single-query cap).")

companies = load_companies()
if companies.empty:
    st.warning("Register a company first in the **🏢 Companies** page.")
    st.stop()

ticker = st.selectbox("Ticker", companies["ticker"].tolist())

all_segments = load_segments()
segs = all_segments[all_segments["ticker"].str.upper() == ticker.upper()].reset_index(drop=True)

# -------- Existing segments (table editor) --------
st.subheader(f"Segments for {ticker}")

if segs.empty:
    st.info("No segments yet. Add one below.")
else:
    display = segs[["segment_name", "trends_keywords", "exclude_terms", "trends_topic_id", "notes"]].fillna("").copy()
    edited = st.data_editor(
        display,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "segment_name": st.column_config.TextColumn("Segment", required=True),
            "trends_keywords": st.column_config.TextColumn("Keywords (separated by |)", width="large"),
            "exclude_terms": st.column_config.TextColumn("Excludes (|-separated)"),
            "trends_topic_id": st.column_config.TextColumn("Topic ID", help="Optional /m/xxxx code"),
            "notes": st.column_config.TextColumn("Notes"),
        },
        key=f"seg_editor_{ticker}",
    )

    cols = st.columns([1, 3])
    if cols[0].button("💾 Save edits", type="primary", use_container_width=True):
        # rebuild this ticker's rows from the editor
        edited_rows = edited.dropna(subset=["segment_name"]).copy()
        edited_rows["ticker"] = ticker.upper()
        other_tickers = all_segments[all_segments["ticker"].str.upper() != ticker.upper()]
        save_segments(pd.concat([other_tickers, edited_rows], ignore_index=True))
        st.success(f"Saved {len(edited_rows)} segment(s) for {ticker}")
        st.rerun()
    cols[1].caption("Tip: Add a row at the bottom by clicking the **+** button, or delete by selecting and pressing Delete.")

st.divider()

# -------- Quick-add a single segment --------
st.subheader("Quick add segment")

with st.form("add_segment", clear_on_submit=True):
    c1, c2 = st.columns([2, 3])
    new_name = c1.text_input("Segment name", placeholder="e.g. iPhone / Data Center / 邏輯製程")
    keywords = c2.text_area(
        "Keywords (one per line)",
        placeholder="iPhone 16\niPhone 17\nApple iPhone",
        height=100,
    )
    c3, c4 = st.columns([3, 2])
    excludes = c3.text_area(
        "Exclude terms (one per line, optional)",
        placeholder="iphone case\niphone repair",
        height=80,
    )
    topic = c4.text_input("Topic ID (optional)", placeholder="/m/04ck9_")
    notes = st.text_input("Notes (optional)")

    submit = st.form_submit_button("➕ Add segment", type="primary")

if submit:
    if not new_name.strip():
        st.error("Segment name required.")
    elif not keywords.strip():
        st.error("At least one keyword required.")
    elif len(segs) >= 5:
        st.error("Already 5 segments — pytrends single-query cap reached. Edit existing or delete first.")
    else:
        kw_list = [k.strip() for k in keywords.splitlines() if k.strip()]
        excl_list = [k.strip() for k in excludes.splitlines() if k.strip()]
        new_row = pd.DataFrame([{
            "ticker": ticker.upper(),
            "segment_name": new_name.strip(),
            "trends_topic_id": topic.strip(),
            "trends_keywords": "|".join(kw_list),
            "exclude_terms": "|".join(excl_list),
            "notes": notes.strip(),
        }])
        save_segments(pd.concat([all_segments, new_row], ignore_index=True))
        st.success(f"Added segment **{new_name}** ({len(kw_list)} keywords)")
        st.rerun()

st.divider()

# -------- TW stock default helper --------
with st.expander("💡 Don't know what to enter? Common patterns"):
    st.markdown("""
    **Single-segment companies (most TW stocks)** — use one segment called `Total` with the company name:
    - segment: `Total`
    - keywords: `TSMC` (English brand for global trends) or `台積電` (for TW-only trends)

    **Multi-segment companies (US tech)** — pick 2-5 distinct product lines:
    - Apple: iPhone / Mac / iPad / Wearables / Services
    - Nvidia: Data Center / Gaming / Pro Viz / Automotive / Networking
    - Tesla: Model 3-Y / Model S-X / Cybertruck / Energy / Software
    """)
