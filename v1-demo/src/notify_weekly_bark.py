#!/usr/bin/env python3
"""Send the validated weekly metal snapshot to Bark."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FACTS_PATH = ROOT / "data" / "processed" / "weekly_report.json"
REVIEW_PATH = ROOT / "reports" / "weekly_data_review.json"
DEFAULT_REPORT_URL = "https://seeln-la.github.io/metal-price-report/v1-demo/weekly/"


def send() -> None:
    bark_key = os.environ.get("BARK_KEY", "").strip()
    if not bark_key:
        raise RuntimeError("环境变量 BARK_KEY 未设置")
    facts = json.loads(FACTS_PATH.read_text(encoding="utf-8"))
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    changes = "；".join(
        f"{item['metal']}{item['weekly_change_pct']:+.2f}%"
        for item in facts["performance"]
    )
    passed = f"{review['passed_count']}/{review['check_count']}项复核通过"
    title = f"金属市场周报｜截至{facts['week_end']}"
    body = f"{changes}\n数据状态：{passed}"
    params = {"title": title, "body": body}
    report_url = os.environ.get("WEEKLY_REPORT_URL", DEFAULT_REPORT_URL).strip()
    if report_url:
        params["url"] = report_url
    url = f"{os.environ.get('BARK_BASE_URL', 'https://api.day.app').rstrip('/')}/{bark_key}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("code") != 200:
        raise RuntimeError(f"Bark 推送失败：{result.get('message', result)}")
    print(f"推送成功：{title}")
    print(body)
    print(f"网页链接：{report_url}")


if __name__ == "__main__":
    send()
