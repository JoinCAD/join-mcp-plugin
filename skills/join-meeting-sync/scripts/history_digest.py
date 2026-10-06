#!/usr/bin/env python3
"""Digest saved get-item-history pages into a per-item list of what changed.

Usage (run from the directory that holds work/):
    python history_digest.py --since 2026-09-30T13:00:00Z \\
        --history 'work/history-*.json' --item-history 'work/item-history-*.json' \\
        --items 'work/items-*.json' [--milestones work/milestones.json] \\
        [--tz America/New_York | --tz=-04:00] [--me "<current-user name>"] \\
        [--currency USD] [--terms work/terms.json] [--index work/items.md] \\
        [--json work/digest.json]

Two kinds of history go in:

- --history: the project-wide log (get-item-history {projectID, since}). It
  shows which items changed in the window, but it reports every cost before a
  change as $0 and can list cost edits the item's own log doesn't have.
- --item-history: per-item logs (get-item-history {itemID}). For an item that
  has one, it replaces the project-wide edits entirely. Fetched without
  `since`, it also gives the item's state at the start of the window.

Printed per item, in item-number order:

    ## #8 Evaluate external shading for classrooms
    https://app.join.build/<project>/items/<item>
    Now: Accepted · Assignee Ben Harris · Due 2026-10-14 · Cost Impact +$1,500 · 75% CD
    At the start: Pending · Due 2026-10-24
    - 30 Sep 14:35 · Ben Harris · Status → Accepted
    - 30 Sep 14:40 · Ben Harris · Due Date → 2026-10-14

"At the start" lists only the fields edited in the window; "?" means the
fetched history doesn't go back far enough to say. Edits by --me are marked
"(your account)": on a shared login that is not necessarily you. Items the
item list doesn't have (deleted, or not visible to you) are listed at the
end, for get-item. --index also writes every listed item and option on one
line each, for matching what was said to items:

    #8.3 · option of #8 · Increase shading by 25% … · Pending · <url>

Costs arrive as strings in two units: items-for-project gives whole currency
units with two decimals ("-86366.80"), get-item-history gives hundredths
("-8636680"). A decimal point means whole units. Printed rounded to whole
units, in --currency (default USD, shown as $).

--terms takes the saved terminology-for-project result. When the project
renames a cost concept (Budget, Running Total, Gap, …), the header says so:

    Project terms: the Budget is "Target Value". Use these labels.

Standard library only. Reads the saved files and writes stdout (and --index,
--json).
"""
import argparse
import glob
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

STATUS = {
    "PENDING": "Pending", "ACCEPTED": "Accepted", "REJECTED": "Rejected",
    "INCORPORATED": "Incorporated", "NOTAPPLICABLE": "Not Applicable", "NOTCHOSEN": "Not Chosen",
}
VISIBILITY = {"PUBLISHED": "Published", "PRIVATE_DRAFT": "Private draft", "SHARED_DRAFT": "Shared draft"}
# Edit kinds whose content the log doesn't carry: a label is all there is.
PLAIN = {
    "ADD_COMMENT": "Comment added",
    "ADD_ASSET": "Attachment added",
    "REMOVE_ASSET": "Attachment removed",
    "CHANGE_SCHEDULE_IMPACT": "Schedule Impact changed",
    "CHANGE_ESTIMATE": "Item estimate changed",
    "CHANGE_MEETING": "Meeting changed",
    "CHANGE_ACTIVITIES": "Timeline events changed",
    "CREATE_OPTION": "Option created",
    "ATTACH_OPTION": "Option attached",
    "DETACH_OPTION": "Option detached",
    "CONVERT_TO_PARENT": "Converted to an item with options",
    "REMOVE_FROM_MILESTONE": "Removed from milestone",
    "ITEM_DELETED": "Deleted",
    "ITEM_REFERENCED": "Referenced in a comment",
    "ITEM_DRAW_SET": "Contingency or allowance draw set",
    "ITEM_DRAW_UPDATE": "Contingency or allowance draw updated",
    "BASELINE": "Baselined",
    "CHANGE_PRIORITY_IMPACTS": "Priority changed",
    "CREATE_PROCORE_CHANGE_EVENT": "Procore change event created",
    "DELETE_PROCORE_CHANGE_EVENT": "Procore change event deleted",
    "CREATE_AUTODESK_POTENTIAL_CHANGE_ORDER": "Autodesk potential change order created",
    "DELETE_AUTODESK_POTENTIAL_CHANGE_ORDER": "Autodesk potential change order deleted",
    "ADD_SHARED_DRAFT_USER_EVENT": "Draft shared with a user",
    "REMOVE_SHARED_DRAFT_USER_EVENT": "Draft unshared with a user",
}
UNKNOWN = "?"
# terminology-for-project concepts and Join's default labels for them.
DEFAULT_TERMS = {
    "ESTIMATE": "Estimate", "TARGET": "Budget", "DELTA": "Delta",
    "RUNNING_TOTAL": "Running Total", "GAP": "Gap", "DIRECT_COST": "Direct Costs",
    "MARKUP": "Markups", "COST_OF_CONSTRUCTION": "Cost of Construction",
    "PROJECT_TOTAL": "Project Total", "PROJECT_RUNNING_TOTAL": "Project Running Total",
}


