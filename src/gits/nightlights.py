"""VIIRS Day/Night Band 夜間燈光 — 透過 Google Earth Engine 取得月度時間序列。

資料源：NOAA VIIRS DNB monthly composite (VCMSLCFG)，2012-04 起，
全球解析度 ~500m。值是 nW/cm²/sr 的輻射量。

ROI 定義在 reference/ntl_rois.csv，每筆是「中心點 + 半徑」的圓形範圍。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from gits.config import PROCESSED_DIR, REFERENCE_DIR

COLLECTION = "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG"
NTL_CSV = REFERENCE_DIR / "ntl_rois.csv"
NTL_PARQUET = PROCESSED_DIR / "nightlights.parquet"


def load_rois() -> pd.DataFrame:
    if not NTL_CSV.exists():
        return pd.DataFrame(columns=["roi_name", "lat", "lon", "radius_m", "related_tickers", "notes"])
    return pd.read_csv(NTL_CSV)


def init_ee() -> None:
    """初始化 Google Earth Engine。沒認證的話拋出友善錯誤。"""
    import ee  # 延後 import，沒裝套件時不會在 module import 就爆
    try:
        ee.Initialize()
    except Exception as e:
        raise RuntimeError(
            "Google Earth Engine 未認證。請先執行：\n"
            "  .venv\\Scripts\\python.exe -m ee authenticate\n"
            "瀏覽器會跳出 Google 登入，完成後重試。\n"
            f"原始錯誤：{e}"
        ) from e


def fetch_monthly_ntl(
    roi_name: str, lat: float, lon: float, radius_m: float = 2500,
    start: str = "2014-01-01", end: str | None = None,
) -> pd.DataFrame:
    """抓取某 ROI 的月度夜間燈光平均亮度。

    回傳 DataFrame: [roi_name, date, avg_rad]
    其中 avg_rad 單位是 nW/cm²/sr。
    """
    import ee
    init_ee()

    end = end or datetime.now().strftime("%Y-%m-%d")
    point = ee.Geometry.Point([lon, lat])
    roi = point.buffer(radius_m)

    coll = ee.ImageCollection(COLLECTION).filterDate(start, end).select("avg_rad")

    def _reduce(img):
        v = img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=500,
            maxPixels=1e9,
        ).get("avg_rad")
        return ee.Feature(None, {
            "date": img.date().format("YYYY-MM-dd"),
            "avg_rad": v,
        })

    fc = coll.map(_reduce)
    info = fc.getInfo()
    rows = []
    for f in info.get("features", []):
        props = f.get("properties", {})
        val = props.get("avg_rad")
        if val is None:
            continue
        rows.append({
            "roi_name": roi_name,
            "date": props["date"],
            "avg_rad": float(val),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
    return df


def fetch_all_rois(start: str = "2014-01-01") -> pd.DataFrame:
    """抓取 reference/ntl_rois.csv 內所有 ROI 的時序。"""
    rois = load_rois()
    if rois.empty:
        return pd.DataFrame()
    parts = []
    for _, row in rois.iterrows():
        df = fetch_monthly_ntl(
            roi_name=row["roi_name"],
            lat=float(row["lat"]),
            lon=float(row["lon"]),
            radius_m=float(row["radius_m"]),
            start=start,
        )
        if not df.empty:
            df["related_tickers"] = row.get("related_tickers", "") or ""
        parts.append(df)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def save_cached(df: pd.DataFrame, path: Path | None = None) -> Path:
    path = path or NTL_PARQUET
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def load_cached(path: Path | None = None) -> pd.DataFrame:
    path = path or NTL_PARQUET
    if not path.exists():
        return pd.DataFrame(columns=["roi_name", "date", "avg_rad", "related_tickers"])
    df = pd.read_parquet(path)
    if not df.empty and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df
