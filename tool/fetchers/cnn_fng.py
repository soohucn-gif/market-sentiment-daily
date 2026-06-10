"""CNN Fear & Greed Index fetcher.

Source: CNN's internal dataviz API. Not officially supported — may change.
Transport: system curl (see _net). CNN's edge returns 418 to curl without
a Referer; browser UA + Accept + Referer gets JSON. On failure (e.g.
datacenter IPs in cloud runs) falls back to the committed seed.
"""
import json
from datetime import datetime, timezone

from . import _net

URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
HEADERS = {
    "Accept": "application/json",
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
}
_SEED_MAX_AGE_DAYS = 30


def _fetch_live() -> dict:
    raw = json.loads(_net.curl_get(URL, headers=HEADERS, timeout=20))

    current = raw["fear_and_greed"]
    hist_points = raw["fear_and_greed_historical"]["data"]

    history = [
        {
            "date": datetime.fromtimestamp(p["x"] / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
            "value": round(p["y"], 1),
        }
        for p in hist_points
    ]
    history.sort(key=lambda h: h["date"])

    return {
        "status": "ok",
        "current": {
            "value": round(current["score"], 1),
            "label": current["rating"],
        },
        "history": history,
    }


def fetch():
    try:
        payload = _fetch_live()
        _net.save_seed("fng", payload)
        return payload
    except Exception as live_err:
        seeded = _net.load_seed("fng", _SEED_MAX_AGE_DAYS)
        if seeded is not None:
            return seeded
        raise live_err
