#!/usr/bin/env python3
"""Generate a facts-only weekly report payload for AI and UI consumers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "processed" / "metal_prices_unified_weekly.csv"
CONFIG_PATH = ROOT / "config" / "metal_sources.json"
QUALITY_PATH = ROOT / "reports" / "unified_weekly_comparability.json"
OUTPUT_PATH = ROOT / "data" / "processed" / "weekly_report.json"


def clean_number(value):
    return None if pd.isna(value) else round(float(value), 6)


def main() -> int:
    df = pd.read_csv(DATA_PATH)
    configs = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    quality = json.loads(QUALITY_PATH.read_text(encoding="utf-8"))
    latest_week = df["week_end"].max()
    latest = df[df["week_end"].eq(latest_week)].copy().sort_values("weekly_change_cny_pct", ascending=False)
    if len(latest) != 4:
        raise ValueError(f"Expected four metals in latest week, found {len(latest)}")

    performance = []
    for _, row in latest.iterrows():
        performance.append({
            "metal": row["metal"],
            "price": clean_number(row["price_cny"]),
            "unit": row["display_unit"],
            "week_high": clean_number(row["week_high_cny"]),
            "week_low": clean_number(row["week_low_cny"]),
            "weekly_change_pct": clean_number(row["weekly_change_cny_pct"]),
            "native_weekly_change_pct": clean_number(row["weekly_change_native_pct"]),
            "source": row["source"],
            "market": row["market"],
            "identifier": row["identifier"],
            "native_unit": row["native_unit"],
            "fx_ticker": row["fx_ticker"],
            "observations": int(row["observations"]),
        })

    trend = {}
    for metal, group in df.groupby("metal"):
        group = group.sort_values("week_end").tail(12)
        trend[metal] = [
            {
                "week_end": row["week_end"],
                "week_start": row["week_start"],
                "price": clean_number(row["price_cny"]),
                "unit": row["display_unit"],
                "weekly_change_pct": clean_number(row["weekly_change_cny_pct"]),
            }
            for _, row in group.iterrows()
        ]

    report = {
        "schema_version": "1.0",
        "report_type": "metal_weekly_facts_only",
        "language": "zh-CN",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "week_end": latest_week,
        "week_start": str(pd.to_datetime(latest["week_start"]).min().date()),
        "display_currency": "CNY",
        "facts_only": True,
        "ai_insight": None,
        "market_summary": {
            "biggest_gainer": performance[0]["metal"],
            "biggest_gainer_change_pct": performance[0]["weekly_change_pct"],
            "biggest_loser": performance[-1]["metal"],
            "biggest_loser_change_pct": performance[-1]["weekly_change_pct"],
            "positive_count": int((latest["weekly_change_cny_pct"] > 0).sum()),
            "negative_count": int((latest["weekly_change_cny_pct"] < 0).sum()),
        },
        "performance": performance,
        "trend_12_weeks": trend,
        "data_sources": {
            "price_sources": [
                {"metal": metal, "source": config["source"], "market": config["market"], "identifier": config["identifier"]}
                for metal, config in configs.items()
            ],
            "fx_source": quality.get("fx_source"),
            "updated_at": quality.get("generated_at"),
        },
        "data_quality": {
            "all_metals_present": len(performance) == 4,
            "weekly_change_cny_comparable": quality.get("weekly_change_cny_comparable"),
            "raw_price_level_comparable": quality.get("raw_price_level_comparable"),
            "missing_metals": quality.get("missing_metals_in_latest_week", []),
            "trend_week_counts": {metal: len(values) for metal, values in trend.items()},
            "warnings": [
                "黄金、白银、铜的人民币价格使用 Yahoo Finance CNY=X 日汇率换算。",
                "锡使用 SHFE 人民币/吨报价，不需要汇率换算。",
                "本文件只包含数据事实，不包含 AI 解读或因果判断。",
            ],
        },
    }
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "week_end": latest_week,
        "performance": [(item["metal"], item["weekly_change_pct"]) for item in performance],
        "facts_only": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
