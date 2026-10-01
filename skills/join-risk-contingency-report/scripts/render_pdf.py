#!/usr/bin/env python3
"""Render report.html to a Letter-landscape PDF and check that it has exactly
the pages the builder laid out (three, plus any appendix pages) with nothing
clipped; also writes a PNG preview of each page so you can look at the result.

Usage:
    python render_pdf.py work/report.html [work/report.pdf]

Exit code 0: page count matches, no page content clipped. Otherwise it prints which
page overflows and by how much (trim rows in build_report's tables or
shorten notes; don't shrink the template's type). Uses Playwright's Chromium
(installed in Claude's cloud workspace; elsewhere `pip install playwright &&
playwright install chromium`).
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
        page = browser.new_page(viewport={"width": 1100, "height": 850})
        page.goto(html.as_uri())
        page.evaluate("document.fonts.ready.then(() => true)")
        page.wait_for_timeout(300)
        page.emulate_media(media="print")
        problems = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.page').forEach((pg, i) => {
                const main = pg.querySelector('main');
                const over = main.scrollHeight - main.clientHeight;
                if (over > 1) out.push(`page ${i+1}: content overflows by ${over}px`);
                pg.querySelectorAll('.block, .col').forEach(b => {
                    const o = b.scrollHeight - b.clientHeight;
                    if (o > 1) out.push(`page ${i+1}: a ${b.className} block is clipped by ${o}px`);
                });
            });
            return out;
        }""")
        page.pdf(path=str(pdf), format="Letter", landscape=True, print_background=True,
                 margin={"top": "0", "right": "0", "bottom": "0", "left": "0"}, prefer_css_page_size=True)
        page.emulate_media(media="screen")
        pages = page.query_selector_all(".page")
        expected = int(page.evaluate("() => document.body.dataset.pages || document.querySelectorAll('.page').length"))
        for i, el in enumerate(pages, 1):
            el.screenshot(path=str(html.with_name(f"{html.stem}-page{i}.png")))
        browser.close()

    try:
        from pypdf import PdfReader
        n = len(PdfReader(str(pdf)).pages)
    except Exception:
        import re
        n = len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))
    print(f"wrote {pdf}: {n} page(s); previews {html.stem}-page1..{len(pages)}.png")
    if n != expected:
        problems.append(f"PDF has {n} pages, expected {expected} — a section spilled over")
    for pr in problems:
        print("PROBLEM:", pr)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
