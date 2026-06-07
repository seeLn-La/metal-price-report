"""
数据自动复核模块。

读取 data/processed/monthly_analysis.csv，执行自动复核规则，
生成 data/processed/validation_result.json。

复核规则：
  1. 完整性检查：四种金属齐全 + 必要字段齐全
  2. 价格合理范围检查：各金属价格在合理区间内
  3. 涨跌幅异常检测：分"需关注"和"异常"两级
  4. 涨跌方向一致性：价格涨跌与涨跌幅符号一致
"""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_INPUT = ROOT_DIR / "data" / "processed" / "monthly_analysis.csv"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "processed" / "validation_result.json"

EXPECTED_METALS_CN = ["黄金", "白银", "铜", "锡"]
REQUIRED_FIELDS = ["price_cny", "change_1m", "change_3m", "change_6m", "change_12m"]

# 价格合理范围（单位：元/克 或 元/吨）
PRICE_RANGES = {
    "黄金": (300, 1200),
    "白银": (3, 20),
    "铜":   (30000, 120000),
    "锡":   (100000, 500000),
}

# 涨跌幅异常阈值
ATTENTION_THRESHOLDS = {
    "change_1m":  30,    # |比上月| > 30% → 需关注
    "change_3m":  60,    # |近三个月| > 60% → 需关注
    "change_6m":  80,    # |近半年| > 80% → 需关注
    "change_12m": 120,   # |近一年| > 120% → 需关注
}

ERROR_THRESHOLDS = {
    "change_1m":  60,    # |比上月| > 60% → 异常
    "change_12m": 200,   # |近一年| > 200% → 异常
}


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _metal_emoji(metal_cn):
    """返回金属对应的 emoji。"""
    mapping = {"黄金": "🥇", "白银": "🥈", "铜": "🟠", "锡": "🛢️"}
    return mapping.get(metal_cn, "⚙️")


