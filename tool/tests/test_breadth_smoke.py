from fetchers import breadth


def test_breadth_live():
    data = breadth.fetch()
    assert data["status"] == "ok"
    for key in ("ndx", "spx"):
        series = data[key]
        assert isinstance(series, list)
        assert len(series) > 100
        # Latest value must be strictly > 0: a breadth indicator hitting exactly
        # 0.0% above 50DMA is essentially impossible (would mean every single
        # stock is below its 50DMA, which historically has never happened).
        assert 0 < series[-1]["value"] <= 100
        # Series must have actual variation -- catches all-zero / all-same silent
        # bugs where the parser picks the wrong column (e.g. Volume, always 0).
        values = {p["value"] for p in series}
        assert len(values) > 5, f"{key} series suspiciously constant: {values}"
    assert "ndx" in data["current"] and "spx" in data["current"]
