"""
数据分析模块。

对 CNY 价格数据计算环比变化、多期变化率，并生成状态标签和预警标记。
"""

import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_INPUT = ROOT_DIR / "data" / "processed" / "commodity_prices_cny.csv"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "processed" / "monthly_analysis.csv"

# 大幅波动阈值
LARGE_MOVE_THRESHOLD = 0.08   # > 8%
REVIEW_THRESHOLD = 0.15       # > 15%


# ═══════════════════════════════════════════════════════════════
# 变化率计算
# ═══════════════════════════════════════════════════════════════

def compute_change(current, previous):
    """计算变化率 = current / previous - 1。"""
    if pd.isna(current) or pd.isna(previous) or previous == 0:
        return None
    return round(current / previous - 1, 6)


# ═══════════════════════════════════════════════════════════════
# 状态标签
# ═══════════════════════════════════════════════════════════════

def _consecutive_direction(series, n=3):
    """检查最近 n 个月是否连续同向（全 > 0 或全 < 0）。"""
    recent = series.dropna()
    if len(recent) < n:
        return False, None
    deltas = recent.iloc[-n:]
    if (deltas > 0).all():
        return True, "up"
    elif (deltas < 0).all():
        return True, "down"
    return False, None


def determine_status_label(change_1m, recent_changes):
    """
    根据当前月变化和近期走势生成中文状态标签。

    优先级：
    1. 单月 ≥ 5%    → 上涨明显 / 下跌明显
    2. 连续3月同向  → 持续上涨 / 持续下跌
    3. 单月 1%~5%   → 温和上涨 / 小幅回落
    4. 单月 -1%~1%  → 变化不大
    """
    if change_1m is None:
        return "数据不足"

    is_consecutive, direction = _consecutive_direction(recent_changes, n=3)

    if change_1m >= 0.05:
        return "上涨明显"
    elif change_1m <= -0.05:
        return "下跌明显"
    elif is_consecutive and direction == "up":
        return "持续上涨"
    elif is_consecutive and direction == "down":
        return "持续下跌"
    elif 0.01 <= change_1m < 0.05:
        return "温和上涨"
    elif -0.05 < change_1m <= -0.01:
        return "小幅回落"
    else:
        return "变化不大"


# ═══════════════════════════════════════════════════════════════
# 主分析流程
# ═══════════════════════════════════════════════════════════════

