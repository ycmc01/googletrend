"""Plotly chart builders for GITS analysis (中文標籤)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def three_axis_chart(
    gits: pd.Series,
    revenue: pd.Series,
    price: pd.Series,
    title: str = "GITS 指標 vs 季營收 vs 股價",
) -> go.Figure:
    """三軸時間序列疊圖。"""
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(x=gits.index, y=gits.values, name="GITS 指標",
                   line=dict(color="#1f77b4", width=2)),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=revenue.index, y=revenue.values, name="季營收 (百萬)",
            line=dict(color="#2ca02c", width=2, dash="dot"), mode="lines+markers",
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=price.index, y=price.values, name="股價",
            line=dict(color="#ff7f0e", width=2), yaxis="y3",
        ),
    )

    fig.update_layout(
        title=title,
        xaxis=dict(domain=[0.0, 0.92], title="日期"),
        yaxis=dict(title="GITS 指標", color="#1f77b4"),
        yaxis2=dict(title="季營收 (百萬)", color="#2ca02c", anchor="x", overlaying="y", side="right"),
        yaxis3=dict(title="股價", color="#ff7f0e", anchor="free", overlaying="y", side="right", position=1.0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        height=560,
    )
    return fig


def segment_contribution_chart(contrib_wide: pd.DataFrame, title: str = "各 segment 對 GITS 的加權貢獻") -> go.Figure:
    """各 segment 加權貢獻的堆疊面積圖。"""
    fig = go.Figure()
    segments = [c for c in contrib_wide.columns if c != "gits"]
    for seg in segments:
        fig.add_trace(
            go.Scatter(
                x=contrib_wide.index,
                y=contrib_wide[seg].values,
                name=seg,
                stackgroup="one",
                hovertemplate=f"{seg}: %{{y:.2f}}<extra></extra>",
            )
        )
    fig.update_layout(title=title, height=480, hovermode="x unified",
                      xaxis_title="日期", yaxis_title="加權貢獻")
    return fig


def lead_lag_chart(corr_df: pd.DataFrame, title: str = "領先/落後相關係數") -> go.Figure:
    """各 lead 值的相關係數長條圖。正 lead = GITS 領先目標。"""
    fig = go.Figure(
        go.Bar(
            x=corr_df["lead"],
            y=corr_df["pearson_r"],
            text=[f"r={r:.2f}<br>p={p:.3f}<br>n={n}" for r, p, n in zip(corr_df["pearson_r"], corr_df["p_value"], corr_df["n"], strict=True)],
            textposition="outside",
            marker=dict(color=corr_df["pearson_r"], colorscale="RdBu_r", cmin=-1, cmax=1),
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="領先期數 (正值 = GITS 領先目標)",
        yaxis_title="Pearson 相關係數 r",
        yaxis_range=[-1, 1],
        height=440,
    )
    return fig


def weekly_gits_vs_price(gits_weekly: pd.Series, price_weekly: pd.Series, title: str) -> go.Figure:
    """週線雙軸：GITS 搜尋指標 + 股價（用於一鍵分析的主圖）。

    自動對齊到兩條線都有資料的重疊時段，避免一邊還沒開始（例如 GITS 需要等
    第一季營收權重才能算）時被誤畫成 0。
    """
    g = gits_weekly.dropna()
    p = price_weekly.dropna()
    if not g.empty and not p.empty:
        start = max(g.index.min(), p.index.min())
        end = min(g.index.max(), p.index.max())
        g = g.loc[start:end]
        p = p.loc[start:end]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(x=g.index, y=g.values,
                   name="GITS 搜尋指標", line=dict(color="#1f77b4", width=2)),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=p.index, y=p.values,
                   name="股價 (週收盤)", line=dict(color="#ff7f0e", width=2)),
        secondary_y=True,
    )
    fig.update_layout(
        title=title,
        xaxis_title="日期",
        height=560,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text="GITS 指標", color="#1f77b4", secondary_y=False)
    fig.update_yaxes(title_text="股價", color="#ff7f0e", secondary_y=True)
    return fig
