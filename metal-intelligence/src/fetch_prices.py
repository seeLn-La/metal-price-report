#!/usr/bin/env python3
"""Fetch and validate one year of daily metal futures data."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

plt.rcParams["font.family"] = ["STHeiti", "Hiragino Sans GB", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CHART_DIR = ROOT / "charts"
REPORT_DIR = ROOT / "reports"

INSTRUMENTS = {
    "黄金": ("GC=F", "美元/金衡盎司"),
    "白银": ("SI=F", "美元/金衡盎司"),
    "铜": ("HG=F", "美元/磅"),
    "锡": ("SN=F", "美元/公吨"),
}


def fetch_one(metal: str, ticker: str, unit: str, fetched_at: str) -> tuple[pd.DataFrame, dict]:
    result = {
        "status": "failed",
        "metal": metal,
        "ticker": ticker,
        "source": "Yahoo Finance",
        "unit": unit,
        "fetched_at": fetched_at,
        "start_date": None,
        "end_date": None,
        "row_count": 0,
        "missing_close": None,
        "duplicate_dates": None,
        "non_positive_close": None,
        "max_abs_daily_change_pct": None,
        "error": None,
    }
    try:
        data = yf.download(ticker, period="1y", interval="1d", auto_adjust=False, progress=False, threads=False)
        if data.empty:
            raise ValueError("Yahoo Finance returned no rows")
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        data = data.reset_index()
        date_col = "Date" if "Date" in data.columns else "Datetime"
        data[date_col] = pd.to_datetime(data[date_col], utc=True).dt.tz_localize(None).dt.normalize()
        data = data.rename(columns={date_col: "date"})
        required = ["date", "Open", "High", "Low", "Close", "Volume"]
        missing = [column for column in required if column not in data.columns]
        if missing:
            raise ValueError(f"missing columns: {missing}")
        clean = data[required].rename(columns={
            "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
        })
        clean = clean.dropna(subset=["date"]).sort_values("date")
        duplicate_dates = int(clean["date"].duplicated().sum())
        clean = clean.drop_duplicates("date")
        clean["metal"] = metal
        clean["ticker"] = ticker
        clean["source"] = "Yahoo Finance"
        clean["unit"] = unit
        clean["fetched_at"] = fetched_at
        clean = clean[["date", "metal", "ticker", "unit", "open", "high", "low", "close", "volume", "source", "fetched_at"]]
        clean.to_csv(RAW_DIR / f"{ticker.replace('=', '_').replace('^', '')}.csv", index=False)
        daily_change = clean["close"].pct_change().abs() * 100
        result.update({
            "status": "success",
            "start_date": clean["date"].min().date().isoformat(),
            "end_date": clean["date"].max().date().isoformat(),
            "row_count": int(len(clean)),
            "missing_close": int(clean["close"].isna().sum()),
            "duplicate_dates": duplicate_dates,
            "non_positive_close": int((clean["close"] <= 0).sum()),
            "max_abs_daily_change_pct": round(float(daily_change.max()), 4) if not daily_change.dropna().empty else None,
        })
        return clean, result
    except Exception as exc:  # Keep other instruments running if one source fails.
        result["error"] = str(exc)
        return pd.DataFrame(), result


def make_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame(columns=["week_end", "metal", "ticker", "unit", "last_close", "week_high", "week_low", "weekly_change_pct", "observation_count"])
    daily = daily.copy()
    daily["week"] = daily["date"].dt.to_period("W-FRI")
    weekly = daily.sort_values("date").groupby(["week", "metal", "ticker", "unit"], as_index=False).agg(
        week_end=("date", "max"), last_close=("close", "last"), week_high=("high", "max"),
        week_low=("low", "min"), observation_count=("close", "count")
    )
    weekly["weekly_change_pct"] = weekly.groupby("metal")["last_close"].pct_change() * 100
    return weekly[["week_end", "metal", "ticker", "unit", "last_close", "week_high", "week_low", "weekly_change_pct", "observation_count"]]


def make_charts(daily: pd.DataFrame) -> None:
    for metal, group in daily.groupby("metal"):
        if group.empty:
            continue
        fig, ax = plt.subplots(figsize=(10, 5.5), dpi=150)
        ax.plot(group["date"], group["close"], color="#58656f", linewidth=1.8)
        ax.set_title(f"{metal}近一年价格趋势")
        ax.set_xlabel("日期")
        ax.set_ylabel(f"价格（{group['unit'].iloc[0]}）")
        ax.grid(True, alpha=0.25)
        fig.text(0.99, 0.01, "数据来源：Yahoo Finance", ha="right", fontsize=8, color="#666666")
        fig.tight_layout()
        filename = {"黄金": "gold", "白银": "silver", "铜": "copper", "锡": "tin"}[metal]
        fig.savefig(CHART_DIR / f"{filename}_1y.png", bbox_inches="tight")
        plt.close(fig)


def main() -> int:
    for directory in (RAW_DIR, PROCESSED_DIR, CHART_DIR, REPORT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).isoformat()
    frames, quality = [], []
    for metal, (ticker, unit) in INSTRUMENTS.items():
        frame, result = fetch_one(metal, ticker, unit, fetched_at)
        if not frame.empty:
            frames.append(frame)
        quality.append(result)
    daily = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not daily.empty:
        daily.sort_values(["date", "metal"]).to_csv(PROCESSED_DIR / "metal_prices_daily.csv", index=False)
        make_weekly(daily)
        make_charts(daily)
    weekly = make_weekly(daily)
    weekly.to_csv(PROCESSED_DIR / "metal_prices_weekly.csv", index=False)
    report = {"checked_at": fetched_at, "source": "Yahoo Finance", "instruments": quality}
    (REPORT_DIR / "data_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if any(item["status"] == "success" for item in quality) else 1


if __name__ == "__main__":
    raise SystemExit(main())
