"""Lead-lag correlation analysis — the PoC's go/no-go test."""
from __future__ import annotations

import pandas as pd
from scipy.stats import pearsonr


def lead_lag_correlation(
    leading: pd.Series,
    target: pd.Series,
    max_lead: int = 4,
    freq: str = "Q",
    min_n: int = 3,
) -> pd.DataFrame:
    """Pearson r between `leading[t]` and `target[t + lead]`.

    A POSITIVE lead means: leading at time t correlates with target `lead` periods later.
    e.g. lead=1 at quarterly freq → GITS this quarter co-moves with next-quarter revenue
    (i.e. GITS is the leading indicator, target is the laggard).

    Returns DataFrame: [lead, n, pearson_r, p_value]
    """
    freq_map = {"Q": "QS", "M": "MS", "W": "W"}
    rule = freq_map.get(freq, freq)

    lead_r = leading.resample(rule).mean().dropna()
    tgt_r = target.resample(rule).mean().dropna()

    rows = []
    for lead in range(-max_lead, max_lead + 1):
        # Shift TARGET so target[t+lead] sits at index t, then correlate with leading[t]
        shifted_target = tgt_r.shift(-lead)
        aligned = pd.concat([lead_r, shifted_target], axis=1, join="inner").dropna()
        if len(aligned) < min_n or aligned.iloc[:, 0].std() == 0 or aligned.iloc[:, 1].std() == 0:
            rows.append({"lead": lead, "n": len(aligned), "pearson_r": float("nan"), "p_value": float("nan")})
            continue
        r, p = pearsonr(aligned.iloc[:, 0], aligned.iloc[:, 1])
        rows.append({"lead": lead, "n": len(aligned), "pearson_r": r, "p_value": p})
    return pd.DataFrame(rows)


def yoy_change(series: pd.Series, periods: int = 4) -> pd.Series:
    """Year-over-year percent change. For quarterly data use periods=4."""
    return series.pct_change(periods=periods)


def qoq_change(series: pd.Series) -> pd.Series:
    """Quarter-over-quarter percent change. Heavily seasonal — interpret with care."""
    return series.pct_change(periods=1)


def deseasonalize_fiscal(series: pd.Series, method: str = "multiplicative") -> pd.Series:
    """Remove fiscal-quarter seasonality by dividing/subtracting the per-quarter-position mean.

    Index must be fiscal quarter-end dates. Position identified by month (3/6/9/12).

    method:
      'multiplicative': value / (position_mean / overall_mean)
      'additive':       value - position_mean

    Caveat: with ≤2 observations per position the seasonal estimate is noisy;
    use only as a directional sanity check.
    """
    df = series.to_frame("value").copy()
    df["pos"] = df.index.month
    pos_mean = df.groupby("pos")["value"].mean()
    if method == "multiplicative":
        overall = df["value"].mean()
        factors = pos_mean / overall
        return df["value"] / df["pos"].map(factors)
    elif method == "additive":
        return df["value"] - df["pos"].map(pos_mean)
    raise ValueError(f"Unknown method: {method!r}")
