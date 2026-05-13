"""營收資料 — 從 XQAPI 匯入季營收或手動編輯。"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import streamlit as st

from gits.reference import load_companies, load_weights, save_weights
from gits.xqapi import get_quarterly_financial_report, quarterly_revenue_to_rows

st.set_page_config(page_title="GITS — 營收資料", page_icon="💰", layout="wide")
st.title("💰 營收資料")
st.caption("各公司季度營收（以原報告貨幣的百萬為單位）。")

companies = load_companies()
if companies.empty:
    st.warning("請先到 **🏢 公司清單** 註冊公司。")
    st.stop()

ticker = st.selectbox("選擇公司", companies["ticker"].astype(str).tolist())

all_weights = load_weights()
w = all_weights[all_weights["ticker"].astype(str).str.upper() == ticker.upper()].copy()

st.subheader("從 XQAPI 匯入")
c1, c2, c3 = st.columns([1, 1, 3])
count = c1.number_input("匯入季數", min_value=4, max_value=40, value=16, step=1)
import_btn = c2.button("📥 匯入營收", type="primary", use_container_width=True)
c3.caption("使用 `/datamatrix/finance` 端點 `financial-report` 指標、period=Q。台股、美股皆支援。")

if import_btn:
    try:
        with st.spinner(f"正在匯入 {ticker} 的 {count} 季營收…"):
            payload = get_quarterly_financial_report(ticker, count=int(count))
        rows = quarterly_revenue_to_rows(payload, ticker)
    except Exception as e:
        st.error(f"匯入失敗：{e}")
        rows = []

    if not rows:
        st.warning("XQAPI 沒回傳季營收。代碼可能不支援或格式錯誤。")
    else:
        new_df = pd.DataFrame(rows)
        keep = all_weights[~(
            (all_weights["ticker"].astype(str).str.upper() == ticker.upper())
            & (all_weights["segment"] == "Total")
        )]
        save_weights(pd.concat([keep, new_df], ignore_index=True))
        st.success(f"已將 {len(new_df)} 季匯入 **Total** segment（{ticker}）")
        st.rerun()

st.divider()

st.subheader(f"{ticker} 的營收列")
if w.empty:
    st.info("尚無營收資料。點上方 **匯入營收** 或直接編輯 CSV。")
else:
    wide = w.pivot_table(
        index=["fiscal_quarter", "quarter_end_date"],
        columns="segment",
        values="revenue_usd_m",
        aggfunc="first",
    ).reset_index().sort_values("quarter_end_date")
    totals = w.drop_duplicates("quarter_end_date").set_index("quarter_end_date")["total_revenue_usd_m"]
    wide["總計"] = wide["quarter_end_date"].map(totals)
    st.dataframe(wide, use_container_width=True, hide_index=True)

    st.caption(
        f"已載入 {w['quarter_end_date'].nunique()} 季 "
        f"（{pd.to_datetime(w['quarter_end_date']).min().date()} ~ "
        f"{pd.to_datetime(w['quarter_end_date']).max().date()}）"
    )

    with st.expander("✏️ 直接編輯資料列"):
        editable = w[["fiscal_quarter", "quarter_end_date", "segment", "revenue_usd_m", "total_revenue_usd_m", "source_filing"]].copy()
        editable["quarter_end_date"] = pd.to_datetime(editable["quarter_end_date"])
        edited = st.data_editor(
            editable,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "fiscal_quarter": st.column_config.TextColumn("會計季"),
                "quarter_end_date": st.column_config.DateColumn("季結束日"),
                "segment": st.column_config.TextColumn("Segment"),
                "revenue_usd_m": st.column_config.NumberColumn("該 segment 營收 (M)"),
                "total_revenue_usd_m": st.column_config.NumberColumn("總營收 (M)"),
                "source_filing": st.column_config.TextColumn("資料來源"),
            },
            key=f"weight_editor_{ticker}",
        )
        if st.button("💾 儲存修改", type="primary"):
            edited = edited.dropna(subset=["quarter_end_date", "segment"]).copy()
            edited["ticker"] = ticker.upper()
            other = all_weights[all_weights["ticker"].astype(str).str.upper() != ticker.upper()]
            save_weights(pd.concat([other, edited], ignore_index=True))
            st.success(f"已儲存 {len(edited)} 列（{ticker}）")
            st.rerun()
