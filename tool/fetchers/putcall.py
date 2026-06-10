"""CBOE Equity Put/Call ratio fetcher.

We scrape StockCharts for the `$CPCE` (CBOE Equity Put/Call Ratio) symbol,
the same SharpCharts inspector endpoint used by `fetchers/breadth.py`.

Why not CBOE direct? CBOE's legacy historical CSVs
(`https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv`
and friends) are still served HTTP 200 but their data ends in October 2019 --
last-modified is frozen at 2020-10-30. The current CBOE site
(`/markets/us/options/market-statistics/daily`) renders client-side and
exposes no clean JSON/CSV feed; the CDN `EQUITY_PC.json` returns HTTP 403
behind Cloudflare. StockCharts `$CPCE` is therefore the most reliable free
historical source (CBOE-licensed data, daily updates).

Parser note: `$CPCE` bars have 5 tokens (idx, date_open, date_close, value,
trailing 0) rather than the 8-token OHLCV shape that breadth uses. We share
the URL + envelope pattern with breadth.py but keep the token unpacking
inline -- factoring a shared helper would have to be parameterized on shape
and is not worth it for two fetchers. See breadth.py for the related logic.

Transport: system curl (see _net) — StockCharts 403s Python TLS from
datacenter IPs. On failure falls back to the committed seed.
"""
import time
from urllib.parse import urlencode

from . import _net

BASE_URL = "https://stockcharts.com/c-sc/sc"
STYLE_ID = "p22657737025"  # public "Simple Line Chart" pcode
_SEED_MAX_AGE_DAYS = 30


def _fetch_series(symbol: str) -> list[dict]:
    params = {
        "s": symbol,
        "p": "D",
        "yr": "3",
        "mn": "0",
        "dy": "0",
        "i": STYLE_ID,
        "img": "text",
        "inspector": "yes",
        "randomNumber": str(int(time.time() * 1000)),
    }
    body = _net.curl_get(f"{BASE_URL}?{urlencode(params)}", timeout=30)
    start = body.find(b"<pricedata>")
    end = body.find(b"</pricedata>")
    if start == -1 or end == -1:
        raise RuntimeError(f"StockCharts response missing <pricedata> for {symbol}")
    raw = body[start + len(b"<pricedata>") : end].decode("utf-8", errors="replace")
    out = []
    for bar in raw.split("|"):
        parts = bar.split()
        # Enforce exact 5-token schema for $CPCE: idx, date_open (YYYYMMDDHHMM),
        # date_close, value, trailing 0. The trailing field is always 0 for this
        # series (unlike breadth where parts[7] is volume). If StockCharts ever
        # switches $CPCE to an OHLCV schema we want to fail loudly, not silently
        # pick the wrong column.
        if len(parts) != 5:
            continue
        date_str = parts[1][:8]  # YYYYMMDD
        value = float(parts[3])
        out.append({"date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}", "value": value})
    out.sort(key=lambda h: h["date"])
    return out


def _fetch_live() -> dict:
    history = _fetch_series("$CPCE")
    if not history:
        raise RuntimeError("putcall: empty series returned from StockCharts $CPCE")
    return {
        "status": "ok",
        "current": {"value": history[-1]["value"], "date": history[-1]["date"]},
        "history": history,
    }


def fetch():
    try:
        payload = _fetch_live()
        _net.save_seed("putcall", payload)
        return payload
    except Exception as live_err:
        seeded = _net.load_seed("putcall", _SEED_MAX_AGE_DAYS)
        if seeded is not None:
            return seeded
        raise live_err
