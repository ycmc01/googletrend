# GITS Scanner

Revenue-weighted Google Trends index for **nowcasting** any public company's quarterly results. Works for **Taiwan and US stocks** — both revenue and stock prices auto-imported from XQAPI.

**Reframe**: this is a nowcasting tool, not a leading-indicator tool. Quarterly earnings are released 30-45 days after the quarter end, so a calendar-coincident GITS at quarter-end gives meaningful informational edge over the official 10-Q.

## Web UI (recommended)

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run web/streamlit_app.py
```

Opens at <http://localhost:8501> with five pages:
1. **🏢 Companies** — Register a ticker; click *Lookup via XQAPI* for TW stocks to auto-fill company name + industry
2. **🏷 Segments** — Define keyword groups per company (default: single `Total` segment with company name)
3. **💰 Weights** — Click *Import revenue* to pull 16+ quarters from XQAPI, or edit manually
4. **⚙ Pipeline** — Run Google Trends + price fetch + GITS compute + HTML report
5. **📈 Report** — View weighted segment contribution, three-axis chart, deseasonalized lead-lag — all interactive

For headless / scripting use, the same operations are available via CLI (see below).

## Productized workflow

Everything is driven by one CLI (`scripts/gits.py`) and three reference CSVs.

### 1. Register a company

```powershell
.\.venv\Scripts\Activate.ps1
python scripts/gits.py company add NVDA "Nvidia Corp" --fy-end-month 1
python scripts/gits.py company list
```

### 2. Define segment keyword groups (the key-in tool)

```powershell
python scripts/gits.py segment add NVDA
```

Interactive prompts walk you through:
- segment name (e.g. `Data Center`)
- positive keywords (one per line, blank line to finish)
- exclude terms
- optional Topic ID (from `trends.google.com` URL after clicking a chip)
- notes

Limit: **5 segments per ticker** (pytrends single-query cap for cross-segment calibration).

Other segment commands:
```powershell
python scripts/gits.py segment list NVDA
python scripts/gits.py segment show NVDA "Data Center"
python scripts/gits.py segment remove NVDA "Data Center"
```

### 3. Fill in revenue weights

Edit `reference/revenue_weights.csv` directly, or import from a prepared CSV:

```powershell
python scripts/gits.py weight import NVDA --csv my_nvda_revenue.csv
python scripts/gits.py weight list NVDA
```

Source: each company's 10-Q / 10-K segment disclosure. Required columns:

```
ticker,fiscal_quarter,quarter_end_date,segment,revenue_usd_m,total_revenue_usd_m,source_filing
```

Aim for **at least 16 fiscal quarters** (4 years) for usable statistical power; 8 is the bare minimum.

### 4. Fetch raw data

```powershell
python scripts/gits.py fetch prices NVDA --start 2021-01-01
python scripts/gits.py fetch trends NVDA --timeframe "today 5-y"
```

### 5. Compute the GITS index

```powershell
python scripts/gits.py compute NVDA
```

### 6. Generate the full HTML report

```powershell
python scripts/gits.py report NVDA
```

Produces `notebooks/report_NVDA.html` with three-axis charts, segment contribution, QoQ + deseasonalized lead-lag analyses.

### 7. 夜間燈光（衛星 ALT-DATA，選用）

整合 VIIRS Day/Night Band 月度合成衛星資料，作為產業聚落生產活動的代理訊號。

**一次性設定**：
```powershell
# 在 https://earthengine.google.com 用 Google 帳號註冊（免費）
# 在 venv 內認證：
python -m ee authenticate
# 跳出瀏覽器登入 → 回到 console 應該看到 "Successfully saved authorization token"
```

**抓取資料**：
```powershell
python scripts/fetch_ntl.py
```
會把 `reference/ntl_rois.csv` 列出的所有 ROI 抓 ~10 年月度資料存到 `data/processed/nightlights.parquet`。

**在網站查看**：左側選單 **🛰 夜間燈光** 頁，能：
- 看某 ROI 月度燈光時序（含 YoY %）
- 與該 ROI 關聯的台股股價對照（含 Pearson r）

## Architecture

```
gits-scanner/
├── reference/
│   ├── companies.csv         (ticker, name, fy_end_month, notes)
│   ├── segments.csv          (ticker, segment_name, keywords, excludes, ...)
│   └── revenue_weights.csv   (ticker, fiscal_q, q_end_date, segment, revenue, total)
├── src/gits/
│   ├── cli.py                Unified CLI (company / segment / weight / fetch / compute / report)
│   ├── reference.py          Read/write helpers for the 3 CSVs
│   ├── collectors/           pytrends (trends) + XQAPI K-line (prices) wrappers
│   ├── xqapi.py              Sysjust XQ API REST client (basic info + revenue + K-line)
│   ├── nightlights.py        VIIRS DNB 衛星夜間燈光（透過 Google Earth Engine）
│   ├── storage/duckdb_io.py  Multi-ticker DuckDB schema
│   ├── engine/               RSV normalize + revenue weighting
│   └── analysis/             Lead-lag backtest + deseasonalization + plotly charts
├── scripts/
│   ├── gits.py               CLI entry point
│   └── _smoke_test.py        Optional health check
├── notebooks/01_poc_template.ipynb  Generic, reads GITS_TICKER from env
└── data/                     Auto-generated parquet + duckdb (gitignored)
```

## Setup (one time)

```powershell
# Python 3.11+ recommended (3.14 also works)
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
pip install --group dev    # jupyter, ipykernel, ruff
```

## Known limitations

- **Cross-segment RSV scale**: works with ≤5 segments per ticker (pytrends single-query limit). For >5 segments, you need a calibration anchor and we don't yet support that automatically.
- **Statistical power**: at 8 quarters, lead-lag correlations have wide CIs. Recommend ≥16 quarters before drawing thesis conclusions.
- **pytrends rate limits**: 429s happen. The `urllib3 v2 method_whitelist` bug is monkey-patched in `trends.py`.
- **iPhone-style dominance**: the highest-volume segment dominates the unweighted RSV scale. The PRD's "absolute pageview conversion" stage (Ahrefs/SEMrush) would solve this but costs ~$500/month and is deferred.

## License

Personal / research use.
