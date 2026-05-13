"""Revenue-weighted aggregation engine — the heart of GITS.

Formula:
    GITS_t = Σ_i ( segment_traffic_{i,t} × revenue_weight_{i,t-1} )

where revenue_weight is the segment's share of total revenue in the most
recent prior fiscal quarter (forward-filled until the next earnings release).
"""
from __future__ import annotations

import pandas as pd

SEGMENT_COLS = ["iPhone", "Mac", "iPad", "Wearables", "Services"]


def load_weights_from_csv(csv_path) -> pd.DataFrame:
    """Read apple_revenue_weights.csv and compute weight_pct per segment.

    Returns long format: [quarter_end, segment, revenue_usd_m, weight_pct]
    Rows where all segment values are missing are dropped.
    """
    df = pd.read_csv(csv_path, parse_dates=["quarter_end_date"])
    df = df.rename(columns={"quarter_end_date": "quarter_end"})

    available_segments = [c for c in SEGMENT_COLS if c in df.columns]
    df = df.dropna(subset=available_segments, how="all").reset_index(drop=True)

    long = df.melt(
        id_vars=["quarter_end"],
        value_vars=available_segments,
        var_name="segment",
        value_name="revenue_usd_m",
    ).dropna(subset=["revenue_usd_m"])

    totals = long.groupby("quarter_end")["revenue_usd_m"].transform("sum")
    long["weight_pct"] = long["revenue_usd_m"] / totals
    long["quarter_end"] = pd.to_datetime(long["quarter_end"])
    return long.sort_values(["quarter_end", "segment"]).reset_index(drop=True)


def forward_fill_weights(weights_long: pd.DataFrame, target_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Map a date series to the weights from the most-recently-ended fiscal quarter.

    Returns wide DataFrame indexed by target_dates, columns = segments, values = weight_pct.
    For dates before the first quarter_end, weights are NaN.
    """
    wide = weights_long.pivot(index="quarter_end", columns="segment", values="weight_pct").sort_index()
    target_dates = pd.DatetimeIndex(target_dates).sort_values()
    aligned = wide.reindex(target_dates.union(wide.index), method=None).sort_index().ffill()
    return aligned.reindex(target_dates)


def compute_gits_index(
    segment_traffic_wide: pd.DataFrame,
    weights_long: pd.DataFrame,
    new_product_weights: dict | None = None,
) -> pd.DataFrame:
    """Compute the weighted GITS index.

    Args:
        segment_traffic_wide: index = date, columns = segments, values = RSV (or pageview)
        weights_long: output of load_weights_from_csv
        new_product_weights: optional {segment_name: assumed_weight_pct} for unreleased products
            applied to dates >= earliest_release_date (currently applied throughout for simplicity)

    Returns:
        DataFrame indexed by date with columns:
          - one column per segment (weighted contribution)
          - 'gits' (sum across segments)
    """
    traffic = segment_traffic_wide.copy()
    traffic.index = pd.to_datetime(traffic.index)

    weights_wide = forward_fill_weights(weights_long, traffic.index)

    common_segments = [c for c in traffic.columns if c in weights_wide.columns]
    if not common_segments:
        raise RuntimeError(
            f"No overlap between traffic segments {list(traffic.columns)} "
            f"and weight segments {list(weights_wide.columns)}"
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
