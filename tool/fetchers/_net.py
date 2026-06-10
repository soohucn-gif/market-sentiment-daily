"""Shared transport + seed-fallback helpers for fetchers.

Transport: every external source here (CNN, StockCharts, Yahoo, AAII)
fingerprints TLS handshakes and/or blocks datacenter IPs. Python
requests/urllib3 gets flagged as a bot far more often than system curl,
so all fetchers shell out to curl with browser-like headers.

Seeds: each fetcher persists its last good payload to
`data/{name}_seed.json` (committed to the repo). When a live fetch
fails — typical for cloud runs whose datacenter IPs upstream WAFs
reject — the fetcher falls back to its seed, annotated with
`stale_since_iso` so the UI can show data age. Local runs (residential
IP) refresh seeds on every success.
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SEED_DIR = Path(__file__).parent.parent / "data"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def curl_get(url: str, headers: dict | None = None, timeout: int = 30) -> bytes:
    """GET via system curl (browser TLS fingerprint). Raises RuntimeError on failure."""
    cmd = ["curl", "-sS", "--fail", "--compressed", "--max-time", str(timeout), "-A", UA]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    try:
        result = subprocess.run(cmd, capture_output=True, check=True, timeout=timeout + 5)
    except FileNotFoundError as e:
        raise RuntimeError("curl not found on PATH") from e
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode(errors="replace").strip()[:200]
        raise RuntimeError(f"curl failed for {url}: {err}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"curl timed out after {timeout}s for {url}") from e
    return result.stdout


def save_seed(name: str, payload: dict) -> None:
    """Persist a fetcher's last good payload. Best-effort — never raises."""
    try:
        SEED_DIR.mkdir(parents=True, exist_ok=True)
        envelope = {
            "saved_at_iso": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        (SEED_DIR / f"{name}_seed.json").write_text(
            json.dumps(envelope, ensure_ascii=False)
        )
    except OSError:
        pass


def load_seed(name: str, max_age_days: float) -> dict | None:
    """Return the seeded payload annotated with `stale_since_iso`, or None."""
    try:
        envelope = json.loads((SEED_DIR / f"{name}_seed.json").read_text())
        saved_at = datetime.fromisoformat(envelope["saved_at_iso"])
        age_days = (datetime.now(timezone.utc) - saved_at).total_seconds() / 86400
        if age_days > max_age_days:
            return None
        payload = dict(envelope["payload"])
        payload["stale_since_iso"] = envelope["saved_at_iso"]
        return payload
    except (OSError, ValueError, KeyError):
        return None
