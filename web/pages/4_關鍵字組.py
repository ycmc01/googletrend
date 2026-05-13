"""關鍵字組 — 定義每家公司的搜尋關鍵字分組。"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import streamlit as st

from gits.reference import load_companies, load_segments, save_segments

st.set_page_config(page_title="GITS — 關鍵字組", page_icon="🏷", layout="wide")
st.title("🏷 關鍵字組（Segment）管理")
st.caption("每個 segment = 一組正向關鍵字。每家公司最多 5 個 segment（Google Trends 單次查詢上限）。")

companies = load_companies()
if companies.empty:
    st.warning("還沒有公司，請先到 **🏢 公司清單** 註冊。")
    st.stop()

ticker = st.selectbox("選擇公司", companies["ticker"].astype(str).tolist())

all_segments = load_segments()
segs = all_segments[all_segments["ticker"].astype(str).str.upper() == ticker.upper()].reset_index(drop=True)

st.subheader(f"{ticker} 的 segments")

if segs.empty:
    st.info("尚未設定任何 segment，使用下方表單新增。")
else:
    display = segs[["segment_name", "trends_keywords", "exclude_terms", "trends_topic_id", "notes"]].fillna("").copy()
    edited = st.data_editor(
        display,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "segment_name": st.column_config.TextColumn("Segment 名稱", required=True),
            "trends_keywords": st.column_config.TextColumn("關鍵字（以 | 分隔）", width="large"),
            "exclude_terms": st.column_config.TextColumn("排除字（以 | 分隔）"),
            "trends_topic_id": st.column_config.TextColumn("Topic ID", help="選填，/m/xxxx 格式"),
            "notes": st.column_config.TextColumn("備註"),
        },
        key=f"seg_editor_{ticker}",
    )

    cols = st.columns([1, 3])
    if cols[0].button("💾 儲存修改", type="primary", use_container_width=True):
        edited_rows = edited.dropna(subset=["segment_name"]).copy()
        edited_rows["ticker"] = ticker.upper()
        other_tickers = all_segments[all_segments["ticker"].astype(str).str.upper() != ticker.upper()]
        save_segments(pd.concat([other_tickers, edited_rows], ignore_index=True))
        st.success(f"已儲存 {ticker} 的 {len(edited_rows)} 個 segment")
        st.rerun()
    cols[1].caption("提示：按 **+** 可新增列；選列後按 Delete 可刪除。")

st.divider()

st.subheader("快速新增單一 segment")

with st.form("add_segment", clear_on_submit=True):
    c1, c2 = st.columns([2, 3])
    new_name = c1.text_input("Segment 名稱", placeholder="例：iPhone / 資料中心 / AI 概念")
    keywords = c2.text_area(
        "關鍵字（一行一個）",
        placeholder="iPhone 16\niPhone 17\nApple iPhone",
        height=100,
    )
    c3, c4 = st.columns([3, 2])
    excludes = c3.text_area(
        "排除字（一行一個，選填）",
        placeholder="iphone case\niphone repair",
        height=80,
    )
    topic = c4.text_input("Topic ID（選填）", placeholder="/m/04ck9_")
    notes = st.text_input("備註（選填）")

    submit = st.form_submit_button("➕ 新增 segment", type="primary")

if submit:
    if not new_name.strip():
        st.error("請輸入 Segment 名稱")
    elif not keywords.strip():
        st.error("至少需要一個關鍵字")
    elif len(segs) >= 5:
        st.error("已有 5 個 segment 達到上限 — 請先刪除或編輯既有的。")
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
        st.success(f"已新增 **{new_name}**（{len(kw_list)} 個關鍵字）")
        st.rerun()

st.divider()

with st.expander("💡 不知道怎麼填？常見範例"):
    st.markdown("""
**單一 segment 公司（多數台股）** — 一個叫「總和」的 segment，關鍵字用公司或產業名：
- segment：`總和`
- 關鍵字：`TSMC`（全球搜尋）或 `台積電`（台灣搜尋）

**多 segment 公司（美股科技）** — 拆 2-5 個產品線：
- Apple：iPhone / Mac / iPad / Wearables / Services
- Nvidia：Data Center / Gaming / Pro Viz / Automotive / Networking
- Tesla：Model 3-Y / Model S-X / Cybertruck / Energy / Software
""")
