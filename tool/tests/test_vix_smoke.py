from fetchers import vix


def test_vix_live():
    data = vix.fetch()
    assert data["status"] == "ok"
    assert data["current"]["value"] > 0
    assert len(data["history"]) > 1000  # VIX since 1990, lots of history
    assert data["history"][0]["date"] < data["history"][-1]["date"]