def load(path):
    """A saved tool result; unwraps the ReadMcpResourceTool envelope."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(d, dict) and "contents" in d:
        d = json.loads(d["contents"][0]["text"])
    return d


def paths(patterns):
    out = []
    for p in patterns or []:
        out += sorted(glob.glob(p)) or ([p] if Path(p).exists() else [])
    return out


def events_in(path):
    d = load(path)
    return d.get("events", []) if isinstance(d, dict) else d


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def zone(spec):
    """IANA name (needs the OS time zone database) or a fixed ±HH:MM offset."""
    if not spec:
        return timezone.utc
    m = re.fullmatch(r"([+-])(\d{1,2}):?(\d{2})", spec)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(spec)
    except Exception:
        sys.exit(f"unknown time zone {spec!r}; pass an offset such as --tz=-04:00")


CURRENCY = "USD"


def units(raw):
    """A cost string in whole currency units: "-86366.80" as is, "-8636680"
    (hundredths, no decimal point) divided by 100."""
    s = str(raw).strip()
    return Decimal(s) if "." in s else Decimal(int(s)) / 100


def money(raw):
    if raw in (None, ""):
        return "—"
    v = int(units(raw).to_integral_value(rounding=ROUND_HALF_UP))
    sign = "−" if v < 0 else ("+" if v > 0 else "")
    prefix = "$" if CURRENCY == "USD" else f"{CURRENCY} "
    return f"{sign}{prefix}{abs(v):,}"


def cost_label(c):
    if not c:
        return "—"
    if c.get("value") is not None:
        return money(c["value"])
    if c.get("min") is not None or c.get("max") is not None:
        return f"{money(c.get('min'))} to {money(c.get('max'))}"
    return "—"


def one_line(s):
    return re.sub(r"\s+", " ", s or "").strip()


def natural(s):
    """Item numbers in Join's order (9 before 10); unnumbered drafts last."""
    if not s:
        return [1]
    return [0] + [(0, int(p)) if p.isdigit() else (1, p.lower()) for p in re.split(r"(\d+)", s) if p]


