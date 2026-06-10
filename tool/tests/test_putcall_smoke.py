from fetchers import putcall


def test_putcall_live():
    data = putcall.fetch()
    assert data["status"] == "ok"
    assert 0.1 < data["current"]["value"] < 3.0
    assert len(data["history"]) > 100
