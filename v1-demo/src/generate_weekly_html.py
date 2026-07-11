#!/usr/bin/env python3
"""Render a mobile-first static weekly report preview from the analysis JSON."""

from __future__ import annotations

import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "data" / "processed" / "weekly_analysis_demo.json"
FACTS_PATH = ROOT / "data" / "processed" / "weekly_report.json"
DRIVERS_PATH = ROOT / "data" / "processed" / "market_drivers.json"
OUTPUT_DIR = ROOT / "public" / "weekly"
OUTPUT_PATH = OUTPUT_DIR / "index.html"


def pct(value: float) -> str:
    return f"{value:+.2f}%"


def price(value: float) -> str:
    return f"{value:,.2f}"


def unit_label(unit: str) -> str:
    return unit.replace("人民币", "元")


def date_label(value: str) -> str:
    parts = value.split("-")
    return f"{int(parts[1])}月{int(parts[2])}日"


def trend_chart(metal: str, points: list[dict]) -> str:
    values = [point["price"] for point in points if point["price"] is not None]
    if not values:
        return "<div class=\"empty-chart\">暂无趋势数据</div>"
    width, height, left, right, top, bottom = 320, 166, 42, 12, 14, 38
    low, high = min(values), max(values)
    span = high - low or max(abs(high) * 0.02, 1)
    chart_points = []
    for index, value in enumerate(values):
        x = left + (width - left - right) * index / max(len(values) - 1, 1)
        y = height - bottom - (height - top - bottom) * (value - low) / span
        chart_points.append(f"{x:.1f},{y:.1f}")
    first_label = points[0]["week_end"][5:]
    last_label = points[-1]["week_end"][5:]
    last_x, last_y = chart_points[-1].split(",")
    period_change = (values[-1] / values[0] - 1) * 100 if values[0] else 0
    latest_change = points[-1].get("weekly_change_pct")
    period_tone = "up" if period_change > 0 else "down" if period_change < 0 else "flat"
    latest_change_text = pct(latest_change) if latest_change is not None else "—"
    month_ticks = []
    seen_months = set()
    for index, point in enumerate(points):
        month = point["week_end"][:7]
        if month in seen_months:
            continue
        seen_months.add(month)
        x = left + (width - left - right) * index / max(len(values) - 1, 1)
        month_text = f"{int(month[5:])}月"
        month_ticks.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height-bottom}" class="chart-month" /><text x="{x:.1f}" y="{height-10}" text-anchor="middle" class="chart-month-label">{month_text}</text>')
    y_ticks = []
    for fraction in (1, 0.5, 0):
        y = height - bottom - (height - top - bottom) * fraction
        value = low + span * fraction
        y_ticks.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" class="chart-grid" /><text x="0" y="{y+4:.1f}" class="chart-tick">{price(value)}</text>')
    return f"""
    <div class="trend-chart">
      <div class="chart-caption"><span>{html.escape(metal)} · 周均价趋势（近3个月）</span><strong>{price(values[-1])}</strong></div>
      <svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(metal)}价格趋势图">
        <line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" class="chart-axis" />
        <line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" class="chart-axis" />
        {''.join(y_ticks)}
        {''.join(month_ticks)}
        <polyline points="{' '.join(chart_points)}" class="chart-line" />
        <circle cx="{last_x}" cy="{last_y}" r="3.5" class="chart-dot" />
      </svg>
      <div class="trend-stats">
        <div><span>3个月均价涨跌</span><strong class="{period_tone}">{pct(period_change)}</strong></div>
        <div><span>均价最高</span><strong>{price(high)}</strong></div>
        <div><span>均价最低</span><strong>{price(low)}</strong></div>
        <div><span>较上周</span><strong>{latest_change_text}</strong></div>
      </div>
    </div>
    """


def source_tag(entry: dict) -> str:
    if entry.get("url"):
        return f'<a href="{html.escape(entry["url"])}" target="_blank" rel="noreferrer">来源</a>'
    return f'<span class="source-note">{html.escape(entry.get("source", "内部复核"))}</span>'