def describe(ev, milestones, from_project_log):
    """One line per kind of edit the event records."""
    c = ev.get("eventContent") or {}
    out = []
    for kind in ev.get("eventTypes") or []:
        if kind == "CREATE_ITEM":
            vis = VISIBILITY.get(c.get("visibility"), "")
            where = milestones.get(c.get("newMilestoneID"), "")
            out.append("Created" + (f" as a {vis.lower()}" if vis and vis != "Published" else "")
                       + (f" in {where}" if where else ""))
        elif kind == "CHANGE_STATUS":
            out.append(f"Status → {STATUS.get(c.get('status'), c.get('status') or UNKNOWN)}")
        elif kind == "CHANGE_COST":
            # The project-wide log reports every "before" as $0.
            before = "" if from_project_log else f" {cost_label(c.get('oldCost'))}"
            out.append(f"Cost Impact{before} → {cost_label(c.get('newCost'))}")
        elif kind == "CHANGE_ASSIGNEE":
            a = c.get("assignee")
            out.append(f"Assignee → {a.get('name')} ({a.get('email')})" if a else "Assignee cleared")
        elif kind == "CHANGE_DUE_DATE":
            d = c.get("dueDate")
            out.append(f"Due Date → {d[:10]}" if d else "Due Date cleared")
        elif kind == "CHANGE_MILESTONE":
            old = milestones.get(c.get("oldMilestoneID"), c.get("oldMilestoneID") or UNKNOWN)
            new = milestones.get(c.get("newMilestoneID"), c.get("newMilestoneID") or UNKNOWN)
            out.append(f"Milestone {old} → {new}")
        elif kind == "CHANGE_NAME":
            out.append(f"Name → “{one_line(c.get('name'))}”")
        elif kind == "CHANGE_DESCRIPTION":
            text = one_line(c.get("description"))
            out.append("Description → “" + (text[:140] + "…" if len(text) > 140 else text) + "”" if text else "Description cleared")
        elif kind == "CHANGE_NUMBER":
            out.append(f"Number {c.get('oldNumber') or '—'} → {c.get('newNumber') or '—'}")
        elif kind == "CHANGE_CATEGORY":
            for ch in c.get("categoryChanges") or []:
                def cat(x):
                    return " ".join(p for p in ((x or {}).get("number"), (x or {}).get("name")) if p) or "—"
                out.append(f"Category {cat(ch.get('oldCategory'))} → {cat(ch.get('newCategory'))}")
            if not c.get("categoryChanges"):
                out.append("Categories changed")
        elif kind == "CHANGE_VISIBILITY":
            out.append(f"Visibility → {VISIBILITY.get(c.get('visibility'), c.get('visibility') or UNKNOWN)}")
        else:
            out.append(PLAIN.get(kind, kind.replace("_", " ").capitalize()))
    return out


def state(it):
    """An item's current state, from items-for-project, in Join's labels."""
    now = []
    if it.get("status"):
        now.append(STATUS.get(it["status"], it["status"]))
    if it.get("visibility") and it["visibility"] != "PUBLISHED":
        now.append(VISIBILITY.get(it["visibility"], it["visibility"]))
    if it.get("assignee"):
        now.append(f"Assignee {it['assignee'].get('name')}")
    if it.get("dueDate"):
        now.append(f"Due {it['dueDate'][:10]}")
    if it.get("cost"):
        now.append(f"Cost Impact {cost_label(it['cost'])}")
    if (it.get("currentMilestone") or {}).get("name"):
        now.append(it["currentMilestone"]["name"])
    return now


def at_start(before, during, milestones):
    """The fields edited in the window, as they stood when it opened. Old
    values come from the first edit in the window where the log records them
    (cost, milestone, number), else from the last edit before the window."""
    def kinds(ev):
        return ev.get("eventTypes") or []

    def first(kind):
        return next((e for e in during if kind in kinds(e)), None)

    def last_before(kind):
        return next((e for e in reversed(before) if kind in kinds(e)), None)

    out = []
    if first("CHANGE_STATUS"):
        e = last_before("CHANGE_STATUS")
        out.append(STATUS.get((e or {}).get("eventContent", {}).get("status"), UNKNOWN) if e else f"Status {UNKNOWN}")
    if first("CHANGE_ASSIGNEE"):
        e = last_before("CHANGE_ASSIGNEE")
        a = (e or {}).get("eventContent", {}).get("assignee") if e else None
        out.append(f"Assignee {a.get('name')}" if a else ("Unassigned" if e else f"Assignee {UNKNOWN}"))
    if first("CHANGE_DUE_DATE"):
        e = last_before("CHANGE_DUE_DATE")
        d = (e or {}).get("eventContent", {}).get("dueDate") if e else None
        out.append(f"Due {d[:10]}" if d else ("No Due Date" if e else f"Due {UNKNOWN}"))
    e = first("CHANGE_COST")
    if e:
        out.append(f"Cost Impact {cost_label(e['eventContent'].get('oldCost'))}")
    e = first("CHANGE_MILESTONE")
    if e:
        out.append(milestones.get(e["eventContent"].get("oldMilestoneID"), UNKNOWN))
    e = first("CHANGE_NUMBER")
    if e:
        out.append(f"Number {e['eventContent'].get('oldNumber') or '—'}")
    if first("CHANGE_NAME"):
        e = last_before("CHANGE_NAME")
        out.append(f"Name “{one_line(e['eventContent'].get('name'))}”" if e else f"Name {UNKNOWN}")
    return out


