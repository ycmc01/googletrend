# GITS Scanner — Apple PoC

Global Intent Leading Indicator Scanner. Revenue-weighted Google Trends index for predicting Apple's quarterly segment revenue and stock price.

## Quickstart

```powershell
# 1. Install dependencies (requires uv: https://github.com/astral-sh/uv)
uv sync

# 2. Fill in segment weights manually
#    Open reference/apple_revenue_weights.csv
#    Read reference/README_FILL_THIS_OUT.txt for instructions
#    Fill in segment revenue (in USD millions) for each fiscal quarter
#    Source: Apple 10-Q / 10-K filings (https://investor.apple.com/sec-filings/)

# 3. Fetch trends data (Google Trends, no API key needed)
uv run python scripts/fetch_trends.py --geo "" --timeframe "today 5-y"

# 4. Fetch stock prices and quarterly revenue
uv run python scripts/fetch_prices.py --ticker AAPL --start 2020-01-01

# 5. Compute GITS index
uv run python scripts/compute_gits.py --geo WW

# 6. Open the PoC notebook
uv run jupyter notebook notebooks/01_apple_poc.ipynb
```

## Project structure

```
gits-scanner/
├── src/gits/
│   ├── config.py              Paths and defaults
│   ├── collectors/            pytrends + yfinance wrappers
│   ├── storage/               DuckDB I/O
│   ├── engine/                RSV normalize + revenue weighting
│   └── analysis/              Lead-lag backtest + plotly charts
├── reference/                 Manually-filled CSVs (segment definitions + weights)
├── scripts/                   CLI entry points
├── notebooks/01_apple_poc.ipynb  Main PoC analysis
└── data/                      Auto-generated parquet + duckdb (gitignored)
```

## PoC verdict criteria

The PoC is **Go** if, at lead = 1 or 2 quarters, `pearson_r > 0.5` and `p_value < 0.05` for GITS YoY vs Apple total-revenue YoY.

If the verdict is **No-Go**, the entire thesis is suspect — stop here, do not extend to Tesla / Nvidia.

## Known limitations (MVP)

- Google Trends RSV is relative, not absolute. Cross-segment magnitudes are calibrated by fitting all 5 segments into ONE pytrends query (max 5 keywords); accurate for Apple but does not generalize beyond 5 segments without a calibration anchor.
- `pytrends` is unofficial and rate-limits aggressively. If you hit 429s, wait an hour or switch to SerpAPI / DataForSEO.
- Segment revenue weights must be filled manually for now. Phase 2 will automate via SEC EDGAR XBRL parsing.
