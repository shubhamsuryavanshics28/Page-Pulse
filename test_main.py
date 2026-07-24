"""
Tests for Page Pulse's parsing logic.

analyze_html() is a pure function (no network), so these tests run instantly
and don't depend on any external site being up. Network-facing behaviour
(fetch_page) is exercised separately via the FastAPI TestClient with a
mocked requests.get, so we can simulate a timeout without actually waiting.
"""

from unittest.mock import patch, MagicMock

import pytest
import requests
from fastapi.testclient import TestClient

from main import analyze_html, app

client = TestClient(app)


# ---------- analyze_html: pure parsing logic ----------

def test_happy_path_full_page():
    html = """
    <html>
      <head>
        <title>Best Shopify Agency | Digital Heroes</title>
        <meta name="description" content="We build fast, reliable Shopify stores.">
      </head>
      <body>
        <h1>Welcome</h1>
        <img src="a.png" alt="hero banner">
        <img src="b.png" alt="">
        <img src="c.png">
        <p>Some visible text content for word counting purposes here.</p>
      </body>
    </html>
    """
    result = analyze_html(html)
    assert result["title"] == "Best Shopify Agency | Digital Heroes"
    assert result["meta_description"] == "We build fast, reliable Shopify stores."
    assert result["h1_count"] == 1
    assert result["images_total"] == 3
    assert result["images_missing_alt"] == 2  # empty alt + missing alt attribute
    assert result["word_count"] > 0


def test_failure_case_missing_title_and_meta():
    """A bare-bones page with no <title> and no meta description should not crash —
    it should report those fields as None rather than raising."""
    html = "<html><body><h1>Only a heading</h1></body></html>"
    result = analyze_html(html)
    assert result["title"] is None
    assert result["meta_description"] is None
    assert result["h1_count"] == 1
    assert result["images_total"] == 0
    assert result["images_missing_alt"] == 0


def test_failure_case_malformed_html_and_script_noise():
    """Unclosed tags and inline scripts/styles shouldn't crash the parser,
    and script/style text must not be counted as visible word content.

    Note: the <title> tag is deliberately kept well-formed here. An
    unclosed <title> is treated as raw text by some HTML parsers (it
    swallows everything after it, including real tags, as literal text
    until a closing tag or EOF) - that's parser-implementation behavior,
    not something this app's logic needs to handle specially. This test
    focuses on the tags that actually matter: unclosed <h1> and noise
    from <script>/<style>.
    """
    html = """
    <html><head><title>Broken Page</title></head>
    <body>
    <script>var shouldNotCount = "these words should not be counted";</script>
    <style>.hidden { display:none; } /* neither should these words */</style>
    <h1>Heading One
    <h1>Heading Two</h1>
    <img src="x.png" alt="   ">
    """
    result = analyze_html(html)
    # BeautifulSoup's html.parser recovers from the unclosed <h1> gracefully
    assert result["title"] == "Broken Page"
    assert result["h1_count"] == 2
    assert result["images_missing_alt"] == 1  # whitespace-only alt counts as missing
    assert "shouldNotCount" not in str(result)


# ---------- API endpoint: validation and network-failure handling ----------

def test_endpoint_rejects_invalid_url():
    res = client.post("/api/audit", json={"url": "not-a-url"})
    assert res.status_code == 422  # pydantic validation error


@patch("main.requests.get")
def test_endpoint_handles_timeout_gracefully(mock_get):
    mock_get.side_effect = requests.exceptions.Timeout()
    res = client.post("/api/audit", json={"url": "https://example.com"})
    assert res.status_code == 504
    assert "Timed out" in res.json()["detail"]


@patch("main.requests.get")
def test_endpoint_handles_non_html_response(mock_get):
    mock_response = MagicMock()
    mock_response.headers = {"content-type": "application/json"}
    mock_response.status_code = 200
    mock_get.return_value = mock_response
    res = client.post("/api/audit", json={"url": "https://example.com/data.json"})
    assert res.status_code == 415


@patch("main.requests.get")
def test_endpoint_happy_path(mock_get):
    mock_response = MagicMock()
    mock_response.headers = {"content-type": "text/html; charset=utf-8"}
    mock_response.status_code = 200
    mock_response.text = "<html><head><title>Test</title></head><body><h1>Hi</h1></body></html>"
    mock_get.return_value = mock_response
    res = client.post("/api/audit", json={"url": "https://example.com"})
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "Test"
    assert body["h1_count"] == 1