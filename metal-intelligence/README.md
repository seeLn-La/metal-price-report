# Metal Intelligence 金属市场周报系统

本系统用于持续获取黄金、白银、铜、锡的市场价格，完成人民币统一换算、数据真实性复核、价格解读和中文周报生成。

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

流程中任意一步失败都会停止，不会用不完整数据生成页面。每次抓取后会先保存 `data/snapshots/<run_id>/` 原始输入快照和 `manifest.json`，再进入统一计算。复核报告保存于 `reports/weekly_data_review.json`。

## 每周自动运行

`.github/workflows/weekly-report.yml` 已配置为每周六北京时间 10:00 运行，也可以在 GitHub Actions 页面手动触发。任务会保存周报页面和复核报告；如果抓取或复核失败，任务会失败，不会把不完整数据当成新周报。

## 数据真实性与发布闸门

字段、单位、市场基准和周度计算口径统一记录在 `config/data_dictionary.json`。其中“市场基准”和“数据获取方式”分开记录：例如黄金的市场基准是 COMEX Gold Futures，数据获取方式是 Yahoo Finance `GC=F`。

周报生成前会自动执行 `src/validate_weekly_data.py`。复核不是只检查页面文字，而是分层检查：

- 来源质量报告是否成功，来源代码、单位和来源标识是否匹配配置；
- 黄金、白银、铜、锡和 USD/CNY 日线是否有重复日期、缺失值、非正价格或异常高低收关系；
- 从日线和汇率重新计算人民币价格、周均价、周高低和周涨跌，逐字段与统一周表比对；
- 最新周是否过期，四种金属是否齐全，周区间是否完整；
- 概览、排名、分析摘要和驱动文字中的数字是否与事实型 JSON 一致；
- 本次复核使用的输入文件 SHA-256 是否记录在 `reports/weekly_data_review.json` 中。

只有复核报告的 `status` 为 `通过`，流水线才会生成周报页面。单独运行页面生成器时也会再次检查这个发布闸门：

```bash
python3 src/generate_weekly_html.py
```

如果只需要查看未通过复核的数据预览，必须明确使用：

```bash
python3 src/generate_weekly_html.py --allow-unverified
```

该选项只适用于内部排查，不代表数据可以正式发布。复核失败时，应先根据 `reports/weekly_data_review.json` 的具体检查项修正数据源、转换逻辑或过期文案，再从原始数据重新运行完整流水线。

## 本周价格解读

报告中的“本周驱动”已调整为“本周价格解读”，面向不熟悉期货的读者。每种金属固定展示：

- 发生了什么：由统一周度事实动态生成，明确本周与近 12 周的时间口径；
- 可能的影响因素：用普通语言说明因素如何可能影响价格，不直接写成确定因果；
- 证据强度：较强、中等、较弱或不足；
- 来源和观察日期：支持回溯原始报道；
- 限制说明：明确当前证据不能证明什么；
- 目前结论和下周观察：区分阶段性判断与后续需要验证的事项。

这些内容保存在 `data/processed/market_drivers.json`，当前为 `schema_version: 2.0`。发布前复核会检查每条影响线索是否具备通俗解释、可能影响、证据强度、来源日期和限制说明，也会阻止驱动文字写入过期的周涨跌数字。

## 输出

- `data/raw/`：各 ticker 的原始标准化数据
- `data/processed/metal_prices_daily.csv`：统一日线数据
- `data/processed/metal_prices_weekly.csv`：周收盘、周高低点和周涨跌幅
- `reports/data_quality_report.json`：来源与质量检查结果
- `reports/weekly_data_review.json`：发布前真实性复核、失败原因和输入文件指纹
- `reports/latest_snapshot.json`：最近一次输入快照指针和 manifest 指纹
- `config/data_dictionary.json`：字段、单位、来源和计算口径
- `public/weekly/index.html`：通过发布闸门后生成的周报页面
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
