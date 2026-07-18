#!/usr/bin/env python3
"""Generate a local, facts-only analysis sample without calling an LLM."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FACTS_PATH = ROOT / "data" / "processed" / "weekly_report.json"
OUTPUT_PATH = ROOT / "data" / "processed" / "weekly_analysis.json"


def trend_label(points: list[dict]) -> str:
    values = [point["price"] for point in points if point["price"] is not None]
    if len(values) < 3:
        return "数据不足"
    if values[-1] > values[0] * 1.03:
        return "上涨"
    if values[-1] < values[0] * 0.97:
        return "下跌"
    return "震荡"


def trend_change_pct(points: list[dict]) -> float | None:
    """Return the change from the first to the last available trend point."""
    values = [point["price"] for point in points if point["price"] is not None]
    if len(values) < 2 or values[0] == 0:
        return None
    return (values[-1] / values[0] - 1) * 100


def direction_groups(performance: list[dict]) -> tuple[list[str], list[str], list[str]]:
    """Group metals by the sign of their latest weekly change."""
    up, down, flat = [], [], []
    for item in performance:
        change = item["weekly_change_pct"]
        if change > 0:
            up.append(item["metal"])
        elif change < 0:
            down.append(item["metal"])
        else:
            flat.append(item["metal"])
    return up, down, flat


def build_summary(performance: list[dict], trend: dict[str, list[dict]]) -> str:
    """Build a scope-explicit summary from the current week's facts."""
    up, down, flat = direction_groups(performance)
    direction_parts = []
    if up:
        direction_parts.append(f"{ '、'.join(up) }上涨")
    if down:
        direction_parts.append(f"{ '、'.join(down) }下跌")
    if flat:
        direction_parts.append(f"{ '、'.join(flat) }持平")

    strongest = max(performance, key=lambda item: item["weekly_change_pct"])
    summary = "本周较上周均价，" + "，".join(direction_parts) + f"，其中{strongest['metal']}涨幅最大（{strongest['weekly_change_pct']:+.2f}%）。"

    gold_points = trend.get("黄金", [])
    gold_trend_change = trend_change_pct(gold_points)
    gold_weekly = next((item["weekly_change_pct"] for item in performance if item["metal"] == "黄金"), None)
    if gold_weekly is not None and gold_trend_change is not None and gold_weekly > 0 and gold_trend_change < 0:
        summary += f"黄金本周上涨{gold_weekly:.2f}%，但近3个月累计下跌{abs(gold_trend_change):.2f}%，短线方向与中期趋势不同。"
    return summary


def main() -> int:
    facts = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
    performance = facts["performance"]
    by_metal = {item["metal"]: item for item in performance}
    metal_analysis = []
    trend = facts["trend_12_weeks"]
    for metal, points in trend.items():
        item = by_metal[metal]
        change = item["weekly_change_pct"]
        direction = "上涨" if change > 0 else "下跌" if change < 0 else "持平"
        metal_analysis.append({
            "metal": metal,
            "price": item["price"],
            "week_close": item["week_close"],
            "week_high": item["week_high"],
            "week_low": item["week_low"],
            "unit": item["unit"],
            "weekly_change_pct": change,
            "trend_12_weeks": trend_label(points),
            "trend_12_weeks_change_pct": trend_change_pct(points),
            "facts": [
                f"本周均价为 {item['price']:.2f} {item['unit']}。",
                f"本周人民币口径价格{direction} {abs(change):.2f}%。",
                f"当前可用趋势数据为 {len(points)} 周。",
            ],
            "interpretation": "现有数据只能确认价格变化，无法确认具体原因。",
            "risk_note": "价格来自不同市场和合约口径，横向比较仅使用周涨跌幅。",
        })
    result = {
        "schema_version": "1.0",
        "report_type": "metal_weekly_analysis",
        "generated_by": "local_facts_only",
        "external_ai_call": False,
        "language": "zh-CN",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "week_end": facts["week_end"],
        "week_start": facts["week_start"],
        "market_snapshot": {
            "biggest_gainer": {
                "metal": facts["market_summary"]["biggest_gainer"],
                "change_pct": facts["market_summary"]["biggest_gainer_change_pct"],
            },
            "biggest_loser": {
                "metal": facts["market_summary"]["biggest_loser"],
                "change_pct": facts["market_summary"]["biggest_loser_change_pct"],
            },
            "one_sentence_summary": build_summary(performance, trend),
            "scope_note": "概览和价格卡片使用较上周均价；趋势图使用近3个月周均价，两个时间口径可能出现相反方向。",
        },
        "metal_analysis": metal_analysis,
        "comparison": {
            "relative_performance": "按人民币口径周涨跌幅，锡表现最强，白银表现最弱。",
            "price_comparison_warning": "黄金、白银以人民币/克展示，铜、锡以人民币/吨展示，原始价格不可直接比较。",
        },
        "data_limitations": facts["data_quality"]["warnings"],
        "next_week_watchlist": ["继续观察四种金属的人民币口径周涨跌变化。"],
    }
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT_PATH), "external_ai_call": False, "week_end": result["week_end"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
