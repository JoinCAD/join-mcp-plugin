#!/usr/bin/env python3
"""Render model.json (from risk_model.py) into the Risk & Contingency
Analysis: Assumptions · Expected outcome · Range of outcomes · Risks appendix.

Usage:
    python build_report.py work/model.json work/report.html [--created "29 Sep 2026, 14:02 PDT"]

Pages: 1 Assumptions (base cost · adjustments · assumed probabilities),
2 Expected outcome (waterfall, walk, contingency), 3 Range of outcomes
(Monte Carlo), then an appendix listing every open risk with its treatment.

The output is one HTML file (the Join mark inlined; Red Hat Text loads from
Google Fonts) laid out for US Letter landscape, one section per page; render it
with render_pdf.py. The waterfall reproduces the app's Cost Risk Calculator
chart (komodo-ui DashboardCharts/CostRiskCalculator): blue base, yellow
pending adds/deducts, orange risks, hatched full exposure over solid expected
value, the black "snake" to the Projected chip, and dashed Budget / Running
Total reference lines with labels on the right.
"""
import html
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from risk_model import money, LIKELIHOOD_LABELS, IMPACT_LABELS, SCENARIO_LABELS, RISK_SCENARIOS  # noqa: E402

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"

C = {  # Join tokens (references/join-design.md)
    "primary": "#000", "muted": "#9B9B9B", "secondary": "#686B6C", "link": "#4B71A9",
    "border": "#D0D5D7", "separator": "#E7EAEF", "bg1": "#F6F7F9",
    "base": "#4B71A9", "adds": "#F6B901", "deducts": "#F6B901", "risks": "#F49144",
    "budget": "#4B71A9", "success": "#6AAF6F", "error": "#E11E29",
}
CHIP_TEXT = {"base": "#fff", "adds": "#000", "deducts": "#000", "risks": "#000"}


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def join_mark():
    p = ASSETS / "join-logo.svg"
    svg = p.read_text() if p.exists() else ""
    return svg.replace("<svg", '<svg class="join-mark"', 1)


def si(v):
    """d3 '~s' style tick: 34M, 1.5B, 250K."""
    a = abs(v)
    if a >= 1e9:
        s = f"{v/1e9:g}B"
    elif a >= 1e6:
        s = f"{v/1e6:g}M"
    elif a >= 1e3:
        s = f"{v/1e3:g}K"
    else:
        s = f"{v:g}"
    return s


def nice_ticks(lo, hi, n=5):
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if raw <= step:
            break
    start = math.ceil(lo / step) * step
    ticks = []
    t = start
    while t <= hi + 1e-9:
        ticks.append(t)
        t += step
    return ticks


def text_w(s, size=12):
    return len(s) * size * 0.56


def chip_svg(x, y, label, placement="top", bg=None, fg=None, size=12):
    """The app's SVG Chip: 24px tall pill centred on x, above (top) or below (bottom) y."""
    h, gap, pad = 22, 6, 7
    w = text_w(label, size) + 2 * pad
    ty = y - gap - h if placement == "top" else y + gap
    fg = fg or C["primary"]
    rect = f'<rect x="{x - w/2:.1f}" y="{ty:.1f}" width="{w:.1f}" height="{h}" rx="4" fill="{bg}"/>' if bg else ""
    return (f'<g>{rect}<text x="{x:.1f}" y="{ty + h/2:.1f}" text-anchor="middle" dominant-baseline="central" '
            f'font-size="{size}" font-weight="500" fill="{fg}">{esc(label)}</text></g>')

# ------------------------------------------------------------ waterfall svg

