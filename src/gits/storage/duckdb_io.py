"""DuckDB storage layer.

Pattern: parquet files in data/raw/ are source of truth; DuckDB acts as
the query engine and stores processed/aggregated tables.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from gits.config import DUCKDB_PATH, RAW_DIR


def get_conn(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path or DUCKDB_PATH))


def init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trends (
            date         DATE,
            segment      VARCHAR,
            rsv          DOUBLE,
            geo          VARCHAR,
            timeframe    VARCHAR,
            PRIMARY KEY (date, segment, geo, timeframe)
        );
        CREATE TABLE IF NOT EXISTS prices (
            date         DATE,
            ticker       VARCHAR,
            open         DOUBLE,
            high         DOUBLE,
            low          DOUBLE,
            close        DOUBLE,
            adj_close    DOUBLE,
            volume       BIGINT,
            PRIMARY KEY (date, ticker)
        );
        CREATE TABLE IF NOT EXISTS segment_weights (
            quarter_end          DATE,
            segment              VARCHAR,
            revenue_usd_m        DOUBLE,
            weight_pct           DOUBLE,
            PRIMARY KEY (quarter_end, segment)
        );
        CREATE TABLE IF NOT EXISTS quarterly_revenue (
            quarter_end           DATE,
            ticker                VARCHAR,
            total_revenue_usd_m   DOUBLE,
            PRIMARY KEY (quarter_end, ticker)
        );
        """
    )


def _upsert(conn: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame, key_cols: list[str]) -> int:
    if df.empty:
        return 0
    conn.register("_stage", df)
    cols = ", ".join(df.columns)
    where = " AND ".join([f"t.{k} = s.{k}" for k in key_cols])
    conn.execute(f"DELETE FROM {table} t USING _stage s WHERE {where}")
    conn.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _stage")
    conn.unregister("_stage")
    return len(df)


def upsert_trends(conn, df: pd.DataFrame) -> int:
    return _upsert(conn, "trends", df, ["date", "segment", "geo", "timeframe"])


def upsert_prices(conn, df: pd.DataFrame) -> int:
    return _upsert(conn, "prices", df, ["date", "ticker"])


def upsert_segment_weights(conn, df: pd.DataFrame) -> int:
    return _upsert(conn, "segment_weights", df, ["quarter_end", "segment"])


def upsert_quarterly_revenue(conn, df: pd.DataFrame) -> int:
    return _upsert(conn, "quarterly_revenue", df, ["quarter_end", "ticker"])


def read_trends(conn, geo: str = "WW") -> pd.DataFrame:
    return conn.execute(
        "SELECT date, segment, rsv FROM trends WHERE geo = ? ORDER BY date, segment",
        [geo],
    ).df()


def read_prices(conn, ticker: str = "AAPL") -> pd.DataFrame:
    return conn.execute(
        "SELECT date, close, adj_close, volume FROM prices WHERE ticker = ? ORDER BY date",
        [ticker],
    ).df()


def read_segment_weights(conn) -> pd.DataFrame:
    return conn.execute(
        "SELECT quarter_end, segment, revenue_usd_m, weight_pct "
        "FROM segment_weights ORDER BY quarter_end, segment"
    ).df()


def read_quarterly_revenue(conn, ticker: str = "AAPL") -> pd.DataFrame:
    return conn.execute(
        "SELECT quarter_end, total_revenue_usd_m FROM quarterly_revenue "
        "WHERE ticker = ? ORDER BY quarter_end",
        [ticker],
    ).df()


def load_raw_parquets(pattern: str) -> pd.DataFrame:
    """Read all parquet files under data/raw matching pattern (e.g. 'trends_*')."""
    files = sorted(RAW_DIR.glob(f"{pattern}.parquet"))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
