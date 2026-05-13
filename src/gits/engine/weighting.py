"""Revenue-weighted aggregation engine — the heart of GITS.

Formula:
    GITS_t = Σ_i ( segment_traffic_{i,t} × revenue_weight_{i,t-1} )

where revenue_weight is the segment's share of total revenue in the most
recent prior fiscal quarter (forward-filled until the next earnings release).
"""
from __future__ import annotations

import pandas as pd

from gits.reference import load_weights


def load_weights_long(ticker: str) -> pd.DataFrame:
    """Read revenue_weights.csv (filtered to ticker) and add weight_pct column.

    Returns long format: [quarter_end, segment, revenue_usd_m, weight_pct]
    Rows missing revenue are dropped.
    """
    df = load_weights(ticker=ticker).dropna(subset=["revenue_usd_m"]).copy()
    if df.empty:
        return pd.DataFrame(columns=["quarter_end", "segment", "revenue_usd_m", "weight_pct"])

    df = df.rename(columns={"quarter_end_date": "quarter_end"})
    df["quarter_end"] = pd.to_datetime(df["quarter_end"], errors="coerce")
    df = df.dropna(subset=["quarter_end"])
    if df.empty:
        return pd.DataFrame(columns=["quarter_end", "segment", "revenue_usd_m", "weight_pct"])
    totals = df.groupby("quarter_end")["revenue_usd_m"].transform("sum")
    df["weight_pct"] = df["revenue_usd_m"] / totals
    return df[["quarter_end", "segment", "revenue_usd_m", "weight_pct"]].sort_values(
        ["quarter_end", "segment"]
    ).reset_index(drop=True)


def load_total_revenue(ticker: str) -> pd.Series:
    """Total revenue per fiscal quarter, indexed by quarter_end_date."""
    df = load_weights(ticker=ticker).dropna(subset=["total_revenue_usd_m"])
    if df.empty:
        return pd.Series(dtype=float, name="total_revenue_usd_m")
    series = (
        df.drop_duplicates("quarter_end_date")
        .set_index("quarter_end_date")["total_revenue_usd_m"]
        .sort_index()
    )
    series.index = pd.to_datetime(series.index)
    return series


def forward_fill_weights(weights_long: pd.DataFrame, target_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Map a date series to the weights from the most-recently-ended fiscal quarter.

    Returns wide DataFrame indexed by target_dates, columns = segments, values = weight_pct.
    For dates before the first quarter_end, weights are NaN.
    """
    wide = weights_long.pivot(index="quarter_end", columns="segment", values="weight_pct").sort_index()
    target_dates = pd.DatetimeIndex(target_dates).sort_values()
    aligned = wide.reindex(target_dates.union(wide.index)).sort_index().ffill()
    return aligned.reindex(target_dates)


def compute_gits_index(
    segment_traffic_wide: pd.DataFrame,
    weights_long: pd.DataFrame,
    new_product_weights: dict | None = None,
) -> pd.DataFrame:
    """Compute the weighted GITS index.

    Args:
        segment_traffic_wide: index = date, columns = segments, values = RSV (or pageview)
        weights_long: output of load_weights_long
        new_product_weights: optional {segment_name: assumed_weight_pct}

    Returns:
        DataFrame indexed by date with one column per segment (weighted contribution)
        plus a 'gits' column (sum across segments).

    Fallback: if `weights_long` only contains a single 'Total' segment (typical for
    Taiwan stocks where 10-Q discloses only total revenue), the total weight is
    distributed equally across all trend segments — so GITS becomes the simple
    average of segment RSVs, scaled by the company's total revenue weight (=1.0).
    """
    traffic = segment_traffic_wide.copy()
    traffic.index = pd.to_datetime(traffic.index)

    weights_wide = forward_fill_weights(weights_long, traffic.index)

    common_segments = [c for c in traffic.columns if c in weights_wide.columns]

    if not common_segments and "Total" in weights_wide.columns:
        trend_segments = list(traffic.columns)
        equal_share = 1.0 / max(len(trend_segments), 1)
        for seg in trend_segments:
            weights_wide[seg] = weights_wide["Total"] * equal_share
        common_segments = trend_segments
        print(
            f"[compute_gits] No segment-level revenue split available; "
            f"distributing 'Total' weight equally across {len(trend_segments)} trend "
            f"segment(s): {trend_segments} (each gets {equal_share:.3f})"
        )

    if not common_segments:
        raise RuntimeError(
            f"No overlap between traffic segments {list(traffic.columns)} "
            f"and weight segments {list(weights_wide.columns)}. "
            f"Either rename a weight row to match a trend segment, or add a "
            f"'Total' weight row that the engine can auto-distribute."
        )

    if new_product_weights:
        for seg, w in new_product_weights.items():
            if seg in weights_wide.columns:
                weights_wide[seg] = weights_wide[seg].fillna(w)
            else:
                weights_wide[seg] = w
            if seg not in common_segments and seg in traffic.columns:
                common_segments.append(seg)

    contributions = traffic[common_segments].mul(weights_wide[common_segments], axis=0)
    contributions["gits"] = contributions.sum(axis=1)
    return contributions
