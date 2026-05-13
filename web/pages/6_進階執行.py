"""進階執行 — 分步驟跑 fetch / compute / report 管線。"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "web"))

import streamlit as st

from gits.reference import load_companies
from lib.utils import run_cli

st.set_page_config(page_title="GITS — 進階執行", page_icon="⚙", layout="wide")
st.title("⚙ 進階執行（手動管線）")
st.caption("分步驟控制每個 pipeline 階段。一般使用者建議用「🚀 一鍵分析」一次跑完。")

companies = load_companies()
if companies.empty:
    st.warning("請先到 **🏢 公司清單** 註冊公司。")
    st.stop()

ticker = st.selectbox("選擇公司", companies["ticker"].astype(str).tolist())

st.divider()

GEO_OPTIONS = {
    "全球": "",
    "台灣 (TW)": "TW",
    "美國 (US)": "US",
    "日本 (JP)": "JP",
    "香港 (HK)": "HK",
    "韓國 (KR)": "KR",
    "中國大陸 (CN)": "CN",
    "新加坡 (SG)": "SG",
    "英國 (GB)": "GB",
}

# Step 1
st.subheader("步驟 1 · 抓取 Google Trends 搜尋熱度")
c1, c2 = st.columns([1, 1])
geo_label = c1.selectbox("搜尋區域", list(GEO_OPTIONS.keys()), index=0)
geo = GEO_OPTIONS[geo_label]
timeframe = c2.text_input("時間範圍", value="today 5-y",
                          help="範例：'today 5-y'、'today 12-m'、'2020-01-01 2025-12-31'")
if st.button("🌐 抓取 Trends", type="primary"):
    with st.spinner("正在呼叫 pytrends…"):
        cli_args = ["fetch", "trends", ticker, "--timeframe", timeframe]
        if geo:
            cli_args.extend(["--geo", geo])
        rc, out, err = run_cli(*cli_args)
    if rc == 0:
        st.success("Trends 抓取完成")
    else:
        st.error(f"失敗（exit {rc}）")
    st.code(out + ("\n--- STDERR ---\n" + err if err else ""), language=None)

st.divider()

# Step 2
st.subheader("步驟 2 · 抓取股價（XQAPI K 線）")
count = st.number_input("日 K 棒數", min_value=100, max_value=5000, value=1500, step=100,
                        help="1500 ≈ 台股 6 年、美股 ~6 年（交易日略少）")
if st.button("💹 抓取股價", type="primary"):
    with st.spinner("正在呼叫 XQAPI…"):
        rc, out, err = run_cli("fetch", "prices", ticker, "--count", str(count))
    if rc == 0:
        st.success("股價抓取完成")
    else:
        st.error(f"失敗（exit {rc}）")
    st.code(out + ("\n--- STDERR ---\n" + err if err else ""), language=None)

st.divider()

# Step 3
st.subheader("步驟 3 · 計算 GITS 指標")
geo_for_compute = geo if geo else "WW"
st.caption(f"將以 geo = `{geo_for_compute}` 讀取（須與步驟 1 一致）")
if st.button("🧮 計算 GITS", type="primary"):
    with st.spinner("正在計算加權指標…"):
        rc, out, err = run_cli("compute", ticker, "--geo", geo_for_compute)
    if rc == 0:
        st.success("GITS 計算完成")
    else:
        st.error(f"失敗（exit {rc}）")
    st.code(out + ("\n--- STDERR ---\n" + err if err else ""), language=None)

st.divider()

# Step 4
st.subheader("步驟 4 · 產生 HTML 報告")
if st.button("📊 產生報告", type="primary"):
    with st.spinner("正在執行 notebook（可能需 1 分鐘）…"):
        rc, out, err = run_cli("report", ticker)
    if rc == 0:
        report_path = PROJECT_ROOT / "notebooks" / f"report_{ticker.upper()}.html"
        st.success(f"報告產生完成：{report_path}")
        st.markdown(f"可用瀏覽器開啟：`{report_path}`")
        if report_path.exists():
            with open(report_path, "rb") as f:
                st.download_button(
                    "⬇ 下載 HTML 報告", f, file_name=report_path.name, mime="text/html"
                )
    else:
        st.error(f"失敗（exit {rc}）")
    st.code(out + ("\n--- STDERR ---\n" + err if err else ""), language=None)
