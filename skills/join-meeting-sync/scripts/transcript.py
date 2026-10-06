#!/usr/bin/env python3
"""Turn a meeting transcript into compact speaker turns.

Usage:
    python transcript.py MEETING_FILE [--start 2026-09-30T14:00-07:00] [--out work/transcript.txt]

Reads WebVTT (Teams, Zoom, Google Meet), SRT, Word .docx (Teams "Download as
.docx", Otter, Meet exports) and plain text or Markdown. Writes a header —
title and date lines as written in the file, duration, speakers by words
spoken — then one line per speaker turn:

    [0:12:03 14:12] Ana Ruiz: We'll go with option two on the shading.

Cues from the same speaker less than 20 seconds apart are merged; "Ruiz, Ana"
is written "Ana Ruiz". WebVTT NOTE lines (where some tools put the title and
date) are kept in the header. With --start (ISO 8601 with a UTC offset) each
turn also carries its wall-clock time, and the header gives the start in UTC:
the `since` for get-item-history. Text with no recognisable timestamps or
speakers (minutes, notes) is passed through unchanged.

Standard library only. Reads the file given and writes --out (or stdout).
"""
import argparse
import html
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

TS = r"(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?"
CUE_TIME = re.compile(rf"^\s*{TS}\s*-->\s*{TS}")
VOICE = re.compile(r"<v(?:\.[^\s>]+)*\s+([^>]+)>(.*?)(?=<v[\s.]|$)", re.S)
TAG = re.compile(r"<[^>]+>")
CLOCK = r"\d{1,2}:\d{2}(?::\d{2})?"
# "Ana Ruiz   0:03" (Teams .docx, Otter): name, two or more spaces or a tab,
# then the offset at line end.
HEADER_LINE = re.compile(rf"^(?P<name>\S.{{0,60}}?)(?:\s{{2,}}|\t)(?P<ts>{CLOCK})\s*$")
# "[00:01:02] Ana Ruiz: text" / "00:01:02 - Ana Ruiz: text"
INLINE_TS_FIRST = re.compile(rf"^\[?(?P<ts>{CLOCK})\]?\s*[-–]?\s*(?P<name>[^:\[\]]{{1,60}}?):\s+(?P<text>.+)$")
# "Ana Ruiz (00:01:02): text" / "Ana Ruiz [00:01:02]: text"
INLINE_TS_AFTER = re.compile(rf"^(?P<name>[^:(\[]{{1,60}}?)\s*[(\[](?P<ts>{CLOCK})[)\]]:?\s*(?P<text>.*)$")
BARE_TS = re.compile(rf"^\[?(?P<ts>{CLOCK})\]?$")
NAME_PREFIX = re.compile(r"^(?P<name>[A-Z][^:]{0,60}?):\s+(?P<text>.+)$", re.S)
DATE_HINT = re.compile(
    r"(\b(19|20)\d{2}-\d{2}-\d{2}\b)|(\b\d{1,2}/\d{1,2}/(19|20)?\d{2}\b)|"
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}\b|"
    r"\b\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b",
    re.I,
)
DURATION_HINT = re.compile(r"^\s*(\d+h\s*)?(\d+m\s*)?(\d+s)?\s*$|^\s*duration\b", re.I)


def seconds(h, m, s, frac=None):
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + (int(frac.ljust(3, "0")) / 1000 if frac else 0)


def clock_seconds(ts):
    parts = [int(p) for p in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def fmt_offset(sec):
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub("", s))).strip()


def display_name(s):
    """'Ruiz, Ana' and 'Ruiz, Ana (Guest)' → 'Ana Ruiz', 'Ana Ruiz (Guest)'."""
    s = s.strip()
    m = re.fullmatch(r"([^,()]+),\s*([^,()]+?)(\s*\(.*\))?", s)
    return f"{m.group(2).strip()} {m.group(1).strip()}{m.group(3) or ''}" if m else s


def name_like(s):
    s = s.strip()
    words = s.split()
    return (
        0 < len(words) <= 6
        and len(s) <= 60
        and not re.search(r"[.?!:;]$", s)
        and not re.search(r"\d{2,}|[•|]", s)
        and not re.match(r"^\d", s)
        and (s[0].isupper() or "@" in s)
    )


