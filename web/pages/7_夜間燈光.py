"""夜間燈光 — 從 Google Earth Engine 取得的 VIIRS DNB 月度時間序列。

實驗性訊號：產業聚落（如新竹科學園區）的夜間燈光強度月變化，
可作為該聚落生產活動的代理指標，與 GITS 搜尋熱度互補。
"""
from __future__ import annotations

import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from gits.nightlights import load_cached, load_rois, NTL_PARQUET
from gits.reference import load_companies
from gits.storage.duckdb_io import get_conn, init_schema, read_prices

st.set_page_config(page_title="GITS — 夜間燈光", page_icon="🛰", layout="wide")
st.title("🛰 夜間燈光（衛星 ALT-DATA）")
st.caption("VIIRS Day/Night Band 月度合成，~500m 解析度。可作為產業聚落生產活動的代理訊號。")

rois = load_rois()
cached = load_cached()

# --------- 操作面板 ----------
top1, top2 = st.columns([2, 1])
with top1:
    if cached.empty:
        st.warning("尚未抓取資料。請先設定 GEE 認證，再執行下方的「抓取/更新資料」。")
    else:
        st.success(f"已快取 {cached['roi_name'].nunique()} 個 ROI，"
                   f"{cached['date'].min().date()} ~ {cached['date'].max().date()}，"
                   f"共 {len(cached)} 個月度點")

