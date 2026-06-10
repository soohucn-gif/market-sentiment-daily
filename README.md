# 美股市场情绪 Dashboard — Daily Snapshot

Self-contained US market sentiment dashboard, regenerated daily
(~10:00 北京时间) by a Claude cloud routine (`market-sentiment-daily`).
This repo is both the tool's home (`tool/`) and the published site.

- **Latest:** https://soohucn-gif.github.io/market-sentiment-daily/
- **Archive:** [archive/](archive/) — one snapshot per day
- **Raw data:** [data.json](data.json)

## Indicators

| # | Indicator | Source | Mode |
|---|-----------|--------|------|
| ① | CNN Fear & Greed | CNN dataviz API (curl) | auto |
| ② | VIX | Yahoo v8 chart API → FRED VIXCLS | auto |
| ③ | Market Breadth (50DMA %) | StockCharts $NDXA50R / $SPXA50R | auto (scrape) |
| ④ | AAII Investor Sentiment | aaii.com weekly XLS | auto (curl, Imperva-hardened) |
| ⑤ | Put/Call Ratio | StockCharts $CPCE (CBOE data) | auto (scrape) |
| ⑥ | LLM Token Expenditure Index | Silicon Data public posts | manual-curated |

Every fetcher saves its last good payload to `tool/data/{name}_seed.json`
and falls back to it when the live source blocks the runner's IP — the
dashboard always renders; stale data is dated, never silent. Public
market data only.

## Run locally

```
cd tool && ./start.sh        # live Flask dashboard at localhost:5055
# or double-click tool/美股情绪.command
cd tool && .venv/bin/python scripts/generate_static.py ..   # regenerate site
```

## Indicator ⑥ refresh

Silicon Data's index has no free API. In a Claude Code session, run
`/update-silicon-data` — Claude reads @Silicon_Data public posts and
appends dated, source-attributed points to `tool/data/silicon_data_index.json`.
