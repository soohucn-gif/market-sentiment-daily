"""Smoke test — hits live CNN endpoint. Skip if offline."""
from fetchers import cnn_fng


def test_cnn_fng_live():
    data = cnn_fng.fetch()
    assert data["status"] == "ok"
    assert 0 <= data["current"]["value"] <= 100
    assert isinstance(data["current"]["label"], str)
    assert len(data["history"]) > 100
    first, last = data["history"][0], data["history"][-1]
    assert "date" in first and "value" in first
    assert first["date"] < last["date"]