with top2:
    if st.button("🛰 抓取 / 更新 NTL 資料", help="呼叫 scripts/fetch_ntl.py，需先完成 GEE 認證"):
        with st.spinner("從 Google Earth Engine 抓取資料中（可能需 1-3 分鐘）…"):
            result = subprocess.run(
                [sys.executable, str(PROJECT_ROOT / "scripts" / "fetch_ntl.py")],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
        if result.returncode == 0:
            st.success("更新完成")
            st.code(result.stdout, language=None)
            st.rerun()
        else:
            st.error(f"失敗（exit {result.returncode}）")
            st.code(result.stdout + "\n--- STDERR ---\n" + result.stderr, language=None)

with st.expander("📋 ROI 清單（可手動編輯 reference/ntl_rois.csv 後重抓）"):
    st.dataframe(rois, use_container_width=True, hide_index=True)

st.divider()

if cached.empty:
    st.info("""
**首次使用步驟：**

1. 在 https://earthengine.google.com 用 Google 帳號註冊（免費，秒過審核）
2. 在專案根目錄執行認證：
   ```powershell
   .\\.venv\\Scripts\\python.exe -m ee authenticate
   ```
   會跳出瀏覽器，登入並授權即可。
3. 回來按上面的「🛰 抓取 / 更新 NTL 資料」按鈕。
""")
    st.stop()

# --------- 主圖：選 ROI 看 NTL 時序 ----------
st.subheader("ROI 月度燈光時序")

roi_choices = sorted(cached["roi_name"].unique().tolist())
selected_roi = st.selectbox("選擇 ROI", roi_choices)

sub = cached[cached["roi_name"] == selected_roi].sort_values("date")
roi_row = rois[rois["roi_name"] == selected_roi]
related_tickers = ""
if not roi_row.empty:
    related_tickers = str(roi_row.iloc[0].get("related_tickers", "") or "")

c1, c2, c3 = st.columns(3)
c1.metric("最新月份", sub["date"].max().strftime("%Y-%m"))
c2.metric("最新燈光值", f"{sub['avg_rad'].iloc[-1]:.2f} nW/cm²/sr")
c3.metric("資料點數", f"{len(sub)} 月")

# YoY 對照圖
sub_yoy = sub.copy()
sub_yoy["yoy_pct"] = sub_yoy["avg_rad"].pct_change(periods=12) * 100

fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_trace(
    go.Scatter(x=sub["date"], y=sub["avg_rad"], name="月度燈光亮度",
               line=dict(color="#1f77b4", width=2)),
    secondary_y=False,
)
fig.add_trace(
    go.Scatter(x=sub_yoy["date"], y=sub_yoy["yoy_pct"], name="YoY %",
               line=dict(color="#d62728", width=1)),
    secondary_y=True,
)
fig.update_layout(
    title=f"{selected_roi} — 夜間燈光月度時序",
    xaxis_title="日期",
    height=480,
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)
fig.update_yaxes(title_text="月度平均亮度 (nW/cm²/sr)", color="#1f77b4", secondary_y=False)
fig.update_yaxes(title_text="同期年增率 %", color="#d62728", secondary_y=True)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# --------- 與股價對照 ----------
if related_tickers.strip():
    st.subheader(f"與關聯個股股價對照")
    st.caption(f"{selected_roi} 關聯代碼：{related_tickers}")

    tickers = [t.strip() for t in related_tickers.split(",") if t.strip()]
    companies = load_companies()
    available = [t for t in tickers if t in companies["ticker"].astype(str).tolist()]

    if not available:
        st.info(f"未在公司清單中找到 {tickers}。先到 🏢 公司清單 註冊這些公司，並執行一鍵分析抓股價。")
    else:
        ticker_choice = st.selectbox("關聯個股", available)

        with get_conn() as conn:
            init_schema(conn)
            prices = read_prices(conn, ticker=ticker_choice)

        if prices.empty:
            st.info(f"{ticker_choice} 沒有股價資料，請先去公司清單跑「重新匯入」。")
        else:
            prices = prices.set_index("date")
            price_monthly = prices["adj_close"].resample("MS").last()

            # 對齊兩條線的時段
            ntl = sub.set_index("date")["avg_rad"]
            ntl.index = pd.to_datetime(ntl.index)
            price_monthly.index = pd.to_datetime(price_monthly.index)
            start = max(ntl.index.min(), price_monthly.index.min())
            end = min(ntl.index.max(), price_monthly.index.max())
            ntl_aligned = ntl.loc[start:end]
            price_aligned = price_monthly.loc[start:end]

            fig2 = make_subplots(specs=[[{"secondary_y": True}]])
            fig2.add_trace(
                go.Scatter(x=ntl_aligned.index, y=ntl_aligned.values,
                           name=f"{selected_roi} 夜間燈光", line=dict(color="#1f77b4", width=2)),
                secondary_y=False,
            )
            fig2.add_trace(
                go.Scatter(x=price_aligned.index, y=price_aligned.values,
                           name=f"{ticker_choice} 月收盤", line=dict(color="#ff7f0e", width=2)),
                secondary_y=True,
            )
            fig2.update_layout(
                title=f"{selected_roi} 夜間燈光 vs {ticker_choice} 股價（月線）",
                xaxis_title="日期",
                height=520,
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig2.update_yaxes(title_text="夜間燈光 (nW/cm²/sr)", color="#1f77b4", secondary_y=False)
            fig2.update_yaxes(title_text="股價", color="#ff7f0e", secondary_y=True)
            st.plotly_chart(fig2, use_container_width=True)

            # 簡單相關係數
            df_corr = pd.concat([ntl_aligned.rename("ntl"), price_aligned.rename("px")], axis=1).dropna()
            if len(df_corr) >= 6:
                from scipy.stats import pearsonr
                r, p = pearsonr(df_corr["ntl"], df_corr["px"])
                col1, col2 = st.columns(2)
                col1.metric("Pearson r（燈光 vs 股價）", f"{r:.3f}")
                col2.metric("p value", f"{p:.4f}")
                if abs(r) > 0.6 and p < 0.05:
                    st.success("**訊號顯著**：燈光亮度與股價有中度以上相關性。")
                elif abs(r) > 0.4:
                    st.info("中度相關。可進一步看領先/落後或對單一公司營收驗證。")
                else:
                    st.warning("弱相關 — 可能 (1) ROI 不夠精準（範圍太大或太小），(2) 該公司不是該聚落主導者，(3) 資料噪音大。")
else:
    st.caption(f"💡 編輯 reference/ntl_rois.csv 為 {selected_roi} 加入關聯股票代碼可解鎖股價對照圖。")

st.divider()
st.markdown("""
### 解讀小提示

- **絕對值意義有限**：夜間燈光的 nW/cm²/sr 不是「景氣分數」，**看相對變化和 YoY**
- **YoY > 5% 持續數月**：聚落整體擴張中（新廠房、夜班加多、燈光擴張）
- **YoY < -5% 持續數月**：產能收縮、節能、或經濟下行
- **解析度限制**：~500m，所以 ROI 半徑 2-5km 較適合（單一廠房太小看不清）
- **季節性**：北半球冬季雪反射會虛胖亮度，建議比較 YoY 而非絕對值
- **VIIRS-DNB 從 2012-04 才有**，再早只能用 DMSP-OLS（解析度差很多）
""")
