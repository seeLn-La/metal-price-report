#!/usr/bin/env python3
"""Build a unified weekly table with RMB display prices and auditable FX fields."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "metal_sources.json"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "reports"
TROY_OUNCE_GRAMS = 31.1034768
POUND_TO_TON = 2204.62262185


def add_fx(daily: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    daily = daily.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    fx = fx.copy()
    fx["date"] = pd.to_datetime(fx["date"])
    merged = daily.merge(fx[["date", "usd_cny"]], on="date", how="left").sort_values("date")
    merged["usd_cny"] = merged["usd_cny"].ffill()
    return merged


def aggregate_weekly(daily: pd.DataFrame, config: dict, metal: str) -> pd.DataFrame:
    daily = daily.copy()
    daily["week"] = daily["date"].dt.to_period("W-FRI")
    daily["native_close"] = pd.to_numeric(daily["close"], errors="coerce")
    daily["native_high"] = pd.to_numeric(daily["high"], errors="coerce")
    daily["native_low"] = pd.to_numeric(daily["low"], errors="coerce")
    daily["price_cny"] = daily["native_close"]
    daily["high_cny"] = daily["native_high"]
    daily["low_cny"] = daily["native_low"]
    if metal in {"黄金", "白银"}:
        daily["price_cny"] = daily["native_close"] * daily["usd_cny"] / TROY_OUNCE_GRAMS
        daily["high_cny"] = daily["native_high"] * daily["usd_cny"] / TROY_OUNCE_GRAMS
        daily["low_cny"] = daily["native_low"] * daily["usd_cny"] / TROY_OUNCE_GRAMS
    elif metal == "铜":
        daily["price_cny"] = daily["native_close"] * daily["usd_cny"] * POUND_TO_TON
        daily["high_cny"] = daily["native_high"] * daily["usd_cny"] * POUND_TO_TON
        daily["low_cny"] = daily["native_low"] * daily["usd_cny"] * POUND_TO_TON
    daily = daily.dropna(subset=["date", "native_close", "price_cny"])
    weekly = daily.sort_values("date").groupby("week", as_index=False).agg(
        week_start=("date", "min"), week_end=("date", "max"), price_cny=("price_cny", "last"), week_high_cny=("high_cny", "max"),
        week_low_cny=("low_cny", "min"), native_last_close=("native_close", "last"),
        usd_cny=("usd_cny", "last"), observations=("price_cny", "count"),
    )
    weekly["weekly_change_cny_pct"] = weekly["price_cny"].pct_change() * 100
    weekly["weekly_change_native_pct"] = weekly["native_last_close"].pct_change() * 100
    weekly["metal"] = metal
    weekly["source"] = config["source"]
    weekly["market"] = config["market"]
    weekly["identifier"] = config["identifier"]
    weekly["display_unit"] = config["display_unit"]
    weekly["native_unit"] = config["native_unit"]
    weekly["fx_ticker"] = "CNY=X" if metal != "锡" else "not_required"
    return weekly


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    sources = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    fx = pd.read_csv(PROCESSED_DIR / "usd_cny_daily.csv")
    yahoo = pd.read_csv(PROCESSED_DIR / "metal_prices_daily.csv")
    tin = pd.read_csv(PROCESSED_DIR / "shfe_tin_main_daily.csv")
    frames = []
    for metal, config in sources.items():
        if metal == "锡":
            daily = tin.copy()
            daily["date"] = pd.to_datetime(daily["date"])
            daily["usd_cny"] = float("nan")
        else:
            daily = yahoo[yahoo["metal"].eq(metal)].copy()
            daily = add_fx(daily, fx)
        frames.append(aggregate_weekly(daily, config, metal))
    unified = pd.concat(frames, ignore_index=True)
    unified["week_end"] = pd.to_datetime(unified["week_end"]).dt.strftime("%Y-%m-%d")
    unified = unified[[
        "week_start", "week_end", "metal", "source", "market", "identifier", "price_cny", "display_unit",
        "week_high_cny", "week_low_cny", "weekly_change_cny_pct", "native_last_close",
        "native_unit", "weekly_change_native_pct", "usd_cny", "fx_ticker", "observations",
    ]].sort_values(["week_end", "metal"])
    unified.to_csv(PROCESSED_DIR / "metal_prices_unified_weekly.csv", index=False)
    latest_week = unified["week_end"].max()
    latest = unified[unified["week_end"].eq(latest_week)]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_week_end": latest_week,
        "latest_week_rows": int(len(latest)),
        "metals_in_latest_week": sorted(latest["metal"].unique().tolist()),
        "display_currency": "CNY",
        "display_units": {"黄金": "人民币/克", "白银": "人民币/克", "铜": "人民币/吨", "锡": "人民币/吨"},
        "fx_source": "Yahoo Finance CNY=X for USD-denominated contracts",
        "fx_conversion_status": "applied_to_gold_silver_copper",
        "weekly_change_cny_comparable": True,
        "raw_price_level_comparable": False,
        "missing_metals_in_latest_week": sorted(set(sources) - set(latest["metal"])),
        "conversion_constants": {"troy_ounce_grams": TROY_OUNCE_GRAMS, "pound_to_ton": POUND_TO_TON},
    }
    (REPORT_DIR / "unified_weekly_comparability.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\nLatest RMB weekly rows:")
    print(latest[["metal", "price_cny", "display_unit", "weekly_change_cny_pct", "weekly_change_native_pct", "usd_cny"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
