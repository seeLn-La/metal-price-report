# Metal Intelligence｜Metal Price Intelligence Weekly

Metal Intelligence is an automated weekly market-reporting system for gold, silver, copper, and tin.

It collects market prices, converts them into a consistent Chinese yuan-based view, validates the underlying data, and generates a readable HTML report for people who may not have a financial background. In addition to showing price changes, the report explains why prices may have moved, how market factors are transmitted into prices, and what the available evidence cannot yet prove.

The project is designed to make metal-price movements easier to understand without presenting uncertain market explanations as confirmed facts.

## What It Does

- Fetches daily prices for gold, silver, copper, and tin
- Converts prices into unified RMB display units
- Aggregates daily data into weekly market indicators
- Validates data freshness, completeness, consistency, and source quality
- Generates a responsive HTML weekly report
- Provides concise price interpretations for each metal
- Records source data snapshots and file fingerprints for traceability
- Automatically publishes the report through GitHub Actions
- Sends the latest report link through Bark notifications

## Price Interpretation

Each weekly report includes one concise explanation for every metal. The explanation focuses on:

1. What changed in price
2. The most relevant market factors
3. How those factors may affect prices
4. The boundary between a reasonable explanation and an unproven conclusion

The report avoids presenting a single event as the definite cause of a price movement. Instead, it distinguishes between observed facts, plausible market mechanisms, and conclusions that still require further evidence.

## Data Sources

- Gold: COMEX Gold Futures via Yahoo Finance (`GC=F`)
- Silver: COMEX Silver Futures via Yahoo Finance (`SI=F`)
- Copper: COMEX Copper Futures via Yahoo Finance (`HG=F`)
- Tin: Shanghai Futures Exchange official data
- Currency conversion: USD/CNY exchange-rate data

Gold and silver are displayed in RMB per gram. Copper and tin are displayed in RMB per metric ton.

## Data Quality and Release Gate

A report is published only after passing the data-quality review process. The validation layer checks:

- Data freshness and complete weekly date ranges
- Missing values and duplicate dates
- Non-positive or abnormal prices
- OHLC consistency
- Currency conversion accuracy
- Recalculated weekly averages and price changes
- Consistency between source data, processed data, analysis, and HTML output
- Stale or inconsistent numerical claims in report text
- SHA-256 fingerprints of the input files used for the report

If the validation process fails, the pipeline stops and does not publish an incomplete report.

## Project Structure

```text
metal-price-report/
├── metal-intelligence/
│   ├── config/          # Data sources, units, and market definitions
│   ├── src/             # Fetching, processing, validation, and rendering
│   ├── data/raw/        # Normalized raw market data
│   ├── data/processed/  # Weekly data and market interpretations
│   ├── data/snapshots/  # Input snapshots and file fingerprints
│   ├── reports/         # Quality and release-gate reports
│   ├── public/weekly/   # Generated HTML report
│   ├── charts/          # Supporting price charts
│   └── prompts/         # Optional analysis prompts
└── .github/workflows/
    └── weekly-report.yml
```

## Running Locally

```bash
cd metal-intelligence
python3 -m pip install -r requirements.txt
python3 src/run_weekly_pipeline.py
```

The pipeline fetches data, builds weekly indicators, validates the results, and generates the report page.

## Automated Weekly Updates

GitHub Actions runs the workflow every Saturday at 10:00 AM China Standard Time. The workflow can also be triggered manually from the GitHub Actions page.

The automated process:

```text
Market data
    ↓
Data normalization
    ↓
RMB conversion and weekly aggregation
    ↓
Data-quality validation
    ↓
HTML report generation
    ↓
GitHub Pages deployment
    ↓
Bark notification
```

## Disclaimer

This project is intended for market information and educational analysis. It is not investment advice, does not provide trading signals, and does not claim that any single factor fully explains a price movement.