def docx_text(path):
    """Paragraph text of a .docx, one paragraph per line (tabs and breaks kept)."""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    lines = []
    for p in root.iter(w + "p"):
        parts = []
        for node in p.iter():
            if node.tag == w + "t":
                parts.append(node.text or "")
            elif node.tag == w + "tab":
                parts.append("\t")
            elif node.tag in (w + "br", w + "cr"):
                parts.append("\n")
        lines.append("".join(parts))
    return "\n".join(lines)


def parse_cues(text):
    """WebVTT / SRT (and the old Teams .docx, which is laid out the same way).
    Returns (preamble_lines, turns) with turns as dicts {t, speaker, text}."""
    preamble, turns, raw = [], [], []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = block.strip("\n").split("\n")
        idx = next((i for i, l in enumerate(lines) if CUE_TIME.match(l)), None)
        if idx is None:
            if not raw:
                for l in lines:
                    if l.startswith("NOTE"):
                        l = l[4:]
                    if l.strip() and not l.startswith(("WEBVTT", "STYLE", "REGION")):
                        preamble.append(l.strip())
            continue
        times = CUE_TIME.match(lines[idx]).groups()
        start, end = seconds(*times[:4]), seconds(*times[4:])
        body_lines = [l for l in lines[idx + 1:] if l.strip()]
        raw.append((start, end, body_lines))
    # A cue may hold several <v> voices; otherwise "Name: text"; otherwise
    # (old Teams .docx) a name-like first line that repeats across cues.
    first_lines = Counter(b[0].strip() for _, _, b in raw if len(b) > 1 and name_like(b[0]))
    repeated = {n for n, c in first_lines.items() if c >= 2}
    use_first_line = repeated and sum(first_lines[n] for n in repeated) >= 0.6 * len(raw)
    for start, end, body_lines in raw:
        body = "\n".join(body_lines)
        voices = VOICE.findall(body)
        if voices:
            for name, said in voices:
                turns.append({"t": start, "end": end, "speaker": clean(name), "text": clean(said)})
            continue
        if use_first_line and len(body_lines) > 1 and body_lines[0].strip() in repeated:
            turns.append({"t": start, "end": end, "speaker": body_lines[0].strip(),
                          "text": clean(" ".join(body_lines[1:]))})
            continue
        m = NAME_PREFIX.match(clean(body))
        if m and name_like(m.group("name")):
            turns.append({"t": start, "end": end, "speaker": m.group("name").strip(), "text": m.group("text")})
        else:
            turns.append({"t": start, "end": end, "speaker": None, "text": clean(body)})
    return preamble, turns


def parse_text(text):
    """Teams/Otter .docx or .txt, Teams copied from the web ("Name" line, then
    an offset line), Meet exports, and "[ts] Name: text" logs."""
    lines = [l.strip() for l in text.replace("\r\n", "\n").split("\n") if l.strip()]
    preamble, turns = [], []
    current_t = None
    cur = None
    i = 0
    while i < len(lines):
        s = lines[i]
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        after = lines[i + 2] if i + 2 < len(lines) else ""
        i += 1
        m = INLINE_TS_FIRST.match(s) or INLINE_TS_AFTER.match(s)
        if m and name_like(m.group("name")):
            cur = {"t": clock_seconds(m.group("ts")), "speaker": m.group("name").strip(), "text": m.group("text").strip()}
            turns.append(cur)
            continue
        m = HEADER_LINE.match(s)
        if m and name_like(m.group("name")):
            cur = {"t": clock_seconds(m.group("ts")), "speaker": m.group("name").strip(), "text": ""}
            turns.append(cur)
            continue
        if name_like(s) and BARE_TS.match(nxt) and after and not NAME_PREFIX.match(after):
            cur = {"t": clock_seconds(BARE_TS.match(nxt).group("ts")), "speaker": s, "text": ""}
            turns.append(cur)
            i += 1
            continue
        m = BARE_TS.match(s)
        if m:
            current_t = clock_seconds(m.group("ts"))
            continue
        m = NAME_PREFIX.match(s)
        if m and name_like(m.group("name")) and (turns or current_t is not None):
            cur = {"t": current_t, "speaker": m.group("name").strip(), "text": m.group("text").strip()}
            turns.append(cur)
            continue
        if cur is not None:
            cur["text"] = (cur["text"] + " " + s).strip()
        elif not turns:
            preamble.append(s)
    return preamble, [t for t in turns if t["text"]]


