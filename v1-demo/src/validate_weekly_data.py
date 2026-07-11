#!/usr/bin/env python3
"""Run deterministic source, value, formula, and content consistency checks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "processed" / "metal_prices_unified_weekly.csv"
FACTS_PATH = ROOT / "data" / "processed" / "weekly_report.json"
DRIVERS_PATH = ROOT / "data" / "processed" / "market_drivers.json"
OUTPUT_PATH = ROOT / "reports" / "weekly_data_review.json"
EXPECTED_UNITS = {"黄金": "人民币/克", "白银": "人民币/克", "铜": "人民币/吨", "锡": "人民币/吨"}
DRIVER_TYPES = ["外部环境", "库存和买货", "价格表现", "注意事项"]
CONCLUSION_STATUSES = {"supported", "mixed", "weak", "insufficient"}
TROY_OUNCE_GRAMS = 31.1034768
POUND_TO_TON = 2204.62262185


def check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "status": "通过" if passed else "未通过", "detail": detail}


def main() -> int:
    df = pd.read_csv(DATA_PATH)
    facts = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
    drivers = json.loads(DRIVERS_PATH.read_text(encoding="utf-8"))
    checks = []
    latest = df[df["week_end"].eq(df["week_end"].max())]
    checks.append(check("最新周四种金属齐全", set(latest["metal"]) == set(EXPECTED_UNITS), f"发现 {sorted(latest['metal'].tolist())}"))
    checks.append(check("人民币展示单位正确", all(latest.set_index("metal")["display_unit"].get(metal) == unit for metal, unit in EXPECTED_UNITS.items()), "黄金/白银为元克，铜/锡为元吨"))
    checks.append(check("价格为正数", bool((df["price_cny"] > 0).all()), "所有统一价格均大于 0"))
    checks.append(check("来源字段完整", bool(df[["source", "market", "identifier"]].notna().all().all()), "每条周度记录都有来源和标识"))
    latest_date = pd.to_datetime(df["week_end"]).max().date()
    today = datetime.now(timezone.utc).date()
    checks.append(check("最新数据未过期", (today - latest_date).days <= 7, f"最新周末：{latest_date.isoformat()}，当前日期：{today.isoformat()}"))

    conversion_failures = []
    for metal, group in df.dropna(subset=["native_last_close", "usd_cny", "price_cny"]).iterrows():
        if metal is None:
            continue
        expected = group["native_last_close"]
        if group["metal"] in {"黄金", "白银"}:
            expected = expected * group["usd_cny"] / TROY_OUNCE_GRAMS
        elif group["metal"] == "铜":
            expected = expected * group["usd_cny"] * POUND_TO_TON
        if abs(expected - group["price_cny"]) > max(abs(expected) * 0.00001, 0.01):
            conversion_failures.append(group["metal"])
    checks.append(check("人民币换算公式一致", not conversion_failures, "黄金/白银/铜逐行按原始价格和汇率复算无差异" if not conversion_failures else f"存在差异：{sorted(set(conversion_failures))}"))
    checks.append(check("锡使用官方人民币口径", bool((df[df["metal"].eq("锡")]["source"] == "SHFE official").all()), "锡价来自 SHFE 官方，未重复换汇"))
    checks.append(check("涨跌公式一致", True, "逐品种按周收盘价复算周涨跌，容差 0.01 个百分点"))
    formula_failures = []
    for metal, group in df.sort_values("week_end").groupby("metal"):
        group = group.reset_index(drop=True)
        expected = group["price_cny"].pct_change() * 100
        actual = group["weekly_change_cny_pct"]
        mismatch = (expected - actual).abs() > 0.01
        mismatch.iloc[0] = False
        if mismatch.any():
            formula_failures.append(metal)
    checks[-1]["status"] = "通过" if not formula_failures else "未通过"
    checks[-1]["detail"] = "无复算差异" if not formula_failures else f"存在差异：{formula_failures}"
    checks.append(check("事实型 JSON 与最新周一致", facts.get("week_end") == df["week_end"].max() and facts.get("facts_only") is True, "JSON 标记为 facts_only 且日期一致"))
    trend_counts = facts.get("data_quality", {}).get("trend_week_counts", {})
    checks.append(check("趋势数据覆盖", all(1 <= trend_counts.get(metal, 0) <= 12 for metal in EXPECTED_UNITS), f"覆盖周数：{trend_counts}"))
    driver_ok = all(set(item.get("type") for item in drivers[metal]["drivers"]) == set(DRIVER_TYPES) for metal in EXPECTED_UNITS if metal in drivers)
    checks.append(check("四种金属驱动分析角度一致", driver_ok, "统一使用外部环境、库存和买货、价格表现、注意事项"))
    checks.append(check("驱动来源可追溯", all(entry.get("source") for item in drivers.values() for entry in item["drivers"]), "每条驱动都记录来源名称"))
    conclusion_ok = all(
        metal in drivers
        and drivers[metal].get("conclusion")
        and drivers[metal].get("conclusion_status") in CONCLUSION_STATUSES
        for metal in EXPECTED_UNITS
    )
    checks.append(check("每种金属都有明确结论", conclusion_ok, "结论必须有正文和 supported/mixed/weak/insufficient 状态"))
    passed = all(item["status"] == "通过" for item in checks)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "通过" if passed else "未通过",
        "check_count": len(checks),
        "passed_count": sum(item["status"] == "通过" for item in checks),
        "checks": checks,
        "method": [
            "源字段和人民币单位检查",
            "正数与完整性检查",
            "最新数据新鲜度检查",
            "人民币换算公式逐行复算",
            "锡的 SHFE 官方来源检查",
            "周涨跌公式复算",
            "事实 JSON 日期和 facts_only 标记检查",
            "趋势覆盖周数检查",
            "四种金属驱动分析角度一致性检查",
            "驱动结论正文和状态检查",
        ],
    }
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
