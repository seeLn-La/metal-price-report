"""
采集美元对人民币汇率数据。

阶段 2：从本地 data/exchange_rates.csv 读取月度平均汇率。
后续阶段将实现自动抓取实时汇率。
"""

from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_CSV = ROOT_DIR / "data" / "exchange_rates.csv"


def load_exchange_rates(csv_path=None):
    """
    从本地 CSV 读取 USD/CNY 月度平均汇率。

    参数
    ----
    csv_path : str or Path, optional
        CSV 文件路径，默认 data/exchange_rates.csv。
        CSV 要求包含字段：date, currency, rate_to_cny

    返回
    ----
    dict[str, float]
        { 'YYYY-MM': rate }  例: { '2025-06': 7.18 }
    """
    csv_path = Path(csv_path) if csv_path else DEFAULT_CSV

    if not csv_path.exists():
        raise FileNotFoundError(f"汇率文件不存在: {csv_path}")

    df = pd.read_csv(csv_path, comment="#")
    required_cols = {"date", "currency", "rate_to_cny"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"汇率 CSV 缺少必要字段: {missing}\n"
            f"  实际字段: {list(df.columns)}\n"
            f"  要求格式: date, currency, rate_to_cny"
        )

    # 解析月份
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if df["date"].isna().any():
        bad = df[df["date"].isna()]
        raise ValueError(
            f"汇率 CSV 中包含无法解析的日期:\n{bad.to_string()}"
        )
    df["month"] = df["date"].dt.strftime("%Y-%m")

    # 仅取美元
    usd = df[df["currency"].str.strip().str.upper() == "USD"]
    if len(usd) == 0:
        raise ValueError("汇率 CSV 中没有 USD 记录")

    # 同一月份有多条时取最后一条
    usd = usd.sort_values("date").drop_duplicates("month", keep="last")

    rates = {}
    for _, row in usd.iterrows():
        try:
            rate = float(row["rate_to_cny"])
        except (ValueError, TypeError):
            raise ValueError(
                f"汇率值无法转为数字: month={row['month']}, "
                f"rate_to_cny={row['rate_to_cny']}"
            )
        if rate <= 0:
            raise ValueError(
                f"汇率必须为正数: month={row['month']}, rate_to_cny={rate}"
            )
        rates[row["month"]] = rate

    print(
        f"[INFO] 从 {csv_path.name} 加载 {len(rates)} 个月份的 USD/CNY 汇率 "
        f"({min(rates.keys())} ~ {max(rates.keys())})"
    )
    return rates


# ═══════════════════════════════════════════════════════════════
# 测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Metal Price Report — 阶段 2a: 加载汇率数据")
    print("=" * 60)

    rates = load_exchange_rates()
    print(f"\n[预览] 共 {len(rates)} 个月份")
    print(f"  最新 5 条:")
    for m in sorted(rates.keys())[-5:]:
        print(f"    {m}: {rates[m]}")
