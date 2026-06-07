"""
报告生成模块。

使用 Jinja2 模板渲染全中文 Markdown 月报和手机端 HTML 页面。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from generate_charts import generate_all as generate_all_charts

ROOT_DIR = Path(__file__).resolve().parent.parent

TEMPLATE_DIR = ROOT_DIR / "templates"
DEFAULT_ANALYSIS = ROOT_DIR / "data" / "processed" / "monthly_analysis.csv"
DEFAULT_VALIDATION = ROOT_DIR / "data" / "processed" / "validation_result.json"
DEFAULT_MD_DIR = ROOT_DIR / "reports"
DEFAULT_HTML_DIR = ROOT_DIR / "public" / "reports"
DEFAULT_CHARTS_DIR = ROOT_DIR / "public" / "charts"


# ═══════════════════════════════════════════════════════════════
# 数值格式化
# ═══════════════════════════════════════════════════════════════

def _fmt_price(val):
    """格式化价格为千分位字符串，保留两位小数。"""
    if val is None:
        return "-"
    return f"{val:,.2f}"


def _fmt_pct(val):
    """将百分比数值（如 4.57, -2.84, None）格式化为显示字符串。"""
    if val is None or pd.isna(val):
        return "-"
    return f"{val:+.2f}%"


def _parse_month(month_str):
    """将 'YYYY-MM' 解析为 (year_int, month_int)。"""
    y, m = month_str.split("-")
    return int(y), int(m)


# ═══════════════════════════════════════════════════════════════
# 小结生成（规则驱动，不使用 LLM）
# ═══════════════════════════════════════════════════════════════

def _build_summary(latest_data, precious_avg, industrial_avg):
    """根据数据特征生成 2-3 条中文小结。"""
    bullets = []

    metals_up = [r for r in latest_data if r["change_1m"] is not None and r["change_1m"] > 0]
    metals_down = [r for r in latest_data if r["change_1m"] is not None and r["change_1m"] < 0]
    large_moves = [r for r in latest_data if r.get("is_large_move")]

    if len(metals_up) >= 3:
        max_up = max(metals_up, key=lambda m: m["change_1m"])
        bullets.append(
            f"本月四种金属中有{len(metals_up)}种上涨，"
            f"其中{max_up['metal_cn']}涨幅最大，整体偏强运行。"
        )
    elif len(metals_down) >= 3:
        max_down = min(metals_down, key=lambda m: m["change_1m"])
        bullets.append(
            f"本月四种金属中有{len(metals_down)}种下跌，"
            f"其中{max_down['metal_cn']}跌幅最大，整体偏弱运行。"
        )
    else:
        bullets.append(
            f"本月四种金属涨跌互现，"
            f"{'、'.join(r['metal_cn'] for r in metals_up)}上涨，"
            f"{'、'.join(r['metal_cn'] for r in metals_down)}下跌。"
        )

    if precious_avg is not None and industrial_avg is not None:
        if industrial_avg > 0 and precious_avg > 0:
            bullets.append("贵金属和工业金属均上涨，整体行情偏暖。")
        elif industrial_avg < 0 and precious_avg < 0:
            bullets.append("贵金属和工业金属均下跌，市场情绪偏谨慎。")
        elif abs(industrial_avg - precious_avg) > 5:
            stronger = "工业金属" if industrial_avg > precious_avg else "贵金属"
            bullets.append(f"{stronger}表现明显强于另一方，走势出现分化。")

    if len(large_moves) > 0:
        names = "、".join(r["metal_cn"] for r in large_moves)
        bullets.append(f"{names}本月波动较大，需关注后续走势变化。")
    else:
        bullets.append("四种金属波动幅度均在正常范围内，未出现异常剧烈波动。")

    return bullets


def _build_comparison_sentence(precious_avg, industrial_avg):
    """生成贵金属/工业金属对比的一句话判断。"""
    if precious_avg is None or industrial_avg is None:
        return "数据不足以对比。"

    diff = abs(industrial_avg - precious_avg)
    if diff < 2:
        return "贵金属和工业金属本月走势基本同步。"
    elif industrial_avg > precious_avg:
        return "工业金属本月表现明显优于贵金属。"
    else:
        return "贵金属本月表现明显优于工业金属。"


def _build_overview_line(metals, top_gainer):
    """生成一句话总览。"""
    up_count = sum(1 for m in metals if m["chg_1m"] is not None and m["chg_1m"] > 0)
    down_count = sum(1 for m in metals if m["chg_1m"] is not None and m["chg_1m"] < 0)

    if up_count >= 3:
        return f"本月{up_count}种金属上涨，整体偏强，{top_gainer['metal_cn']}领涨。"
    elif down_count >= 3:
        return f"本月{down_count}种金属下跌，整体偏弱，需关注后续走势。"
    else:
        return "本月金属涨跌互现，行情分化明显。"


# ═══════════════════════════════════════════════════════════════
# 告警提取
# ═══════════════════════════════════════════════════════════════

def _extract_alerts(validation_path, report_month):
    """从校验报告的 checks 中提取未通过或需关注的事项。"""
    if not validation_path.exists():
        return []

    with open(validation_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    alerts = []
    for check in report.get("checks", []):
        result = check.get("result", "")
        if result in ("未通过", "需关注"):
            alerts.append(f"{check['name']}：{check['message']}")
    return alerts


def _extract_validation_status(validation_path):
    """读取校验报告状态（'正常' / '需关注' / '异常'）。"""
    if not validation_path.exists():
        return "未知"
    with open(validation_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    return report.get("status_text", report.get("status", "未知"))


# ═══════════════════════════════════════════════════════════════
# 数据准备（Markdown 用）
# ═══════════════════════════════════════════════════════════════

def _prepare_context(analysis_path, validation_path, target_month=None):
    """从分析数据中构建模板上下文（Markdown 和 HTML 通用部分）。"""
    df = pd.read_csv(analysis_path)

    if target_month is None:
        target_month = df["month"].max()

    latest = df[df["month"] == target_month].copy()

    if len(latest) == 0:
        print(f"[ERROR] 找不到月份: {target_month}")
        sys.exit(1)

    year, month_num = _parse_month(target_month)
    today = datetime.now().strftime("%Y年%m月%d日")

    # ── 四种金属数据 ──
    metals = []
    metal_order = ["黄金", "白银", "铜", "锡"]
    for name in metal_order:
        row = latest[latest["metal_cn"] == name]
        if len(row) == 0:
            print(f"[WARN] 缺少金属: {name}")
            continue
        r = row.iloc[0]
        metals.append({
            "metal_cn":       r["metal_cn"],
            "price":          _fmt_price(r["price_cny"]),
            "unit":           r["unit_cny"],
            "chg_1m":         r["change_1m"],
            "chg_3m":         r["change_3m"],
            "chg_6m":         r["change_6m"],
            "chg_12m":        r["change_12m"],
            "status":         r["status_label"],
            "is_large_move":  bool(r.get("is_large_move", False)),
            "needs_review":   bool(r.get("needs_review", False)),
        })

    # ── 涨幅最高 / 跌幅最大 ──
    valid = [m for m in metals if m["chg_1m"] is not None]
    top_gainer = max(valid, key=lambda m: m["chg_1m"]) if valid else None
    top_loser  = min(valid, key=lambda m: m["chg_1m"]) if valid else None

    # ── 贵金属 vs 工业金属 ──
    precious = [m for m in metals if m["metal_cn"] in ("黄金", "白银") and m["chg_1m"] is not None]
    industrial = [m for m in metals if m["metal_cn"] in ("铜", "锡") and m["chg_1m"] is not None]

    precious_avg = sum(m["chg_1m"] for m in precious) / len(precious) if precious else None
    industrial_avg = sum(m["chg_1m"] for m in industrial) / len(industrial) if industrial else None

    comparison_sentence = _build_comparison_sentence(precious_avg, industrial_avg)
    overview_line = _build_overview_line(metals, top_gainer)

    # ── 告警 ──
    alerts = _extract_alerts(validation_path, target_month)

    # ── 小结 ──
    latest_data = [
        {"metal_cn": m["metal_cn"], "change_1m": m["chg_1m"], "is_large_move": m["is_large_move"]}
        for m in metals
    ]
    summary_bullets = _build_summary(latest_data, precious_avg, industrial_avg)

    return {
        "year":                year,
        "month_name":          str(month_num),
        "month_str":           target_month,
        "report_date":         today,
        "overview_line":       overview_line,
        "top_gainer":          top_gainer,
        "top_loser":           top_loser,
        "metals":              metals,
        "precious_avg":        precious_avg,
        "industrial_avg":      industrial_avg,
        "comparison_sentence": comparison_sentence,
        "alerts":              alerts,
        "has_alerts":          len(alerts) > 0,
        "summary_bullets":     summary_bullets,
    }


# ═══════════════════════════════════════════════════════════════
# Markdown 渲染
# ═══════════════════════════════════════════════════════════════

def render_markdown(context, output_path=None):
    """使用 Jinja2 渲染 Markdown 报告并保存到文件。"""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("report.md.j2")
    md_content = template.render(**context)

    if output_path is None:
        output_path = DEFAULT_MD_DIR / f"{context['month_str']}-metal-report.md"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md_content, encoding="utf-8")

    print(f"[INFO] Markdown 报告已保存: {output_path}")
    return str(output_path)


# ═══════════════════════════════════════════════════════════════
# HTML 渲染
# ═══════════════════════════════════════════════════════════════

def render_html(context, output_path=None, chart_paths=None):
    """
    使用 Jinja2 渲染手机端 HTML 报告。

    参数
    ----
    context : dict
        基础上下文（来自 _prepare_context）。
    output_path : str or Path
        输出 .html 路径，默认 public/reports/YYYY-MM/index.html。
    chart_paths : tuple
        (trend_chart_path, bar_chart_path)。

    返回
    ----
    str
        输出的 HTML 文件路径。
    """
    # ── 扩展上下文：添加 HTML 专用字段 ──
    html_context = dict(context)

    if chart_paths:
        trend_path, bar_path = chart_paths
        # 计算 HTML 到图表的相对路径
        if output_path:
            html_dir = Path(output_path).parent
            if trend_path:
                html_context["has_trend_chart"] = True
                html_context["trend_chart_src"] = str(
                    Path(trend_path).relative_to(html_dir)
                )
            else:
                html_context["has_trend_chart"] = False
                html_context["trend_chart_src"] = ""

            if bar_path:
                html_context["has_bar_chart"] = True
                html_context["bar_chart_src"] = str(
                    Path(bar_path).relative_to(html_dir)
                )
            else:
                html_context["has_bar_chart"] = False
                html_context["bar_chart_src"] = ""
        else:
            html_context["has_trend_chart"] = bool(trend_path)
            html_context["trend_chart_src"] = f"../../charts/{Path(trend_path).name}" if trend_path else ""
            html_context["has_bar_chart"] = bool(bar_path)
            html_context["bar_chart_src"] = f"../../charts/{Path(bar_path).name}" if bar_path else ""
    else:
        html_context["has_trend_chart"] = False
        html_context["trend_chart_src"] = ""
        html_context["has_bar_chart"] = False
        html_context["bar_chart_src"] = ""

    # 校验状态
    validation_path = DEFAULT_VALIDATION
    html_context["validation_status"] = _extract_validation_status(validation_path)

    # ── 渲染 ──
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("report.html.j2")
    html_content = template.render(**html_context)

    if output_path is None:
        output_path = (
            DEFAULT_HTML_DIR / context["month_str"] / "index.html"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")

    print(f"[INFO] HTML 报告已保存: {output_path}")
    return str(output_path)


# ═══════════════════════════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════════════════════════

def generate(analysis_path=None, validation_path=None,
             output_md_path=None, output_html_path=None,
             target_month=None, with_charts=True):
    """
    生成全中文 Markdown 月报 + 手机端 HTML 页面。

    返回
    ----
    dict
        {'md': md_path, 'html': html_path}
    """
    analysis_path = Path(analysis_path) if analysis_path else DEFAULT_ANALYSIS
    validation_path = Path(validation_path) if validation_path else DEFAULT_VALIDATION

    if not analysis_path.exists():
        raise FileNotFoundError(f"分析数据不存在: {analysis_path}")

    # ── 1. 生成图表 ──
    chart_paths = (None, None)
    if with_charts:
        try:
            chart_paths = generate_all_charts(
                analysis_path=analysis_path,
                charts_dir=DEFAULT_CHARTS_DIR,
                target_month=target_month,
            )
        except Exception as e:
            print(f"[WARN] 图表生成失败，跳过: {e}")

    # ── 2. 准备上下文 ──
    context = _prepare_context(analysis_path, validation_path, target_month)

    # ── 3. 生成 Markdown ──
    md_path = render_markdown(context, output_md_path)

    # ── 4. 生成 HTML ──
    html_path = render_html(context, output_html_path, chart_paths)

    # ── 5. 控制台摘要 ──
    print(f"\n{'='*60}")
    print(f"📋 金银铜锡价格月报｜{context['year']}年{context['month_name']}月")
    print(f"{'='*60}")
    if context["top_gainer"]:
        print(f"  涨幅最高: {context['top_gainer']['metal_cn']} "
              f"{_fmt_pct(context['top_gainer']['chg_1m'])}")
    if context["top_loser"]:
        print(f"  跌幅最大: {context['top_loser']['metal_cn']} "
              f"{_fmt_pct(context['top_loser']['chg_1m'])}")
    for m in context["metals"]:
        flag = " ⚠️" if m["is_large_move"] else ""
        print(f"  {m['metal_cn']:>4s}: ¥{m['price']:>12s} {m['unit']}  "
              f"比上月{_fmt_pct(m['chg_1m']):>8s}  {m['status']}{flag}")
    print(f"  告警数量: {len(context['alerts'])}")
    print(f"  报告文件: {md_path}")
    print(f"  HTML页面: {html_path}")
    print(f"{'='*60}")

    return {"md": md_path, "html": html_path}


# ═══════════════════════════════════════════════════════════════
# 测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Metal Price Report — 阶段 5: 生成月报（MD + HTML + 图表）")
    print("=" * 60)

    result = generate()
    print(f"\n[DONE] 全部生成完毕。")
