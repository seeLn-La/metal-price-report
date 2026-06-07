# Metal Price Report（金银铜锡价格月报系统）

自动采集金银铜锡价格数据，生成月度价格报告。

## 项目结构

```
metal-price-report/
├── data/                # 数据目录
│   ├── raw/             # 原始采集数据
│   ├── processed/       # 清洗/转换后的数据
│   └── exchange_rates.csv  # 汇率数据
├── reports/             # 生成的报告文件
├── public/              # 发布目录
│   ├── reports/         # 公开发布的报告
│   └── charts/          # 生成的图表
├── templates/           # Jinja2 模板
│   ├── report.md.j2     # Markdown 报告模板
│   └── report.html.j2   # HTML 报告模板
├── src/                 # 源代码
│   ├── main.py                  # 主入口
│   ├── fetch_commodity_data.py  # 采集大宗商品数据
│   ├── fetch_exchange_rate.py   # 采集汇率数据
│   ├── transform_units.py       # 单位转换
│   ├── analyze.py               # 数据分析
│   ├── validate_data.py         # 数据校验
│   ├── generate_charts.py       # 图表生成
│   ├── generate_report.py       # 报告生成
│   └── push_bark.py             # Bark 推送
├── requirements.txt     # Python 依赖
├── .env.example         # 环境变量示例
└── README.md            # 本文件
```

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
python src/main.py
```

## License

MIT
