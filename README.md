# Metal Price Report

金属市场周报项目。当前正式系统目录为 `metal-intelligence/`，用于黄金、白银、铜、锡的周度价格抓取、人民币统一换算、数据真实性复核和 HTML 周报生成。

## 当前运行入口

```bash
cd metal-intelligence
python3 src/run_weekly_pipeline.py
```

如果只是内部查看尚未通过新鲜度闸门的预览：

```bash
cd metal-intelligence
python3 src/generate_weekly_html.py --allow-unverified
```

正式发布必须通过 `metal-intelligence/reports/weekly_data_review.json` 的发布闸门。当前项目暂不执行 GitHub push。

## 目录结构

```text
metal-price-report/
├── metal-intelligence/     # 当前唯一有效的周报系统
├── .github/                 # GitHub Actions：每周抓取、复核、发布和通知
├── archive/legacy-monthly/  # 旧版月报系统，仅作历史归档，不参与当前运行
├── .env                     # 本地私密配置，不提交 GitHub
├── .gitignore               # 忽略密钥、缓存和运行快照
└── README.md                # 当前项目总说明
```

## `metal-intelligence/` 内部职责

```text
metal-intelligence/
├── config/                  # 数据源、市场基准、单位和计算口径
├── src/                     # 抓取、转换、事实生成、复核和页面生成程序
├── data/raw/                # 本次抓取得到的原始标准化日线
├── data/processed/          # 统一人民币周表、事实 JSON 和价格解读
├── data/snapshots/          # 每次运行的原始输入快照和 SHA-256 指纹
├── reports/                 # 来源质量、可比性和发布闸门报告
├── public/weekly/            # 通过闸门后生成的周报页面
├── charts/                  # 近一年辅助趋势图
└── prompts/                 # AI 分析提示词，仅在接入外部模型时使用
```

### 数据链路

```text
Yahoo Finance / SHFE 官方
        ↓
data/raw/
        ↓
人民币换算与周度聚合
        ↓
data/processed/
        ↓
数据真实性复核 + 发布闸门
        ↓
public/weekly/index.html
```

### 当前数据口径

| 品种 | 市场基准 | 获取方式 | 展示单位 |
| --- | --- | --- | --- |
| 黄金 | COMEX Gold Futures | Yahoo Finance `GC=F` | 人民币/克 |
| 白银 | COMEX Silver Futures | Yahoo Finance `SI=F` | 人民币/克 |
| 铜 | COMEX Copper Futures | Yahoo Finance `HG=F` | 人民币/吨 |
| 锡 | SHFE Tin Futures | SHFE 官方 | 人民币/吨 |

## `archive/legacy-monthly/`

这里保存旧版月报系统的历史文件，包括旧的抓取脚本、模板、月度数据和页面。它不在当前 GitHub Actions 周报路径中，不会被当前流水线读取。保留归档是为了需要追溯旧报告或旧实现时仍然可以恢复；确认新系统长期稳定后，再单独决定是否永久删除。

## GitHub 发布前检查

1. 先更新数据并确认 `metal-intelligence/reports/weekly_data_review.json` 状态为 `通过`。
2. 检查 `metal-intelligence/public/weekly/index.html` 的概览、价格卡片和价格解读是否一致。
3. 确认 `.env` 未被加入 Git，Bark 等密钥只配置在 GitHub Actions Secrets。
4. 本地确认后，再进行 commit 和 push。
