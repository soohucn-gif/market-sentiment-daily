"""Unit tests for fetchers/_net.py seed helpers — deterministic, no network."""
import json
import time
from pathlib import Path

from fetchers import _net


def test_seed_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(_net, "SEED_DIR", tmp_path)
    payload = {"status": "ok", "current": {"value": 1.5}, "history": [{"date": "2026-06-01", "value": 1.5}]}
    _net.save_seed("demo", payload)
    loaded = _net.load_seed("demo", max_age_days=7)
    assert loaded is not None
    assert loaded["current"]["value"] == 1.5
    assert "stale_since_iso" in loaded  # annotated on load


def test_seed_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(_net, "SEED_DIR", tmp_path)
    # Write an envelope dated far in the past
    old = {"saved_at_iso": "2020-01-01T00:00:00+00:00", "payload": {"status": "ok"}}
    (tmp_path / "demo_seed.json").write_text(json.dumps(old))
    assert _net.load_seed("demo", max_age_days=45) is None


def test_seed_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(_net, "SEED_DIR", tmp_path)
    assert _net.load_seed("nope", max_age_days=7) is None


def test_curl_get_rejects_bad_exit(monkeypatch):
    # curl against an unroutable address fails fast with a clear error
    try:
        _net.curl_get("http://127.0.0.1:9", timeout=2)
        raised = False
    except RuntimeError as e:
        raised = True
        assert "curl" in str(e)
    assert raised
