#!/usr/bin/env python3
"""Fetch SHFE official daily tin futures data and build a main-contract series."""

from __future__ import annotations

import json
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import requests

plt.rcParams["font.family"] = ["STHeiti", "Hiragino Sans GB", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CHART_DIR = ROOT / "charts"
REPORT_DIR = ROOT / "reports"
SOURCE_URL = "https://www.shfe.com.cn/data/tradedata/future/dailydata/kx{date}.dat"
SOURCE_PAGE = "https://www.shfe.com.cn/eng/Market/Futures/Metal/sn_f/"
HEADERS = {"User-Agent": "Mozilla/4.0 (compatible; MSIE 5.5; Windows NT)"}


def fetch_day(day: date) -> tuple[str, list[dict], str | None]:
    date_text = day.strftime("%Y%m%d")
    url = SOURCE_URL.format(date=date_text)
    for attempt in range(3):
        try:
            response = requests.get(url, headers=HEADERS, timeout=60)
            if response.status_code == 404:
                return date_text, [], None
            response.raise_for_status()
            payload = response.json()
            rows = []
            for item in payload.get("o_curinstrument", []):
                variety = str(item.get("PRODUCTGROUPID") or item.get("PRODUCTID", "")).split("_")[0].strip().upper()
                if variety != "SN" or item.get("DELIVERYMONTH", "") in {"", "小计", "合计"}:
                    continue
                rows.append({
                    "date": day.isoformat(),
                    "symbol": f"SN{item.get('DELIVERYMONTH', '').strip()}",
                    "variety": "SN",
                    "open": item.get("OPENPRICE"),
                    "high": item.get("HIGHESTPRICE"),
                    "low": item.get("LOWESTPRICE"),
                    "close": item.get("CLOSEPRICE"),
                    "settle": item.get("SETTLEMENTPRICE"),
                    "pre_settle": item.get("PRESETTLEMENTPRICE"),
                    "volume": item.get("VOLUME"),
                    "open_interest": item.get("OPENINTEREST"),
                    "turnover": item.get("TURNOVER"),
                    "source": "SHFE official",
                    "source_url": url,
                })
            return date_text, rows, None
        except Exception as exc:
            if attempt == 2:
                return date_text, [], str(exc)
            time.sleep(1.5 * (attempt + 1))
    return date_text, [], "unknown error"


def choose_main_contract(data: pd.DataFrame) -> pd.DataFrame:
    """Choose the highest-volume contract per day and retain the rule in the output."""
    data = data.copy()
    numeric = ["open", "high", "low", "close", "settle", "pre_settle", "volume", "open_interest", "turnover"]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["date", "close", "volume"])
    data = data[data["close"] > 0]
    data = data.sort_values(["date", "volume", "open_interest"], ascending=[True, False, False])
    data = data.drop_duplicates("date").sort_values("date")
    data["selection_rule"] = "每日成交量最高的 SHFE 锡合约"
    data["unit"] = "人民币/吨"
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365, help="lookback calendar days")
    parser.add_argument("--workers", type=int, default=8, help="parallel official-file requests")
    args = parser.parse_args()
    for directory in (RAW_DIR, PROCESSED_DIR, CHART_DIR, REPORT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=args.days)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    rows, failures = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(fetch_day, day) for day in days]
        for future in as_completed(futures):
            date_text, day_rows, error = future.result()
            rows.extend(day_rows)
            if error:
                failures.append({"date": date_text, "error": error})
    raw = pd.DataFrame(rows)
    if raw.empty:
        report = {"status": "failed", "source": "SHFE official", "source_url": SOURCE_PAGE, "error": "No SN rows returned", "failed_days": failures}
        (REPORT_DIR / "shfe_tin_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    raw = raw.sort_values(["date", "symbol"])
    raw.to_csv(RAW_DIR / "shfe_tin_contracts_daily.csv", index=False)
    main_contract = choose_main_contract(raw)
    main_contract.to_csv(PROCESSED_DIR / "shfe_tin_main_daily.csv", index=False)
    weekly = main_contract.copy()
    weekly["date"] = pd.to_datetime(weekly["date"])
    weekly["week"] = weekly["date"].dt.to_period("W-FRI")
    weekly = weekly.groupby("week", as_index=False).agg(
        week_end=("date", "max"), last_close=("close", "last"), week_high=("high", "max"),
        week_low=("low", "min"), observation_count=("close", "count"), contract_count=("symbol", "nunique")
    )
    weekly["weekly_change_pct"] = weekly["last_close"].pct_change() * 100
    weekly["unit"] = "人民币/吨"
    weekly.to_csv(PROCESSED_DIR / "shfe_tin_main_weekly.csv", index=False)
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=150)
    ax.plot(main_contract["date"], main_contract["close"], color="#58656f", linewidth=1.8)
    ax.set_title(f"SHFE 锡主力连续近{args.days}天价格趋势")
    ax.set_xlabel("日期")
    ax.set_ylabel("价格（人民币/吨）")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
    ax.grid(True, alpha=0.25)
    fig.text(0.99, 0.01, "数据来源：上海期货交易所官方日行情", ha="right", fontsize=8, color="#666666")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "tin_shfe_1y.png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    quality = {
        "status": "success",
        "source": "SHFE official",
        "source_page": SOURCE_PAGE,
        "source_url_template": SOURCE_URL,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "start_date": str(main_contract["date"].min()),
        "end_date": str(main_contract["date"].max()),
        "contract_rows": int(len(raw)),
        "main_series_rows": int(len(main_contract)),
        "main_contracts_observed": int(main_contract["symbol"].nunique()),
        "missing_close": int(main_contract["close"].isna().sum()),
        "non_positive_close": int((main_contract["close"] <= 0).sum()),
        "failed_days": failures,
        "selection_rule": "每日成交量最高的 SHFE 锡合约",
        "unit": "人民币/吨",
    }
    (REPORT_DIR / "shfe_tin_quality_report.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(quality, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
