"""Market breadth fetcher: % of NDX-100 / SPX-500 stocks above their 50-day MA.

Scraped from StockCharts (fragile -- may break if site changes). StockCharts
does not expose `$NDXA50R` / `$SPXA50R` via any official free API, and Yahoo
dropped these symbols. We hit the `/c-sc/sc` SharpCharts endpoint in inspector
mode (`img=text&inspector=yes`). The response is `Content-Type: text/plain`
whose body begins with a base64-encoded PNG payload (`img/png;base64,...`),
followed by `<chartdata>` / `<pricedata>` text blocks describing the bars
(no binary GIF magic bytes -- don't look for `GIF89a`). We parse the
`<pricedata>` block (pipe-separated `x date_open date_close O H L C V`).
A valid chart-style id (`i=`) is required; we use the public 'Simple Line
Chart' pcode `p22657737025`.

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
        # Enforce exact 8-token schema: idx, date_open (YYYYMMDDHHMM), date_close, O, H, L, C, V.
        # A looser guard (e.g. `< 7`) would silently accept a 7-token shape where
        # parts[6] becomes V (always 0 for breadth indices), emitting an all-zero series.
        if len(parts) != 8:
            continue
        date_str = parts[1][:8]  # YYYYMMDD
        close = float(parts[6])
        out.append({"date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}", "value": close})
    out.sort(key=lambda h: h["date"])
    return out


def _fetch_live() -> dict:
    ndx = _fetch_series("$NDXA50R")
    spx = _fetch_series("$SPXA50R")
    if not ndx or not spx:
        raise RuntimeError("breadth: empty series returned from StockCharts")
    return {
        "status": "ok",
        "current": {"ndx": ndx[-1]["value"], "spx": spx[-1]["value"]},
        "ndx": ndx,
        "spx": spx,
    }


def fetch():
    try:
        payload = _fetch_live()
        _net.save_seed("breadth", payload)
        return payload
    except Exception as live_err:
        seeded = _net.load_seed("breadth", _SEED_MAX_AGE_DAYS)
        if seeded is not None:
            return seeded
        raise live_err
