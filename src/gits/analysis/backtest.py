"""Lead-lag correlation analysis — the PoC's go/no-go test."""
from __future__ import annotations

import pandas as pd
from scipy.stats import pearsonr


def lead_lag_correlation(
    leading: pd.Series,
    target: pd.Series,
    max_lead: int = 4,
    freq: str = "Q",
) -> pd.DataFrame:
    """Pearson r between `leading` (resampled, shifted forward by N periods) and `target`.

    A POSITIVE lead value means: leading[t] correlates with target[t+lead].
    e.g. lead=1 at quarterly freq → GITS this quarter predicts next-quarter revenue.

    Returns DataFrame: [lead, n, pearson_r, p_value]
    """
    freq_map = {"Q": "QS", "M": "MS", "W": "W"}
    rule = freq_map.get(freq, freq)

    lead_r = leading.resample(rule).mean().dropna()
    tgt_r = target.resample(rule).mean().dropna()

    rows = []
    for lead in range(-max_lead, max_lead + 1):
        shifted = lead_r.shift(-lead) if lead >= 0 else lead_r.shift(-lead)
        aligned = pd.concat([shifted, tgt_r], axis=1, join="inner").dropna()
        if len(aligned) < 4:
            rows.append({"lead": lead, "n": len(aligned), "pearson_r": float("nan"), "p_value": float("nan")})
            continue
        r, p = pearsonr(aligned.iloc[:, 0], aligned.iloc[:, 1])
        rows.append({"lead": lead, "n": len(aligned), "pearson_r": r, "p_value": p})
    return pd.DataFrame(rows)


def yoy_change(series: pd.Series, periods: int = 4) -> pd.Series:
    """Year-over-year percent change. For quarterly data use periods=4."""
    return series.pct_change(periods=periods)
