"""Google Trends collector via pytrends.

Strategy: Apple has 5 segments which fits exactly within pytrends' 5-keyword
per-query limit. One single query returns CROSS-COMPARABLE relative search
volume across all segments — solving the core RSV calibration problem.

For within-segment drill-down (e.g. iPhone 15 vs 16 vs 17), use
`fetch_segment_drilldown` which runs a separate query per segment.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
from pytrends.request import TrendReq
from rich.console import Console
from tenacity import retry, stop_after_attempt, wait_exponential

console = Console()

PYTRENDS_KWARGS = dict(hl="en-US", tz=360, timeout=(10, 25), retries=2, backoff_factor=0.5)


def _segment_to_query(row: pd.Series) -> str:
    """Pick the pytrends identifier for a segment: topic ID preferred, else first keyword."""
    topic = row.get("trends_topic_id")
    if isinstance(topic, str) and topic.strip():
        return topic.strip()
    keywords = str(row.get("trends_keywords", "")).split("|")
    first = next((k.strip() for k in keywords if k.strip()), None)
    if not first:
        raise ValueError(f"Segment {row['segment_name']!r} has no topic_id or keywords")
    return first


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=4, max=60))
def _build_and_fetch(pytrends: TrendReq, kw_list: list[str], timeframe: str, geo: str) -> pd.DataFrame:
    pytrends.build_payload(kw_list, timeframe=timeframe, geo=geo)
    df = pytrends.interest_over_time()
    if df is None or df.empty:
        raise RuntimeError("pytrends returned empty frame — possibly rate limited")
    return df


def fetch_cross_segment_trends(
    segments_df: pd.DataFrame,
    timeframe: str = "today 5-y",
    geo: str = "",
) -> pd.DataFrame:
    """Fetch RSV for all segments in ONE query → cross-comparable scale.

    Returns long-format DataFrame: [date, segment, rsv]
    """
    if len(segments_df) > 5:
        raise ValueError(
            f"pytrends accepts max 5 terms per query; got {len(segments_df)} segments. "
            "Split into multiple queries with a shared anchor for calibration."
        )

    queries = [_segment_to_query(row) for _, row in segments_df.iterrows()]
    console.print(f"[cyan]Fetching cross-segment trends ({geo or 'WW'}, {timeframe})[/cyan]")
    console.print(f"  Queries: {queries}")

    pytrends = TrendReq(**PYTRENDS_KWARGS)
    df = _build_and_fetch(pytrends, queries, timeframe, geo)

    if "isPartial" in df.columns:
        df = df.drop(columns=["isPartial"])

    rename_map = dict(zip(queries, segments_df["segment_name"].tolist(), strict=True))
    df = df.rename(columns=rename_map)

    long_df = (
        df.reset_index()
        .melt(id_vars="date", var_name="segment", value_name="rsv")
        .assign(geo=geo or "WW", timeframe=timeframe)
    )
    return long_df


def fetch_segment_drilldown(
    segment_row: pd.Series,
    timeframe: str = "today 5-y",
    geo: str = "",
    pause: float = 5.0,
) -> pd.DataFrame:
    """Drill down within a single segment — fetch each sub-keyword.

    Useful for answering "which iPhone generation is driving the trend?".
    NOT cross-comparable to other segments' drill-downs.
    """
    keywords = [k.strip() for k in str(segment_row["trends_keywords"]).split("|") if k.strip()]
    if not keywords:
        return pd.DataFrame(columns=["date", "segment", "keyword", "rsv"])

    pytrends = TrendReq(**PYTRENDS_KWARGS)
    chunks: list[pd.DataFrame] = []
    for i in range(0, len(keywords), 5):
        batch = keywords[i : i + 5]
        df = _build_and_fetch(pytrends, batch, timeframe, geo)
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        chunks.append(df)
        time.sleep(pause)

    wide = pd.concat(chunks, axis=1)
    long_df = (
        wide.reset_index()
        .melt(id_vars="date", var_name="keyword", value_name="rsv")
        .assign(segment=segment_row["segment_name"], geo=geo or "WW", timeframe=timeframe)
    )
    return long_df[["date", "segment", "keyword", "rsv", "geo", "timeframe"]]


def save_trends_parquet(df: pd.DataFrame, raw_dir: Path, name_prefix: str) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    path = raw_dir / f"{name_prefix}_{today}.parquet"
    df.to_parquet(path, index=False)
    return path