def waterfall_svg(model, width=860, height=600):
    wf = model["waterfall"]
    ml, mr, mt, mb = 74, 128, 40, 52
    iw, ih = width - ml - mr, height - mt - mb
    bars = [wf["base"], wf["adds"], wf["deducts"], wf["risks"]]
    labels = {"base": "Base Cost", "adds": "Exp. Adds", "deducts": "Exp. Deducts", "risks": "Exp. Risks", "projected": "Projected"}
    lines = []
    if wf.get("budget"):
        lines.append(("budget", wf["budget"], "Budget", C["budget"], "10 4"))
    lines.append(("runningTotal", wf["running_total"], "Running Total", C["primary"], "6 3"))

    # y domain, as chartScale.ts
    base_v = bars[0]["expected"]
    deltas = [b["extent"] - b["baseline"] for b in bars[1:]]
    lo = base_v + sum(d for d in deltas if d < 0)
    hi = base_v + sum(d for d in deltas if d > 0)
    vals = [lo, hi] + [v for _, v, *_ in lines] + [bars[0]["extent"]]
    vmin, vmax = min(vals), max(vals)
    vpp = (vmax - vmin) / ih if vmax > vmin else 1
    dom_lo, dom_hi = vmin - vpp * 38, vmax + vpp * 38

    def y(v):
        return mt + ih - (v - dom_lo) / (dom_hi - dom_lo) * ih

    # x layout, as d3 scaleBand with padding 0.28 and bar padding 0.15
    keys = [b["type"] for b in bars] + ["projected"]
    n, padding = len(keys), 0.28
    step = iw / (n - padding + 2 * padding)
    band = step * (1 - padding)
    cols = {}
    for i, k in enumerate(keys):
        x0 = ml + padding * step + i * step
        left = x0 + band * 0.15
        cols[k] = (left, left + band * 0.7)

    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']
    out.append('<defs>')
    for k in ("base", "adds", "risks"):
        out.append(f'<pattern id="hatch-{k}" width="5" height="5" patternUnits="userSpaceOnUse">'
                   f'<path d="M-1,1 l2,-2 M0,5 l5,-5 M4,6 l2,-2" stroke="{C[k]}" stroke-width="1"/></pattern>')
    out.append(f'<clipPath id="plot"><rect x="{ml}" y="{mt}" width="{iw}" height="{ih}"/></clipPath></defs>')

    # y axis: grid, ticks, label
    for t in nice_ticks(dom_lo, dom_hi, 5):
        yy = y(t)
        out.append(f'<line x1="{ml}" x2="{ml + iw}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{C["separator"]}"/>')
        out.append(f'<text x="{ml - 10}" y="{yy:.1f}" text-anchor="end" dominant-baseline="central" font-size="12" fill="{C["secondary"]}">{si(t)}</text>')
    out.append(f'<line x1="{ml}" x2="{ml}" y1="{mt}" y2="{mt + ih}" stroke="{C["border"]}"/>')
    out.append(f'<line x1="{ml}" x2="{ml + iw}" y1="{mt + ih}" y2="{mt + ih}" stroke="{C["border"]}"/>')
    out.append(f'<text transform="translate(16 {mt + ih/2:.1f}) rotate(-90)" text-anchor="middle" font-size="12" fill="{C["secondary"]}">Cost in USD $</text>')

    # reference lines; labels (two 11px lines each) are pushed apart when two lines sit within 30px
    ordered = sorted(lines, key=lambda l: y(l[1]))
    label_y = [y(v) for _, v, *_ in ordered]
    for i in range(1, len(label_y)):
        if label_y[i] - label_y[i - 1] < 30:
            shift = 30 - (label_y[i] - label_y[i - 1])
            label_y[i - 1] -= shift / 2
            label_y[i] += shift / 2
    for (_, v, label, color, dash), ly in zip(ordered, label_y):
        yy = y(v)
        out.append(f'<line x1="{ml}" x2="{ml + iw}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{color}" stroke-dasharray="{dash}" opacity="0.7"/>')
        out.append(f'<text x="{ml + iw + 8}" y="{ly - 4:.1f}" font-size="11" font-weight="700" fill="{color}">{esc(label)}</text>')
        out.append(f'<text x="{ml + iw + 8}" y="{ly + 3:.1f}" dominant-baseline="hanging" font-size="11" font-weight="700" fill="{color}">{esc(money(v))}</text>')

    # bars: hatched range then solid expected, then chips
    chips = []
    for b in bars:
        k = b["type"]
        left, right = cols[k]
        w = right - left
        up = b["expected"] >= b["baseline"]
        segs = []
        if abs(b["extent"] - b["expected"]) > 0.5:
            segs.append(("hatch", b["expected"], b["extent"]))
        segs.append(("solid", b["baseline"], b["expected"]))
        placement = "top" if up else "bottom"
        anchors = {}
        for kind, a, c in segs:
            y1, y2 = y(a), y(c)
            top, hgt = min(y1, y2), abs(y1 - y2)
            if hgt <= 0:
                continue
            fill = C[k] if kind == "solid" else f"url(#hatch-{'adds' if k == 'deducts' else k})"
            out.append(f'<rect clip-path="url(#plot)" x="{left:.1f}" y="{top:.1f}" width="{w:.1f}" height="{hgt:.1f}" fill="{fill}"/>')
            anchors[kind] = (top if placement == "top" else top + hgt, money(c - b["baseline"], signed=(k != "base")))
        # solid chip sits on its segment; the hatched-range chip must clear it (chip 22px + gaps)
        if "solid" in anchors:
            ay, lab = anchors["solid"]
            chips.append(chip_svg((left + right) / 2, ay, lab, placement, bg=C[k], fg=CHIP_TEXT[k]))
        if "hatch" in anchors:
            ay, lab = anchors["hatch"]
            if "solid" in anchors:
                sy = anchors["solid"][0]
                if placement == "top" and sy - ay < 34:
                    ay = sy - 34
                elif placement == "bottom" and ay - sy < 34:
                    ay = sy + 34
            chips.append(chip_svg((left + right) / 2, ay, lab, placement))
    out.extend(chips)

    # snake
    pts = []
    for i, b in enumerate(bars):
        left, right = cols[b["type"]]
        yy = y(b["expected"])
        pts.append(((left + right) / 2 if i == 0 else left, yy))
        pts.append((right, yy))
    pl, pr = cols["projected"]
    end = ((pl + pr) / 2, y(wf["projected"]))
    pts.append(end)
    d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}" + "".join(f" H {x:.1f} V {yy:.1f}" for x, yy in pts[1:])
    out.append(f'<path d="{d}" fill="none" stroke="{C["primary"]}" stroke-width="1"/>')
    for x, yy in (pts[0], end):
        out.append(f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="6" fill="{C["primary"]}"/>')
    out.append(chip_svg(end[0], end[1] - 6, f"Projected {money(wf['projected'])}", "top", bg=C["primary"], fg="#fff"))
    arrow = "▲" if wf["delta"] >= 0 else "▼"
    out.append(chip_svg(end[0], end[1] + 6, f"{arrow} {money(wf['delta'], signed=True)}", "bottom"))

    # x axis labels
    for k in keys:
        left, right = cols[k]
        out.append(f'<text x="{(left + right)/2:.1f}" y="{mt + ih + 26}" text-anchor="middle" font-size="12" fill="{C["primary"]}">{labels[k]}</text>')
    out.append("</svg>")
    return "\n".join(out)

# ----------------------------------------------------------- monte carlo svg

def _stagger_labels(items, min_gap):
    """items: [(x, text_width)] sorted by x → row index per item so labels don't overlap."""
    rows, ends = [], []
    for x, w in items:
        placed = False
        for r, end in enumerate(ends):
            if x - w / 2 > end + min_gap:
                ends[r] = x + w / 2
                rows.append(r)
                placed = True
                break
        if not placed:
            ends.append(x + w / 2)
            rows.append(len(ends) - 1)
    return rows


def _clamp_label_x(xx, text_width, svg_width, margin=2):
    """Centre for a middle-anchored label so it never runs past the SVG edges
    (a reference line at the extreme of the range would otherwise clip)."""
    half = text_width / 2 + margin
    return max(half, min(svg_width - half, xx))


def histogram_svg(model, width=620, height=300):
    mc, cs, wf = model["monte_carlo"], model["cost_summary"], model["waterfall"]
    ml, mr, mt, mb = 46, 14, 58, 44
    iw, ih = width - ml - mr, height - mt - mb
    hist = mc["histogram"]
    xlo, xhi = hist[0]["lo"], hist[-1]["hi"]
    refs = [("Base Cost", mc["base"], C["primary"], "2 3"), ("Running Total", cs["running_total"], C["primary"], "6 3")]
    if cs.get("budget"):
        refs.append(("Budget", cs["budget"], C["budget"], "10 4"))
    refs += [("P50", mc["percentiles"][50], C["muted"], ""), ("P80", mc["percentiles"][80], C["muted"], "")]
    xlo = min(xlo, min(v for _, v, *_ in refs)); xhi = max(xhi, max(v for _, v, *_ in refs))
    pad = (xhi - xlo) * 0.03
    xlo, xhi = xlo - pad, xhi + pad
    ymax = max(h["share"] for h in hist) * 100 * 1.08

    def x(v):
        return ml + (v - xlo) / (xhi - xlo) * iw

    def y(p):
        return mt + ih - p / ymax * ih

    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']
    for t in nice_ticks(0, ymax, 4):
        out.append(f'<line x1="{ml}" x2="{ml + iw}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{C["separator"]}"/>')
        out.append(f'<text x="{ml - 8}" y="{y(t):.1f}" text-anchor="end" dominant-baseline="central" font-size="11" fill="{C["secondary"]}">{t:g}%</text>')
    for t in nice_ticks(xlo, xhi, 6):
        out.append(f'<text x="{x(t):.1f}" y="{mt + ih + 18}" text-anchor="middle" font-size="11" fill="{C["secondary"]}">{si(t)}</text>')
    out.append(f'<line x1="{ml}" x2="{ml + iw}" y1="{mt + ih}" y2="{mt + ih}" stroke="{C["border"]}"/>')
    rt = cs["running_total"]
    for h in hist:
        mid = (h["lo"] + h["hi"]) / 2
        fill = C["base"] if mid <= rt else C["risks"]
        x0, x1 = x(h["lo"]), x(h["hi"])
        top = y(h["share"] * 100)
        out.append(f'<rect x="{x0 + 0.5:.1f}" y="{top:.1f}" width="{max(0.5, x1 - x0 - 1):.1f}" height="{mt + ih - top:.1f}" fill="{fill}" opacity="0.85"/>')
    labels = []
    for n, v, *_ in refs:
        w = text_w(f"{n} {money(v)}", 11) + 4
        labels.append((_clamp_label_x(x(v), w, width), w))
    order = sorted(range(len(refs)), key=lambda i: labels[i][0])
    rows = _stagger_labels([labels[i] for i in order], 6)
    row_of = {order[j]: rows[j] for j in range(len(order))}
    for i, (name, v, color, dash) in enumerate(refs):
        xx = x(v)
        out.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{mt - 4}" y2="{mt + ih}" stroke="{color}" stroke-width="1"'
                   + (f' stroke-dasharray="{dash}"' if dash else "") + ' opacity="0.9"/>')
        ly = mt - 8 - row_of[i] * 14
        lx = labels[i][0]
        out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="11" font-weight="700" fill="{color}" '
                   f'paint-order="stroke" stroke="#fff" stroke-width="3" stroke-linejoin="round">{esc(name)} {esc(money(v))}</text>')
    out.append(f'<text x="{ml + iw/2:.1f}" y="{height - 6}" text-anchor="middle" font-size="11" fill="{C["secondary"]}">Outcome (Project cost, USD $)</text>')
    out.append(f'<text transform="translate(12 {mt + ih/2:.1f}) rotate(-90)" text-anchor="middle" font-size="11" fill="{C["secondary"]}">Share of trials</text>')
    out.append("</svg>")
    return "\n".join(out)


