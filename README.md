# Page Pulse

A small tool that audits any URL: HTTP status, response time, title, meta
description, H1 count, images missing alt text, and approximate word count.

Built for the Digital Heroes SDE internship task kit (Task A + Task B).

---

## Setup

```bash
git clone <this-repo-url>
cd page-pulse
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open **http://localhost:8000** — the frontend is served directly by the
backend, so there's nothing else to run.

Run the tests:

```bash
pip install pytest httpx
pytest -v
```

---

## API contract

### `POST /api/audit`

**Request body**

```json
{ "url": "https://example.com" }
```

`url` must include the scheme (`http://` or `https://`) and a domain.
Anything else returns `422` before a network call is even attempted.

**Success response — `200`**

```json
{
  "url": "https://example.com",
  "http_status": 200,
  "response_time_ms": 227.6,
  "title": "Example Domain",
  "meta_description": null,
  "h1_count": 1,
  "images_total": 0,
  "images_missing_alt": 0,
  "word_count": 28
}
```

**Error responses**

| Status | When |
|---|---|
| `422` | URL fails validation (bad format), or the server returned a valid response but it wasn't parseable as expected |
| `502` | Could not connect to the target host |
| `504` | Target host didn't respond within 8 seconds |
| `415` | Target URL responded, but with non-HTML content (e.g. a JSON API, a PDF, an image) |

Every failure mode returns a JSON `{"detail": "..."}` — the API never returns
a bare 500 or a stack trace for an expected failure.

---

## Three design decisions

**1. Parsing logic is a pure function, separate from the network call.**
`analyze_html(html: str) -> dict` takes a string and returns the report — no
`requests` call inside it. This is what makes the test suite fast and
reliable: the happy-path and malformed-HTML tests run in milliseconds and
don't depend on any external site staying up. `fetch_page()` handles timing,
status codes, and content-type checks separately, and is the only place
network exceptions are caught.

**2. Used `html.parser` instead of `lxml` as BeautifulSoup's backend.**
`lxml` is faster but is a C extension that needs to compile or ship binaries,
which adds friction on free-tier deploy targets (Render, Railway) that build
from a clean image. `html.parser` is part of the Python standard library, so
the only real dependency is `beautifulsoup4` itself. For a single-page audit
tool, the speed difference is irrelevant — reliability of the deploy isn't.

**3. Backend serves the frontend directly instead of splitting into two
deployed services.** A separate frontend/backend deploy means CORS
configuration, two free-tier services to keep awake, and two URLs to hand
in. Since the frontend is one static HTML file with no build step, FastAPI
just serves it directly (`FileResponse` + `StaticFiles` mount). One
`uvicorn` process, one URL, nothing to keep in sync.

---

## What I'd change with another day

- Add a lightweight cache (even an in-memory TTL dict) so re-auditing the
  same URL within a few minutes doesn't refetch it.
- Surface *why* an image is missing alt text differently — a decorative
  icon missing alt is a different problem than a product photo missing alt,
  and right now they're counted the same.
- Add a basic rate limiter so the tool can't be pointed at one target
  repeatedly in a tight loop.

---

## AI usage disclosure

*(Personalize this paragraph honestly before submitting — see the note in
chat for what to say here.)*
