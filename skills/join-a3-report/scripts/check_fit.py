#!/usr/bin/env python3
"""Render the report to a one-page A3 PDF and verify nothing overflows.

Usage:
    python check_fit.py report.html [report.pdf]

Exit code 0 means: PDF is exactly one page AND no section body is clipped.
Otherwise it prints which sections overflow and by how much, so you can
trim rows or shorten text and re-run. It also lists sparse panels and any
table / timeline cells that wrapped onto a second line (data rows should
not wrap; wrap=True tables are the deliberate exception). Uses the Chromium bundled with
Playwright (already installed in Claude's cloud workspace; elsewhere run
`pip install playwright && playwright install chromium`).
"""
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    html = Path(sys.argv[1]).resolve()
    pdf = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else html.with_suffix(".pdf")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html.as_uri())
        page.evaluate("document.fonts.ready.then(() => true)")
        page.emulate_media(media="print")
        overflow = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('section').forEach((s, i) => {
                const body = s.querySelector('.sec-body');
                const title = (s.querySelector('h2') || {}).textContent || `section ${i+1}`;
                const over = body.scrollHeight - body.clientHeight;
                const used = Array.from(body.children).reduce((h, c) => h + c.getBoundingClientRect().height, 0);
                const fill = body.clientHeight ? used / body.clientHeight : 1;
                if (over > 2) out.push({section: title.trim(), overflow_px: Math.round(over)});
                else if (fill < 0.55) out.push({section: title.trim(), fill_pct: Math.round(fill*100)});
                // data rows should not wrap: a table cell or timeline cell taller than ~1.6 lines has wrapped
                let wrapped = 0;
                body.querySelectorAll('table.list:not(.wrap) td, .tl-row .date, .tl-row .what').forEach(td => {
                    const lh = parseFloat(getComputedStyle(td).lineHeight) || 16;
                    const pad = parseFloat(getComputedStyle(td).paddingTop || 0) + parseFloat(getComputedStyle(td).paddingBottom || 0);
                    if (td.getBoundingClientRect().height - pad > lh * 1.6) wrapped++;
                });
                if (wrapped) out.push({section: title.trim(), wrapped_cells: wrapped});
            });
            const pg = document.querySelector('.page');
            const pageOver = pg.scrollHeight - pg.clientHeight;
            if (pageOver > 2) out.push({section: '<page>', overflow_px: Math.round(pageOver)});
            return out;
        }""")
        page.pdf(path=str(pdf), format="A3", landscape=True, print_background=True,
                 margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        browser.close()

    # Count pages without extra dependencies: PDF page objects.
    data = pdf.read_bytes()
    pages = data.count(b"/Type /Page") - data.count(b"/Type /Pages")
    try:
        from pypdf import PdfReader  # more reliable when available
        pages = len(PdfReader(str(pdf)).pages)
    except Exception:
        pass

    clipped = [o for o in overflow if "overflow_px" in o]
    sparse = [o for o in overflow if "fill_pct" in o]
    wrapped = [o for o in overflow if "wrapped_cells" in o]
    ok = pages == 1 and not clipped
    print(f"pdf: {pdf}")
    print(f"pages: {pages} {'OK' if pages == 1 else 'PROBLEM: must be exactly 1'}")
    if clipped:
        print("clipped content (reduce rows / shorten text):")
        for o in clipped:
            print(f"  - {o['section']}: {o['overflow_px']}px hidden")
    else:
        print("overflow: none")
    if sparse:
        print("sparse sections (under 55% of the panel used — add rows, a chart, or a short explanation; white space reads as missing data):")
        for o in sparse:
            print(f"  - {o['section']}: {o['fill_pct']}% filled")
    if wrapped:
        print("wrapped data rows (cells should stay on one line — shorten the text, drop a column, or let the name truncate):")
        for o in wrapped:
            print(f"  - {o['section']}: {o['wrapped_cells']} cells wrap")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
