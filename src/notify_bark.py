"""
Bark 手机推送模块。

从 monthly_analysis.csv 和 validation_result.json 中提取关键信息，
通过 Bark API 发送全中文手机推送通知。

依赖环境变量：
  BARK_KEY      — 必填，Bark App 的 Key
  BARK_BASE_URL — 可选，默认 https://api.day.app
  REPORT_URL    — 可选，点击通知后打开的链接
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent

DEFAULT_ANALYSIS = ROOT_DIR / "data" / "processed" / "monthly_analysis.csv"
DEFAULT_VALIDATION = ROOT_DIR / "data" / "processed" / "validation_result.json"


# ═══════════════════════════════════════════════════════════════
# 数据读取
# ═══════════════════════════════════════════════════════════════

def _load_latest_data(analysis_path):
    """加载最新月份的分析数据，返回 DataFrame。"""
    df = pd.read_csv(analysis_path)
    latest_month = df["month"].max()
    return df[df["month"] == latest_month], latest_month


def _load_validation(validation_path):
    """加载校验结果。"""
    if not validation_path.exists():
        return {"status_text": "未知", "summary": ""}
    with open(validation_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════
# 推送正文生成
# ═══════════════════════════════════════════════════════════════

def _build_body(latest_df, latest_month, validation):
    """
    根据规则生成 Bark 推送正文。

    返回 (title, body) 元组。
    """
    # ── 解析年月 ──
    y, m = latest_month.split("-")
    year = int(y)
    month = int(m)

    # ── 按 change_1m 排序，找最高/最低 ──
    valid = latest_df[latest_df["change_1m"].notna()].copy()

    if len(valid) == 0:
        body = f"{year}年{month}月：本月数据不足，无法生成摘要。"
        return "金银铜锡价格月报", body

    top_row = valid.loc[valid["change_1m"].idxmax()]
    bot_row = valid.loc[valid["change_1m"].idxmin()]

    top_metal = top_row["metal_cn"]
    top_chg = top_row["change_1m"]
    bot_metal = bot_row["metal_cn"]
    bot_chg = bot_row["change_1m"]

    has_up = top_chg > 0
    has_down = bot_chg < 0

    # ── 状态文字 ──
    status_text = validation.get("status_text", "未知")

    # ── 组装正文 ──
    if has_up and has_down:
        # 有涨有跌
        body = (
            f"{year}年{month}月：{top_metal}本月上涨{top_chg:.2f}%，"
            f"表现最强；{bot_metal}下跌{abs(bot_chg):.2f}%，"
            f"回调明显。数据状态：{status_text}。"
        )
    elif has_up and not has_down:
        # 只有涨，没有跌
        body = (
            f"{year}年{month}月：{top_metal}本月上涨{top_chg:.2f}%，"
            f"表现最强；四类金属本月均未下跌。"
            f"数据状态：{status_text}。"
        )
    elif not has_up and has_down:
        # 只有跌，没有涨
        body = (
            f"{year}年{month}月：四类金属本月均未上涨；"
            f"{bot_metal}下跌{abs(bot_chg):.2f}%，"
            f"回调明显。数据状态：{status_text}。"
        )
    else:
        # 既没有涨也没有跌（持平）
        body = (
            f"{year}年{month}月：四类金属本月整体平稳。"
            f"数据状态：{status_text}。"
        )

    return "金银铜锡价格月报", body


# ═══════════════════════════════════════════════════════════════
# Bark 推送
# ═══════════════════════════════════════════════════════════════

def _send_bark(title, body, bark_key, base_url, report_url=None):
    """
    通过 Bark API 发送推送通知。

    参数
    ----
    title : str
        推送标题。
    body : str
        推送正文。
    bark_key : str
        Bark Key。
    base_url : str
        Bark 服务地址。
    report_url : str or None
        点击通知后打开的链接。
    """
    api_url = f"{base_url.rstrip('/')}/{bark_key}"

    # URL 编码
    import urllib.parse
    params = {
        "title": title,
        "body": body,
    }
    if report_url:
        params["url"] = report_url

    query_string = urllib.parse.urlencode(params)
    full_url = f"{api_url}?{query_string}"

    try:
        req = urllib.request.Request(full_url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("code") == 200:
                print(f"[INFO] Bark 推送成功: {title}")
                print(f"[INFO] 正文: {body}")
                return True
            else:
                msg = result.get("message", f"未知错误 (code={result.get('code')})")
                raise RuntimeError(f"Bark 推送失败：{msg}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Bark 推送失败：网络错误 — {e}")
    except json.JSONDecodeError:
        raise RuntimeError("Bark 推送失败：无法解析服务器响应")


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def notify(analysis_path=None, validation_path=None):
    """
    读取数据并发送 Bark 推送。

    返回
    ----
    bool
        推送是否成功。
    """
    analysis_path = Path(analysis_path) if analysis_path else DEFAULT_ANALYSIS
    validation_path = Path(validation_path) if validation_path else DEFAULT_VALIDATION

    # ── 检查环境变量 ──
    bark_key = os.environ.get("BARK_KEY", "").strip()
    if not bark_key:
        print("[ERROR] 环境变量 BARK_KEY 未设置，无法发送推送。")
        sys.exit(1)

    bark_base_url = os.environ.get("BARK_BASE_URL", "https://api.day.app").strip()
    report_url = os.environ.get("REPORT_URL", "").strip() or None

    # ── 检查数据文件 ──
    if not analysis_path.exists():
        print(f"[ERROR] 分析数据不存在: {analysis_path}")
        sys.exit(1)

    # ── 加载数据 ──
    latest_df, latest_month = _load_latest_data(analysis_path)
    validation = _load_validation(validation_path)

    print("=" * 60)
    print("Metal Price Report — Bark 推送")
    print("=" * 60)
    print(f"[INFO] 最新月份: {latest_month}")
    print(f"[INFO] 数据状态: {validation.get('status_text', '未知')}")

    # ── 生成推送内容 ──
    title, body = _build_body(latest_df, latest_month, validation)

    print(f"[INFO] 推送标题: {title}")
    print(f"[INFO] 推送正文: {body}")
    if report_url:
        print(f"[INFO] 报告链接: {report_url}")

    # ── 发送 ──
    _send_bark(title, body, bark_key, bark_base_url, report_url)
    return True


# ═══════════════════════════════════════════════════════════════
# 测试入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    notify()
