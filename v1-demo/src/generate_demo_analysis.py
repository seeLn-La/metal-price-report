#!/usr/bin/env python3
"""Generate a local, facts-only analysis sample without calling an LLM."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FACTS_PATH = ROOT / "data" / "processed" / "weekly_report.json"
OUTPUT_PATH = ROOT / "data" / "processed" / "weekly_analysis_demo.json"


def trend_label(points: list[dict]) -> str:
    values = [point["price"] for point in points if point["price"] is not None]
    if len(values) < 3:
        return "数据不足"
    if values[-1] > values[0] * 1.03:
        return "上涨"
    if values[-1] < values[0] * 0.97:
        return "下跌"
    return "震荡"


def main() -> int:
    facts = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
    performance = facts["performance"]
    by_metal = {item["metal"]: item for item in performance}
    metal_analysis = []
    for metal, points in facts["trend_12_weeks"].items():
        item = by_metal[metal]
        change = item["weekly_change_pct"]
        direction = "上涨" if change > 0 else "下跌" if change < 0 else "持平"
        metal_analysis.append({
            "metal": metal,
            "price": item["price"],
            "unit": item["unit"],
            "weekly_change_pct": change,
            "trend_12_weeks": trend_label(points),
            "facts": [
                f"本周收盘价为 {item['price']:.2f} {item['unit']}。",
                f"本周人民币口径价格{direction} {abs(change):.2f}%。",
                f"当前可用趋势数据为 {len(points)} 周。",
            ],
            "interpretation": "现有数据只能确认价格变化，无法确认具体原因。",
            "risk_note": "价格来自不同市场和合约口径，横向比较仅使用周涨跌幅。",
        })
    result = {
        "schema_version": "1.0",
        "report_type": "metal_weekly_demo_analysis",
        "generated_by": "local_facts_only_demo",
        "external_ai_call": False,
        "language": "zh-CN",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "week_end": facts["week_end"],
        "market_snapshot": {
            "biggest_gainer": {
                "metal": facts["market_summary"]["biggest_gainer"],
                "change_pct": facts["market_summary"]["biggest_gainer_change_pct"],
            },
            "biggest_loser": {
                "metal": facts["market_summary"]["biggest_loser"],
                "change_pct": facts["market_summary"]["biggest_loser_change_pct"],
            },
            "one_sentence_summary": "本周金属价格表现分化：锡和铜上涨，黄金小幅上涨，白银小幅下跌。",
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
