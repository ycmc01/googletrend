"""GITS Scanner — 一鍵分析（主入口）。

簡化流程：使用者只需輸入股票代碼 + 關鍵字 → 自動跑完整 pipeline → 顯示週線圖。
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import plotly.io as pio
import streamlit as st

pio.renderers.default = "browser"

from gits.analysis.plots import weekly_gits_vs_price
from gits.collectors.prices import save_parquet as save_prices_parquet
from gits.collectors.trends import fetch_cross_segment_trends, save_trends_parquet
from gits.config import RAW_DIR
from gits.engine.normalize import pivot_trends_wide
from gits.engine.weighting import compute_gits_index, load_total_revenue, load_weights_long
from gits.reference import (
    load_companies,
    load_segments,
    load_weights,
    save_companies,
    save_segments,
    save_weights,
)
from gits.storage.duckdb_io import (
    get_conn,
    init_schema,
    read_prices,
    read_trends,
    upsert_prices,
    upsert_segment_weights,
    upsert_trends,
)
from gits.xqapi import (
    extract_field,
    get_basic_info,
    get_kline,
    get_quarterly_financial_report,
    kline_to_prices_df,
    norm_ticker,
    quarterly_revenue_to_rows,
)

st.set_page_config(page_title="GITS 一鍵分析", page_icon="🚀", layout="wide")
st.title("🚀 GITS 一鍵分析")
st.caption("輸入股票代碼與關鍵字 → 自動產生股價與 GITS 搜尋熱度週線對照圖")

GEO_OPTIONS = {
    "台灣 (TW)": "TW",
    "全球": "",
    "美國 (US)": "US",
    "日本 (JP)": "JP",
    "香港 (HK)": "HK",
}

with st.form("quick_analyze"):
    c1, c2 = st.columns([1, 2])
    ticker = c1.text_input("股票代碼", placeholder="例：2330 或 AAPL", help="台股輸入 4 位數代碼，美股輸入英文代號")
    geo_label = c2.selectbox("搜尋熱度區域", list(GEO_OPTIONS.keys()), index=0,
                              help="選擇 Google Trends 搜尋的地理範圍")
    keywords_input = st.text_area(
        "關鍵字組（一行一個）",
        placeholder="AI\nLLM\nAI Agent",
        height=140,
        help="這些關鍵字會在 Google Trends 中合併查詢，作為單一綜合搜尋熱度指標",
    )
    submit = st.form_submit_button("🚀 開始分析", type="primary", use_container_width=True)


def _bare(ticker: str) -> str:
    return norm_ticker(ticker).split(".", 1)[0]


def _extract_company_name(payload: dict) -> str | None:
    for f in payload.get("fields", []):
        if f.get("cName") == "公司全名":
            try:
                return f["values"][0]["value"]
            except (KeyError, IndexError):
                return None
    return None


def _save_company(bare_ticker: str, name: str) -> None:
    df = load_companies()
    df = df[df["ticker"].astype(str).str.upper() != bare_ticker.upper()]
    is_tw = bare_ticker.isdigit()
    new_row = pd.DataFrame([{
        "ticker": bare_ticker,
        "name": name,
        "fiscal_year_end_month": 12 if is_tw else 9,
        "notes": "由一鍵分析建立",
    }])
    save_companies(pd.concat([df, new_row], ignore_index=True))


def _save_segment(bare_ticker: str, keywords: list[str]) -> None:
    df = load_segments()
    df = df[df["ticker"].astype(str).str.upper() != bare_ticker.upper()]
    new_row = pd.DataFrame([{
        "ticker": bare_ticker,
        "segment_name": "自訂組合",
        "trends_topic_id": "",
        "trends_keywords": "|".join(keywords),
        "exclude_terms": "",
        "notes": "由一鍵分析建立",
    }])
    save_segments(pd.concat([df, new_row], ignore_index=True))


def _save_revenue(bare_ticker: str) -> int:
    try:
        fin = get_quarterly_financial_report(bare_ticker, count=16)
        rows = quarterly_revenue_to_rows(fin, bare_ticker)
    except Exception:
        return 0
    if not rows:
        return 0
    new_df = pd.DataFrame(rows)
    all_weights = load_weights()
    keep = all_weights[~(
        (all_weights["ticker"].astype(str).str.upper() == bare_ticker.upper())
        & (all_weights["segment"] == "Total")
    )]
    save_weights(pd.concat([keep, new_df], ignore_index=True))
    return len(rows)


if submit:
    if not ticker or not keywords_input:
        st.error("請輸入股票代碼與至少一個關鍵字")
        st.stop()

    bare = _bare(ticker)
    keywords = [k.strip() for k in keywords_input.splitlines() if k.strip()]
    geo = GEO_OPTIONS[geo_label]

    progress = st.progress(0.0)
    status = st.empty()

    # Step 1: XQAPI 公司資訊
    status.info("⏳ 步驟 1/5：從 XQAPI 查詢公司全名…")
    try:
        info = get_basic_info(bare, fields="公司全名,交易所產業分類")
        company_name = _extract_company_name(info) or bare
    except Exception as e:
        st.warning(f"XQAPI 查詢失敗（將以代碼為名）：{e}")
        company_name = bare
    _save_company(bare, company_name)
    _save_segment(bare, keywords)
    progress.progress(0.20)

    # Step 2: 季營收
    status.info("⏳ 步驟 2/5：匯入季營收（XQAPI）…")
    n_rev = _save_revenue(bare)
    progress.progress(0.40)

    # Step 3: 股價
    status.info("⏳ 步驟 3/5：抓取股價 K 線（XQAPI）…")
    try:
        kline_payload = get_kline(bare, count=1500)
        prices_df = kline_to_prices_df(kline_payload, bare)
        save_prices_parquet(prices_df, RAW_DIR, f"prices_{bare}")
        with get_conn() as conn:
            init_schema(conn)
            upsert_prices(conn, prices_df)
    except Exception as e:
        st.error(f"股價抓取失敗：{e}")
        st.stop()
    progress.progress(0.60)

    # Step 4: Google Trends
    status.info("⏳ 步驟 4/5：抓取 Google Trends 搜尋熱度（可能需 10-30 秒）…")
    seg_payload = pd.DataFrame([{
        "ticker": bare,
        "segment_name": "自訂組合",
        "trends_topic_id": "",
        "trends_keywords": "|".join(keywords),
        "exclude_terms": "",
    }])
    try:
        trends_df = fetch_cross_segment_trends(seg_payload, timeframe="today 5-y", geo=geo, ticker=bare)
        save_trends_parquet(trends_df, RAW_DIR, f"trends_{bare}_{geo or 'WW'}")
        with get_conn() as conn:
            init_schema(conn)
            upsert_trends(conn, trends_df)
    except Exception as e:
        st.error(f"Google Trends 抓取失敗（可能達到頻率限制，請稍後再試）：{e}")
        st.stop()
    progress.progress(0.80)

    # Step 5: GITS 計算
    status.info("⏳ 步驟 5/5：計算 GITS 指標並繪圖…")
    with get_conn() as conn:
        init_schema(conn)
        trends_long = read_trends(conn, ticker=bare, geo=geo or "WW")
        prices = read_prices(conn, ticker=bare).set_index("date")

    weights_long = load_weights_long(bare)
    traffic_wide = pivot_trends_wide(trends_long)
    if weights_long.empty:
        gits_weekly = traffic_wide.iloc[:, 0]
        st.warning("沒有營收資料，GITS 直接等於關鍵字組原始搜尋熱度（未做加權）。")
    else:
        gits_df = compute_gits_index(traffic_wide, weights_long)
        gits_weekly = gits_df["gits"]
        upsert_to_segment_weights = weights_long.assign(ticker=bare)[
            ["ticker", "quarter_end", "segment", "revenue_usd_m", "weight_pct"]
        ]
        with get_conn() as conn:
            upsert_segment_weights(conn, upsert_to_segment_weights)

    price_weekly = prices["adj_close"].resample("W").last()
    progress.progress(1.0)
    status.success(f"✅ 完成！{company_name} ({bare})")

    st.divider()

    # 主圖：GITS + 股價 週線
    fig = weekly_gits_vs_price(
        gits_weekly.dropna(),
        price_weekly.dropna(),
        title=f"{company_name} ({bare}) — GITS 搜尋指標 vs 股價（週線）",
    )
    st.plotly_chart(fig, use_container_width=True)

    # 摘要卡片
    m1, m2, m3, m4 = st.columns(4)
    latest_gits = float(gits_weekly.dropna().iloc[-1]) if gits_weekly.dropna().size else float("nan")
    latest_price = float(price_weekly.dropna().iloc[-1]) if price_weekly.dropna().size else float("nan")
    latest_date = gits_weekly.dropna().index.max()
    earliest_date = gits_weekly.dropna().index.min()
    m1.metric("GITS 最新值", f"{latest_gits:.1f}" if pd.notna(latest_gits) else "—")
    m2.metric("股價最新值", f"{latest_price:.2f}" if pd.notna(latest_price) else "—")
    m3.metric("週數", f"{gits_weekly.dropna().size} 週")
    m4.metric("資料區間", f"{earliest_date.date()} ~ {latest_date.date()}" if pd.notna(latest_date) else "—")

    # 後續導引
    st.divider()
    st.subheader("下一步")
    st.markdown(f"""
- **想看更深入的分析？** 點左側選單的 **📈 詳細報告**，選 `{bare}` 查看：
  - 三軸對照圖（GITS / 季營收 / 股價）
  - 季度對齊的領先/落後相關係數
  - 去季節性後的訊號強度
- **不懂報告怎麼看？** 點左側 **📖 使用說明** 看圖表閱讀指南
- **想調整關鍵字組？** 點左側 **🏷 關鍵字組**，可以新增多個 segment 做加權
- **想看更多季營收明細？** 點左側 **💰 營收資料**
    """)

    if n_rev:
        st.caption(f"💡 已自動匯入 {n_rev} 季營收資料")
