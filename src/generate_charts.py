"""
图表生成模块。

使用 matplotlib 生成价格走势图（累计涨跌幅）和月度涨跌幅对比图。
输出到 public/charts/。
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_ANALYSIS = ROOT_DIR / "data" / "processed" / "monthly_analysis.csv"
DEFAULT_CHARTS_DIR = ROOT_DIR / "public" / "charts"

# 金属颜色（金色、银色、铜色、锡灰）
METAL_COLORS = {
    "黄金": "#D4A017",
    "白银": "#6B7280",
    "铜":   "#C2410C",
    "锡":   "#2563EB",
}

# 涨跌色
UP_COLOR   = "#E53E3E"   # 红色
DOWN_COLOR = "#38A169"   # 绿色

# ── 中文字体设置（兼容 macOS 和 Ubuntu） ──
CJK_FONT_CANDIDATES = [
    # macOS 字体
    "Lantinghei SC",
    "Heiti TC",
    "PingFang HK",
    "STHeiti",
    # Ubuntu / Linux 字体
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "Noto Sans CJK SC",
    "Noto Sans CJK",
    "Noto Sans SC",
    "DejaVu Sans",
]
_font_found = False
for font_name in CJK_FONT_CANDIDATES:
    try:
        matplotlib.font_manager.findfont(font_name, fallback_to_default=False)
        plt.rcParams["font.family"] = font_name
        _font_found = True
        break
    except Exception:
        continue

if not _font_found:
    # 最后兜底：不指定字体，让 matplotlib 用默认字体 + 删除字体缓存
    print("[WARN] 未找到中文字体，图表中文可能显示为方框。")
    print("[WARN] 请安装中文字体：sudo apt install fonts-wqy-zenhei")

plt.rcParams["axes.unicode_minus"] = False


# ═══════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════

def _load_trend_data(analysis_path, target_month, n_months=12):
    """加载四种金属最近 n 个月的价格数据，计算累计涨跌幅（以第1个月为100）。"""
    df = pd.read_csv(analysis_path)

    # 取最近 n 个月的完整数据
    all_months = sorted(df["month"].unique())
    if target_month not in all_months:
        # 用最新月份
        target_month = all_months[-1]

    idx = all_months.index(target_month)
    start_idx = max(0, idx - n_months + 1)
    window_months = all_months[start_idx:idx + 1]

    trend = {}
    for metal_en, metal_cn in [("gold", "黄金"), ("silver", "白银"),
                                 ("copper", "铜"), ("tin", "锡")]:
        sub = df[df["metal_en"] == metal_en].copy()
        sub = sub[sub["month"].isin(window_months)].sort_values("month")

        if len(sub) < 2:
            continue

        base = sub["price_cny"].iloc[0]
        if base == 0:
            continue

        rebased = sub["price_cny"].values / base * 100
        trend[metal_cn] = {
            "months":  sub["month"].tolist(),
            "rebased": rebased.tolist(),
            "labels":  [m[2:].replace("-", "/") for m in sub["month"]],  # 25/06
        }

    return trend


def _load_bar_data(analysis_path, target_month):
    """加载四种金属在目标月份的环比涨跌幅。"""
    df = pd.read_csv(analysis_path)
    latest = df[df["month"] == target_month]

    bar_data = {}
    for _, row in latest.iterrows():
        bar_data[row["metal_cn"]] = row["change_1m"]
    return bar_data


# ═══════════════════════════════════════════════════════════════
# 图表 1：近一年累计涨跌幅走势
# ═══════════════════════════════════════════════════════════════

def generate_trend_chart(analysis_path, output_path, target_month=None):
    """生成近一年价格累计涨跌幅走势图。"""
    analysis_path = Path(analysis_path)
    if target_month is None:
        df = pd.read_csv(analysis_path)
        target_month = df["month"].max()

    trend = _load_trend_data(analysis_path, target_month, n_months=12)

    if not trend:
        print("[WARN] 没有足够数据生成走势图")
        return None

    fig, ax = plt.subplots(figsize=(10, 5))

    for metal_cn, data in trend.items():
        color = METAL_COLORS.get(metal_cn, "#333333")
        ax.plot(
            data["labels"], data["rebased"],
            color=color, linewidth=2.8, marker="o", markersize=5,
            label=metal_cn,
        )

    # 基线 100
    ax.axhline(y=100, color="#999999", linewidth=0.8, linestyle="--", alpha=0.6)

    ax.set_title("近一年价格累计涨跌幅走势", fontsize=16, fontweight="bold", pad=15)
    ax.set_ylabel("累计涨跌幅（基准=100）", fontsize=11)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12),
              fontsize=11, framealpha=0.8, ncol=4)

    # Y轴格式 — 直接标数值如 100, 120, 140
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f"))

    # 网格
    ax.grid(True, axis="y", alpha=0.3, linewidth=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # 旋转 X 轴标签
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=9)

    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    print(f"[INFO] 走势图已保存: {output_path}")
    return str(output_path)


# ═══════════════════════════════════════════════════════════════
# 图表 2：本月涨跌幅对比（横向柱状图）
# ═══════════════════════════════════════════════════════════════

def generate_monthly_change_chart(analysis_path, output_path, target_month=None):
    """生成本月涨跌幅对比横向柱状图。"""
    analysis_path = Path(analysis_path)
    if target_month is None:
        df = pd.read_csv(analysis_path)
        target_month = df["month"].max()

    bar_data = _load_bar_data(analysis_path, target_month)

    if not bar_data:
        print("[WARN] 没有足够数据生成本月涨跌幅图")
        return None

    metal_order = ["黄金", "白银", "铜", "锡"]
    values = [bar_data.get(m) for m in metal_order]
    colors = [UP_COLOR if v is not None and v >= 0 else DOWN_COLOR
              for v in values]

    fig, ax = plt.subplots(figsize=(8, 4.5))

    y_pos = np.arange(len(metal_order))
    bars = ax.barh(y_pos, values, height=0.5, color=colors, edgecolor="white", linewidth=0.5)

    # 在柱上标注数值
    for i, (v, c) in enumerate(zip(values, colors)):
        if v is None:
            continue
        sign = "+" if v >= 0 else ""
        ax.text(
            v + (0.4 if v >= 0 else -0.4), i,
            f"{sign}{v:.2f}%",
            va="center",
            ha="left" if v >= 0 else "right",
            fontsize=12,
            fontweight="bold",
            color=c,
        )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(metal_order, fontsize=13)
    ax.axvline(x=0, color="#666666", linewidth=1)
    ax.set_title("本月涨跌幅对比", fontsize=16, fontweight="bold", pad=15)

    # 确保 0 在中间 —— 计算对称范围
    max_abs = max(abs(v) for v in values if v is not None)
    limit = max(max_abs * 1.3, 2)
    ax.set_xlim(-limit, limit)

    ax.grid(True, axis="x", alpha=0.3, linewidth=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)

    fig.tight_layout()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    print(f"[INFO] 涨跌幅图已保存: {output_path}")
    return str(output_path)


# ═══════════════════════════════════════════════════════════════
# 批量生成
# ═══════════════════════════════════════════════════════════════

def generate_all(analysis_path=None, charts_dir=None, target_month=None):
    """生成全部图表，返回 (trend_path, bar_path)。"""
    analysis_path = Path(analysis_path) if analysis_path else DEFAULT_ANALYSIS
    charts_dir = Path(charts_dir) if charts_dir else DEFAULT_CHARTS_DIR

    if target_month is None:
        df = pd.read_csv(analysis_path)
        target_month = df["month"].max()

    month_str = target_month

    trend_path = generate_trend_chart(
        analysis_path,
        charts_dir / f"trend-{month_str}.png",
        target_month,
    )
    bar_path = generate_monthly_change_chart(
        analysis_path,
        charts_dir / f"monthly-change-{month_str}.png",
        target_month,
    )
    return trend_path, bar_path


# ═══════════════════════════════════════════════════════════════
# 测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Metal Price Report — 阶段 5a: 生成图表")
    print("=" * 60)

    t, b = generate_all()
    print(f"\n[DONE] 图表已生成:")
    if t:
        print(f"  走势图: {t}")
    if b:
        print(f"  涨跌幅图: {b}")
