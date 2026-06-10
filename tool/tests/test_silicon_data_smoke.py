"""Offline test — reads the curated local data file, no network."""
from fetchers import silicon_data


def test_silicon_data_curated_series():
    data = silicon_data.fetch()
    assert data["status"] == "ok"
    assert 0.1 < data["current"]["value"] < 20.0
    assert len(data["history"]) >= 3
    dates = [p["date"] for p in data["history"]]
    assert dates == sorted(dates), "history must be ascending by date"
    assert data["current"]["value"] == data["history"][-1]["value"]
    assert data["current"]["date"] == data["history"][-1]["date"]
    # Every curated point must carry a value in plausible index range
    assert all(0.1 < p["value"] < 20.0 for p in data["history"])