def analyze(input_path=None, output_path=None):
    """
    读入 CNY 价格数据，计算多期变化率并输出分析 CSV。

    参数
    ----
    input_path : str or Path
        输入 CSV（commodity_prices_cny.csv）。
    output_path : str or Path
        输出 CSV 路径。

    返回
    ----
    pd.DataFrame
        包含所有分析字段的 DataFrame。
    """
    input_path = Path(input_path) if input_path else DEFAULT_INPUT
    output_path = Path(output_path) if output_path else DEFAULT_OUTPUT

    # ── 1. 读入 ──
    if not input_path.exists():
        raise FileNotFoundError(f"CNY 价格文件不存在: {input_path}")

    df = pd.read_csv(input_path)
    df = df.sort_values(["metal_en", "month"]).reset_index(drop=True)

    # 确保 month 是字符串格式 YYYY-MM
    df["month"] = df["month"].astype(str)

    required_cols = {"month", "metal_en", "metal_cn", "price_cny", "unit_cny"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"输入 CSV 缺少字段: {missing}")

    print(f"[INFO] 读入 {len(df)} 条 CNY 价格记录 ({input_path.name})")

    # ── 2. 为每种金属构建价格时间序列并计算变化率 ──
    results = []
    metals = sorted(df["metal_en"].unique())

    for metal_en in metals:
        sub = df[df["metal_en"] == metal_en].copy()
        sub = sub.sort_values("month").reset_index(drop=True)

        prices = sub["price_cny"].values
        months = sub["month"].values
        metal_cn_val = sub["metal_cn"].iloc[0]
        unit_cny_val = sub["unit_cny"].iloc[0]

        # 构建价格查找表（month → price）
        price_map = dict(zip(months, prices))

        for i, (month, price) in enumerate(zip(months, prices)):
            chg_1m = compute_change(
                price,
                price_map.get(_offset_month(month, -1))
            )
            chg_3m = compute_change(
                price,
                price_map.get(_offset_month(month, -3))
            )
            chg_6m = compute_change(
                price,
                price_map.get(_offset_month(month, -6))
            )
            chg_12m = compute_change(
                price,
                price_map.get(_offset_month(month, -12))
            )

            # 近期变化序列（用于状态标签中的连续判断）
            recent = sub.iloc[:i+1]
            recent_changes = pd.Series([
                compute_change(
                    recent.iloc[j]["price_cny"],
                    recent.iloc[j-1]["price_cny"]
                )
                for j in range(1, len(recent))
            ])

            status = determine_status_label(chg_1m, recent_changes)

            is_large = False
            needs_rv = False
            if chg_1m is not None:
                is_large = abs(chg_1m) > LARGE_MOVE_THRESHOLD
                needs_rv = abs(chg_1m) > REVIEW_THRESHOLD

            results.append({
                "month":           month,
                "metal_cn":        metal_cn_val,
                "metal_en":        metal_en,
                "price_cny":       price,
                "unit_cny":        unit_cny_val,
                "change_1m":       fmt_pct(chg_1m),
                "change_3m":       fmt_pct(chg_3m),
                "change_6m":       fmt_pct(chg_6m),
                "change_12m":      fmt_pct(chg_12m),
                "status_label":    status,
                "is_large_move":   is_large,
                "needs_review":    needs_rv,
            })

    # ── 3. 汇总 & 输出 ──
    result = pd.DataFrame(results)
    result = result.sort_values(["metal_en", "month"]).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False, encoding="utf-8")
    print(f"[INFO] 分析完成，输出: {output_path}")

    # 摘要
    large_count = result["is_large_move"].sum()
    review_count = result["needs_review"].sum()
    print(f"[INFO] 总计 {len(result)} 条分析记录")
    print(f"  is_large_move (|Δ|>8%):  {large_count} 条")
    print(f"  needs_review (|Δ|>15%): {review_count} 条")

    for metal_en in metals:
        sub = result[result["metal_en"] == metal_en]
        latest = sub.iloc[-1]
        chg1 = _pct_str(latest['change_1m'])
        chg3 = _pct_str(latest['change_3m'])
        chg12 = _pct_str(latest['change_12m'])
        print(
            f"  {latest['metal_cn']:>4s}: "
            f"Δ1m={chg1:>8s}  "
            f"Δ3m={chg3:>8s}  "
            f"Δ12m={chg12:>8s}  "
            f"状态: {latest['status_label']}"
        )

    return result


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _offset_month(month_str, delta):
    """返回 month_str (YYYY-MM) 偏移 delta 个月后的月份字符串。"""
    year, mon = month_str.split("-")
    total = int(year) * 12 + int(mon) - 1 + delta
    y, m = divmod(total, 12)
    return f"{y}-{m+1:02d}"


def fmt_pct(val):
    """将变化率转为百分比数值（如 3.21），None 则为 None。"""
    if val is None:
        return None
    return round(val * 100, 2)


def _pct_str(val):
    """将 fmt_pct 输出的数值转为显示字符串（如 +3.21%）。"""
    if val is None:
        return "     -"
    return f"{val:+.2f}%"


# ═══════════════════════════════════════════════════════════════
# 测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Metal Price Report — 阶段 3a: 数据分析")
    print("=" * 60)

    analysis_df = analyze()

    print(f"\n[预览] 末尾 8 行（各金属最新 2 月）:")
    for m in ["gold", "silver", "copper", "tin"]:
        sub = analysis_df[analysis_df["metal_en"] == m].tail(2)
        print(sub.to_string(index=False))
        print()