def _fmt_pct(val):
    """将数值格式化为百分比字符串。"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "-"
    return f"{val:+.2f}%"


def _get_offset_price(metal_df, current_month, offset):
    """获取 current_month 往前 offset 个月的价格。"""
    months = metal_df["month"].tolist()
    if current_month not in months:
        return None
    idx = months.index(current_month)
    target = idx - offset
    if target < 0:
        return None
    return metal_df.iloc[target]["price_cny"]


# ═══════════════════════════════════════════════════════════════
# 校验入口
# ═══════════════════════════════════════════════════════════════

def validate(input_path=None, output_path=None):
    """
    执行自动复核，生成 validation_result.json。

    返回
    ----
    dict
        校验结果字典。
    """
    input_path = Path(input_path) if input_path else DEFAULT_INPUT
    output_path = Path(output_path) if output_path else DEFAULT_OUTPUT

    if not input_path.exists():
        result = {
            "status": "error",
            "status_text": "异常",
            "level": "error",
            "summary": f"数据文件不存在：{input_path}",
            "checks": [
                {"name": "数据文件", "result": "未通过", "message": f"找不到 {input_path}"}
            ],
        }
        _write_json(result, output_path)
        print(f"[ERROR] 数据文件不存在: {input_path}")
        sys.exit(1)

    try:
        df = pd.read_csv(input_path)
    except Exception as e:
        result = {
            "status": "error",
            "status_text": "异常",
            "level": "error",
            "summary": f"无法读取 CSV：{e}",
            "checks": [
                {"name": "数据读取", "result": "未通过", "message": str(e)}
            ],
        }
        _write_json(result, output_path)
        sys.exit(1)

    print("=" * 60)
    print("Metal Price Report — 自动复核")
    print("=" * 60)
    print(f"[INFO] 读入 {len(df)} 条记录 ({input_path.name})")

    checks = []
    has_error = False
    has_attention = False

    # ── 确定最新月份 ──
    latest_month = df["month"].max()
    latest_df = df[df["month"] == latest_month]
    print(f"[INFO] 最新月份: {latest_month}")

    # ── 检查 1: 完整性检查 ──
    check1_ok, check1_msg = _check_completeness(df, latest_df, latest_month)
    checks.append({
        "name": "完整性检查",
        "result": "通过" if check1_ok else "未通过",
        "message": check1_msg,
    })
    if not check1_ok:
        has_error = True
    print(f"  {'✅' if check1_ok else '❌'} 完整性检查: {check1_msg}")

    # ── 检查 2: 价格范围检查 ──
    check2_ok, check2_msg = _check_price_ranges(latest_df)
    checks.append({
        "name": "价格范围检查",
        "result": "通过" if check2_ok else "未通过",
        "message": check2_msg,
    })
    if not check2_ok:
        has_error = True
    print(f"  {'✅' if check2_ok else '❌'} 价格范围检查: {check2_msg}")

    # ── 检查 3: 涨跌幅异常检测 ──
    check3_ok, check3_msg, check3_attention = _check_change_anomalies(latest_df)
    checks.append({
        "name": "涨跌幅异常检测",
        "result": "需关注" if check3_attention else ("通过" if check3_ok else "未通过"),
        "message": check3_msg,
    })
    if not check3_ok:
        has_error = True
    if check3_attention:
        has_attention = True
    print(f"  {'⚠️' if check3_attention else ('✅' if check3_ok else '❌')} 涨跌幅异常检测: {check3_msg}")

    # ── 检查 4: 涨跌方向一致性 ──
    check4_ok, check4_msg = _check_direction_consistency(df, latest_month)
    checks.append({
        "name": "涨跌方向一致性检查",
        "result": "通过" if check4_ok else "未通过",
        "message": check4_msg,
    })
    if not check4_ok:
        has_error = True
    print(f"  {'✅' if check4_ok else '❌'} 涨跌方向一致性检查: {check4_msg}")

    # ── 汇总 ──
    if has_error:
        status = "error"
        status_text = "异常"
        level = "error"
        summary = "数据存在异常，请检查校验明细。"
    elif has_attention:
        status = "attention"
        status_text = "需关注"
        level = "warning"
        summary = "数据完整，但部分涨跌幅超过常规范围，建议关注。"
    else:
        status = "normal"
        status_text = "正常"
        level = "success"
        summary = "数据完整，单位换算和涨跌方向未发现明显异常。"

    result = {
        "status": status,
        "status_text": status_text,
        "level": level,
        "summary": summary,
        "checks": checks,
    }

    _write_json(result, output_path)

    # 控制台摘要
    total = len(checks)
    passed = sum(1 for c in checks if c["result"] == "通过")
    print(f"\n[结果] {passed}/{total} 项检查通过")
    print(f"[状态] {status_text}")

    return result


# ═══════════════════════════════════════════════════════════════
# 检查 1: 完整性检查
# ═══════════════════════════════════════════════════════════════

def _check_completeness(df, latest_df, latest_month):
    """检查四种金属是否齐全、必要字段是否完整。"""
    metals_found = set(latest_df["metal_cn"].unique()) if "metal_cn" in latest_df.columns else set()
    missing_metals = [m for m in EXPECTED_METALS_CN if m not in metals_found]

    if missing_metals:
        return False, f"最新月份（{latest_month}）缺少金属：{'、'.join(missing_metals)}"

    # 检查必要字段
    missing_fields = []
    for field in REQUIRED_FIELDS:
        if field not in df.columns:
            missing_fields.append(field)
            continue
        # 对最新月份的四种金属，检查字段是否为空
        for metal in EXPECTED_METALS_CN:
            row = latest_df[latest_df["metal_cn"] == metal]
            if len(row) == 0:
                continue
            val = row.iloc[0][field]
            if pd.isna(val):
                missing_fields.append(f"{metal}的{field}")

    if missing_fields:
        return False, f"以下字段缺失或为空：{'、'.join(missing_fields)}"

    found_str = "、".join(sorted(metals_found))
    return True, f"四种金属（{found_str}）数据齐全，必要字段完整。"


# ═══════════════════════════════════════════════════════════════
# 检查 2: 价格范围检查
# ═══════════════════════════════════════════════════════════════

def _check_price_ranges(latest_df):
    """检查各金属价格是否在合理范围内。"""
    out_of_range = []

    for metal_cn, (low, high) in PRICE_RANGES.items():
        row = latest_df[latest_df["metal_cn"] == metal_cn]
        if len(row) == 0:
            continue
        price = row.iloc[0]["price_cny"]
        if pd.isna(price):
            out_of_range.append(f"{metal_cn}价格缺失")
        elif price < low or price > high:
            out_of_range.append(
                f"{metal_cn}价格 {price:,.2f} 超出合理范围（{low:,}～{high:,}）"
            )

    if out_of_range:
        return False, "；".join(out_of_range)

    # 生成一句话汇总
    parts = []
    for metal_cn, (low, high) in PRICE_RANGES.items():
        row = latest_df[latest_df["metal_cn"] == metal_cn]
        if len(row) == 0:
            continue
        price = row.iloc[0]["price_cny"]
        parts.append(f"{metal_cn} {price:,.2f}")
    return True, "各金属价格均在合理范围内（" + "，".join(parts) + "）。"


# ═══════════════════════════════════════════════════════════════
# 检查 3: 涨跌幅异常检测
# ═══════════════════════════════════════════════════════════════

def _check_change_anomalies(latest_df):
    """
    检测最新月份各金属涨跌幅是否异常。

    两级阈值：
      - 需关注：超过 ATTENTION_THRESHOLDS
      - 异常：超过 ERROR_THRESHOLDS

    返回 (all_ok, message, has_attention)
    """
    errors = []
    attentions = []

    for _, row in latest_df.iterrows():
        metal_cn = row["metal_cn"]

        for field, threshold in ERROR_THRESHOLDS.items():
            val = row.get(field)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            if abs(val) > threshold:
                label = _field_label(field)
                errors.append(
                    f"{metal_cn}{label} {_fmt_pct(val)}，超过异常阈值 ±{threshold}%"
                )

        for field, threshold in ATTENTION_THRESHOLDS.items():
            val = row.get(field)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            if abs(val) > threshold:
                # 已经计入异常的不重复
                already_error = any(
                    metal_cn in e and _field_label(field) in e for e in errors
                )
                if not already_error:
                    label = _field_label(field)
                    attentions.append(
                        f"{metal_cn}{label} {_fmt_pct(val)}，超过关注阈值 ±{threshold}%"
                    )

    has_attention = len(attentions) > 0
    has_error = len(errors) > 0

    if has_error:
        return False, "；".join(errors), has_attention
    elif has_attention:
        return True, "；".join(attentions), True
    else:
        return True, "各金属涨跌幅均在常规范围内，未发现异常波动。", False


def _field_label(field):
    """返回字段的中文标签。"""
    mapping = {
        "change_1m":  "比上月",
        "change_3m":  "近三个月",
        "change_6m":  "近半年",
        "change_12m": "近一年",
    }
    return mapping.get(field, field)


# ═══════════════════════════════════════════════════════════════
# 检查 4: 涨跌方向一致性
# ═══════════════════════════════════════════════════════════════

def _check_direction_consistency(df, latest_month):
    """
    检查最新月份：价格涨跌方向与涨跌幅符号是否一致。

    规则：
      - 本月价格 > 对比月价格 → 涨跌幅必须为正
      - 本月价格 < 对比月价格 → 涨跌幅必须为负
      - 价格持平 → 涨跌幅应在 ±0.1% 以内

    检查四种周期：比上月(1)、近三个月(3)、近半年(6)、近一年(12)。
    """
    conflicts = []

    for metal_cn in EXPECTED_METALS_CN:
        metal_df = df[df["metal_cn"] == metal_cn].sort_values("month").reset_index(drop=True)
        if metal_df.empty or latest_month not in metal_df["month"].values:
            continue

        row = metal_df[metal_df["month"] == latest_month].iloc[0]

        checks_periods = [
            ("change_1m",  "比上月",   1),
            ("change_3m",  "近三个月", 3),
            ("change_6m",  "近半年",   6),
            ("change_12m", "近一年",   12),
        ]

        for field, label, offset in checks_periods:
            change_val = row.get(field)
            if change_val is None or (isinstance(change_val, float) and pd.isna(change_val)):
                continue

            prev_price = _get_offset_price(metal_df, latest_month, offset)
            if prev_price is None:
                continue

            curr_price = row["price_cny"]

            # 价格持平 → 涨跌幅应在 ±0.1% 以内
            if abs(curr_price - prev_price) < 0.005:
                if abs(change_val) > 0.1:
                    conflicts.append(
                        f"{metal_cn}{label}：价格基本持平（{curr_price:,.2f} vs {prev_price:,.2f}），"
                        f"但涨跌幅为 {_fmt_pct(change_val)}"
                    )
            elif curr_price > prev_price and change_val < 0:
                conflicts.append(
                    f"{metal_cn}{label}：本月价格 {curr_price:,.2f} 高于对比月 {prev_price:,.2f}，"
                    f"但涨跌幅为负（{_fmt_pct(change_val)}）"
                )
            elif curr_price < prev_price and change_val > 0:
                conflicts.append(
                    f"{metal_cn}{label}：本月价格 {curr_price:,.2f} 低于对比月 {prev_price:,.2f}，"
                    f"但涨跌幅为正（{_fmt_pct(change_val)}）"
                )

    if conflicts:
        return False, "；".join(conflicts)
    else:
        return True, "四种金属各周期涨跌方向均与价格变动一致。"


# ═══════════════════════════════════════════════════════════════
# 输出
# ═══════════════════════════════════════════════════════════════

def _write_json(result, output_path):
    """写入 JSON 文件。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[INFO] 校验报告已保存: {output_path}")


# ═══════════════════════════════════════════════════════════════
# 测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    result = validate()
    print(f"\n[输出] 状态: {result['status_text']} ({result['status']})")
    print(f"[输出] 摘要: {result['summary']}")