def main() -> int:
    report = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    facts = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
    drivers = json.loads(DRIVERS_PATH.read_text(encoding="utf-8"))
    trend_charts = "".join(trend_chart(metal, points) for metal, points in facts["trend_12_weeks"].items())
    snapshot = report["market_snapshot"]
    cards = []
    driver_blocks = []
    for item in report["metal_analysis"]:
        change = item["weekly_change_pct"]
        tone = "up" if change > 0 else "down" if change < 0 else "flat"
        points = facts["trend_12_weeks"].get(item["metal"], [])
        trend_values = [point["price"] for point in points if point["price"] is not None]
        trend_low = min(trend_values) if trend_values else item["price"]
        trend_high = max(trend_values) if trend_values else item["price"]
        position = ((item["price"] - trend_low) / (trend_high - trend_low) * 100) if trend_high > trend_low else 50
        driver = drivers.get(item["metal"], {"headline": "暂未提供事件分析", "drivers": [], "caveat": "", "conclusion": "暂不足以下结论。", "conclusion_status": "insufficient"})
        driver_items = "".join(f"<li><span class=\"driver-type\">{html.escape(entry['type'])}</span>{html.escape(entry['text'])} {source_tag(entry)}</li>" for entry in driver["drivers"])
        cards.append(f"""
        <article class="metal-card">
          <div class="metal-head">
            <div>
              <h2>{html.escape(item['metal'])}</h2>
              <span class="unit">{html.escape(unit_label(item['unit']))}</span>
            </div>
            <span class="change {tone}"><span>{pct(change)}</span><span class="change-label">较上周</span></span>
          </div>
          <div class="price-label">本周均价</div>
          <div class="price">{price(item['price'])}<span>{html.escape(unit_label(item['unit']))}</span></div>
          { '<div class="price-note">国际市场基准价，不含首饰加工费和品牌溢价</div>' if item['metal'] == '黄金' else '' }
          <div class="secondary-prices"><span>周末收盘 {price(item.get('week_close', item['price']))}</span><span>周内高低 {price(item['week_high'])} / {price(item['week_low'])}</span></div>
          <div class="position-label"><span>近3个月价格位置</span><strong>{position:.0f}%</strong></div>
          <div class="position-track"><span style="left:{position:.1f}%"></span></div>
        </article>
        """)
        driver_blocks.append(f"""
        <article class="driver-card">
          <div class="driver-card-head"><strong>{html.escape(item['metal'])}</strong><span>{html.escape(driver['headline'])}</span></div>
          <ul class="driver-list">{driver_items}</ul>
          <p class="driver-conclusion"><strong>当前结论</strong>{html.escape(driver.get('conclusion', '暂不足以下结论。'))}</p>
          <p class="driver-caveat">{html.escape(driver['caveat'])}</p>
        </article>
        """)
    warnings = "".join(f"<li>{html.escape(item)}</li>" for item in report["data_limitations"])
    sources = "".join(
        f"<li><strong>{html.escape(item['metal'])}</strong> · {html.escape(item['source'])} · {html.escape(item['identifier'])}</li>"
        for item in facts["data_sources"]["price_sources"]
    )
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>金属市场周报｜截至 {html.escape(report['week_end'])}</title>
  <style>
    :root {{ --paper:#f6f4ef; --ink:#252525; --muted:#77736b; --line:#ded9cf; --up:#b44335; --down:#2f7d5a; --accent:#9a6b24; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB",sans-serif; line-height:1.55; }}
    main {{ width:min(100% - 28px, 760px); margin:0 auto; padding:28px 0 48px; }}
    header {{ padding:10px 2px 28px; border-bottom:1px solid var(--line); }}
    .eyebrow {{ color:var(--accent); font-size:12px; letter-spacing:.12em; text-transform:uppercase; }}
    h1 {{ margin:8px 0 5px; font-size:clamp(28px,7vw,46px); line-height:1.12; letter-spacing:0; }}
    .date {{ color:var(--muted); font-size:14px; }}
    section {{ margin-top:26px; }}
    .section-head {{ display:flex; justify-content:space-between; align-items:baseline; gap:12px; margin-bottom:12px; }}
    h2.section-title {{ margin:0; font-size:18px; }}
    .section-meta {{ color:var(--muted); font-size:12px; }}
    .summary {{ padding:18px 0 4px; font-size:18px; max-width:650px; }}
    .summary strong {{ color:var(--accent); }}
    .rank-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }}
    .rank {{ border-top:3px solid var(--line); padding:12px 2px; }}
    .rank small {{ color:var(--muted); display:block; font-size:12px; }}
    .rank strong {{ display:block; margin-top:3px; font-size:22px; }}
    .up {{ color:var(--up); }} .down {{ color:var(--down); }} .flat {{ color:var(--muted); }}
    .metal-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    .metal-card {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:16px; min-width:0; }}
    .metal-head {{ display:flex; justify-content:space-between; align-items:start; gap:10px; }}
    .metal-head h2 {{ margin:0; font-size:20px; }}
    .unit {{ color:var(--muted); font-size:12px; }}
    .change {{ display:flex; align-items:baseline; gap:5px; font-size:18px; font-weight:700; white-space:nowrap; }}
    .price-label {{ margin-top:18px; color:var(--muted); font-size:11px; }}
    .price {{ margin:3px 0 8px; font-size:28px; font-weight:750; line-height:1; }}
    .price span {{ margin-left:5px; color:var(--muted); font-size:12px; font-weight:400; }}
    .price-note {{ margin-top:-8px; color:var(--muted); font-size:11px; }}
    .secondary-prices {{ display:flex; flex-direction:column; gap:2px; margin-top:10px; color:var(--muted); font-size:11px; }}
    .change-label {{ color:var(--muted); font-size:11px; font-weight:400; }}
    .analysis-intro {{ margin:0 0 12px; color:var(--muted); font-size:13px; }}
    .position-track {{ position:relative; height:6px; margin-top:6px; border-radius:999px; background:linear-gradient(90deg,#d8e9df,#e9d9b4,#eed0cb); }}
    .position-track span {{ position:absolute; top:50%; width:12px; height:12px; border:2px solid #fff; border-radius:50%; background:#9a6b24; box-shadow:0 0 0 1px #9a6b24; transform:translate(-50%,-50%); }}
    .position-label {{ display:flex; justify-content:space-between; margin-top:14px; color:var(--muted); font-size:11px; }}
    .position-label strong {{ color:var(--ink); font-size:11px; }}
    .driver-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    .driver-card {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px; }}
    .driver-card-head {{ display:flex; justify-content:space-between; gap:10px; align-items:baseline; }}
    .driver-card-head strong {{ font-size:17px; }} .driver-card-head span {{ color:var(--muted); font-size:12px; text-align:right; }}
    .driver-list {{ margin:7px 0 0; padding-left:17px; color:#5d5952; font-size:12px; }}
    .driver-list li {{ margin:5px 0; }}
    .driver-type {{ display:inline-block; margin-right:5px; color:var(--accent); font-weight:650; }}
    .driver-list a {{ color:var(--accent); white-space:nowrap; }}
    .source-note {{ color:var(--muted); white-space:nowrap; }}
    .driver-caveat {{ margin:8px 0 0; color:var(--muted); font-size:11px; }}
    .driver-conclusion {{ margin:10px 0 0; padding-top:9px; border-top:1px solid var(--line); font-size:12px; line-height:1.6; }}
    .driver-conclusion strong {{ display:block; margin-bottom:2px; color:var(--accent); font-size:11px; }}
    .trend-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    .trend-chart {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:12px; }}
    .chart-caption {{ display:flex; justify-content:space-between; gap:8px; font-size:13px; }}
    .chart-caption strong {{ font-size:13px; }}
    .trend-chart svg {{ display:block; width:100%; height:auto; margin-top:8px; }}
    .chart-axis {{ stroke:#9f998e; stroke-width:1; }}
    .chart-grid {{ stroke:#ebe7df; stroke-width:1; }}
    .chart-tick {{ fill:#77736b; font-size:9px; }}
    .chart-month {{ stroke:#f0ede7; stroke-width:1; stroke-dasharray:2 3; }}
    .chart-month-label {{ fill:#77736b; font-size:9px; }}
    .chart-line {{ fill:none; stroke:#9a6b24; stroke-width:2.5; stroke-linecap:round; stroke-linejoin:round; }}
    .chart-dot {{ fill:#9a6b24; }}
    .chart-labels {{ display:flex; justify-content:space-between; color:var(--muted); font-size:11px; }}
    .trend-stats {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:7px 12px; margin-top:11px; padding-top:10px; border-top:1px solid var(--line); }}
    .trend-stats div {{ display:flex; justify-content:space-between; gap:8px; font-size:12px; }}
    .trend-stats span {{ color:var(--muted); }} .trend-stats strong {{ font-weight:650; }}
    .empty-chart {{ color:var(--muted); font-size:13px; padding:24px 0; }}
    .panel {{ border-top:1px solid var(--line); padding-top:14px; }}
    .notice {{ color:#76551f; font-size:14px; }}
    ul {{ margin:8px 0 0; padding-left:20px; color:var(--muted); font-size:13px; }}
    footer {{ margin-top:32px; padding-top:16px; border-top:1px solid var(--line); color:var(--muted); font-size:12px; }}
    @media (max-width:560px) {{ .metal-grid {{ grid-template-columns:1fr; }} .trend-grid {{ grid-template-columns:1fr; }} .driver-grid {{ grid-template-columns:1fr; }} .summary {{ font-size:17px; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="eyebrow">Metal Intelligence · Weekly Facts</div>
      <h1>金属市场周报</h1>
      <div class="date">本周行情：{date_label(report['week_start'])} - {date_label(report['week_end'])} · 人民币展示口径</div>
    </header>
    <section aria-labelledby="summary-title">
      <div class="section-head"><h2 id="summary-title" class="section-title">本周概览</h2><span class="section-meta">事实数据</span></div>
      <p class="summary">{html.escape(snapshot['one_sentence_summary'])}</p>
      <div class="rank-grid">
        <div class="rank"><small>本周涨幅最大</small><strong class="up">{html.escape(snapshot['biggest_gainer']['metal'])} {pct(snapshot['biggest_gainer']['change_pct'])}</strong></div>
        <div class="rank"><small>本周表现最弱</small><strong class="down">{html.escape(snapshot['biggest_loser']['metal'])} {pct(snapshot['biggest_loser']['change_pct'])}</strong></div>
      </div>
    </section>
    <section aria-labelledby="prices-title">
      <div class="section-head"><h2 id="prices-title" class="section-title">价格与变化</h2><span class="section-meta">较上周均价</span></div>
      <p class="analysis-intro">价格位置表示当前价格在近3个月区间中的位置：0% 接近最低价，100% 接近最高价。</p>
      <div class="metal-grid">{''.join(cards)}</div>
    </section>
    <section aria-labelledby="trend-title">
      <div class="section-head"><h2 id="trend-title" class="section-title">价格趋势</h2><span class="section-meta">近3个月</span></div>
      <div class="trend-grid">{trend_charts}</div>
    </section>
    <section aria-labelledby="drivers-title">
      <div class="section-head"><h2 id="drivers-title" class="section-title">本周驱动</h2><span class="section-meta">事件与供需</span></div>
      <div class="driver-grid">{''.join(driver_blocks)}</div>
    </section>
    <section aria-labelledby="sources-title">
      <div class="section-head"><h2 id="sources-title" class="section-title">数据来源</h2><span class="section-meta">可追溯</span></div>
      <div class="panel"><ul>{sources}</ul></div>
    </section>
  </main>
</body>
</html>
"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(document, encoding="utf-8")
    print(OUTPUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
