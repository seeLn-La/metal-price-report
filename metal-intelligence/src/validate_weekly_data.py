#!/usr/bin/env python3
"""Run deterministic source, value, formula, and content consistency checks."""

from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from build_unified_weekly import add_fx, aggregate_weekly
from generate_weekly_analysis import build_summary


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "processed" / "metal_prices_unified_weekly.csv"
DAILY_PATH = ROOT / "data" / "processed" / "metal_prices_daily.csv"
FX_PATH = ROOT / "data" / "processed" / "usd_cny_daily.csv"
TIN_DAILY_PATH = ROOT / "data" / "processed" / "shfe_tin_main_daily.csv"
CONFIG_PATH = ROOT / "config" / "metal_sources.json"
DATA_DICTIONARY_PATH = ROOT / "config" / "data_dictionary.json"
FACTS_PATH = ROOT / "data" / "processed" / "weekly_report.json"
ANALYSIS_PATH = ROOT / "data" / "processed" / "weekly_analysis.json"
DRIVERS_PATH = ROOT / "data" / "processed" / "market_drivers.json"
QUALITY_PATH = ROOT / "reports" / "data_quality_report.json"
FX_QUALITY_PATH = ROOT / "reports" / "usd_cny_quality_report.json"
TIN_QUALITY_PATH = ROOT / "reports" / "shfe_tin_quality_report.json"
SNAPSHOT_POINTER_PATH = ROOT / "reports" / "latest_snapshot.json"
SNAPSHOT_REQUIRED_PATHS = {
    "config/metal_sources.json",
    "config/data_dictionary.json",
    "data/raw/GC_F.csv",
    "data/raw/SI_F.csv",
    "data/raw/HG_F.csv",
    "data/raw/USD_CNY.csv",
    "data/raw/shfe_tin_contracts_daily.csv",
    "data/processed/metal_prices_daily.csv",
    "data/processed/usd_cny_daily.csv",
    "data/processed/shfe_tin_main_daily.csv",
    "reports/data_quality_report.json",
    "reports/usd_cny_quality_report.json",
    "reports/shfe_tin_quality_report.json",
}
OUTPUT_PATH = ROOT / "reports" / "weekly_data_review.json"
EXPECTED_UNITS = {"黄金": "人民币/克", "白银": "人民币/克", "铜": "人民币/吨", "锡": "人民币/吨"}
DRIVER_EVIDENCE_LEVELS = {"较强", "中等", "较弱", "不足"}
CONCLUSION_STATUSES = {"supported", "mixed", "weak", "insufficient"}
TROY_OUNCE_GRAMS = 31.1034768
POUND_TO_TON = 2204.62262185
MAX_STALENESS_DAYS = 7


def check(name: str, passed: bool, detail: str) -> dict:
    return {"name": name, "status": "通过" if passed else "未通过", "detail": detail}


