from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.getenv("GITS_DATA_DIR") or PROJECT_ROOT / "data")
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
REFERENCE_DIR = PROJECT_ROOT / "reference"
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"

DUCKDB_PATH = PROCESSED_DIR / "gits.duckdb"

COMPANIES_CSV = REFERENCE_DIR / "companies.csv"
SEGMENTS_CSV = REFERENCE_DIR / "segments.csv"
REVENUE_WEIGHTS_CSV = REFERENCE_DIR / "revenue_weights.csv"

DEFAULT_GEO = ""
DEFAULT_TIMEFRAME = "today 5-y"

for d in (RAW_DIR, PROCESSED_DIR, REFERENCE_DIR):
    d.mkdir(parents=True, exist_ok=True)
