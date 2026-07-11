#!/usr/bin/env python3
"""Run the complete weekly data refresh and stop on the first failed step."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(label: str, script: str, *args: str) -> None:
    command = [sys.executable, str(ROOT / "src" / script), *args]
    print(f"\n== {label} ==")
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the Metal Intelligence weekly report")
    parser.add_argument("--tin-days", type=int, default=365, help="SHFE tin lookback in calendar days")
    parser.add_argument("--workers", type=int, default=8, help="parallel workers for SHFE official files")
    args = parser.parse_args()

    run("抓取黄金、白银、铜", "fetch_prices.py")
    run("抓取美元兑人民币汇率", "fetch_fx.py")
    run("抓取 SHFE 官方锡价", "fetch_shfe_tin.py", "--days", str(args.tin_days), "--workers", str(args.workers))
    run("统一周度人民币数据", "build_unified_weekly.py")
    run("生成事实型周报数据", "generate_weekly_json.py")
    run("生成演示分析", "generate_demo_analysis.py")
    run("执行数据复核", "validate_weekly_data.py")
    run("更新周报页面", "generate_weekly_html.py")
    print("\n周报更新完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