def fingerprint(path: Path) -> dict:
    """Record the exact input file used for this review."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def source_quality_failures() -> list[str]:
    """Verify that each declared source completed successfully."""
    failures = []
    if not QUALITY_PATH.exists():
        return ["缺少 data_quality_report.json"]
    quality = json.loads(QUALITY_PATH.read_text(encoding="utf-8"))
    expected_tickers = {"黄金": "GC=F", "白银": "SI=F", "铜": "HG=F"}
    instruments = {item.get("metal"): item for item in quality.get("instruments", [])}
    for metal, ticker in expected_tickers.items():
        item = instruments.get(metal, {})
        if item.get("status") != "success" or item.get("ticker") != ticker:
            failures.append(f"{metal} 来源未成功或代码不匹配")
    if not FX_QUALITY_PATH.exists():
        failures.append("缺少 usd_cny_quality_report.json")
    else:
        fx_quality = json.loads(FX_QUALITY_PATH.read_text(encoding="utf-8"))
        if fx_quality.get("status") != "success" or fx_quality.get("ticker") != "CNY=X":
            failures.append("美元兑人民币来源未成功或代码不匹配")
    if not TIN_QUALITY_PATH.exists():
        failures.append("缺少 shfe_tin_quality_report.json")
    else:
        tin_quality = json.loads(TIN_QUALITY_PATH.read_text(encoding="utf-8"))
        if tin_quality.get("status") != "success" or tin_quality.get("source") != "SHFE official":
            failures.append("锡价 SHFE 官方来源未成功")
    return failures


def snapshot_failures(configs: dict) -> list[str]:
    """Verify the latest snapshot exists and still matches current source inputs."""
    if not SNAPSHOT_POINTER_PATH.exists():
        return ["缺少 latest_snapshot.json"]
    pointer = json.loads(SNAPSHOT_POINTER_PATH.read_text(encoding="utf-8"))
    manifest_path = ROOT / pointer.get("manifest", "")
    snapshot_dir = ROOT / pointer.get("snapshot_dir", "")
    if not manifest_path.exists() or not snapshot_dir.exists():
        return ["快照目录或 manifest 不存在"]
    failures = []
    if pointer.get("manifest_sha256") != hashlib.sha256(manifest_path.read_bytes()).hexdigest():
        failures.append("latest_snapshot.json 的 manifest 指纹不匹配")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("source_config") != configs:
        failures.append("快照中的来源配置与当前配置不一致")
    manifest_paths = {item.get("path") for item in manifest.get("files", [])}
    missing_required = SNAPSHOT_REQUIRED_PATHS - manifest_paths
    if missing_required:
        failures.append("快照缺少必要输入：" + "、".join(sorted(missing_required)))
    for item in manifest.get("files", []):
        source_path = ROOT / item["path"]
        snapshot_path = snapshot_dir / item["snapshot_path"]
        if not source_path.exists() or not snapshot_path.exists():
            failures.append(f"快照文件缺失：{item['path']}")
            continue
        expected_hash = item.get("sha256")
        if hashlib.sha256(snapshot_path.read_bytes()).hexdigest() != expected_hash:
            failures.append(f"快照文件自身指纹不匹配：{item['path']}")
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != expected_hash:
            failures.append(f"当前输入与快照不一致：{item['path']}")
    if not manifest.get("files"):
        failures.append("manifest 没有记录输入文件")
    return failures


def raw_data_failures(configs: dict) -> list[str]:
    """Check raw/processed daily inputs before any weekly aggregation."""
    failures = []
    daily = pd.read_csv(DAILY_PATH)
    required_daily = {"date", "metal", "ticker", "close", "high", "low", "source", "fetched_at"}
    if not required_daily.issubset(daily.columns):
        return [f"金属日线缺少字段：{sorted(required_daily - set(daily.columns))}"]
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce")
    for metal, config in configs.items():
        if metal == "锡":
            continue
        sub = daily[daily["metal"].eq(metal)]
        if sub.empty:
            failures.append(f"{metal} 没有日线数据")
            continue
        if sub[["date", "close", "high", "low"]].isna().any().any():
            failures.append(f"{metal} 日线存在日期或价格缺失")
        if sub.duplicated("date").any():
            failures.append(f"{metal} 日线存在重复日期")
        numeric_prices = sub[["close", "high", "low"]].apply(pd.to_numeric, errors="coerce")
        if (numeric_prices <= 0).any().any():
            failures.append(f"{metal} 日线存在非正价格")
        if (sub["high"] < sub["low"]).any() or (sub["close"] > sub["high"]).any() or (sub["close"] < sub["low"]).any():
            failures.append(f"{metal} 日线高低收价格关系异常")
        if set(sub["ticker"].dropna()) != {config["identifier"]} or set(sub["source"].dropna()) != {config["source"]}:
            failures.append(f"{metal} 日线来源或代码与配置不一致")

    fx = pd.read_csv(FX_PATH)
    if fx.empty or fx["usd_cny"].isna().any() or (pd.to_numeric(fx["usd_cny"], errors="coerce") <= 0).any():
        failures.append("美元兑人民币日线为空或包含无效汇率")
    if fx["date"].duplicated().any():
        failures.append("美元兑人民币日线存在重复日期")

    tin = pd.read_csv(TIN_DAILY_PATH)
    if tin.empty:
        failures.append("SHFE 锡主力日线为空")
    else:
        if tin["date"].duplicated().any():
            failures.append("SHFE 锡主力日线存在重复日期")
        if (pd.to_numeric(tin["close"], errors="coerce") <= 0).any():
            failures.append("SHFE 锡主力日线存在非正价格")
        if set(tin["source"].dropna()) != {"SHFE official"} or tin["source_url"].isna().any():
            failures.append("SHFE 锡日线来源证据不完整")
    return failures


def config_alignment_failures(df: pd.DataFrame, configs: dict) -> list[str]:
    """Ensure the unified table still carries the configured provenance."""
    failures = []
    for metal, config in configs.items():
        sub = df[df["metal"].eq(metal)]
        if sub.empty:
            failures.append(f"统一周表缺少 {metal}")
            continue
        expected = {
            "source": config["source"],
            "market": config["market"],
            "identifier": config["identifier"],
            "display_unit": config["display_unit"],
            "native_unit": config["native_unit"],
        }
        for column, value in expected.items():
            if set(sub[column].dropna()) != {value}:
                failures.append(f"{metal} 的 {column} 与来源配置不一致")
    return failures


def recompute_transform_failures(df: pd.DataFrame, configs: dict) -> list[str]:
    """Rebuild the unified weekly table from daily inputs and compare values."""
    fx = pd.read_csv(FX_PATH)
    yahoo = pd.read_csv(DAILY_PATH)
    tin = pd.read_csv(TIN_DAILY_PATH)
    frames = []
    for metal, config in configs.items():
        if metal == "锡":
            daily = tin.copy()
            daily["date"] = pd.to_datetime(daily["date"])
            daily["usd_cny"] = float("nan")
        else:
            daily = add_fx(yahoo[yahoo["metal"].eq(metal)].copy(), fx)
        frames.append(aggregate_weekly(daily, config, metal))
    expected = pd.concat(frames, ignore_index=True)
    for table in (expected, df):
        table["week_start"] = pd.to_datetime(table["week_start"]).dt.strftime("%Y-%m-%d")
        table["week_end"] = pd.to_datetime(table["week_end"]).dt.strftime("%Y-%m-%d")
    keys = ["week_start", "week_end", "metal"]
    compare_columns = ["price_cny", "week_close_cny", "week_high_cny", "week_low_cny", "weekly_change_cny_pct", "native_avg_close", "native_last_close", "weekly_change_native_pct", "usd_cny", "observations"]
    merged = expected[keys + compare_columns].merge(df[keys + compare_columns], on=keys, how="outer", suffixes=("_expected", "_actual"), indicator=True)
    failures = []
    if not (merged["_merge"] == "both").all():
        failures.append("统一周表与日线重算结果的记录数不一致")
    for column in compare_columns:
        expected_values = pd.to_numeric(merged[f"{column}_expected"], errors="coerce")
        actual_values = pd.to_numeric(merged[f"{column}_actual"], errors="coerce")
        equal = np.isclose(expected_values, actual_values, rtol=1e-7, atol=1e-4, equal_nan=True)
        if not bool(equal.all()):
            failures.append(f"统一周表字段 {column} 无法由日线重算复现")
    return failures


def driver_price_claim_failures(drivers: dict, facts_by_metal: dict) -> list[str]:
    """Reject stale numeric weekly claims in qualitative driver explanations."""
    pattern = re.compile(r"本周[^。！？；]*?(?:上涨|下跌)[^。！？；]*?([+-]?\d+(?:\.\d+)?)%")
    failures = []
    for metal, item in drivers.get("metals", {}).items():
        expected = facts_by_metal.get(metal, {}).get("weekly_change_pct")
        if expected is None:
            continue
        searchable_text = [item.get("headline", ""), item.get("reader_summary", ""), item.get("conclusion", ""), item.get("caveat", "")]
        searchable_text.extend(item.get("evidence_gaps", []))
        searchable_text.extend(item.get("watch_next_week", []))
        for entry in item.get("factors", []):
            searchable_text.extend(entry.get(field, "") for field in ("plain_explanation", "possible_effect", "limitation"))
        for text in searchable_text:
            for match in pattern.finditer(text):
                claimed = float(match.group(1))
                if abs(claimed - expected) > 0.01:
                    failures.append(f"{metal} 驱动文字写入 {claimed:.2f}%，事实周涨跌为 {expected:.2f}%")
    return failures


def driver_schema_failures(drivers: dict) -> list[str]:
    """Require reader-friendly explanations to carry evidence and limitations."""
    failures = []
    if drivers.get("schema_version") != "2.0":
        failures.append("驱动分析 schema_version 必须为 2.0")
    if not drivers.get("reader_note"):
        failures.append("驱动分析缺少读者说明")
    metals = drivers.get("metals", {})
    required_fields = {"headline", "reader_summary", "factors", "evidence_gaps", "conclusion", "conclusion_status", "watch_next_week", "caveat"}
    for metal in EXPECTED_UNITS:
        item = metals.get(metal)
        if not item:
            failures.append(f"{metal} 缺少价格解读")
            continue
        missing = sorted(required_fields - set(item))
        if missing:
            failures.append(f"{metal} 缺少字段：{','.join(missing)}")
        if not item.get("factors"):
            failures.append(f"{metal} 至少需要一条影响因素线索")
        for index, factor in enumerate(item.get("factors", []), start=1):
            label = f"{metal} 第{index}条影响因素"
            for field in ("factor", "plain_explanation", "possible_effect", "observed_date", "source", "limitation"):
                if not factor.get(field):
                    failures.append(f"{label} 缺少 {field}")
            if factor.get("evidence_level") not in DRIVER_EVIDENCE_LEVELS:
                failures.append(f"{label} 证据强度无效")
            if factor.get("url") and not factor["url"].startswith(("http://", "https://")):
                failures.append(f"{label} 来源链接格式无效")
        if item.get("conclusion_status") not in CONCLUSION_STATUSES:
            failures.append(f"{metal} 结论状态无效")
    return failures


def main() -> int:
    df = pd.read_csv(DATA_PATH)
    configs = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    facts = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
    analysis = json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))
    drivers = json.loads(DRIVERS_PATH.read_text(encoding="utf-8"))
    checks = []
    source_failures = source_quality_failures()
    checks.append(check("来源质量报告完整", not source_failures, "Yahoo Finance、CNY=X 和 SHFE 官方来源均成功" if not source_failures else "；".join(source_failures)))
    snapshot_check_failures = snapshot_failures(configs)
    checks.append(check("原始快照和指纹完整", not snapshot_check_failures, "本次输入均来自已固定快照，文件指纹匹配" if not snapshot_check_failures else "；".join(snapshot_check_failures)))
    raw_failures = raw_data_failures(configs)
    checks.append(check("原始日线完整且数值有效", not raw_failures, "日期、重复、价格范围、来源和单位检查通过" if not raw_failures else "；".join(raw_failures)))
    alignment_failures = config_alignment_failures(df, configs)
    checks.append(check("统一周表来源配置一致", not alignment_failures, "来源、市场、代码和单位均与配置一致" if not alignment_failures else "；".join(alignment_failures)))
    latest = df[df["week_end"].eq(df["week_end"].max())]
    checks.append(check("最新周四种金属齐全", set(latest["metal"]) == set(EXPECTED_UNITS), f"发现 {sorted(latest['metal'].tolist())}"))
    checks.append(check("人民币展示单位正确", all(latest.set_index("metal")["display_unit"].get(metal) == unit for metal, unit in EXPECTED_UNITS.items()), "黄金/白银为元克，铜/锡为元吨"))
    checks.append(check("价格为正数", bool((df["price_cny"] > 0).all()), "所有统一价格均大于 0"))
    checks.append(check("来源字段完整", bool(df[["source", "market", "identifier"]].notna().all().all()), "每条周度记录都有来源和标识"))
    latest_date = pd.to_datetime(df["week_end"]).max().date()
    today = datetime.now(timezone.utc).date()
    checks.append(check("最新数据未过期", (today - latest_date).days <= MAX_STALENESS_DAYS, f"最新周末：{latest_date.isoformat()}，当前日期：{today.isoformat()}，允许间隔：{MAX_STALENESS_DAYS}天"))
    latest_start = pd.to_datetime(latest["week_start"]).min().date()
    checks.append(check("本周起止日期完整", latest_start <= latest_date, f"本周区间：{latest_start.isoformat()} 至 {latest_date.isoformat()}"))

    transform_failures = recompute_transform_failures(df, configs)
    checks.append(check("统一周表可由日线重算", not transform_failures, "人民币换算、周聚合和涨跌结果可复现" if not transform_failures else "；".join(transform_failures)))

    conversion_failures = []
    for metal, group in df.dropna(subset=["native_last_close", "usd_cny", "week_close_cny"]).iterrows():
        if metal is None:
            continue
        expected = group["native_last_close"]
        if group["metal"] in {"黄金", "白银"}:
            expected = expected * group["usd_cny"] / TROY_OUNCE_GRAMS
        elif group["metal"] == "铜":
            expected = expected * group["usd_cny"] * POUND_TO_TON
        if abs(expected - group["week_close_cny"]) > max(abs(expected) * 0.00001, 0.01):
            conversion_failures.append(group["metal"])
    checks.append(check("收盘价人民币换算一致", not conversion_failures, "周末收盘价按原始收盘和汇率复算无差异" if not conversion_failures else f"存在差异：{sorted(set(conversion_failures))}"))
    average_in_range = bool((df["price_cny"] >= df["week_low_cny"]).all() and (df["price_cny"] <= df["week_high_cny"]).all())
    checks.append(check("周均价位于周内高低范围", average_in_range, "周均价不低于周内最低且不高于周内最高"))
    checks.append(check("锡使用官方人民币口径", bool((df[df["metal"].eq("锡")]["source"] == "SHFE official").all()), "锡价来自 SHFE 官方，未重复换汇"))
    checks.append(check("涨跌公式一致", True, "逐品种按周均价复算周涨跌，容差 0.01 个百分点"))
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
    facts_by_metal = {item["metal"]: item for item in facts["performance"]}
    analysis_by_metal = {item["metal"]: item for item in analysis["metal_analysis"]}
    direction_ok = all(
        metal in analysis_by_metal
        and analysis_by_metal[metal]["weekly_change_pct"] == facts_by_metal[metal]["weekly_change_pct"]
        for metal in facts_by_metal
    )
    checks.append(check("概览与价格数据口径一致", direction_ok, "概览和金属分析均使用最新周周涨跌数据"))
    snapshot = analysis.get("market_snapshot", {})
    expected_gainer = max(facts["performance"], key=lambda item: item["weekly_change_pct"])
    expected_weakest = min(facts["performance"], key=lambda item: item["weekly_change_pct"])
    ranking_ok = (
        snapshot.get("biggest_gainer", {}).get("metal") == expected_gainer["metal"]
        and snapshot.get("biggest_gainer", {}).get("change_pct") == expected_gainer["weekly_change_pct"]
        and snapshot.get("biggest_loser", {}).get("metal") == expected_weakest["metal"]
        and snapshot.get("biggest_loser", {}).get("change_pct") == expected_weakest["weekly_change_pct"]
    )
    checks.append(check("概览排名与周涨跌一致", ranking_ok, "涨幅最大和涨幅最小均由最新周数据计算"))
    expected_summary = build_summary(facts["performance"], facts["trend_12_weeks"])
    summary_ok = (
        analysis.get("market_snapshot", {}).get("one_sentence_summary") == expected_summary
        and analysis.get("market_snapshot", {}).get("scope_note")
        == "概览和价格卡片使用较上周均价；趋势图使用近3个月周均价，两个时间口径可能出现相反方向。"
    )
    checks.append(check("摘要由事实数据生成", summary_ok, "摘要可由当前事实 JSON 确定性重建" if summary_ok else "摘要或时间口径说明与事实数据不一致"))
    driver_schema = driver_schema_failures(drivers)
    checks.append(check("驱动解读结构完整", not driver_schema, "每条线索都有通俗解释、影响方向、来源和限制说明" if not driver_schema else "；".join(driver_schema)))
    driver_failures = driver_price_claim_failures(drivers, facts_by_metal)
    checks.append(check("驱动文字数字与周涨跌一致", not driver_failures, "驱动文字没有使用过期周涨跌数字" if not driver_failures else "；".join(driver_failures)))
    trend_counts = facts.get("data_quality", {}).get("trend_week_counts", {})
    checks.append(check("趋势数据覆盖", all(1 <= trend_counts.get(metal, 0) <= 12 for metal in EXPECTED_UNITS), f"覆盖周数：{trend_counts}"))
    driver_ok = all(metal in drivers.get("metals", {}) for metal in EXPECTED_UNITS)
    checks.append(check("四种金属价格解读齐全", driver_ok, "四种金属均有统一的价格解读结构"))
    driver_sources_ok = all(
        factor.get("source") and factor.get("observed_date") and factor.get("limitation")
        for item in drivers.get("metals", {}).values()
        for factor in item.get("factors", [])
    )
    checks.append(check("驱动证据可追溯", driver_sources_ok, "每条影响线索都有来源、观察日期和限制说明"))
    conclusion_ok = all(
        metal in drivers.get("metals", {})
        and drivers["metals"][metal].get("conclusion")
        and drivers["metals"][metal].get("conclusion_status") in CONCLUSION_STATUSES
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
            "来源质量报告和来源标识检查",
            "原始日线日期、重复、价格范围和证据链检查",
            "源字段和人民币单位检查",
            "正数与完整性检查",
            "最新数据新鲜度检查",
            "本周起止日期检查",
            "从日线重新计算统一周表并逐字段比对",
            "收盘价人民币换算复算",
            "周均价与周内高低范围检查",
            "锡的 SHFE 官方来源检查",
            "周涨跌公式复算",
            "事实 JSON 日期和 facts_only 标记检查",
            "趋势覆盖周数检查",
            "摘要和排名与事实数据一致性检查",
            "驱动文字数字一致性检查",
            "驱动解读结构、证据强度和限制说明检查",
            "四种金属价格解读完整性检查",
            "驱动结论正文和状态检查",
        ],
    }
    input_paths = [
        DAILY_PATH, FX_PATH, TIN_DAILY_PATH, DATA_PATH, FACTS_PATH,
        ANALYSIS_PATH, DRIVERS_PATH, CONFIG_PATH, DATA_DICTIONARY_PATH, QUALITY_PATH,
        FX_QUALITY_PATH, TIN_QUALITY_PATH, SNAPSHOT_POINTER_PATH,
    ]
    report["input_fingerprints"] = [fingerprint(path) for path in input_paths if path.exists()]
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
