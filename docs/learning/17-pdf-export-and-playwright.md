# A17 — PDF export and Playwright

> **Status:** done. A "Download PDF" button next to the score ring saves the
> report you're looking at as a real PDF file.

## What we built

The button POSTs the report already showing on screen to a new backend
endpoint, `POST /scan/pdf`. That endpoint rebuilds the report as a plain HTML
page — by hand, in Python, since there's no React on the server — hands that
HTML to a real but invisible ("headless") browser via a library called
Playwright, asks it to print, and streams the resulting PDF bytes back. The
frontend turns those bytes into a file the browser saves to disk.

## The one big idea: a headless browser

"Headless" means a real browser engine — the same code that runs Chrome —
running with no visible window, driven entirely by code: open a page, set
some HTML, ask it to do something, close it.

Why reach for a whole browser just to make a PDF? A PDF is basically "print
this webpage," and browsers have done that correctly for decades — real CSS,
real fonts, real layout, for free. An HTML-to-PDF *library* has to reimplement
all of that itself, and usually has gaps (our score ring uses inline SVG,
which plenty of lightweight PDF libraries choke on). Using an actual browser
sidesteps the problem instead of solving it twice.

**Playwright** is the library that drives one. Small standalone example — run
`python -m playwright install chromium` once, then run this:

```python
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content("<h1 style='color: teal'>Hello, PDF</h1>")
        await page.pdf(path="hello.pdf")
        await browser.close()

asyncio.run(main())
```

A real `hello.pdf` appears, with proper font rendering, and no window ever
opened. `backend/report/pdf.py`'s `generate_pdf()` does exactly this, just
with a much longer HTML string, and `page.pdf()` returning bytes instead of
writing to disk, since those bytes need to travel over HTTP.

## The other thing worth knowing: escaping untrusted text

`render_html()` builds the page from Python f-strings — including text that
came from a *scanned website*, like a finding's `evidence` field, which might
hold the literal text of an HTTP header. If that text contains `<` and `>` and
gets dropped into the HTML unescaped, a stray `<script>` tag would genuinely
execute inside the page being printed, since Playwright is a real browser.

The fix is `html.escape()`, applied to every piece of dynamic text:

```python
from html import escape

comment = "nice site! <script>alert('hi')</script>"
print(f"<p>{escape(comment)}</p>")
# <p>nice site! &lt;script&gt;alert(&#x27;hi&#x27;)&lt;/script&gt;</p>
```

It still reads the same to a person, but a browser now treats it as inert text
instead of running it as markup. Every `escape(...)` call in `pdf.py` exists
for this reason.

## The actual code

`render_html()` is the Python twin of `Report.tsx` — same score-ring math,
same category grouping — rebuilt by hand because Python can't run a React
component. The endpoint takes the whole report as its request body, not just
a URL:

```python
@app.post("/scan/pdf")
async def scan_pdf(report: ScanReport) -> Response:
    pdf_bytes = await generate_pdf(report)
    ...
    return Response(content=pdf_bytes, media_type="application/pdf", ...)
```

Re-running the scan server-side was rejected on purpose — a site's headers
could change between the on-screen scan and the PDF export moments later, so
the file could disagree with what's on screen. Sending the whole report
guarantees the PDF matches exactly what the user is looking at.

On the frontend, a PDF is binary data, not JSON — `fetch()` hands that back as
a **`Blob`**, and `URL.createObjectURL()` turns it into a temporary link an
`<a>` tag can "download":

```javascript
const blob = await response.blob();
const url = URL.createObjectURL(blob);
const link = document.createElement("a");
link.href = url;
link.download = "sentinels-example-com.pdf";
link.click();   // never added to the page -- click() alone starts the save
```

One real bug worth knowing: on Windows, running the server with
`uvicorn --reload` switches Python to an event loop that can't start
subprocesses — and Playwright's browser *is* a subprocess. `pdf.py` works
around this by running the PDF generation on its own dedicated event loop in a
separate thread, so exporting still works even under `--reload`.

## Try it

1. Time `generate_pdf()` and compare to a scan's own `duration_ms` — launching
   a whole browser process costs more than all five scan agents combined.
2. POST a hand-crafted report with a finding title of `<b>bold text</b>` to
   `/scan/pdf` and open the PDF — the title should read as literal text, not
   render bold. Comment out that one `escape()` call and try again to see it
   actually render bold.
3. In `generate_pdf()`, change `print_background=True` to `False` and export
   again — the dark page background disappears, since browsers skip
   background colours when printing unless told otherwise.

## A few words worth knowing

- **Headless browser** — a real browser engine running with no visible
  window, driven entirely by code.
- **Playwright** — the library used here to launch and control headless
  Chromium.
- **`html.escape()`** — converts `<`, `>`, `&`, and quotes into inert HTML-entity
  text, so untrusted text can't be interpreted as markup.
- **`Blob`** / **object URL** — the browser's way of holding raw binary data
  and giving it a temporary URL an `<a download>` can point at.

---

**Next:** the roadmap's remaining follow-ups — see `docs/ROADMAP.md`.
