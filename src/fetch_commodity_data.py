"""
采集金银铜锡大宗商品价格数据。

从世界银行 Commodity Markets Pink Sheet 月度 Excel 文件中提取
黄金、白银、铜、锡的月度价格（原始美元价格）。
"""

import sys
from pathlib import Path

import pandas as pd
import requests

# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

# 世界银行 Pink Sheet 月度历史数据（Excel）
# 可从环境变量 PINK_SHEET_URL 覆盖，或手动放入 data/raw/pink_sheet_monthly.xlsx
PINK_SHEET_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)

# 目标金属：{Excel 中精确字段名: (中文名, 英文名, 单位)}
TARGET_METALS = {
    "Gold":   ("黄金", "gold",   "美元/盎司"),
    "Silver": ("白银", "silver", "美元/盎司"),
    "Copper": ("铜",   "copper", "美元/吨"),
    "Tin":    ("锡",   "tin",    "美元/吨"),
}

# 项目根目录
ROOT_DIR = Path(__file__).resolve().parent.parent

# Pink Sheet 中存放月度价格的 sheet 名称
SHEET_NAME = "Monthly Prices"


# ═══════════════════════════════════════════════════════════════
# 下载
# ═══════════════════════════════════════════════════════════════

def download_pink_sheet(url=None, cache_path=None):
    """下载 Pink Sheet Excel 文件，优先使用本地缓存（24 小时内有效）。"""
    if url is None:
        url = PINK_SHEET_URL

    if cache_path is None:
        cache_path = ROOT_DIR / "data" / "raw" / "pink_sheet_monthly.xlsx"
    else:
        cache_path = Path(cache_path)

    # 缓存有效则直接返回
    if cache_path.exists():
        import time
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < 24:
            print(f"[INFO] 使用本地缓存 ({age_hours:.1f} 小时前): {cache_path}")
            return str(cache_path)
        else:
            print(f"[INFO] 缓存已过期 ({age_hours:.1f} 小时前)，重新下载...")

    print(f"[INFO] 正在下载 Pink Sheet ...")
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        if cache_path.exists():
            print(f"[WARN] 下载失败，回退到本地缓存: {e}")
            return str(cache_path)
        else:
            print(f"[ERROR] 下载失败且无本地缓存: {e}")
            sys.exit(1)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(resp.content)
    print(f"[INFO] 已保存至: {cache_path}  ({len(resp.content):,} bytes)")
    return str(cache_path)


# ═══════════════════════════════════════════════════════════════
# 解析
# ═══════════════════════════════════════════════════════════════

def _get_header_row(filepath, sheet_name):
    """读取表头行（第 4 行，0-indexed），返回字段名列表。"""
    raw = pd.read_excel(filepath, sheet_name=sheet_name, header=None, nrows=6)
    return raw.iloc[4].tolist()


def _find_target_columns(header_names):
    """在表头中精确匹配目标金属字段，返回 {metal_excel_name: col_index}。"""
    col_map = {}
    for metal_name in TARGET_METALS:
        found = False
        for idx, name in enumerate(header_names):
            # 精确字符串匹配（strip 掉首尾空格）
            if isinstance(name, str) and name.strip() == metal_name:
                col_map[metal_name] = idx
                print(f"[INFO] 找到 {metal_name} → 列 {idx}")
                found = True
                break
        if not found:
            print(f"[ERROR] 未在 Pink Sheet 中找到字段: '{metal_name}'")
    return col_map


def _print_available_columns(header_names):
    """打印 Excel 中所有可用字段，方便调试。"""
    print("\n[INFO] Pink Sheet 中可用的字段：")
    for idx, name in enumerate(header_names):
        if pd.notna(name):
            print(f"  列 {idx:>3d}: [{name}]")


def parse_metal_prices(filepath):
    """
    从 Pink Sheet Excel 中提取四种金属的月度价格。

    参数
    ----
    filepath : str
        Pink Sheet .xlsx 文件路径。

    返回
    ----
    pd.DataFrame
        字段：month, metal_cn, metal_en, price_usd, unit_usd
    """
    # 检查 sheet 是否存在
    xl = pd.ExcelFile(filepath)
    if SHEET_NAME not in xl.sheet_names:
        print(f"[ERROR] 未找到 sheet '{SHEET_NAME}'，可用 sheets: {xl.sheet_names}")
        sys.exit(1)

    # 读取表头并定位目标列
    header_names = _get_header_row(filepath, SHEET_NAME)
    col_map = _find_target_columns(header_names)

    if len(col_map) < len(TARGET_METALS):
        _print_available_columns(header_names)
        sys.exit(1)

    # 读取全部数据（跳过前 6 行元数据）
    df = pd.read_excel(filepath, sheet_name=SHEET_NAME, header=None, skiprows=6)

    # ── 筛选有效月份行 ──
    month_col = 0
    month_raw = df.iloc[:, month_col].astype(str)
    valid_mask = month_raw.str.match(r'^\d{4}M\d{2}$')
    df = df[valid_mask].copy()

    # 转换月份格式: 2025M01 → 2025-01
    df['month'] = df.iloc[:, month_col].apply(
        lambda v: f"{str(v)[:4]}-{str(v)[5:7]}"
    )

    # ── 提取四种金属，从宽表转长表 ──
    records = []
    for metal_excel_name, (metal_cn, metal_en, unit_cn) in TARGET_METALS.items():
        col_idx = col_map[metal_excel_name]
        for _, row in df.iterrows():
            raw_val = row.iloc[col_idx]
            if pd.isna(raw_val):
                continue
            try:
                price = float(raw_val)
            except (ValueError, TypeError):
                continue
            if price <= 0:
                continue
            records.append({
                'month':      row['month'],
                'metal_cn':   metal_cn,
                'metal_en':   metal_en,
                'price_usd':  price,
                'unit_usd':   unit_cn,
            })

    result = pd.DataFrame(records)
    result = result.sort_values(['metal_en', 'month']).reset_index(drop=True)

    # ── 摘要 ──
    print(f"[INFO] 共提取 {len(result)} 条价格记录")
    for metal_en in ['gold', 'silver', 'copper', 'tin']:
        sub = result[result['metal_en'] == metal_en]
        if len(sub) > 0:
            print(f"  {metal_en:>6s}: {sub['month'].min()} ~ {sub['month'].max()}, "
                  f"{len(sub)} 行, "
                  f"最新 {sub['price_usd'].iloc[-1]:,.2f} {sub['unit_usd'].iloc[0]}")

    return result


# ═══════════════════════════════════════════════════════════════
# 输出
# ═══════════════════════════════════════════════════════════════

def save_to_csv(df, output_path=None):
    """将价格数据保存为标准化 CSV。"""
    if output_path is None:
        output_path = ROOT_DIR / "data" / "processed" / "commodity_prices_usd.csv"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding='utf-8')
    print(f"[INFO] CSV 已保存: {output_path}")
    return str(output_path)


# ═══════════════════════════════════════════════════════════════
# 主入口（测试用）
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Metal Price Report — 阶段 1: 采集 Pink Sheet 数据")
    print("=" * 60)

    # 1. 下载（如本地已有有效缓存则跳过）
    xlsx_path = download_pink_sheet()

    # 2. 解析
    prices_df = parse_metal_prices(xlsx_path)

    # 3. 保存
    csv_path = save_to_csv(prices_df)

    # 4. 预览
    print(f"\n[预览] 前 8 行:")
    print(prices_df.head(8).to_string(index=False))
    print(f"\n[预览] 末尾 5 行:")
    print(prices_df.tail(5).to_string(index=False))

    print(f"\n[DONE] 输出文件: {csv_path}")