def renamed_terms(path):
    """{concept: (default label, project label)} for the concepts the project
    renames; empty without a terms file."""
    if not path:
        return {}
    d = load(path)
    terms = d.get("terms", d) if isinstance(d, dict) else {}
    out = {}
    for concept, default in DEFAULT_TERMS.items():
        label = str(terms.get(concept) or "").strip()
        if label and label != default:
            out[concept] = (default, label)
    return out


def write_index(path, items):
    lines = []
    for iid in sorted(items, key=lambda i: natural(items[i].get("number"))):
        it = items[iid]
        parent = items.get(it.get("parentID") or "")
        parts = [f"#{it.get('number') or '—'}"]
        if it.get("parentID"):
            parts.append(f"option of #{parent.get('number') if parent else UNKNOWN}")
        parts += [one_line(it.get("name"))] + state(it) + [it.get("url") or iid]
        lines.append(" · ".join(parts))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since", required=True, help="start of the window (ISO 8601 with offset)")
    ap.add_argument("--history", nargs="+", default=[], help="project-wide get-item-history pages (globs ok)")
    ap.add_argument("--item-history", nargs="+", default=[], help="per-item get-item-history pages (globs ok)")
    ap.add_argument("--items", nargs="+", default=[], help="items-for-project pages (globs ok)")
    ap.add_argument("--milestones", help="milestones-for-project result")
    ap.add_argument("--tz", help="show times in this zone: IANA name or ±HH:MM (default UTC)")
    ap.add_argument("--me", help="the current-user name (or email), to mark that account's edits")
    ap.add_argument("--currency", default="USD", help="the project's currency code (project record `currency`)")
    ap.add_argument("--terms", help="terminology-for-project result, to report renamed cost concepts")
    ap.add_argument("--index", help="also write a one-line-per-item index here")
    ap.add_argument("--json", help="also write the digest as JSON here")
    args = ap.parse_args()

    global CURRENCY
    CURRENCY = args.currency.upper()
    tz = zone(args.tz)
    since = parse_time(args.since)
    if since.tzinfo is None:
        sys.exit("--since needs a UTC offset or Z")

    milestones = {}
    if args.milestones:
        for m in load(args.milestones).get("milestones", []):
            milestones[m["id"]] = m.get("name") or m["id"]

    items = {}
    for p in paths(args.items):
        for it in load(p).get("items", []):
            items[it["id"]] = it
            for o in it.get("options") or []:
                items.setdefault(o["id"], {**o, "parentID": it["id"]})
            if (it.get("currentMilestone") or {}).get("id"):
                milestones.setdefault(it["currentMilestone"]["id"], it["currentMilestone"].get("name"))
    if args.index:
        write_index(args.index, items)

    # Per-item logs are the record wherever we have one.
    per_item = {}
    for p in paths(args.item_history):
        for ev in events_in(p):
            per_item.setdefault(ev.get("itemID"), {})[ev["id"]] = ev
    by_item = {}
    for p in paths(args.history):
        for ev in events_in(p):
            if ev.get("itemID") not in per_item:
                by_item.setdefault(ev.get("itemID"), {})[ev["id"]] = ev
    sources = {iid: "project" for iid in by_item}
    for iid, evs in per_item.items():
        by_item[iid] = evs
        sources[iid] = "item"

    def at(ev):
        return parse_time(ev.get("timestamp")) or since

    timelines = {}
    for iid, evs in by_item.items():
        ordered = sorted(evs.values(), key=at)
        during = [e for e in ordered if at(e) >= since]
        if during:
            timelines[iid] = ([e for e in ordered if at(e) < since], during)
    renamed = renamed_terms(args.terms)
    terms_line = ("Project terms: " + "; ".join(
        f"the {default} is “{label}”" for default, label in renamed.values()) + ". Use these labels.") if renamed else ""
    if not timelines:
        print("\n".join(filter(None, ["No edits in the window.", terms_line])))
        return

    me = (args.me or "").lower()

    def fmt(t):
        return parse_time(t).astimezone(tz).strftime("%d %b %H:%M")

    known = sorted((i for i in timelines if i in items), key=lambda i: natural(items[i].get("number")))
    unknown = [i for i in timelines if i not in items]
    n_edits = sum(len(d) for _, d in timelines.values())
    zone_label = since.astimezone(tz).strftime("%Z") or args.tz or "UTC"
    lines = [
        f"# Join edits from {since.astimezone(tz).strftime('%d %b %Y %H:%M')} {zone_label} to now — "
        f"{n_edits} edit{'s' if n_edits != 1 else ''} on {len(timelines)} item{'s' if len(timelines) != 1 else ''}",
        f"Times in {args.tz or 'UTC'}. Items marked [project log] have no per-item history loaded: "
        "their cost edits show no before value, and the log can list cost edits the item's own log doesn't.",
    ]
    if terms_line:
        lines.append(terms_line)
    if me:
        lines.append(f"Edits by the {args.me} account are marked (your account).")
    digest = []
    for iid in known + unknown:
        before, during = timelines[iid]
        from_project_log = sources[iid] == "project"
        rows = []
        for ev in during:
            u = ev.get("user") or {}
            mine = bool(me) and me in ((u.get("email") or "").lower(), (u.get("name") or "").lower())
            rows.append({
                "id": ev["id"], "time": ev.get("timestamp"), "user": u.get("name"), "email": u.get("email"),
                "yourAccount": mine, "types": ev.get("eventTypes") or [],
                "changes": describe(ev, milestones, from_project_log),
            })
        start_state = [] if from_project_log else at_start(before, during, milestones)
        entry = {"itemID": iid, "source": sources[iid], "atStart": start_state, "edits": rows}
        it = items.get(iid)
        if it:
            parent = items.get(it.get("parentID") or "")
            entry.update(number=it.get("number"), name=one_line(it.get("name")), url=it.get("url"),
                         parentID=it.get("parentID"), now=state(it))
            title = f"## #{it.get('number') or '—'} {one_line(it.get('name'))}"
            if it.get("parentID"):
                title += f" (option of #{parent.get('number') if parent else UNKNOWN})"
            if from_project_log:
                title += " [project log]"
            lines += ["", title]
            if it.get("url"):
                lines.append(it["url"])
            if state(it):
                lines.append("Now: " + " · ".join(state(it)))
        else:
            lines += ["", f"## {iid} (not in the item list: get-item, or deleted / not visible to you)"
                      + (" [project log]" if from_project_log else "")]
        if start_state:
            lines.append("At the start: " + " · ".join(start_state))
        for r in rows:
            who = (r["user"] or UNKNOWN) + (" (your account)" if r["yourAccount"] else "")
            lines.append(f"- {fmt(r['time'])} · {who} · " + "; ".join(r["changes"]))
        digest.append(entry)

    print("\n".join(lines))
    if args.json:
        Path(args.json).write_text(json.dumps({
            "since": since.isoformat(),
            "renamedTerms": {k: v[1] for k, v in renamed.items()},
            "items": digest,
        }, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
