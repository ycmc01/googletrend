"""主題趨勢 — 查任意產業／題材名詞的 Google Trends 搜尋熱度。

與其他頁面不同，這頁不綁公司、不算營收加權，純粹比較關鍵字本身的
相對搜尋熱度（RSV）。一次查詢最多 5 個詞（pytrends 單查上限），
所有詞在同一次查詢內取得，RSV 為跨詞可比的 0-100 刻度。
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from gits.collectors.trends import fetch_cross_segment_trends

st.set_page_config(page_title="GITS — 主題趨勢", page_icon="🔍", layout="wide")
st.title("🔍 主題趨勢")
st.caption(
    "查任意產業／題材名詞的 Google 搜尋熱度，不需綁公司。例：矽光子、小型核電、CoWoS。"
    "一次最多 5 個詞，所有詞在同一查詢內取得，熱度刻度跨詞可比。"
)

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

TIMEFRAME_OPTIONS = {
    "近 5 年": "today 5-y",
    "近 12 個月": "today 12-m",
    "近 3 個月": "today 3-m",
    "2004 至今": "all",
}


def _parse_terms(raw: str) -> list[tuple[str, str]]:
    """每行一個詞，回傳 [(顯示標籤, 查詢字串), ...]。

    支援 `標籤 = 查詢詞` 語法，方便替 Topic ID（如 /m/0k8z）取個好讀的名字。
    """
    terms: list[tuple[str, str]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if "=" in line:
            label, query = line.split("=", 1)
            label, query = label.strip(), query.strip()
        else:
            label = query = line
        if query:
            terms.append((label or query, query))
    return terms


def _build_segments_df(terms: list[tuple[str, str]]) -> pd.DataFrame:
    """把使用者輸入包成 fetch_cross_segment_trends 接受的 segments 格式。"""
    return pd.DataFrame(
        {
            "segment_name": [label for label, _ in terms],
            "trends_topic_id": ["" for _ in terms],
            "trends_keywords": [query for _, query in terms],
            "exclude_terms": ["" for _ in terms],
        }
    )


def _trend_chart(long_df: pd.DataFrame, geo_label: str) -> go.Figure:
    """各主題詞的 RSV 折線圖。"""
    fig = go.Figure()
    for seg, grp in long_df.groupby("segment", sort=False):
        fig.add_trace(
            go.Scatter(
                x=grp["date"], y=grp["rsv"], name=str(seg),
                mode="lines", line=dict(width=2),
                hovertemplate=f"{seg}: %{{y:.0f}}<extra></extra>",
            )
        )
    fig.update_layout(
        title=f"主題搜尋熱度（RSV，{geo_label}）",
        xaxis_title="日期",
        yaxis_title="相對搜尋熱度 RSV (0-100)",
        yaxis_range=[0, 105],
        height=520,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


# -------- 輸入 --------

c1, c2 = st.columns([2, 1])
keywords_input = c1.text_area(
    "主題詞（每行一個，最多 5 個）",
    placeholder="矽光子\n小型核電\nCoWoS\n固態電池\n人形機器人",
    height=170,
    help=(
        "每行一個查詢詞。短詞容易語意混淆（例：COP 可能指康菲石油／氣候大會），"
        "可改貼 Google Trends 的 Topic ID（如 /m/0k8z），並用「標籤 = /m/0k8z」"
        "語法替它取好讀的名字。"
    ),
)
geo_label = c2.selectbox("搜尋區域", list(GEO_OPTIONS.keys()), index=0)
tf_label = c2.selectbox("時間範圍", list(TIMEFRAME_OPTIONS.keys()), index=0)

submit = st.button("🔍 查詢趨勢", type="primary", use_container_width=True)

if not submit:
    st.stop()

terms = _parse_terms(keywords_input)
if not terms:
    st.error("請至少輸入一個主題詞")
    st.stop()
if len(terms) > 5:
    st.error(f"一次最多 5 個詞（pytrends 單查上限），目前有 {len(terms)} 個。請刪減。")
    st.stop()

geo = GEO_OPTIONS[geo_label]
timeframe = TIMEFRAME_OPTIONS[tf_label]
segments_df = _build_segments_df(terms)

with st.spinner("正在向 Google Trends 查詢…（10-30 秒）"):
    try:
        long_df = fetch_cross_segment_trends(
            segments_df, timeframe=timeframe, geo=geo, ticker="THEME"
        )
    except Exception as e:  # noqa: BLE001
        st.error(
            f"查詢失敗（可能達到 Google Trends 頻率限制，請稍候再試）：{e}"
        )
        st.stop()

if long_df.empty:
    st.warning("沒有取得任何資料，請換個關鍵字或稍後再試。")
    st.stop()

st.success(f"完成 — {len(terms)} 個主題詞，{long_df['date'].nunique()} 個時間點。")

st.plotly_chart(_trend_chart(long_df, geo_label), use_container_width=True)

# -------- 相對熱度摘要 --------

st.subheader("相對熱度摘要")

rows = []
for seg, grp in long_df.groupby("segment", sort=False):
    s = grp.set_index("date")["rsv"].sort_index()
    latest = s.iloc[-1] if len(s) else float("nan")
    # 與約一年前（52 週）比較；資料不足則退回最早值
    base_idx = -53 if len(s) > 53 else 0
    base = s.iloc[base_idx] if len(s) else float("nan")
    yoy = (latest - base) / base * 100 if base else float("nan")
    rows.append(
        {
            "主題詞": seg,
            "最新熱度": round(latest, 1),
            "平均熱度": round(s.mean(), 1),
            "最高熱度": round(s.max(), 1),
            "近一年變化 %": round(yoy, 1) if pd.notna(yoy) else None,
        }
    )

summary = pd.DataFrame(rows).sort_values("最新熱度", ascending=False).reset_index(drop=True)
st.dataframe(summary, use_container_width=True, hide_index=True)
st.caption(
    "RSV 為 Google Trends 相對搜尋熱度：同一查詢內最熱的時間點為 100，其餘按比例縮放。"
    "「近一年變化」為最新值相對約 52 週前的百分比變動。"
)

csv = long_df.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "⬇ 下載原始資料 (CSV)", csv,
    file_name=f"theme_trends_{geo or 'WW'}.csv", mime="text/csv",
)