def cdf_svg(model, width=420, height=300):
    mc, cs = model["monte_carlo"], model["cost_summary"]
    ml, mr, mt, mb = 56, 14, 70, 44
    iw, ih = width - ml - mr, height - mt - mb
    cdf = mc["cdf"]
    xlo, xhi = cdf[0]["x"], cdf[-1]["x"]
    marks = [("Running Total", cs["running_total"], C["primary"], mc["p_within_contingency"])]
    if cs.get("budget") and mc.get("p_within_budget") is not None:
        marks.append(("Budget", cs["budget"], C["budget"], mc["p_within_budget"]))
    xlo = min(xlo, min(v for _, v, *_ in marks)); xhi = max(xhi, max(v for _, v, *_ in marks))
    pad = (xhi - xlo) * 0.03
    xlo, xhi = xlo - pad, xhi + pad

    def x(v):
        return ml + (v - xlo) / (xhi - xlo) * iw

    def y(p):
        return mt + ih - p / 100 * ih

    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']
    for t in (0, 20, 40, 50, 60, 80, 100):
        dash = ' stroke-dasharray="2 3"' if t in (50, 80) else ""
        col = C["muted"] if t in (50, 80) else C["separator"]
        out.append(f'<line x1="{ml}" x2="{ml + iw}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{col}"{dash}/>')
        out.append(f'<text x="{ml - 8}" y="{y(t):.1f}" text-anchor="end" dominant-baseline="central" font-size="11" fill="{C["secondary"]}">{t}%</text>')
    for t in nice_ticks(xlo, xhi, 4):
        out.append(f'<text x="{x(t):.1f}" y="{mt + ih + 18}" text-anchor="middle" font-size="11" fill="{C["secondary"]}">{si(t)}</text>')
    out.append(f'<line x1="{ml}" x2="{ml + iw}" y1="{mt + ih}" y2="{mt + ih}" stroke="{C["border"]}"/>')
    d = " ".join(f"{'M' if i == 0 else 'L'} {x(p['x']):.1f} {y(p['p']):.1f}" for i, p in enumerate(cdf))
    out.append(f'<path d="{d}" fill="none" stroke="{C["primary"]}" stroke-width="2"/>')
    subs = [f"{p:.0f}% of trials at or below" for *_, p in marks]
    widths = [max(text_w(f"{n} {money(v)}", 11), text_w(s, 11)) + 4 for (n, v, *_), s in zip(marks, subs)]
    labels = [(_clamp_label_x(x(v), w, width), w) for (n, v, *_), w in zip(marks, widths)]
    order = sorted(range(len(marks)), key=lambda i: labels[i][0])
    rows = _stagger_labels([labels[i] for i in order], 6)
    row_of = {order[j]: rows[j] for j in range(len(order))}
    for i, (name, v, color, p) in enumerate(marks):
        xx, yy = x(v), y(p)
        out.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{mt - 4}" y2="{mt + ih}" stroke="{color}" stroke-dasharray="6 3" opacity="0.8"/>')
        out.append(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="5" fill="{color}"/>')
        ly = mt - 8 - row_of[i] * 26
        halo = 'paint-order="stroke" stroke="#fff" stroke-width="3" stroke-linejoin="round"'
        sub = subs[i]
        lx = labels[i][0]
        out.append(f'<text x="{lx:.1f}" y="{ly - 12:.1f}" text-anchor="middle" font-size="11" font-weight="700" fill="{color}" {halo}>{esc(name)} {esc(money(v))}</text>')
        out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-size="11" fill="{color}" {halo}>{sub}</text>')
    out.append(f'<text x="{ml + iw/2:.1f}" y="{height - 6}" text-anchor="middle" font-size="11" fill="{C["secondary"]}">Outcome (Project cost, USD $)</text>')
    out.append(f'<text transform="translate(12 {mt + ih/2:.1f}) rotate(-90)" text-anchor="middle" font-size="11" fill="{C["secondary"]}">Cumulative share of trials</text>')
    out.append("</svg>")
    return "\n".join(out)

# ------------------------------------------------------------------ blocks

def chip(cls, label):
    return f'<span class="chip {cls}">{esc(label)}</span>'


def table(headers, rows, num_cols=(), widths=None, total=None):
    if not rows:
        return '<p class="empty">None</p>'
    colgroup = "".join(f'<col style="width:{w}">' for w in widths) if widths else ""
    th = "".join(f'<th class="{"num" if i in num_cols else ""}">{esc(h)}</th>' for i, h in enumerate(headers))
    body = []
    for r in rows:
        cls = ""
        if r and isinstance(r[0], dict):        # {"class": "selected"} marker as first element
            cls, r = f' class="{r[0]["class"]}"', r[1:]
        tds = "".join(f'<td class="{"num" if i in num_cols else ""}" title="{esc(_plain(c))}">{c}</td>' for i, c in enumerate(r))
        body.append(f"<tr{cls}>{tds}</tr>")
    if total:
        tds = "".join(f'<td class="{"num" if i in num_cols else ""}">{c}</td>' for i, c in enumerate(total))
        body.append(f'<tr class="total">{tds}</tr>')
    return f'<table class="list"><colgroup>{colgroup}</colgroup><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def _plain(c):
    import re
    return re.sub(r"<[^>]+>", "", str(c))


def kv(pairs, total=None):
    out = ['<div class="kv">']
    for k, v in pairs:
        out.append(f"<div>{k}</div><div>{v}</div>")
    if total:
        out.append(f'<div class="total">{total[0]}</div><div class="total">{total[1]}</div>')
    out.append("</div>")
    return "".join(out)


def metrics(items):
    out = ['<div class="metrics">']
    for m in items:
        tone = f" {m['tone']}" if m.get("tone") else ""
        note = f'<div class="note">{m["note"]}</div>' if m.get("note") else ""
        out.append(f'<div class="metric{tone}"><div class="label">{m["label"]}</div><div class="value">{m["value"]}</div>{note}</div>')
    out.append("</div>")
    return "".join(out)


def link(url, text):
    return f'<a href="{esc(url)}">{esc(text)}</a>' if url else esc(text)


def risk_urgency(score):
    if score is None:
        return None
    return "high" if score >= 15 else "medium" if score >= 6 else "low"

# ------------------------------------------------------------------- pages

def page(model, section, body, n, total, created):  # total = number of pages, set once all pages are known
    p, ms = model["project"], model.get("milestone") or {}
    sub = f'<b>{esc(ms.get("name", "Active milestone"))}</b> · {esc(ms.get("date", "")[:10])}' if ms else ""
    return f'''<div class="page">
  <header>
    <div><h1>{link(p.get("url"), p.get("name", "Project"))}</h1><div class="sub">{sub}</div></div>
    <div class="report-name"><div class="name">Risk &amp; Contingency Analysis</div><div class="section">{esc(section)}</div></div>
  </header>
  <main>{body}</main>
  <footer><div class="left">{esc(created)}</div><div class="join-logo">{join_mark()}</div><div class="right">Page {n} of {total}</div></footer>
</div>'''


MAX_ROWS = 6   # rows per "carried as decided" table on page 1; the rest go to the appendix


def treat_of(r):
    src = r["cost_source"]
    return ("certain" if r["override"] == "certain" else "excluded" if r["override"] == "excluded"
            else "override" if isinstance(r["override"], dict) else src)


TREAT_LABEL = {"certain": "Certain", "excluded": "Excluded", "override": "Set here", "assumed": "Assumed", "join": "In Join"}


def risk_row(r):
    treat = treat_of(r)
    return [esc(r["number"]), link(r.get("url"), r["name"]),
            f'{r["likelihood"]} · {LIKELIHOOD_LABELS.get(r["likelihood"], "?")}', f'{r["impact"]} · {IMPACT_LABELS.get(r["impact"], "?")}',
            money(r["assumed_cost"]) if r["assumed_cost"] else "—", chip(treat if treat != "join" else "pending", TREAT_LABEL[treat]),
            f'{r["probability"]:.0f}%', money(r["expected"])]


RISK_HEAD = ["#", "Risk", "Likelihood", "Impact", "Cost Impact", "Cost from", "Prob.", "Expected"]
RISK_WIDTHS = ["5%", "31%", "12%", "12%", "13%", "10%", "8%", "9%"]


def item_row(i):
    return [esc(i["number"]), link(i.get("url"), i["name"]), money(i["cost_hi"] if i["kind"] == "add" else i["cost_lo"], signed=True),
            chip(i["override"], "Accepted" if i["override"] == "accepted" else "Rejected")]


def risk_adjust_row(r):
    o = r["override"]
    if o == "certain":
        carried = chip("certain", "Certain")
    elif o == "excluded":
        carried = chip("excluded", "Excluded")
    elif isinstance(o, dict) and "cost" in o:
        carried = chip("override", f"Cost Impact {money(o['cost'])}")
    elif isinstance(o, dict) and "probability" in o:
        carried = chip("override", f"{o['probability']:g}% probability")
    else:
        carried = ""
    return [esc(r["number"]), link(r.get("url"), r["name"]), carried]


def carried_items(model):
    return sorted([i for i in model["items"] if i["override"] in ("accepted", "rejected")], key=lambda i: -abs(i["cost"]))


def carried_risks(model):
    return sorted([r for r in model["risks"] if r["override"] not in (None, "", False)], key=lambda r: -r["expected"])


def page_assumptions(model):
    a, cs, wf = model["assumptions"], model["cost_summary"], model["waterfall"]
    risks, items = model["risks"], model["items"]
    ms = model.get("milestone") or {}
    url = model["project"].get("url") or ""
    open_link = f'<a class="sec-link" href="{esc(url)}">Open project in Join →</a>' if url else ""
    head = (f'<div class="sec-head"><div><h2>Assumptions</h2><div class="sec-sub">This page details the assumptions that drive the rest of the report.</div></div>'
            f'{open_link}</div>')

    # column 1 — base cost
    cont_note = " · supplied by you, not in Join" if cs.get("contingency_is_override") else ""
    scope = "project-level" if not a["include_company_risks"] else "project + company"
    base_kv = kv([
        ("Milestone", esc(ms.get("name", "active")) + (f' · {esc(ms.get("date", "")[:10])}' if ms.get("date") else "")),
        ("Running Total", money(cs["running_total"])),
        ("− Contingency held", money(cs["contingency"]) + esc(cont_note)),
    ], total=("= Base Cost", money(wf["base"]["expected"])))
    counts_kv = kv([
        ("Budget", money(cs["budget"]) if cs["budget"] else "none"),
        ("Open risks", f'{len(risks)} · {scope}'),
        ("Pending adds", f'{cs["pending_adds_count"]} items · {money(cs["pending_adds"], signed=True)}'),
        ("Pending deducts", f'{cs["pending_deducts_count"]} items · {money(cs["pending_deducts"], signed=True)}'),
    ] + ([("Allowances in the estimate", money(cs["allowances"]) + " · not modeled")] if cs["allowances"] else []))
    b_base = f'<div class="block"><h3>Base cost</h3>{base_kv}<div style="height:3mm"></div>{counts_kv}</div>'

    # column 2 — adjustments
    c_items, c_risks = carried_items(model), carried_risks(model)
    item_rows = [item_row(i) for i in c_items[:MAX_ROWS]]
    more_i = f'<p class="secondary">+{len(c_items) - MAX_ROWS} more, listed in the appendix</p>' if len(c_items) > MAX_ROWS else ""
    risk_rows = [risk_adjust_row(r) for r in c_risks[:MAX_ROWS]]
    more_r = f'<p class="secondary">+{len(c_risks) - MAX_ROWS} more, listed in the appendix</p>' if len(c_risks) > MAX_ROWS else ""
    notes = "".join(f'<p class="secondary">· {esc(n)}</p>' for n in a.get("notes", []))
    items_tbl = (table(["#", "Item", "Cost Impact", "Carried as"], item_rows, num_cols=(2,), widths=["11%", "45%", "22%", "22%"])
                 if item_rows else '<p class="secondary">None — every pending item carries the probability at right.</p>')
    risks_tbl = (table(["#", "Risk", "Carried as"], risk_rows, widths=["11%", "55%", "34%"])
                 if risk_rows else '<p class="secondary">None — every open risk carries the probability at right.</p>')
    b_adj = (f'<div class="block"><h3>Adjustments</h3><h4>Pending items carried as decided</h4>{items_tbl}{more_i}'
             f'<h4 style="margin-top:3mm">Risks carried as decided</h4>{risks_tbl}{more_r}'
             + (f'<div style="margin-top:3mm">{notes}</div>' if notes else "") + '</div>')

    # column 3 — assumed probabilities
    probs = a["risk_probabilities"]
    counts = {}
    for r in risks:
        counts[r["likelihood"]] = counts.get(r["likelihood"], 0) + 1
    prob_rows = [[f"{L} · {LIKELIHOOD_LABELS[L]}", f"{probs.get(L, 0):.0f}%", str(counts.get(L, 0))] for L in (1, 2, 3, 4, 5)]
    method = a["costless_risk_method"]
    costless = [r for r in risks if r["cost_source"] == "assumed"]
    if method == "pct_of_running_total":
        cl_rows = [[f"{I} · {IMPACT_LABELS[I]}", f"{a['impact_pct'][I]:g}% of Running Total", money(cs['running_total'] * a['impact_pct'][I] / 100)] for I in (1, 2, 3, 4, 5)]
        cl_head, cl_widths = ["Impact", "", "Cost Impact"], ["36%", "40%", "24%"]
    elif method == "fixed":
        cl_rows = [[f"{I} · {IMPACT_LABELS[I]}", "", money(a['impact_dollars'][I])] for I in (1, 2, 3, 4, 5)]
        cl_head, cl_widths = ["Impact", "", "Cost Impact"], ["50%", "20%", "30%"]
    else:
        cl_rows, cl_head, cl_widths = [], [], []
    prob_kv = kv([("A pending add is accepted", f"{a['adds_pct']:g}%"), ("A pending deduct is accepted", f"{a['deducts_pct']:g}%")])
    cl_tbl = table(cl_head, cl_rows, num_cols=(2,), widths=cl_widths) if cl_rows else '<p class="secondary">Excluded from the analysis.</p>'
    b_prob = (f'<div class="block"><h3>Assumed probabilities</h3>{prob_kv}'
              f'<h4 style="margin-top:3mm">A risk occurs, by Likelihood</h4>'
              f'{table(["Likelihood", "Probability", "Risks"], prob_rows, num_cols=(1, 2), widths=["50%", "28%", "22%"])}'
              f'<h4 style="margin-top:3mm">Cost Impact for risks without one in Join <span class="secondary" style="font-weight:400">— {len(costless)} of {len(risks)}</span></h4>'
              f'{cl_tbl}</div>')
    return f'{head}<div class="cols three assumptions">{b_base}{b_adj}{b_prob}</div>'


def page_waterfall(model):
    wf, cs, a = model["waterfall"], model["cost_summary"], model["assumptions"]
    live_risks = [r for r in model["risks"] if r["probability"] > 0 and r["assumed_cost"] > 0]
    carried = carried_items(model)
    n_add = sum(1 for i in carried if i["kind"] == "add")
    n_ded = len(carried) - n_add
    add_txt = f" · {n_add} carried as decided" if n_add else ""
    ded_txt = f" · {n_ded} carried as decided" if n_ded else ""
    adds = wf["adds"]["expected"] - wf["adds"]["baseline"]
    deds = wf["deducts"]["expected"] - wf["deducts"]["baseline"]
    rsk = wf["risks"]["expected"] - wf["risks"]["baseline"]
    rows = [
        ("", "Base Cost", f"Running Total {money(wf['running_total'])} − contingency {money(wf['contingency'])}", money(wf["base"]["expected"])),
        ("+", "Expected Adds", f"Pending Adds {money(cs['pending_adds'], signed=True)} × {a['adds_pct']:g}%{add_txt}", money(adds, signed=True)),
        ("−", "Expected Deducts", f"Pending Deducts {money(cs['pending_deducts'], signed=True)} × {a['deducts_pct']:g}%{ded_txt}", money(deds, signed=True)),
        ("+", "Expected Risks", f"Cost Impact × probability, {len(live_risks)} open risks", money(rsk, signed=True)),
    ]
    walk = ['<table class="walk"><colgroup><col style="width:16px"><col><col style="width:72px"></colgroup>']
    for op, label, sub, val in rows:
        walk.append(f'<tr><td class="op">{op}</td><td><div>{label}</div><div class="sub">{esc(sub)}</div></td><td class="val">{val}</td></tr>')
    walk.append(f'<tr class="total"><td class="op">=</td><td><div>Projected</div><div class="sub">Expected project cost</div></td><td class="val">{money(wf["projected"])}</td></tr>')
    walk.append("</table>")
    draw = wf["projected"] - wf["base"]["expected"]
    short = draw - wf["contingency"]
    verdict = ("Current remaining contingency is sufficient to cover expected project outcome."
               if short <= 0 else f"{money(short)} more contingency needed to bridge to expected project cost.")
    cont_kv = kv([("Current remaining contingency", money(wf["contingency"])),
                  ("Needed to reach Projected", money(draw))])
    cont = f'<div class="block"><h3>Contingency</h3>{cont_kv}<div class="verdict">{esc(verdict)}</div></div>'
    legend = ('<div class="legend">'
              '<span><i style="background:#4B71A9"></i>Base Cost</span>'
              '<span><i style="background:#F6B901"></i>Pending adds / deducts × probability</span>'
              '<span><i style="background:#F49144"></i>Risks × probability</span>'
              '<span><i class="line"></i>Running Total</span>'
              '<span><i class="line budget"></i>Budget</span></div>')
    body = (f'<div class="sec-head"><div><h2>Expected outcome</h2><div class="sec-sub">Each bar walks the Base Cost up by the expected value of pending items and risks under the assumptions on page 1.</div></div></div>'
            f'<div class="cols chart"><div class="col"><div class="fill">{waterfall_svg(model)}</div>{legend}</div>'
            f'<div class="col"><div class="block"><h3>Walk</h3>{"".join(walk)}</div>{cont}</div></div>')
    return body


def page_montecarlo(model):
    mc, cs, wf = model["monte_carlo"], model["cost_summary"], model["waterfall"]
    P = mc["percentiles"]
    rt, base, held = cs["running_total"], mc["base"], wf["contingency"]
    rows = []
    for p in (10, 50, 80, 90, 95):
        add = P[p] - rt
        if add > 0:
            total = held + add
            rows.append([f"P{p}", money(P[p]), money(add, signed=True), f"{money(total)} · {total / base * 100:.1f}%"])
        else:
            rows.append([f"P{p}", money(P[p]), "—", "—"])
    stats = table(["Confidence", "Outcome", "Additional contingency needed", "Total contingency"], rows, num_cols=(1, 2, 3), widths=["18%", "22%", "32%", "28%"])
    draws = 100 - mc["p_within_base"]
    budget_finding = (f'<div class="finding"><div class="value">{mc["p_within_budget"]:.0f}%</div><div class="text"><b>of trials stay within Budget</b> ({money(cs["budget"])})</div></div>'
                      if mc.get("p_within_budget") is not None else "")
    findings = (f'<div class="findings">'
                f'<div class="finding"><div class="value">{mc["p_within_contingency"]:.0f}%</div><div class="text"><b>of trials stay within the Running Total</b> — the contingency held ({money(held)}) covers the outcome</div></div>'
                f'{budget_finding}'
                f'<div class="finding"><div class="value">{draws:.0f}%</div><div class="text"><b>of trials draw on contingency</b> — outcome above Base Cost ({money(base)})</div></div>'
                f'</div>')
    legend = ('<div class="legend">'
              '<span><i style="background:#4B71A9"></i>Within Running Total</span>'
              '<span><i style="background:#F49144"></i>Beyond contingency held</span>'
              '<span><i class="line dotted"></i>Base Cost</span><span><i class="line"></i>Running Total</span><span><i class="line budget"></i>Budget</span></div>')
    intro = ('A Monte Carlo simulation plays the project out thousands of times, each time deciding at random — with the probabilities on page 1 — '
             'which pending items are accepted and which risks occur, and records the resulting cost. The spread of those results is the range of outcomes. '
             '<a href="https://en.wikipedia.org/wiki/Monte_Carlo_method">Learn more →</a>')
    body = (f'<div class="sec-head"><div><h2>Range of outcomes</h2><div class="sec-sub">{intro}</div></div></div>'
            f'<div class="cols mc">'
            f'<div class="col"><h3>Distribution of outcomes</h3><div class="fill">{histogram_svg(model)}</div>{legend}'
            f'<div class="block" style="margin-top:2mm"><h3>Outcome by confidence level</h3>{stats}<p class="chart-caption" style="margin-top:1.5mm">Additional contingency needed = outcome − Running Total {money(rt)}. Total contingency = the {money(held)} held plus the additional amount, as a % of Base Cost {money(base)}.</p></div></div>'
            f'<div class="col">{findings}<h3 style="margin-top:2mm">Confidence curve</h3><div class="fill">{cdf_svg(model)}</div><p class="chart-caption">The share of trials whose outcome is at or below each cost.</p></div>'
            f'</div>')
    return body


def normalize(model):
    """JSON turns int keys into strings; put the numeric tables back."""
    mc = model["monte_carlo"]
    mc["percentiles"] = {int(k): v for k, v in mc["percentiles"].items()}
    for k in ("contingency_needed", "shortfall"):
        mc[k] = {int(kk): v for kk, v in mc[k].items()}
    a = model["assumptions"]
    for k in ("risk_probabilities", "impact_pct", "impact_dollars"):
        a[k] = {int(kk): v for kk, v in a[k].items()}
    return model


def appendix_pages(model):
    """Every open risk with its treatment (always, when there are risks), plus
    the pending items carried as decided when page 1 could not list them all.
    ~24 rows per Letter-landscape page."""
    risks = sorted(model["risks"], key=lambda r: -r["expected"])
    items = carried_items(model)
    blocks = []
    if risks:
        blocks.append(("risks", risks))
    if len(items) > MAX_ROWS:
        blocks.append(("items", items))
    pages, per_page = [], 24
    for kind, rows in blocks:
        for start in range(0, len(rows), per_page):
            chunk = rows[start:start + per_page]
            if kind == "risks":
                body = (f'<div class="sec-head"><div><h2>Risks modeled — all {len(risks)} open risks</h2>'
                        f'<div class="sec-sub">Ranked by expected cost (Cost Impact × probability); rows {start + 1}–{start + len(chunk)}. '
                        f'Cost from: In Join = as entered in Join · Set here = supplied for this analysis · Assumed = from the Impact table on page 1. Certain = 100%, Excluded = 0%.</div></div></div>'
                        + table(RISK_HEAD, [risk_row(r) for r in chunk], num_cols=(4, 6, 7), widths=RISK_WIDTHS))
                pages.append(("Appendix · Risks modeled", body))
            else:
                body = (f'<div class="sec-head"><div><h2>Pending items carried as decided — all {len(items)}</h2>'
                        f'<div class="sec-sub">Rows {start + 1}–{start + len(chunk)}.</div></div></div>'
                        + table(["#", "Item", "Cost Impact", "Carried as"], [item_row(i) for i in chunk], num_cols=(2,), widths=["6%", "64%", "15%", "15%"]))
                pages.append(("Appendix · Items carried as decided", body))
    return pages


def build(model, created=None):
    created = created or f"Created {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M')} UTC"
    sections = [
        ("1 · Assumptions", page_assumptions(model)),
        ("2 · Expected outcome", page_waterfall(model)),
        ("3 · Range of outcomes", page_montecarlo(model)),
    ] + appendix_pages(model)
    total = len(sections)
    pages = [page(model, sec, body, n, total, created) for n, (sec, body) in enumerate(sections, 1)]
    tpl = (ASSETS / "template.html").read_text()
    title = f'{model["project"].get("name", "Project")} — Risk & Contingency Analysis'
    html = tpl.replace("{{TITLE}}", esc(title)).replace("{{PAGES}}", "\n".join(pages))
    return html.replace("<body>", f'<body data-pages="{total}">', 1)


def main():
    args = sys.argv[1:]
    created = None
    if "--created" in args:
        i = args.index("--created")
        created = "Created " + args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        print(__doc__)
        sys.exit(2)
    model = normalize(json.loads(Path(args[0]).read_text()))
    out = Path(args[1])
    out.write_text(build(model, created))
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
