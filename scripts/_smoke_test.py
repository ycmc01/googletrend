"""Smoke test: verify all third-party and project imports work."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb
import pandas
import plotly
import pyarrow
import pytrends
import scipy

from gits.analysis.backtest import lead_lag_correlation  # noqa: F401
from gits.analysis.plots import three_axis_chart  # noqa: F401
from gits.collectors.prices import fetch_prices  # noqa: F401
from gits.collectors.trends import fetch_cross_segment_trends  # noqa: F401
from gits.engine.weighting import compute_gits_index  # noqa: F401
from gits.storage.duckdb_io import get_conn, init_schema
from gits.xqapi import get_kline  # noqa: F401

print("All imports OK")
print(f"  pandas    {pandas.__version__}")
print(f"  numpy     {__import__('numpy').__version__}")
print(f"  duckdb    {duckdb.__version__}")
print(f"  pyarrow   {pyarrow.__version__}")
print(f"  plotly    {plotly.__version__}")
print(f"  scipy     {scipy.__version__}")

conn = get_conn()
init_schema(conn)
tables = conn.execute("SHOW TABLES").df()
print(f"DuckDB tables created: {tables['name'].tolist()}")
conn.close()
print("DuckDB schema OK")
