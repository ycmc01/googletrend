"""Plotly chart builders for GITS analysis."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def three_axis_chart(
    gits: pd.Series,
    revenue: pd.Series,
    price: pd.Series,
    title: str = "GITS Index vs Revenue vs Stock Price",
) -> go.Figure:
    """Three-axis time-series overlay."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(x=gits.index, y=gits.values, name="GITS Index", line=dict(color="#1f77b4", width=2)),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=revenue.index, y=revenue.values, name="Quarterly Revenue (USD M)",
            line=dict(color="#2ca02c", width=2, dash="dot"), mode="lines+markers",
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=price.index, y=price.values, name="AAPL Close",
            line=dict(color="#ff7f0e", width=1), yaxis="y3",
        ),
    )

    fig.update_layout(
        title=title,
        xaxis=dict(domain=[0.0, 0.92]),
        yaxis=dict(title="GITS Index", color="#1f77b4"),
        yaxis2=dict(title="Revenue (USD M)", color="#2ca02c", anchor="x", overlaying="y", side="right"),
        yaxis3=dict(title="AAPL Close", color="#ff7f0e", anchor="free", overlaying="y", side="right", position=1.0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        height=560,
    )
    return fig


def segment_contribution_chart(contrib_wide: pd.DataFrame, title: str = "Segment Contribution to GITS") -> go.Figure:
    """Stacked area of each segment's weighted contribution."""
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
    fig.update_layout(title=title, height=480, hovermode="x unified", yaxis_title="Weighted Contribution")
    return fig


def lead_lag_chart(corr_df: pd.DataFrame, title: str = "Lead-Lag Correlation") -> go.Figure:
    """Bar chart of correlation at each lead. Positive lead = GITS leads target."""
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
        xaxis_title="Lead (positive = GITS leads target)",
        yaxis_title="Pearson r",
        yaxis_range=[-1, 1],
        height=440,
    )
    return fig
