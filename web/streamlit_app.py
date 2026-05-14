"""GITS Scanner — 主入口。

使用 st.navigation 自訂側邊欄頁面名稱（不靠檔名）。檔名維持 ASCII
讓 .bat 啟動器不必處理 cp950 trail-byte 問題。
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
from gits.engine.weighting import compute_gits_index, load_weights_long
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
    get_basic_info,
    get_kline,
    get_quarterly_financial_report,
    kline_to_prices_df,
    norm_ticker,
    quarterly_revenue_to_rows,
)

st.set_page_config(page_title="GITS分析", page_icon="🚀", layout="wide")


GEO_OPTIONS = {
    "台灣 (TW)": "TW",
    "全球": "",
    "美國 (US)": "US",
    "日本 (JP)": "JP",
    "香港 (HK)": "HK",
}

NEW_CHOICE = "🆕 新增其他公司..."


# -------- helpers --------

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


def _save_or_update_single_segment(bare_ticker: str, keywords: list[str]) -> None:
    """寫入單一 segment「自訂組合」（僅用於新公司或單一 segment 公司）。"""
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


# -------- home page renderer --------

def _render_home_page():
    """一鍵分析主頁。"""
    st.title("🚀 GITS分析")
    st.caption("從清單選已有公司就會自動帶入關鍵字，按一次按鈕就能看到股價 vs 搜尋熱度週線圖。")

    companies_df = load_companies()
    existing_tickers = companies_df["ticker"].astype(str).tolist()

    ticker_choices = existing_tickers + [NEW_CHOICE] if existing_tickers else [NEW_CHOICE]
    selected = st.selectbox("公司", ticker_choices, index=0)

    if selected == NEW_CHOICE:
        is_new = True
        multi_segment_mode = False
        cc1, cc2 = st.columns([1, 2])
        new_ticker = cc1.text_input("股票代碼", placeholder="例：TSLA")
        geo_label = cc2.selectbox("搜尋熱度區域", list(GEO_OPTIONS.keys()), index=0)
        default_keywords = ""
        ticker_for_run = new_ticker.strip()
        company_display_name = ticker_for_run.upper() if ticker_for_run else None
    else:
        is_new = False
        ticker_for_run = selected
        row = companies_df[companies_df["ticker"].astype(str) == selected].iloc[0]
        company_display_name = row["name"]

        cc1, cc2 = st.columns([1, 2])
        cc1.markdown(f"**公司名稱**：{company_display_name}")
        geo_label = cc2.selectbox("搜尋熱度區域", list(GEO_OPTIONS.keys()), index=0)

        segs = load_segments(selected)
        multi_segment_mode = len(segs) > 1

        if multi_segment_mode:
            st.success(f"**{selected} 已有 {len(segs)} 個 segment（將沿用既有設定，不會覆寫）：**")
            seg_summary = pd.DataFrame({
                "Segment": segs["segment_name"],
                "關鍵字": segs["trends_keywords"].astype(str).str.replace("|", ", "),
            })
            st.dataframe(seg_summary, use_container_width=True, hide_index=True)
            default_keywords = None
        else:
            existing_kws = []
            if not segs.empty:
                for kw in str(segs.iloc[0]["trends_keywords"]).split("|"):
                    if kw.strip():
                        existing_kws.append(kw.strip())
            default_keywords = "\n".join(existing_kws)

    if not multi_segment_mode:
        keywords_input = st.text_area(
            "關鍵字組（每行一個）" + ("" if is_new else "　— 已載入既有設定，編輯後送出會覆寫"),
            value=default_keywords or "",
            placeholder="AI\nLLM\nAI Agent",
            height=140,
            help="這些關鍵字會在 Google Trends 中合併查詢，作為單一綜合搜尋熱度指標",
        )
    else:
        keywords_input = None

    submit = st.button("🚀 開始分析", type="primary", use_container_width=True)

    if not submit:
        return

    # --- 執行流程 ---
    if not ticker_for_run:
        st.error("請選擇公司或輸入股票代碼")
        return

    if not multi_segment_mode and not (keywords_input or "").strip():
        st.error("請輸入至少一個關鍵字")
        return

    bare = _bare(ticker_for_run)
    geo = GEO_OPTIONS[geo_label]

    progress = st.progress(0.0)
    status = st.empty()

    if is_new:
        status.info(f"⏳ 步驟 1/5：註冊 {bare} 並查詢公司資訊…")
        try:
            info = get_basic_info(bare, fields="公司全名,交易所產業分類")
            company_name = _extract_company_name(info) or bare
        except Exception as e:
            st.warning(f"XQAPI 查詢公司失敗（以代碼代替）：{e}")
            company_name = bare
        _save_company(bare, company_name)
        local_company_display = company_name
    else:
        status.info(f"⏳ 步驟 1/5：使用已有公司 {bare}（{company_display_name}）")
        local_company_display = company_display_name
    progress.progress(0.20)

    if not multi_segment_mode:
        keywords = [k.strip() for k in (keywords_input or "").splitlines() if k.strip()]
        status.info(f"⏳ 步驟 2/5：儲存關鍵字組（{len(keywords)} 個）…")
        _save_or_update_single_segment(bare, keywords)
    else:
        status.info(f"⏳ 步驟 2/5：使用既有 {len(load_segments(bare))} 個 segment 設定…")
    progress.progress(0.35)

    status.info("⏳ 步驟 3/5：從 XQAPI 匯入季營收（若已存在會更新）…")
    n_rev = _save_revenue(bare)
    progress.progress(0.50)

    status.info("⏳ 步驟 4/5：從 XQAPI 抓取股價 K 線…")
    try:
        kline_payload = get_kline(bare, count=1500)
        prices_df = kline_to_prices_df(kline_payload, bare)
        save_prices_parquet(prices_df, RAW_DIR, f"prices_{bare}")
        with get_conn() as conn:
            init_schema(conn)
            upsert_prices(conn, prices_df)
    except Exception as e:
        st.error(f"股價抓取失敗：{e}")
        return
    progress.progress(0.70)

    status.info("⏳ 步驟 5/5：抓取 Google Trends 搜尋熱度並計算 GITS（10-30 秒）…")
    segs_for_fetch = load_segments(bare)
    try:
        trends_df = fetch_cross_segment_trends(segs_for_fetch, timeframe="today 5-y", geo=geo, ticker=bare)
        save_trends_parquet(trends_df, RAW_DIR, f"trends_{bare}_{geo or 'WW'}")
        with get_conn() as conn:
            init_schema(conn)
            upsert_trends(conn, trends_df)
    except Exception as e:
        st.error(f"Google Trends 抓取失敗（可能達到頻率限制，請稍候再試）：{e}")
        return

    with get_conn() as conn:
        init_schema(conn)
        trends_long = read_trends(conn, ticker=bare, geo=geo or "WW")
        prices = read_prices(conn, ticker=bare).set_index("date")

    weights_long = load_weights_long(bare)
    traffic_wide = pivot_trends_wide(trends_long)
    if weights_long.empty:
        gits_weekly = traffic_wide.iloc[:, 0] if len(traffic_wide.columns) else pd.Series(dtype=float)
        st.warning("沒有營收資料，GITS 直接等於關鍵字組原始搜尋熱度（未做加權）。")
    else:
        gits_df = compute_gits_index(traffic_wide, weights_long)
        gits_weekly = gits_df["gits"]
        upsert_to_segment_weights = weights_long.assign(ticker=bare)[
            ["ticker", "quarter_end", "segment", "revenue_usd_m", "weight_pct"]
        ]
        with get_conn() as conn:
            upsert_segment_weights(conn, upsert_to_segment_weights)

    price_weekly = prices["adj_close"].resample("W").last() if not prices.empty else pd.Series(dtype=float)
    progress.progress(1.0)
    status.success(f"✅ 完成！{local_company_display}（{bare}）")

    st.divider()

    fig = weekly_gits_vs_price(
        gits_weekly.dropna(),
        price_weekly.dropna(),
        title=f"{local_company_display} ({bare}) — GITS 搜尋指標 vs 股價（週線）",
    )
    st.plotly_chart(fig, use_container_width=True)

    m1, m2, m3, m4 = st.columns(4)
    g = gits_weekly.dropna()
    p = price_weekly.dropna()
    m1.metric("GITS 最新值", f"{g.iloc[-1]:.1f}" if g.size else "—")
    m2.metric("股價最新值", f"{p.iloc[-1]:.2f}" if p.size else "—")
    m3.metric("資料週數", f"{g.size} 週")
    m4.metric("資料區間", f"{g.index.min().date()} ~ {g.index.max().date()}" if g.size else "—")

    st.divider()
    st.subheader("下一步")
    st.markdown(f"""
