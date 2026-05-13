"""Streamlit-facing re-export of the XQAPI client (canonical impl lives in gits.xqapi)."""
from gits.xqapi import (  # noqa: F401
    BASE_URL,
    extract_field,
    get_basic_info,
    get_kline,
    get_monthly_revenue,
    get_quarterly_financial_report,
    kline_to_prices_df,
    norm_ticker,
    quarterly_revenue_to_rows,
)
