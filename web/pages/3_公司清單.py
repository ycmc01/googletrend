"""公司清單 — 註冊與管理追蹤的股票。

新增公司時會自動：
  1. XQAPI 查詢公司全名 (可手動覆寫)
  2. 儲存公司
  3. 自動匯入最近 16 季營收
  4. 自動匯入最近 1500 個交易日的股價
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import streamlit as st

from gits.collectors.prices import save_parquet as save_prices_parquet
from gits.config import RAW_DIR
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
    upsert_prices,
)
from gits.xqapi import (
    get_basic_info,
    get_kline,
    get_quarterly_financial_report,
    kline_to_prices_df,
    quarterly_revenue_to_rows,
)

st.set_page_config(page_title="GITS — 公司清單", page_icon="🏢", layout="wide")
st.title("🏢 公司清單")
st.caption("註冊要追蹤的股票。儲存時會自動匯入該公司的營收與股價 — 不必再手動執行。")


def _xqapi_lookup():
    """XQAPI 查詢公司名 callback。"""
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

    st.session_state.co_name_field = name_raw
    notes_parts = [p for p in [industry, sector] if p]
    if notes_parts:
        st.session_state.co_notes_field = " / ".join(notes_parts)
    extra = f"（{exchange}）" if exchange else ""
    st.session_state._lookup_msg = ("success", f"已自動帶入：{name_raw} {extra}")


def _save_company():
    """儲存公司 callback — 只負責 sanity check + 記錄要儲存的目標。
    實際的儲存 + 自動匯入會在 callback 結束後執行（這樣才能顯示 spinner）。
    """
    ticker = (st.session_state.get("co_ticker_field") or "").strip().upper()
    name = (st.session_state.get("co_name_field") or "").strip()
    fy_end = int(st.session_state.get("co_fy_end_field") or 12)
    notes = (st.session_state.get("co_notes_field") or "").strip()

    if not ticker:
        st.session_state._save_msg = ("error", "請輸入股票代碼")
        return
    if not name:
        # 沒填名稱就先自動跑 XQAPI 查
        _xqapi_lookup()
        name = (st.session_state.get("co_name_field") or "").strip()
        if not name:
            st.session_state._save_msg = ("error", "請輸入公司名稱（或先按查詢自動帶入）")
            return

    bare = ticker.split(".")[0]
    # 標記為「待處理」，下面主流程會看到後執行完整匯入
    st.session_state._pending_company = {
        "ticker": bare, "name": name,
        "fiscal_year_end_month": fy_end, "notes": notes,
    }


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
bcol2.button("✅ 儲存並自動匯入（公司 + 16 季營收 + 1500 天股價）",
             on_click=_save_company, type="primary", use_container_width=True)

# 顯示 lookup 訊息
if msg := st.session_state.pop("_lookup_msg", None):
    severity, text = msg
    getattr(st, severity)(text)

# 處理「待儲存 + 自動匯入」（這在 callback 之外執行，所以可以顯示 spinner）
if pending := st.session_state.pop("_pending_company", None):
    bare = pending["ticker"]
    name = pending["name"]
    summary = []

    # 1. 儲存公司
    with st.spinner(f"[1/3] 儲存公司 {bare}…"):
        df = load_companies()
        df = df[df["ticker"].astype(str).str.upper() != bare]
        new_row = pd.DataFrame([pending])
        save_companies(pd.concat([df, new_row], ignore_index=True))
    summary.append(f"✅ 已儲存公司 {bare}（{name}）")

    # 2. 自動匯入營收
    with st.spinner(f"[2/3] 從 XQAPI 匯入 {bare} 的 16 季營收…"):
        try:
            payload = get_quarterly_financial_report(bare, count=16)
            rev_rows = quarterly_revenue_to_rows(payload, bare)
            if rev_rows:
                new_df = pd.DataFrame(rev_rows)
                all_weights = load_weights()
                keep = all_weights[~(
                    (all_weights["ticker"].astype(str).str.upper() == bare)
                    & (all_weights["segment"] == "Total")
                )]
                save_weights(pd.concat([keep, new_df], ignore_index=True))
                summary.append(f"✅ 已匯入 {len(rev_rows)} 季營收（Total segment）")
            else:
                summary.append("⚠️ XQAPI 沒回傳營收資料（可能不支援此代碼）")
        except Exception as e:
            summary.append(f"⚠️ 營收匯入失敗：{e}")

    # 3. 自動匯入股價
    with st.spinner(f"[3/3] 從 XQAPI 抓取 {bare} 的 1500 日 K 線…"):
        try:
            kline = get_kline(bare, count=1500)
            prices_df = kline_to_prices_df(kline, bare)
            if not prices_df.empty:
                save_prices_parquet(prices_df, RAW_DIR, f"prices_{bare}")
                with get_conn() as conn:
                    init_schema(conn)
                    upsert_prices(conn, prices_df)
                summary.append(f"✅ 已匯入 {len(prices_df)} 個交易日股價（{prices_df['date'].min()} ~ {prices_df['date'].max()}）")
            else:
                summary.append("⚠️ XQAPI 沒回傳 K 線資料")
        except Exception as e:
            summary.append(f"⚠️ 股價匯入失敗：{e}")

    st.success("**" + "  /  ".join(summary[:1]) + "**")
    for line in summary[1:]:
        st.write(line)
    st.info(f"下一步：到 **🏷 關鍵字組** 為 {bare} 設定要追蹤的關鍵字，再到 **⚙ 進階執行** 抓取 Google Trends 並計算 GITS。")

    # 清空表單
    st.session_state.co_ticker_field = ""
    st.session_state.co_name_field = ""
    st.session_state.co_notes_field = ""
    st.session_state.co_fy_end_field = 12
    st.balloons()

if msg := st.session_state.pop("_save_msg", None):
    severity, text = msg
    getattr(st, severity)(text)

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

    # 重新匯入功能（避免使用者覺得「沒辦法 refresh」）
    with st.expander("🔄 重新匯入已存在公司的營收與股價"):
        st.caption("如果一段時間沒更新、或要拿到最新一季資料，可以重新抓。")
        ref_ticker = st.selectbox("選擇代碼", [""] + companies["ticker"].astype(str).tolist(), key="refresh_ticker")
        if ref_ticker and st.button(f"重新匯入 {ref_ticker}", key="refresh_btn"):
            steps = []
            with st.spinner(f"匯入 {ref_ticker} 的營收…"):
                try:
                    payload = get_quarterly_financial_report(ref_ticker, count=16)
                    rev_rows = quarterly_revenue_to_rows(payload, ref_ticker)
                    if rev_rows:
                        new_df = pd.DataFrame(rev_rows)
                        all_w = load_weights()
                        keep = all_w[~(
                            (all_w["ticker"].astype(str).str.upper() == ref_ticker.upper())
                            & (all_w["segment"] == "Total")
                        )]
                        save_weights(pd.concat([keep, new_df], ignore_index=True))
                        steps.append(f"✅ {len(rev_rows)} 季營收")
                    else:
                        steps.append("⚠️ 無營收資料")
                except Exception as e:
                    steps.append(f"⚠️ 營收失敗：{e}")
            with st.spinner(f"匯入 {ref_ticker} 的股價…"):
                try:
                    kline = get_kline(ref_ticker, count=1500)
                    prices_df = kline_to_prices_df(kline, ref_ticker)
                    if not prices_df.empty:
                        save_prices_parquet(prices_df, RAW_DIR, f"prices_{ref_ticker}")
                        with get_conn() as conn:
                            init_schema(conn)
                            upsert_prices(conn, prices_df)
                        steps.append(f"✅ {len(prices_df)} 天股價")
                    else:
                        steps.append("⚠️ 無 K 線資料")
                except Exception as e:
                    steps.append(f"⚠️ 股價失敗：{e}")
            st.success(f"完成：{' / '.join(steps)}")
            st.rerun()

    with st.expander("⚠ 刪除公司"):
        ticker_to_del = st.selectbox("選擇要刪除的代碼", [""] + companies["ticker"].astype(str).tolist(),
                                       key="del_ticker")
        if ticker_to_del and st.button("🗑 刪除此公司（連同其關鍵字組與營收）", type="primary", key="del_btn"):
            save_companies(companies[companies["ticker"].astype(str).str.upper() != ticker_to_del.upper()])
            if not segments.empty:
                save_segments(segments[segments["ticker"].astype(str).str.upper() != ticker_to_del.upper()])
            if not weights.empty:
                save_weights(weights[weights["ticker"].astype(str).str.upper() != ticker_to_del.upper()])
            st.success(f"已刪除 {ticker_to_del}")
            st.rerun()