- **想看更深入的分析？** 點左側 **📈 詳細報告**，選 `{bare}` 查看：
  - 三軸對照圖（GITS / 季營收 / 股價）
  - 季度對齊的領先/落後相關係數
  - 去季節性後的訊號強度
- **不懂報告怎麼看？** 點左側 **📖 使用說明** 看圖表閱讀指南
- **想調整關鍵字組？** 點左側 **🏷 關鍵字組**，可以新增多個 segment 做加權
- **想看更多季營收明細？** 點左側 **💰 營收資料**
    """)

    if n_rev:
        st.caption(f"💡 已自動匯入/更新 {n_rev} 季營收資料")


# -------- 多頁面導覽 --------

pages = [
    st.Page(_render_home_page, title="GITS分析", icon="🚀", default=True),
    st.Page("pages/1_詳細報告.py", title="詳細報告", icon="📈"),
    st.Page("pages/2_使用說明.py", title="使用說明", icon="📖"),
    st.Page("pages/3_公司清單.py", title="公司清單", icon="🏢"),
    st.Page("pages/4_關鍵字組.py", title="關鍵字組", icon="🏷"),
    st.Page("pages/5_營收資料.py", title="營收資料", icon="💰"),
    st.Page("pages/6_進階執行.py", title="進階執行", icon="⚙"),
]

pg = st.navigation(pages)
pg.run()