def merge(turns, gap=20, paragraph=30):
    """Merge consecutive turns by the same speaker that start within `gap`
    seconds of the previous one, so a topic change keeps its own timestamp.
    Unattributed cues merge into paragraphs of about `paragraph` seconds."""
    out = []
    for t in turns:
        t = dict(t, speaker=display_name(t["speaker"]) if t["speaker"] else None)
        prev = out[-1] if out else None
        same = prev is not None and prev["speaker"] == t["speaker"]
        if same and prev["t"] is not None and t["t"] is not None:
            if t["speaker"] is None:
                same = t["t"] - prev["t"] < paragraph
            else:
                same = t["t"] - prev["last"] <= gap
        if same:
            prev["text"] = (prev["text"] + " " + t["text"]).strip()
            prev["last"] = t["t"]
            prev["end"] = t.get("end", prev.get("end"))
        else:
            out.append(dict(t, last=t["t"]))
    return out


def parse_start(s):
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        sys.exit("--start needs a UTC offset, e.g. 2026-09-30T14:00-07:00, so the history window is right")
    return dt


def render(path, preamble, turns, start=None):
    out = [f"# Transcript: {Path(path).name}"]
    head = [l for l in preamble if l.strip()][:8]
    if head:
        out.append("Header lines (as written): " + " | ".join(head))
        dates = [l for l in head if DATE_HINT.search(l)]
        if dates:
            out.append(f"Date as written: {dates[0]}")
        durations = [l for l in head if DURATION_HINT.match(l) and l.strip()]
        if durations:
            out.append(f"Duration as written: {durations[0]}")
    if start:
        utc = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append(f"Start: {start.isoformat()} = {utc} (since for get-item-history)")
    ends = [t["end"] for t in turns if t.get("end") is not None]
    timed = [t["t"] for t in turns if t["t"] is not None]
    if ends:
        out.append(f"Ends: {fmt_offset(max(ends))}"
                   + (f" ({(start + timedelta(seconds=max(ends))).strftime('%H:%M')})" if start else ""))
    elif timed:
        out.append(f"Last timestamp: {fmt_offset(max(timed))}")
    words = Counter()
    for t in turns:
        if t["speaker"]:
            words[t["speaker"]] += len(t["text"].split())
    if words:
        out.append("Speakers (words): " + " · ".join(f"{n} {c}" for n, c in words.most_common()))
    out.append(f"Turns: {len(turns)}")
    out.append("---")
    for t in turns:
        stamp = ""
        if t["t"] is not None:
            stamp = fmt_offset(t["t"])
            if start:
                stamp += " " + (start + timedelta(seconds=t["t"])).strftime("%H:%M")
            stamp = f"[{stamp}] "
        who = f"{t['speaker']}: " if t["speaker"] else ""
        out.append(f"{stamp}{who}{t['text']}")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("file")
    ap.add_argument("--start", help="meeting start, ISO 8601 with UTC offset")
    ap.add_argument("--out", help="write here instead of stdout")
    args = ap.parse_args()

    path = Path(args.file)
    text = docx_text(path) if path.suffix.lower() == ".docx" else path.read_text(encoding="utf-8-sig", errors="replace")
    start = parse_start(args.start) if args.start else None

    if any(CUE_TIME.match(l) for l in text.splitlines()[:200]):
        preamble, turns = parse_cues(text)
    else:
        preamble, turns = parse_text(text)

    if len(turns) < 3:
        # Minutes or notes: nothing to normalise.
        result = text if text.endswith("\n") else text + "\n"
    else:
        result = render(path, preamble, merge(turns), start)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(result, encoding="utf-8")
        print(f"wrote {args.out} ({len(result.splitlines())} lines)")
    else:
        sys.stdout.write(result)


if __name__ == "__main__":
    main()
