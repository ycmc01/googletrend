"""公司清單 — 註冊與管理追蹤的股票（支援 XQAPI 自動帶入公司名）。"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import streamlit as st

from gits.reference import (
    load_companies,
    load_segments,
    load_weights,
    save_companies,
    save_segments,
    save_weights,
)
from gits.xqapi import get_basic_info

st.set_page_config(page_title="GITS — 公司清單", page_icon="🏢", layout="wide")
st.title("🏢 公司清單")
st.caption("註冊要追蹤的股票。台股輸入 4 位數代碼會自動透過 XQAPI 帶入公司全名。")

st.subheader("新增公司")

with st.form("add_company", clear_on_submit=False):
    col1, col2 = st.columns([2, 3])
    ticker_input = col1.text_input(
        "股票代碼", placeholder="例：2330 或 AAPL",
        help="台股輸入數字代碼，美股輸入英文代號"
    )
    name_input = col2.text_input("公司名稱", placeholder="點下面的 🔍 自動查詢")
    fy_end = col1.number_input("會計年度結束月份", min_value=1, max_value=12, value=12, step=1,
                                help="台股大多 12 月、Apple 9 月")
    notes = col2.text_input("備註（選填）", value="")

    bcol1, bcol2 = st.columns([1, 4])
    lookup = bcol1.form_submit_button("🔍 從 XQAPI 查詢", use_container_width=True)
    submit = bcol2.form_submit_button("✅ 儲存公司", type="primary", use_container_width=True)

if lookup:
    if not ticker_input.strip():
        st.warning("請先輸入股票代碼")
    else:
        try:
            with st.spinner(f"正在查詢 {ticker_input}…"):
                payload = get_basic_info(
                    ticker_input,
                    fields="公司全名,交易所產業分類,所屬產業,掛牌交易所",
                )
        except Exception as e:
            st.error(f"XQAPI 查詢失敗：{e}")
        else:
            name_raw = industry = sector = exchange = None
            for f in payload.get("fields", []):
                if f.get("cName") == "公司全名":
                    name_raw = f["values"][0]["value"]
                elif f.get("cName") == "交易所產業分類":
                    industry = f["values"][0]["value"]
                elif f.get("cName") == "所屬產業":
                    sector = f["values"][0]["value"]
                elif f.get("cName") == "掛牌交易所":
                    exchange = f["values"][0]["value"]

            st.success(f"找到：**{name_raw}**　·　交易所：{exchange}　·　產業：{industry}")
            if sector:
                st.caption(f"所屬產業：{sector}")
            st.info("把以下資訊複製到上方表單，然後按 **儲存公司**：")
            st.code(
                f"公司名稱：{name_raw}\n備註：{industry or ''} / {sector or ''}",
                language=None,
            )

if submit:
    ticker = ticker_input.strip().upper()
    if "." not in ticker:
        ticker = (ticker + ".TW") if ticker.isdigit() else (ticker + ".US")
    bare_ticker = ticker.split(".")[0]

    if not name_input.strip():
        st.error("請輸入公司名稱")
    else:
        df = load_companies()
        df = df[df["ticker"].astype(str).str.upper() != bare_ticker]
        new_row = pd.DataFrame([{
            "ticker": bare_ticker,
            "name": name_input.strip(),
            "fiscal_year_end_month": int(fy_end),
            "notes": notes,
        }])
        save_companies(pd.concat([df, new_row], ignore_index=True))
        st.success(f"已儲存 {bare_ticker}（{name_input.strip()}）")
        st.balloons()

st.divider()

st.subheader("已註冊的公司")
companies = load_companies()
if companies.empty:
    st.info("還沒有公司，從上方新增吧。")
else:
    segments = load_segments()
    weights = load_weights()
    rows = []
    for _, c in companies.iterrows():
        ticker = str(c["ticker"])
        seg_count = (segments["ticker"].astype(str).str.upper() == ticker.upper()).sum() if not segments.empty else 0
        if not weights.empty:
            w = weights[weights["ticker"].astype(str).str.upper() == ticker.upper()]
            q_count = w["quarter_end_date"].nunique()
        else:
            q_count = 0
        rows.append({
            "代碼": ticker, "公司名稱": c["name"],
            "會計年度月": int(c["fiscal_year_end_month"]) if str(c["fiscal_year_end_month"]).strip() else "",
            "備註": c.get("notes", "") or "",
            "Segment 數": seg_count, "營收季數": q_count,
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

    with st.expander("⚠ 刪除公司"):
        ticker_to_del = st.selectbox("選擇要刪除的代碼", [""] + companies["ticker"].astype(str).tolist())
        if ticker_to_del and st.button("🗑 刪除此公司（連同其關鍵字組與營收）", type="primary"):
            save_companies(companies[companies["ticker"].astype(str).str.upper() != ticker_to_del.upper()])
            if not segments.empty:
                save_segments(segments[segments["ticker"].astype(str).str.upper() != ticker_to_del.upper()])
            if not weights.empty:
                save_weights(weights[weights["ticker"].astype(str).str.upper() != ticker_to_del.upper()])
            st.success(f"已刪除 {ticker_to_del}")
            st.rerun()
