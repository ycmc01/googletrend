"""詳細報告 — 完整 GITS 分析與互動圖表。"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import plotly.io as pio
import streamlit as st

pio.renderers.default = "browser"

from gits.analysis.backtest import deseasonalize_fiscal
from gits.analysis.plots import (
    lead_lag_chart,
    segment_contribution_chart,
    three_axis_chart,
    weekly_gits_vs_price,
)
from gits.engine.normalize import align_to_apple_fiscal_quarters, pivot_trends_wide
from gits.engine.weighting import compute_gits_index, load_total_revenue, load_weights_long
from gits.reference import load_companies
from gits.storage.duckdb_io import get_conn, init_schema, read_prices, read_trends

st.set_page_config(page_title="GITS — 詳細報告", page_icon="📈", layout="wide")
st.title("📈 詳細報告")
st.caption("完整 GITS 分析：季度對齊、領先/落後、去季節性。先在「🚀 一鍵分析」或「⚙ 進階執行」抓好資料再來看本頁。")

companies = load_companies()
if companies.empty:
    st.warning("還沒有註冊公司 — 請先到「🚀 一鍵分析」或「🏢 公司清單」新增。")
    st.stop()

c_top1, c_top2 = st.columns([1, 1])
ticker = c_top1.selectbox("股票代碼", companies["ticker"].astype(str).tolist())
geo = c_top2.selectbox("搜尋熱度區域", ["WW", "TW", "US", "JP", "HK"], index=0)

conn = get_conn()
init_schema(conn)

trends_long = read_trends(conn, ticker=ticker, geo=geo)
prices_df = read_prices(conn, ticker=ticker)
weights_long = load_weights_long(ticker)
csv_revenue = load_total_revenue(ticker)

m1, m2, m3, m4 = st.columns(4)
m1.metric("週度資料筆數", len(trends_long))
m2.metric("股價日數", len(prices_df))
m3.metric("Segment 數", trends_long["segment"].nunique() if not trends_long.empty else 0)
m4.metric("營收季數", len(csv_revenue))

if trends_long.empty:
    st.error(f"找不到 {ticker} 在 `{geo}` 地區的搜尋熱度資料。請先到「🚀 一鍵分析」或「⚙ 進階執行」抓取。")
    st.stop()
if weights_long.empty:
    st.error(f"找不到 {ticker} 的營收資料。請到「💰 營收資料」匯入。")
    st.stop()

prices = prices_df.set_index("date")
traffic_wide = pivot_trends_wide(trends_long)
gits = compute_gits_index(traffic_wide, weights_long)

st.divider()
st.subheader("1. 週線：GITS vs 股價")
st.plotly_chart(
    weekly_gits_vs_price(
        gits["gits"].dropna(),
        prices["adj_close"].resample("W").last().dropna(),
        title=f"{ticker} — GITS 搜尋指標 vs 股價（週線）",
    ),
    use_container_width=True,
)

st.subheader("2. 各 segment 對 GITS 的加權貢獻")
st.plotly_chart(
    segment_contribution_chart(gits, title=f"{ticker} — Segment 加權貢獻堆疊圖"),
    use_container_width=True,
)

if not csv_revenue.empty and not prices.empty:
    st.subheader("3. 三軸對照圖：GITS / 季營收 / 股價")
    fig3 = three_axis_chart(
        gits=gits["gits"].resample("QS").mean(),
        revenue=csv_revenue,
        price=prices["adj_close"].resample("W").last(),
        title=f"{ticker} — GITS（季均）vs 季營收 vs 股價",
    )
    st.plotly_chart(fig3, use_container_width=True)

fiscal_ends = list(csv_revenue.index)
traffic_at_fq = align_to_apple_fiscal_quarters(traffic_wide, fiscal_ends)
gits_fq = compute_gits_index(traffic_at_fq, weights_long)["gits"].dropna()

st.subheader("4. GITS 在會計季結束日的快照")
st.caption("把週線資料聚合到該會計季最後一天，與當季實際營收並列。")
side_by_side = gits_fq.to_frame("GITS").join(csv_revenue.rename("營收 (百萬)")).round(2)
st.dataframe(side_by_side, use_container_width=True)

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

    st.subheader("5. 領先/落後相關係數（去季節性）")
    st.caption("Lead=0 高相關 ≒ 領先官方財報 ~30-45 天的 nowcasting 訊號（詳見📖 使用說明）")

    gits_des = deseasonalize_fiscal(gits_fq)
    rev_des = deseasonalize_fiscal(csv_revenue)
    corr_rev = fq_lead_lag(gits_des, rev_des, max_lead=2)
    st.markdown("**GITS vs 季營收（去季節性後）**")
    st.dataframe(corr_rev, use_container_width=True, hide_index=True)
    st.plotly_chart(lead_lag_chart(corr_rev, title=f"GITS → {ticker} 營收 (去季節)"), use_container_width=True)

    if not prices.empty:
        price_at_fq = pd.Series({d: prices["adj_close"].asof(d) for d in fiscal_ends}).sort_index().astype(float)
        price_des = deseasonalize_fiscal(price_at_fq)
        corr_px = fq_lead_lag(gits_des, price_des, max_lead=2)
        st.markdown("**GITS vs 股價（去季節性後）**")
        st.dataframe(corr_px, use_container_width=True, hide_index=True)
        st.plotly_chart(lead_lag_chart(corr_px, title=f"GITS → {ticker} 股價 (去季節)"), use_container_width=True)
else:
    st.info(f"需要 ≥ 4 個會計季的重疊才能計算領先/落後分析，目前只有 {len(gits_fq)} 季。")
