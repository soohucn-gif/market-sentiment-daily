from fetchers import aaii


def test_aaii_live():
    data = aaii.fetch()
    assert data["status"] == "ok"
    for k in ("bullish", "neutral", "bearish"):
        series = data[k]
        assert len(series) > 50
        assert 0 <= series[-1]["value"] <= 100
    cur = data["current"]
    assert {"bullish", "neutral", "bearish"} <= set(cur.keys())
