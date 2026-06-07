"""
单位转换模块。

将国际市场价格（美元/盎司、美元/吨）转换为人民币计价单位（元/克、元/吨）。
"""

import sys
from pathlib import Path

import pandas as pd

from fetch_exchange_rate import load_exchange_rates

ROOT_DIR = Path(__file__).resolve().parent.parent

# 金衡盎司 → 克
TROY_OZ_TO_GRAM = 31.1035

# 需要从「美元/盎司」转为「元/克」的金属
OZ_METALS = {"gold", "silver"}

# 输入 / 输出路径
DEFAULT_INPUT = ROOT_DIR / "data" / "processed" / "commodity_prices_usd.csv"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "processed" / "commodity_prices_cny.csv"


# ═══════════════════════════════════════════════════════════════
# 原子转换函数
# ═══════════════════════════════════════════════════════════════

def usd_per_ounce_to_cny_per_gram(price_usd_oz, exchange_rate):
    """
    美元/盎司 → 元/克。

    公式：price_usd_oz × exchange_rate ÷ 31.1035
    """
    if not isinstance(price_usd_oz, (int, float)) or price_usd_oz <= 0:
        raise ValueError(
            f"美元价格必须为正数，收到: {price_usd_oz}"
        )
    if not isinstance(exchange_rate, (int, float)) or exchange_rate <= 0:
        raise ValueError(
            f"汇率必须为正数，收到: {exchange_rate}"
        )
    return price_usd_oz * exchange_rate / TROY_OZ_TO_GRAM


def usd_per_ton_to_cny_per_ton(price_usd_ton, exchange_rate):
    """
    美元/吨 → 元/吨。

    公式：price_usd_ton × exchange_rate
    """
    if not isinstance(price_usd_ton, (int, float)) or price_usd_ton <= 0:
        raise ValueError(
            f"美元价格必须为正数，收到: {price_usd_ton}"
        )
    if not isinstance(exchange_rate, (int, float)) or exchange_rate <= 0:
        raise ValueError(
            f"汇率必须为正数，收到: {exchange_rate}"
        )
    return price_usd_ton * exchange_rate


# ═══════════════════════════════════════════════════════════════
# 批量转换
# ═══════════════════════════════════════════════════════════════

def transform(input_path=None, rates=None, output_path=None):
    """
    读取 USD 价格数据，按当月汇率转换为人民币价格，输出 CSV。

    参数
    ----
    input_path : str or Path, optional
        输入 CSV（commodity_prices_usd.csv）。
    rates : dict[str, float], optional
        {'YYYY-MM': usd_cny_rate}，若为 None 则从 exchange_rates.csv 加载。
    output_path : str or Path, optional
        输出 CSV 路径。

    返回
    ----
    pd.DataFrame
        含 CNY 价格的完整 DataFrame。
    """
    input_path = Path(input_path) if input_path else DEFAULT_INPUT
    output_path = Path(output_path) if output_path else DEFAULT_OUTPUT

    # ── 1. 读取 USD 价格 ──
    if not input_path.exists():
        raise FileNotFoundError(f"USD 价格文件不存在: {input_path}")

    df = pd.read_csv(input_path)
    required_cols = {"month", "metal_en", "price_usd", "unit_usd"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"USD 价格 CSV 缺少必要字段: {missing}\n"
            f"  实际字段: {list(df.columns)}"
        )

    print(f"[INFO] 读入 {len(df)} 条 USD 价格记录 ({input_path.name})")

    # ── 2. 加载汇率 ──
    if rates is None:
        rates = load_exchange_rates()

    # ── 3. 逐行换算 ──
    cny_prices = []
    missing_months = set()
    errors = []

    for _, row in df.iterrows():
        month = row["month"]
        metal = row["metal_en"]
        price_usd = row["price_usd"]

        # 校验汇率
        rate = rates.get(month)
        if rate is None:
            missing_months.add(month)
            continue

        # 执行换算
        try:
            if metal in OZ_METALS:
                price_cny = usd_per_ounce_to_cny_per_gram(price_usd, rate)
                unit_cny = "元/克"
            else:
                price_cny = usd_per_ton_to_cny_per_ton(price_usd, rate)
                unit_cny = "元/吨"
        except ValueError as e:
            errors.append(f"{month} {row['metal_cn']}: {e}")
            continue

        # 结果校验
        if not isinstance(price_cny, (int, float)) or price_cny <= 0:
            errors.append(
                f"{month} {row['metal_cn']}: "
                f"换算结果非正数 (price_usd={price_usd}, rate={rate}, "
                f"result={price_cny})"
            )
            continue
        if not isinstance(rate, (int, float)) or rate <= 0:
            errors.append(
                f"{month} {row['metal_cn']}: "
                f"汇率非正数 (rate={rate})"
            )
            continue

        cny_prices.append({
            "month":           month,
            "metal_cn":        row["metal_cn"],
            "metal_en":        metal,
            "price_usd":       price_usd,
            "unit_usd":        row["unit_usd"],
            "usd_cny_avg":     round(rate, 4),
            "price_cny":       round(price_cny, 2),
            "unit_cny":        unit_cny,
            "exchange_source": "本地 CSV (data/exchange_rates.csv)",
        })

    # ── 4. 错误检查 ──
    if missing_months:
        sorted_months = sorted(missing_months)
        print(
            f"\n[ERROR] 以下月份缺少 USD/CNY 汇率，无法换算："
        )
        for m in sorted_months:
            metals = df[df["month"] == m]["metal_cn"].unique()
            print(f"  {m}: 影响 {', '.join(metals)}")
        sys.exit(1)

    if errors:
        print(f"\n[ERROR] 换算过程中出现错误：")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    # ── 5. 输出 ──
    result = pd.DataFrame(cny_prices)
    result = result.sort_values(["metal_en", "month"]).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False, encoding="utf-8")

    # 摘要
    print(f"[INFO] 成功换算 {len(result)} 条记录")
    for metal_en in ["gold", "silver", "copper", "tin"]:
        sub = result[result["metal_en"] == metal_en]
        if len(sub) > 0:
            latest = sub.iloc[-1]
            print(
                f"  {latest['metal_cn']:>4s}: "
                f"${latest['price_usd']:>12,.2f} {latest['unit_usd']}  "
                f"× {latest['usd_cny_avg']}  →  "
                f"¥{latest['price_cny']:>12,.2f} {latest['unit_cny']}"
            )

    print(f"[INFO] 输出: {output_path}")
    return result


# ═══════════════════════════════════════════════════════════════
# 测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Metal Price Report — 阶段 2: USD → CNY 换算")
    print("=" * 60)

    cny_df = transform()

    print(f"\n[预览] 前 5 行:")
    print(cny_df.head(5).to_string(index=False))
    print(f"\n[预览] 末尾 5 行:")
    print(cny_df.tail(5).to_string(index=False))
