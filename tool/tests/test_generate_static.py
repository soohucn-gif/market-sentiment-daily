"""Unit tests for the static HTML assembly — pure logic, no network."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from generate_static import build_static_html

TEMPLATE = """<!DOCTYPE html>
<html><head>
<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
</head><body>
<div id="overview"></div>
<script src="{{ url_for('static', filename='app.js') }}"></script>
</body></html>"""

CSS = "body { color: red; }"
JS = 'const x = "\\d+"; loadData(false);'
PAYLOAD = {"fetched_at": "2026-06-10T02:00:00+00:00",
           "indicators": {"vix": {"status": "ok", "history": []}}}


def test_css_is_inlined():
    html = build_static_html(TEMPLATE, CSS, JS, PAYLOAD)
    assert "<link rel=\"stylesheet\"" not in html
    assert CSS in html


def test_js_is_inlined_and_app_js_src_removed():
    html = build_static_html(TEMPLATE, CSS, JS, PAYLOAD)
    assert "url_for('static', filename='app.js')" not in html
    assert 'loadData(false);' in html


def test_payload_injected_before_app_js():
    html = build_static_html(TEMPLATE, CSS, JS, PAYLOAD)
    assert "window.__PRELOADED__" in html
    assert html.index("window.__PRELOADED__") < html.index("loadData(false);")
    assert '"fetched_at": "2026-06-10T02:00:00+00:00"' in html


def test_echarts_cdn_kept():
    html = build_static_html(TEMPLATE, CSS, JS, PAYLOAD)
    assert "echarts.min.js" in html


def test_script_close_tag_in_payload_is_escaped():
    payload = {"indicators": {"x": {"status": "error",
                                    "error_msg": "bad </script> tag"}}}
    html = build_static_html(TEMPLATE, CSS, JS, payload)
    assert "bad </script>" not in html  # must be escaped, else breaks HTML
    assert "<\\/script>" in html
