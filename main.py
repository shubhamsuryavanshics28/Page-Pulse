"""
Page Pulse — a small URL auditing tool.

Backend built with FastAPI. Given any URL, fetches the page and returns
a JSON report: HTTP status, response time, title, meta description,
H1 count, images missing alt text, and approximate word count.

Design note: the parsing logic (analyze_html) is a pure function with
no network calls, so it can be unit tested directly. Network fetching
(fetch_page) is a separate function, so failures there (timeouts, bad
URLs, non-HTML responses) are handled independently and never crash
the parser.
"""

import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

app = FastAPI(title="Page Pulse", description="Audit any URL for basic SEO/health signals.")

REQUEST_TIMEOUT_SECONDS = 8
USER_AGENT = "PagePulse/1.0 (+https://digitalheroesco.com) Training Task Bot"


class AuditRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def url_must_look_valid(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("URL must start with http:// or https:// and include a domain.")
        return value


def analyze_html(html: str) -> dict:
    """
    Pure parsing function: takes raw HTML text, returns the audit fields.
    No network access here — this is what unit tests exercise directly.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title = soup.title.get_text(strip=True) if soup.title and soup.title.string else None

    # Meta description
    meta_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = None
    if meta_tag and meta_tag.get("content"):
        meta_description = meta_tag["content"].strip()

    # H1 count
    h1_count = len(soup.find_all("h1"))

    # Images missing alt text (missing attribute OR empty/whitespace-only alt)
    images = soup.find_all("img")
    images_missing_alt = sum(
        1 for img in images if not img.get("alt") or not img.get("alt").strip()
    )

    # Approximate word count: strip script/style tags, then count whitespace-split tokens
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible_text = soup.get_text(separator=" ")
    word_count = len([w for w in visible_text.split() if w.strip()])

    return {
        "title": title,
        "meta_description": meta_description,
        "h1_count": h1_count,
        "images_total": len(images),
        "images_missing_alt": images_missing_alt,
        "word_count": word_count,
    }


def fetch_page(url: str) -> dict:
    """
    Fetches the URL and returns timing + status + raw HTML.
    Raises HTTPException with a sensible status code and message for every
    failure mode we expect (timeout, connection failure, non-HTML response)
    so the API never returns a raw 500 / stack trace to the client.
    """
    start = time.perf_counter()
    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail=f"Timed out after {REQUEST_TIMEOUT_SECONDS}s waiting for a response from that URL.",
        )
    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=502,
            detail="Could not connect to that URL. Check the domain and try again.",
        )
    except requests.exceptions.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Request failed: {exc}")

    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type.lower():
        raise HTTPException(
            status_code=415,
            detail=f"That URL returned '{content_type or 'unknown'}' content, not HTML. "
            "Page Pulse only audits HTML pages.",
        )

    return {
        "http_status": response.status_code,
        "response_time_ms": elapsed_ms,
        "html": response.text,
    }


@app.post("/api/audit")
def audit(payload: AuditRequest):
    fetched = fetch_page(payload.url)
    parsed = analyze_html(fetched["html"])
    return {
        "url": payload.url,
        "http_status": fetched["http_status"],
        "response_time_ms": fetched["response_time_ms"],
        **parsed,
    }


# --- Serve the frontend (single static page) ---
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse("frontend/index.html")
