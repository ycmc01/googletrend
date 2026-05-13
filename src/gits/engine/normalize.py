"""RSV normalization and time resampling."""
from __future__ import annotations

import pandas as pd


def pivot_trends_wide(long_df: pd.DataFrame) -> pd.DataFrame:
    """Long [date, segment, rsv] → wide DataFrame indexed by date, columns = segments."""
    wide = (
        long_df.pivot_table(index="date", columns="segment", values="rsv", aggfunc="mean")
        .sort_index()
    )
    wide.index = pd.to_datetime(wide.index)
    return wide


def resample_to_monthly(wide: pd.DataFrame, how: str = "mean") -> pd.DataFrame:
    """Resample weekly/daily RSV to monthly. Use mean by default."""
    return wide.resample("MS").agg(how)


def resample_to_quarterly(wide: pd.DataFrame, how: str = "mean") -> pd.DataFrame:
    """Resample to fiscal-quarter-ish (calendar Q-start). For Apple FY alignment,
    use align_to_apple_fiscal_quarters after this."""
    return wide.resample("QS").agg(how)


def align_to_apple_fiscal_quarters(daily_or_weekly: pd.DataFrame, quarter_ends: list[pd.Timestamp]) -> pd.DataFrame:
    """Aggregate RSV to Apple's fiscal-quarter buckets defined by quarter_ends.

    Apple's fiscal Q ends ~late Sep / Dec / Mar / Jun. Each bucket [prev_end+1, this_end].
    Returns DataFrame indexed by quarter_end with mean RSV per segment over the bucket.
    """
    quarter_ends_sorted = sorted(pd.to_datetime(quarter_ends))
    rows = []
    for i, q_end in enumerate(quarter_ends_sorted):
        q_start = (quarter_ends_sorted[i - 1] + pd.Timedelta(days=1)) if i > 0 else daily_or_weekly.index.min()
        mask = (daily_or_weekly.index >= q_start) & (daily_or_weekly.index <= q_end)
        sub = daily_or_weekly.loc[mask]
        if sub.empty:
            continue
        row = sub.mean(numeric_only=True)
        row.name = q_end
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame()
