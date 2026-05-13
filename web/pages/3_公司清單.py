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
st.caption("註冊要追蹤的股票。點「🔍 從 XQAPI 查詢」後，公司名稱與備註會自動帶入下方欄位。")


def _xqapi_lookup():
    """XQAPI 查詢 callback — 寫入 widget 的 session_state，下次 rerender 自動帶入。"""
    ticker = (st.session_state.get("co_ticker_field") or "").strip()
    if not ticker:
        st.session_state._lookup_msg = ("warning", "請先輸入股票代碼")
        return
    try:
        payload = get_basic_info(ticker, fields="公司全名,交易所產業分類,所屬產業,掛牌交易所")
    except Exception as e:
        st.session_state._lookup_msg = ("error", f"XQAPI 查詢失敗：{e}")
        return

    name_raw = industry = sector = exchange = None
    for f in payload.get("fields", []):
        cn = f.get("cName")
        vals = f.get("values") or []
        v = vals[0].get("value") if vals else None
        if cn == "公司全名": name_raw = v
        elif cn == "交易所產業分類": industry = v
        elif cn == "所屬產業": sector = v
        elif cn == "掛牌交易所": exchange = v

    if not name_raw:
        st.session_state._lookup_msg = ("warning", f"XQAPI 找不到 {ticker} 的公司名稱")
        return

    # 直接寫入 widget 的 session_state
    st.session_state.co_name_field = name_raw
    notes_parts = [p for p in [industry, sector] if p]
    if notes_parts:
        st.session_state.co_notes_field = " / ".join(notes_parts)

    extra = f"（{exchange}）" if exchange else ""
    st.session_state._lookup_msg = ("success", f"已自動帶入：{name_raw} {extra}")


def _save_company():
    """儲存公司 callback。"""
    ticker = (st.session_state.get("co_ticker_field") or "").strip().upper()
    name = (st.session_state.get("co_name_field") or "").strip()
    fy_end = int(st.session_state.get("co_fy_end_field") or 12)
    notes = (st.session_state.get("co_notes_field") or "").strip()

    if not ticker:
        st.session_state._save_msg = ("error", "請輸入股票代碼")
        return
    if not name:
        st.session_state._save_msg = ("error", "請輸入公司名稱（可先點查詢自動帶入）")
        return

    bare = ticker.split(".")[0]
    df = load_companies()
    df = df[df["ticker"].astype(str).str.upper() != bare]
    new_row = pd.DataFrame([{
        "ticker": bare, "name": name,
        "fiscal_year_end_month": fy_end, "notes": notes,
    }])
    save_companies(pd.concat([df, new_row], ignore_index=True))
    st.session_state._save_msg = ("success", f"已儲存 {bare}（{name}）")
    # 清空表單供下一筆使用
    st.session_state.co_ticker_field = ""
    st.session_state.co_name_field = ""
    st.session_state.co_notes_field = ""
    st.session_state.co_fy_end_field = 12


st.subheader("新增公司")

# 初始化 session_state 鍵
st.session_state.setdefault("co_ticker_field", "")
st.session_state.setdefault("co_name_field", "")
st.session_state.setdefault("co_fy_end_field", 12)
st.session_state.setdefault("co_notes_field", "")

col1, col2 = st.columns([2, 3])
col1.text_input("股票代碼", key="co_ticker_field", placeholder="例：2330 或 AMD",
                help="台股輸入數字代碼，美股輸入英文代號")
col2.text_input("公司名稱", key="co_name_field", placeholder="點下面的 🔍 自動查詢")
col1.number_input("會計年度結束月份", min_value=1, max_value=12, step=1, key="co_fy_end_field",
                  help="台股大多 12 月、Apple 9 月、Nvidia 1 月")
col2.text_input("備註（選填）", key="co_notes_field")

bcol1, bcol2 = st.columns([1, 4])
bcol1.button("🔍 從 XQAPI 查詢", on_click=_xqapi_lookup, use_container_width=True)
bcol2.button("✅ 儲存公司", on_click=_save_company, type="primary", use_container_width=True)

# 顯示 callback 設定的訊息
if msg := st.session_state.pop("_lookup_msg", None):
    severity, text = msg
    getattr(st, severity)(text)

if msg := st.session_state.pop("_save_msg", None):
    severity, text = msg
    getattr(st, severity)(text)
    if severity == "success":
        st.balloons()
        st.rerun()  # 重整下方表格

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
