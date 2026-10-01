#!/usr/bin/env python3
"""Assemble an A3 report from a JSON spec and the bundled Join-styled template.

Usage:
    python build_report.py spec.json out.html

Spec shape (HTML fields are raw HTML you author; helpers in join_data.py
produce the common blocks):

{
  "title": "Tab title",
  "project_name": "1885 North Oak Hospital",
  "subtitle": "<b>100% DD</b> · Design Development · 28 Feb 2026 · <a href=...>Open in Join</a>",
  "logos": {"owner": "path/or/null", "preparer": "path/or/null"},   # "join" is optional: the Join mark is built into the template
  "metrics": [{"label": "Project Running Total", "value": "$257.9M", "note": "incl. Owner Costs", "tone": ""}],
  "sections": [ {"title": "...", "subtitle": "...", "link": {"label": "Items", "url": "..."}, "body": "<p>...</p>"} ],  # exactly 6
  "created": "Created 26 Sep 2026, 14:02 CDT",   # the only footer text: the timestamp. No "from Join data", no "prepared by"
  "footer_right": ""                               # normally empty
}

Logos are inlined as data URIs. The template loads Red Hat Text from Google
Fonts and falls back to Helvetica when offline.
"""
import base64
import json
import mimetypes
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
TEMPLATE = ASSETS / "template.html"


def data_uri(path, mime=None):
    p = Path(path)
    mime = mime or mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def img_tag(path, alt):
    if not path:
        return None
    if not Path(path).exists():
        print(f"warning: image not found: {path}", file=sys.stderr)
        return None
    return f'<img src="{data_uri(path)}" alt="{alt}">'


def logo_or_slot(path, alt, slot_text):
    return img_tag(path, alt) or f'<span class="slot">{slot_text}</span>'


def render_metrics(metrics):
    out = []
    for m in metrics:
        tone = f" {m['tone']}" if m.get("tone") else ""
        note = f'<div class="note">{m["note"]}</div>' if m.get("note") else ""
        out.append(f'<div class="metric{tone}"><div class="label">{m["label"]}</div>'
                   f'<div class="value">{m["value"]}</div>{note}</div>')
    return "".join(out)


def render_sections(sections):
    if len(sections) != 6:
        print(f"warning: template is laid out for 6 sections, got {len(sections)}", file=sys.stderr)
    out = []
    for s in sections:
        link = s.get("link") or {}
        link_html = (f'<a class="sec-link" href="{link["url"]}">{link.get("label", "View in Join")} →</a>'
                     if link.get("url") else "")
        sub = f'<div class="sec-sub">{s["subtitle"]}</div>' if s.get("subtitle") else ""
        out.append(f'<section><div class="sec-head"><div><h2>{s["title"]}</h2>{sub}</div>{link_html}</div>'
                   f'<div class="sec-body">{s["body"]}</div></section>')
    return "".join(out)


FOOTER_NOISE = re.compile(r"\s*(from|using|based on|with)\s+(the\s+)?join(\s+data)?\.?\s*$|\s*[·|-]\s*(prepared|generated|created)\s+by.*$", re.I)


def footer_stamp(spec):
    """The footer carries only the creation timestamp. Anything after it
    ('from Join data', 'prepared by …') is stripped with a warning."""
    created = spec.get("created") or f"Created {__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%d %b %Y, %H:%M')} UTC"
    clean = FOOTER_NOISE.sub("", created).strip()
    if clean != created.strip():
        print(f"warning: footer text trimmed to {clean!r} (only the timestamp belongs there)", file=sys.stderr)
    return clean


def build(spec):
    html = TEMPLATE.read_text()
    logos = spec.get("logos") or {}
    # The Join mark is inline in the template (komodo-ui's JoinLogo); logos.join swaps in a custom file only when given.
    custom_join = img_tag(logos.get("join"), "Join") if logos.get("join") else None
    if custom_join:
        html = re.sub(r"<!--JOIN_LOGO_START-->.*?<!--JOIN_LOGO_END-->", custom_join, html, flags=re.S)
    repl = {
        "{{TITLE}}": spec.get("title") or spec["project_name"],
        "{{PROJECT_NAME}}": spec["project_name"],
        "{{SUBTITLE}}": spec.get("subtitle", ""),
        "{{OWNER_LOGO}}": logo_or_slot(logos.get("owner"), "Owner logo", "Owner logo"),
        "{{PREPARER_LOGO}}": logo_or_slot(logos.get("preparer"), "Preparer logo", "Preparer logo"),
        "{{METRICS}}": render_metrics(spec.get("metrics", [])),
        "{{SECTIONS}}": render_sections(spec.get("sections", [])),
        "{{CREATED}}": footer_stamp(spec),
        "{{FOOTER_RIGHT}}": spec.get("footer_right", ""),
    }
    for k, v in repl.items():
        html = html.replace(k, v)
    return html


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    spec = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2])
    out.write_text(build(spec))
    print(f"wrote {out} ({os.path.getsize(out)//1024} KB)")


if __name__ == "__main__":
    main()
