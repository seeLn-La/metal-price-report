#!/usr/bin/env python3
"""Fetch the USD/CNY daily reference series used for display conversion."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "reports"


def main() -> int:
    for directory in (RAW_DIR, PROCESSED_DIR, REPORT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).isoformat()
    data = yf.download("CNY=X", period="1y", interval="1d", auto_adjust=False, progress=False, threads=False)
    if data.empty:
        raise RuntimeError("Yahoo Finance returned no USD/CNY rows")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.reset_index()
    date_col = "Date" if "Date" in data.columns else "Datetime"
    data[date_col] = pd.to_datetime(data[date_col], utc=True).dt.tz_localize(None).dt.normalize()
    fx = data.rename(columns={date_col: "date", "Close": "usd_cny"})[["date", "usd_cny"]].dropna()
    fx["usd_cny"] = pd.to_numeric(fx["usd_cny"], errors="coerce")
    fx = fx.dropna().drop_duplicates("date").sort_values("date")
    fx["ticker"] = "CNY=X"
    fx["source"] = "Yahoo Finance"
    fx["fetched_at"] = fetched_at
    fx.to_csv(RAW_DIR / "USD_CNY.csv", index=False)
    fx.to_csv(PROCESSED_DIR / "usd_cny_daily.csv", index=False)
    report = {
        "status": "success", "ticker": "CNY=X", "source": "Yahoo Finance", "fetched_at": fetched_at,
        "start_date": fx["date"].min().date().isoformat(), "end_date": fx["date"].max().date().isoformat(),
        "row_count": int(len(fx)), "missing_rate": int(fx["usd_cny"].isna().sum()), "unit": "人民币/美元",
    }
    (REPORT_DIR / "usd_cny_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
