"""Flask app for the market sentiment dashboard."""
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import logging
from flask import Flask, jsonify, render_template, request
from werkzeug.serving import WSGIRequestHandler
# Avoid macOS reverse-DNS startup hangs (~30s on some networks)
WSGIRequestHandler.address_string = lambda self: self.client_address[0]

from cache import TTLCache
from fetchers import cnn_fng, vix, breadth, aaii, putcall, silicon_data

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("sentiment")

_cache = TTLCache(ttl_seconds=600)  # 10 min

FETCHERS = {
    "fng": cnn_fng.fetch,
    "vix": vix.fetch,
    "breadth": breadth.fetch,
    "aaii": aaii.fetch,
    "putcall": putcall.fetch,
    "sdtoken": silicon_data.fetch,
}


def _safe(key, fn):
    try:
        return key, fn()
    except Exception as e:
        log.exception("Fetcher %s failed", key)
        return key, {"status": "error", "error_msg": f"{type(e).__name__}: {e}"}


def gather_indicators(force: bool = False) -> dict:
    cache_key = "indicators_payload"
    if not force:
        cached = _cache.get(cache_key)
        if cached:
            return cached

    indicators = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        future_to_key = {pool.submit(_safe, k, fn): k for k, fn in FETCHERS.items()}
        try:
            for fut in as_completed(future_to_key, timeout=30):
                key, data = fut.result()
                indicators[key] = data
        except concurrent.futures.TimeoutError:
            log.warning("Orchestrator timeout — some fetchers did not complete in 30s")
        # Fill in any fetcher that didn't return in time
        for fut, key in future_to_key.items():
            if key not in indicators:
                if fut.done() and not fut.cancelled():
                    try:
                        _, data = fut.result()
                        indicators[key] = data
                    except Exception as e:
                        indicators[key] = {"status": "error", "error_msg": f"{type(e).__name__}: {e}"}
                else:
                    indicators[key] = {"status": "error", "error_msg": "orchestrator timeout"}

    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "indicators": indicators,
    }
    _cache.set(cache_key, payload)
    return payload


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/indicators")
def api_indicators():
    force = request.args.get("force") == "1"
    return jsonify(gather_indicators(force=force))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5055, debug=False)
