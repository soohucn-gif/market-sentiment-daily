# 美股市场情绪 Dashboard

Local Flask app showing 6 sentiment indicators.

## Run
Double-click `美股情绪.command`, or:
```
./start.sh
```

## Indicators

| # | Indicator | Source | Mode |
|---|-----------|--------|------|
| ① | CNN Fear & Greed | CNN dataviz API | auto |
| ② | VIX | Yahoo Finance (yfinance) | auto |
| ③ | Market Breadth (50DMA %) | StockCharts $NDXA50R / $SPXA50R | auto (scrape) |
| ④ | AAII Investor Sentiment | aaii.com weekly XLS | auto (curl + disk-cache fallback) |
| ⑤ | Put/Call Ratio | StockCharts $CPCE (CBOE data) | auto (scrape) |
| ⑥ | LLM Token Expenditure Index | Silicon Data public posts | manual-curated |

## Indicator ⑥ — Silicon Data LLM Token Expenditure Index

Usage-weighted average price (USD) the whole market pays per 1M LLM
tokens — the marginal willingness to pay for AI. No free API exists
(Silicon Data's Token Index API is paid; Bloomberg/Macrobond are
terminal-licensed), so the series is curated by Claude from publicly
reported values into `data/silicon_data_index.json`.

**To refresh:** in a Claude Code session at the repo root, run
`/update-silicon-data`. Claude searches @Silicon_Data posts and press
coverage, appends new dated points with sources, and commits. Estimated
points (derived from percent changes rather than directly reported) are
flagged and drawn as hollow circles.

## 云端每日快照（Daily Cloud Snapshot）

A Claude cloud routine (`market-sentiment-daily`, cron `0 2 * * *` UTC ≈
北京 10:00) clones this repo, runs `scripts/generate_static.py`, and
publishes the self-contained snapshot to the public Pages repo:

- **Latest:** https://soohucn-gif.github.io/market-sentiment-daily/
- **Archive:** one HTML per day under `archive/`
- **Notification:** PushNotification to the user's devices with the
  six current values + link (same channel as other routines)

Local generation (any time): `.venv/bin/python scripts/generate_static.py`
→ writes `dist/` (gitignored here; published copy lives in the public repo).

Cloud-IP caveats: AAII (Imperva) usually blocks datacenter IPs — the
fetcher falls back to the committed `data/aaii_seed.json` (weekly data,
45-day leash; refresh it locally now and then). StockCharts sources may
also throttle cloud IPs; failures degrade to error cards, never block
the build.

## Stack
- Python 3.10+ / Flask / yfinance / pandas / ECharts (CDN)
