# 金属周报 V1 数据获取 Demo

本 Demo 用于验证黄金、白银、铜、锡四个国际期货价格能否通过 Yahoo Finance 稳定获取，并为后续中文周报提供标准化日线和周度数据。

## 数据源

| 品种 | Yahoo Finance ticker | 价格单位 |
| --- | --- | --- |
| 黄金 | `GC=F` | 美元/金衡盎司 |
| 白银 | `SI=F` | 美元/金衡盎司 |
| 铜 | `HG=F` | 美元/磅 |
| 锡 | `SN=F` | 美元/公吨 |

Yahoo Finance 是聚合数据源，不是交易所官方 API。它适合本阶段的数据链路验证；正式发布前，应为关键品种补充交易所或授权数据源交叉验证。

## 运行

```bash
python3 -m pip install -r requirements.txt
python3 src/fetch_prices.py
```

## 每周更新（推荐）

使用统一入口完成抓取、人民币换算、数据复核和页面更新：

```bash
python3 src/run_weekly_pipeline.py
```

默认会抓取近一年 SHFE 锡数据。若只做短期测试，可使用：

```bash
python3 src/run_weekly_pipeline.py --tin-days 100
```

流程中任意一步失败都会停止，不会用不完整数据生成页面。复核报告保存于 `reports/weekly_data_review.json`。

## 每周自动运行

`.github/workflows/weekly-report.yml` 已配置为每周六北京时间 10:00 运行，也可以在 GitHub Actions 页面手动触发。任务会保存周报页面和复核报告；如果抓取或复核失败，任务会失败，不会把不完整数据当成新周报。

## 输出

- `data/raw/`：各 ticker 的原始标准化数据
- `data/processed/metal_prices_daily.csv`：统一日线数据
- `data/processed/metal_prices_weekly.csv`：周收盘、周高低点和周涨跌幅
- `reports/data_quality_report.json`：来源与质量检查结果
- `charts/`：成功获取品种的近一年趋势图

## 统一周度数据

运行：

```bash
python3 src/build_unified_weekly.py
```

配置文件为 `config/metal_sources.json`，统一输出为 `data/processed/metal_prices_unified_weekly.csv`。当前展示统一使用人民币：黄金、白银为人民币/克，铜、锡为人民币/吨。黄金、白银和铜使用 `CNY=X` 日汇率换算；锡本身就是 SHFE 人民币/吨报价。输出同时保留原始单位、汇率和两种涨跌幅，便于审计。

比较性检查结果保存于 `reports/unified_weekly_comparability.json`。

## SHFE 锡价验证

由于 Yahoo Finance 的 `SN=F` 无数据，锡价使用上海期货交易所官方日行情文件。运行：

```bash
python3 src/fetch_shfe_tin.py --days 30 --workers 8
```

脚本默认支持近 365 天；验证时建议先用较短区间，因 SHFE 官方接口按交易日逐文件提供数据，全年首次抓取耗时较长。之后可按月缓存，避免每周重复读取全年历史。

脚本逐日读取 SHFE 官方数据，筛选 `SN` 品种，并按“每日成交量最高的合约”构建主力连续序列。输出会明确标注这是连续合约序列，单位为人民币/吨。

- `data/raw/shfe_tin_contracts_daily.csv`：官方返回的各锡合约日线
- `data/processed/shfe_tin_main_daily.csv`：主力连续日线
- `data/processed/shfe_tin_main_weekly.csv`：主力连续周线
- `reports/shfe_tin_quality_report.json`：来源和质量检查
- `charts/tin_shfe_1y.png`：近一年趋势图

SHFE 官方页面：[锡期货](https://www.shfe.com.cn/eng/Market/Futures/Metal/sn_f/)。
