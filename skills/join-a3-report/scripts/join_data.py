"""Helpers for turning saved Join connector output into A3 report content.

    import sys; sys.path.insert(0, "<skill>/scripts")
    from join_data import *

Units (see references/data-gathering.md): every connector tool returns money
in WHOLE CURRENCY UNITS — the list/cost tools as decimal strings
("33554413.16", "-39336.84"), the detailed milestone report resource as plain
numbers. Nothing is in cents. `amount()` parses either; `money()` formats in
the project's currency once `configure(project)` has been called.

Terminology: a project can rename its cost concepts (Estimate → "Baseline
Estimate", Budget → "Target Budget", …) and Join shows the renamed labels
everywhere in that project. `terminology-for-project` returns the labels;
pass its result to `configure(project, terms)` and every label this module
renders comes out in the project's own words. `T("TARGET")` gives the label
for a concept when you author text yourself. The concepts without a
terminology entry keep Join's defaults: Accepted Changes, Pending Adds /
Deducts, Potential Range, Owner Costs, Cost Impact, Schedule Impact, Past Due.

Start every author script with:

    project = project_record(load("work/project.json"), PROJECT_ID)
    configure(project, load("work/terms.json"))     # currency + terminology
"""
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------- terminology
# Concept keys and default labels exactly as terminology-for-project returns them.

DEFAULT_TERMS = {
    "ESTIMATE": "Estimate",                       # the milestone's baseline estimate; items are changes relative to it
    "TARGET": "Budget",                           # the target budget
    "DELTA": "Delta",                             # Budget − Estimate
    "RUNNING_TOTAL": "Running Total",             # Estimate + accepted items
    "GAP": "Gap",                                 # Budget − Running Total
    "DIRECT_COST": "Direct Costs",
    "MARKUP": "Markups",
    "COST_OF_CONSTRUCTION": "Cost of Construction",   # everything except Owner Costs
    "PROJECT_TOTAL": "Project Total",             # everything including Owner Costs
    "PROJECT_RUNNING_TOTAL": "Project Running Total",
}
TERMS = dict(DEFAULT_TERMS)


def set_terms(terms):
    """Install a project's terminology. Accepts the terminology-for-project
    result ({"terms": {...}}), a bare {concept: label} dict, a path to a saved
    result, or None (defaults). Unknown or blank labels fall back to the default."""
    global TERMS
    if terms is None:
        TERMS = dict(DEFAULT_TERMS)
        return TERMS
    if isinstance(terms, (str, Path)):
        terms = load(terms)
    t = terms.get("terms", terms) if isinstance(terms, dict) else {}
    TERMS = {k: (str(t.get(k) or "").strip() or v) for k, v in DEFAULT_TERMS.items()}
    return TERMS


def T(concept):
    """The project's label for a cost concept: T("TARGET") → 'Budget' or
    'Target Budget'. Use it wherever you write one of these words yourself
    (subtitles, notes, the delivery message)."""
    return TERMS.get(concept) or DEFAULT_TERMS[concept]


def renamed_terms():
    """{concept: (default, project label)} for every concept the project renamed."""
    return {k: (DEFAULT_TERMS[k], TERMS[k]) for k in DEFAULT_TERMS if TERMS[k] != DEFAULT_TERMS[k]}


def terminology_note():
    """One sentence for the delivery message, or '' when the project uses
    Join's default labels: 'This project calls the Estimate "Baseline Estimate"
    and the Budget "Target Budget"; the sheet uses those labels.'"""
    r = renamed_terms()
    if not r:
        return ""
    parts = [f'the {d} "{p}"' for d, p in r.values()]
    body = ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]
    return f"This project calls {body}; the sheet uses those labels."


def configure(project=None, terms=None, currency=None):
    """One call at the top of an author script: sets the currency from the
    project record (`currency`: USD, GBP, …) and the terminology from the
    saved terminology-for-project result. Returns (currency code, TERMS)."""
    code = currency or (project or {}).get("currency")
    if code:
        set_currency(code)
    set_terms(terms)
    return CURRENCY["code"], TERMS

# --------------------------------------------------------------------- loading

def load(path):
    """Load a saved tool result; unwraps the ReadMcpResourceTool envelope."""
    d = json.loads(Path(path).read_text())
    if isinstance(d, dict) and "contents" in d:
        d = json.loads(d["contents"][0]["text"])
    return d


def load_pages(*paths, key):
    out = []
    for p in paths:
        out.extend(load(p).get(key, []))
    return out


def load_timeline(*paths):
    """Concatenate timeline-for-project pages (activities live under timeline.activities)."""
    out = []
    for p in paths:
        out.extend((load(p).get("timeline") or {}).get("activities", []))
    return out


def load_glob(pattern, key):
    """load_glob('work/items-*.json', 'items') — concatenates every page."""
    return load_pages(*sorted(Path().glob(pattern)), key=key)


def project_record(d, project_id=None):
    """The one project record from a saved list-my-projects / search-projects
    page (`projects[]`, matched on id when given) or an already-bare record."""
    if isinstance(d, dict) and "projects" in d:
        ps = d["projects"]
        return next((p for p in ps if p["id"] == project_id), ps[0] if ps else {}) if ps else {}
    return d or {}

# ----------------------------------------------------------------------- money
# The connector returns money in whole currency units: decimal strings from
# the list/cost tools ("33554413.16"), plain numbers from the milestone report
# resource. Nothing is divided by 100 anywhere in this module.

CURRENCY_SYMBOLS = {"USD": "$", "CAD": "CA$", "AUD": "A$", "NZD": "NZ$", "SGD": "S$", "HKD": "HK$", "MXN": "MX$",
                    "GBP": "£", "EUR": "€", "JPY": "¥", "CNY": "¥", "INR": "₹", "KRW": "₩", "ILS": "₪", "PHP": "₱",
                    "CHF": "CHF ", "SEK": "kr ", "NOK": "kr ", "DKK": "kr ", "ZAR": "R", "BRL": "R$", "AED": "AED ", "SAR": "SAR "}
CURRENCY = {"code": "USD", "symbol": "$"}


def set_currency(code):
    """Format money in the project's currency (project record `currency`,
    also on get-contingency-report). Unknown codes print as 'CODE 1.2M'."""
    code = (code or "USD").upper()
    CURRENCY["code"] = code
    CURRENCY["symbol"] = CURRENCY_SYMBOLS.get(code, code + " ")
    return CURRENCY


def amount(x):
    """Connector money → float in whole units: '33554413.16' → 33554413.16,
    -39336.84 → -39336.84, None / '' → 0.0."""
    if x in (None, ""):
        return 0.0
    return float(x)


def money(value, signed=False):
    """$1.2B / $209.8M / $531K / $2,013 (or £, €, … per set_currency).
    Negative shown with a true minus."""
    if value is None:
        return "—"
    sym = CURRENCY["symbol"]
    neg = value < 0
    a = abs(value)
    if a >= 1e9:
        s = f"{sym}{a/1e9:.2f}B".replace(".00B", "B")
    elif a >= 1e6:
        s = f"{sym}{a/1e6:.1f}M"
    elif a >= 1e4:
        s = f"{sym}{a/1e3:.0f}K"
    else:
        s = f"{sym}{a:,.0f}"
    if neg:
        return "−" + s
    return ("+" + s) if signed and value > 0 else s


def money_str(x, signed=False):
    """money() straight from a connector string: money_str('2000000.00') → $2.0M; None → —."""
    return money(amount(x), signed) if x not in (None, "") else "—"


# Legacy names from when the connector returned cents. They now parse whole
# units like amount()/money_str() — nothing is divided — so an older author
# script keeps producing correct figures.
cents = amount
money_cents = money_str


def pct(part, whole):
    return f"{100*part/whole:.1f}%" if whole else "—"


def gap_class(gap):
    """Gap / Delta are shown in Join's muted grey, whatever the sign — the sign
    itself carries the meaning (negative = over budget). Never red."""
    return "gap"


def impact_class(x):
    """Cost Impact coloring as in the app: deducts (savings) green like Accepted
    Changes; adds in the default text color, not red."""
    return "pos" if x < 0 else ""


def fmt_date(iso, style="%d %b %Y"):
    if not iso:
        return "—"
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime(style)


def parse_dt(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else None


def now_stamp(tz_label="UTC"):
    """'Created 26 Sep 2026, 14:02 UTC' — the only footer text allowed. Never
    append a source note ('from Join data', 'prepared by', …)."""
    return f"Created {datetime.now(timezone.utc).strftime('%d %b %Y, %H:%M')} {tz_label}"


def fmt_span(start, end):
    """Date or date range for timeline rows, never wrapping: '15 Oct 2026',
    '26 Jun – 15 Oct 2026', '01 Dec 2025 – 30 Jun 2027' (both years when they differ)."""
    if not end or start == end:
        return fmt_date(start)
    s, e = parse_dt(start), parse_dt(end)
    if s.year == e.year:
        return f"{s.strftime('%d %b')} – {e.strftime('%d %b %Y')}"
    return f"{s.strftime('%d %b %Y')} – {e.strftime('%d %b %Y')}"

# ------------------------------------------------------------ report rows

def report_rows(report, source=None, line_type=None, counted_only=True):
    rows = report["rows"]
    if source:
        rows = [r for r in rows if r["source"] == source]
    if line_type:
        rows = [r for r in rows if r["lineType"] == line_type]
    if counted_only:
        rows = [r for r in rows if r["isCountedInTotals"]]
    return rows


def row_total(r):
    return r["costDetail"]["total"] or 0.0

# ---------------------------------------------------------- cost summary

def cost_summary(costs, project, report, items=None):
    """Join's cost summary, all-in (Project Total basis), in the project's currency.

    costs   = project-costs result (active milestone, includes Owner Costs line)
    project = record from list-my-projects (budget/estimate = Cost of Construction)
    report  = detailed milestone report for the active milestone, default cost
              mode (allocated markups, owner costs included) so item totals
              are on the same all-in basis
    items   = items_catalog() output; if omitted, pending figures come from
              the report's ITEM rows
    """
    bd = {b["name"]: amount(b["cost"]) for b in costs["breakdown"]}
    coc = bd.get("DirectCostsAndAllocatedMarkups", amount(costs["total"]))
    owner = bd.get("OwnerCosts", 0.0)
    project_total = amount(costs["total"])                      # Estimate, all-in
    budget_coc = amount(project.get("budget") or 0)
    budget_rows = sum(row_total(r) for r in report_rows(report, "MILESTONE_BUDGET"))
    budget = budget_rows if budget_rows else budget_coc          # all-in when owner-cost budget lines exist
    it = items if items is not None else item_rows(report)
    accepted = accepted_changes(it)
    pend = [i for i in it if i["status"] == "PENDING" and not i["is_option"]]
    adds = sum(i["cost_hi"] for i in pend if i["cost_hi"] > 0)
    deducts = sum(i["cost_lo"] for i in pend if i["cost_lo"] < 0)
    running = project_total + accepted
    return {
        "cost_of_construction": coc, "owner_costs": owner, "has_owner_costs": owner > 0,
        "estimate": project_total,                 # Project Total (Estimate incl. Owner Costs)
        "budget": budget, "budget_is_all_in": abs(budget - budget_coc) > 0.5,
        "accepted_changes": accepted,
        "running_total": running,                  # Project Running Total
        "pending_adds": adds, "pending_deducts": deducts, "pending_count": len(pend),
        "potential_low": running + deducts, "potential_high": running + adds,
        "gap": budget - running if budget else None,
        "gap_min": (budget - (running + adds)) if budget else None,
        "gap_max": (budget - (running + deducts)) if budget else None,
    }


def accepted_changes(items):
    """Accepted Changes = accepted items plus accepted OPTIONS whose parent is
    not itself an accepted row (an item accepted via one of its options shows
    up only as that option in the milestone report)."""
    accepted_ids = {i["id"] for i in items if i["status"] == "ACCEPTED"}
    tot = 0.0
    for i in items:
        if i["status"] != "ACCEPTED":
            continue
        if not i["is_option"] or i.get("parent_id") not in accepted_ids:
            tot += i["cost"]
    return tot


def header_metrics(cs, risks=None, next_event=None):
    """The default header strip: Running Total · Budget · Gap · Pending Deducts ·
    Pending Adds · Risk Cost Impact (if any) · Next milestone/event (if any),
    labelled in the project's terminology (Project Running Total, Budget, Gap,
    Estimate and Cost of Construction come from T())."""
    m = [
        {"label": T("PROJECT_RUNNING_TOTAL"), "value": money(cs["running_total"]),
         "note": f"{T('ESTIMATE')} + Accepted Changes" + (", incl. Owner Costs" if cs["has_owner_costs"] else "")},
        {"label": T("TARGET"), "value": money(cs["budget"]) if cs["budget"] else f"No {T('TARGET')}",
         "note": "incl. Owner Costs" if cs["budget_is_all_in"] else (T("COST_OF_CONSTRUCTION") if cs["has_owner_costs"] else "")},
        {"label": T("GAP"), "value": money(cs["gap"], signed=True) if cs["gap"] is not None else "—", "tone": gap_class(cs["gap"]),
         "note": (f"{T('TARGET')} − {T('RUNNING_TOTAL')}" if cs["gap"] is not None else "")},
        {"label": "Pending Deducts", "value": money(cs["pending_deducts"], signed=True), "note": f"{cs['pending_count']} pending items"},
        {"label": "Pending Adds", "value": money(cs["pending_adds"], signed=True),
         "note": f"Potential Range {money(cs['potential_low'])} – {money(cs['potential_high'])}"},
    ]
    if risks:
        rs = open_risks(risks)
        if rs:
            exp = risk_cost_impact_total(risks)
            m.append({"label": "Open Risks", "value": str(len(rs)), "note": f"Cost Impact {money(exp)}" if exp else "Cost Impact not set"})
    if next_event:
        m.append({"label": "Next " + ("Milestone" if next_event.get("milestoneID") else "Event"),
                  "value": fmt_date(next_event["startDate"]), "note": next_event["name"]})
    return m

# ---------------------------------------------------------- rollups

UNIFORMAT_L1 = {"A": "Substructure", "B": "Shell", "C": "Interiors", "D": "Services", "E": "Equipment & Furnishings",
                "F": "Special Construction & Demolition", "G": "Building Sitework", "Z": "General"}
MASTERFORMAT_L1 = {"01": "General Requirements", "02": "Existing Conditions", "03": "Concrete", "04": "Masonry", "05": "Metals",
                   "06": "Wood, Plastics, Composites", "07": "Thermal & Moisture Protection", "08": "Openings", "09": "Finishes",
                   "10": "Specialties", "11": "Equipment", "12": "Furnishings", "13": "Special Construction", "14": "Conveying Equipment",
                   "21": "Fire Suppression", "22": "Plumbing", "23": "HVAC", "25": "Integrated Automation", "26": "Electrical",
                   "27": "Communications", "28": "Electronic Safety & Security", "31": "Earthwork", "32": "Exterior Improvements",
                   "33": "Utilities", "34": "Transportation", "35": "Waterway & Marine", "40": "Process Interconnections",
                   "41": "Material Processing", "42": "Process Heating/Cooling", "43": "Process Gas & Liquid", "44": "Pollution Control",
                   "45": "Industry-Specific Manufacturing", "46": "Water & Wastewater", "48": "Electrical Power Generation"}


def _is_uf(num):
    return bool(re.fullmatch(r"[A-Z]\d*(\.\d+)?", num or ""))


def _is_mf(num):
    return bool(re.fullmatch(r"\d{6}(\.\d+)?", num or ""))


def rollup(rows, keyfn, value=row_total):
    """Group rows by keyfn(row). Returns [(label, dollars)] sorted ALPHANUMERICALLY
    (Join lists categories in their natural order, not by size)."""
    acc = defaultdict(float)
    for r in rows:
        k = keyfn(r)
        if k is not None:
            acc[k] += value(r) or 0.0
    return sorted(((k, v) for k, v in acc.items() if abs(v) >= 0.5), key=lambda kv: natural_key(kv[0]))


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


OWNER_COSTS = "Owner Costs"


def by_uniformat_l1(r):
    if r.get("lineType") == "OWNER_COST":
        return OWNER_COSTS
    for c in r["categories"]:
        if _is_uf(c["number"]):
            return f"{c['number'][0]} {UNIFORMAT_L1.get(c['number'][0], '')}".strip()
    return "Uncategorized"


def by_masterformat_l1(r):
    if r.get("lineType") == "OWNER_COST":
        return OWNER_COSTS
    for c in r["categories"]:
        if _is_mf(c["number"]):
            return f"{c['number'][:2]} {MASTERFORMAT_L1.get(c['number'][:2], '')}".strip()
    return "Uncategorized"


def by_custom(values, unassigned="Unassigned"):
    """Rollup by a custom categorization (Location, Building, Phase, …):
    pass the set of that categorization's category numbers/names."""
    vs = set(values)

    def f(r):
        if r.get("lineType") == "OWNER_COST":
            return OWNER_COSTS
        for c in r["categories"]:
            if c["number"] in vs or (c["name"] and c["name"] in vs):
                return c["number"] or c["name"]
        return unassigned
    return f


def distinct_categories(rows, level=1):
    """Custom category values present on rows, with row count and total —
    use to see what a Location-type categorization contains."""
    acc = defaultdict(lambda: [0, 0.0])
    for r in rows:
        for c in r["categories"]:
            if c["level"] == level and not _is_uf(c["number"]) and not _is_mf(c["number"]):
                k = c["number"] or c["name"]
                acc[k][0] += 1
                acc[k][1] += row_total(r)
    return sorted(acc.items(), key=lambda kv: natural_key(kv[0]))


def unwrap_item(d):
    """get-item returns {"item": {...}} or {"option": {...}}; accept either or a bare record."""
    return d.get("item") or d.get("option") or d


def categorization_values(item_details, name):
    """Values of a named categorization observed on get-item results (or on
    items-for-project rows that carry categories), e.g.
    categorization_values(details, 'Location') -> {'Main Clinic', 'Building A'}."""
    vs = set()
    for d in item_details:
        d = unwrap_item(d)
        for c in d.get("categories", []):
            if c["categorization"]["name"].lower() == name.lower():
                vs.add(c["number"] or c["name"])
    return vs


def pick_breakdown_axis(categorizations, item_details, est_rows, min_coverage=0.5):
    """Default axis for the cost breakdown: a location / programmatic-area
    categorization if the project has one and the estimate lines use it; else
    UniFormat (system); else MasterFormat (trade). Returns (label, keyfn).

    Custom-category values are taken from get-item details (the only place
    the connector names the categorization), so call get-item on the pending
    items first. Prints the share of estimate landing in 'Unassigned'; if it
    is large, list values with distinct_categories() and pass the full set to
    by_custom() yourself."""
    names = [c["categorization"]["name"] for c in categorizations.get("items", [])]
    est_rows = [r for r in est_rows if r.get("lineType") != "OWNER_COST"]
    total = sum(row_total(r) for r in est_rows) or 1.0
    for n in names:
        if re.search(r"location|area|building|program|zone|department|phase|wing|site", n, re.I):
            vals = {v for v in categorization_values(item_details, n) if v}
            if not vals:
                continue
            keyfn = by_custom(vals)
            assigned = sum(row_total(r) for r in est_rows if keyfn(r) != "Unassigned")
            print(f"axis {n!r}: {len(vals)} values, {100*assigned/total:.0f}% of estimate assigned")
            if assigned >= min_coverage * total:
                return n, keyfn
    if any(_is_uf(c["number"]) for r in est_rows for c in r["categories"]):
        return "UniFormat", by_uniformat_l1
    if any(_is_mf(c["number"]) for r in est_rows for c in r["categories"]):
        return "MasterFormat", by_masterformat_l1
    return None, None


def breakdown_table(pairs, budget=None, cs=None):
    """Join's milestone-summary columns per category: Estimate · Budget · Delta
    (headers in the project's terminology), alphanumeric, with a Project Total
    row; when cs is given, the buildup rows
    (Accepted Changes, Project Running Total, Owner Costs) follow so a short
    category list still fills the panel."""
    rows, classes = [], []
    for label, v in pairs:
        b = (budget or {}).get(label)
        d = (b - v) if b is not None else None
        rows.append([esc(label), money(v), money(b) if b is not None else "—",
                     f'<span class="{gap_class(d)}">{money(d, signed=True)}</span>' if d is not None else "—"])
        classes.append("")
    if cs:
        if cs["has_owner_costs"]:
            rows.append(["Owner Costs", money(cs["owner_costs"]), "", ""]); classes.append("")
        bt = cs["budget"] if cs["budget"] else None
        rows.append([f"{T('PROJECT_TOTAL')} ({T('ESTIMATE')})", money(cs["estimate"]), money(bt) if bt else "—",
                     f'<span class="{gap_class(bt - cs["estimate"])}">{money(bt - cs["estimate"], signed=True)}</span>' if bt else "—"]); classes.append("total")
        rows.append(["Accepted Changes", money(cs["accepted_changes"], signed=True), "", ""]); classes.append("")
        rows.append([T("PROJECT_RUNNING_TOTAL"), money(cs["running_total"]), money(bt) if bt else "—",
                     f'<span class="{gap_class(cs["gap"])}">{money(cs["gap"], signed=True)}</span>' if cs["gap"] is not None else "—"]); classes.append("total")
    return table(["Category", T("ESTIMATE"), T("TARGET"), T("DELTA")], rows, num_cols=(1, 2, 3), row_classes=classes)


def buildup(cs, report_separated=None):
    """Cost buildup rows for when a breakdown won't fit: Direct Costs / Markups /
    Cost of Construction / Owner Costs / Project Total, each labelled in the
    project's terminology. Pass a report fetched with markupMode
    SEPARATED_MARKUPS to split direct costs from markups; otherwise only Cost
    of Construction / Owner Costs / Project Total are shown."""
    rows = []
    if report_separated:
        by_type = defaultdict(float)
        for r in report_rows(report_separated, "MILESTONE_ESTIMATE"):
            by_type[r["lineType"]] += row_total(r)
        direct = by_type.pop("DIRECT_COST", 0.0)
        owner = by_type.pop("OWNER_COST", 0.0)
        markups = sum(by_type.values())
        rows += [(T("DIRECT_COST"), direct, "sub"), (T("MARKUP"), markups, "sub")]
    rows.append((T("COST_OF_CONSTRUCTION"), cs["cost_of_construction"], ""))
    if cs["has_owner_costs"]:
        rows.append(("Owner Costs", cs["owner_costs"], ""))
    rows.append((f"{T('PROJECT_TOTAL')} ({T('ESTIMATE')})", cs["estimate"], "total"))
    rows.append(("Accepted Changes", cs["accepted_changes"], "sub"))
    rows.append((T("PROJECT_RUNNING_TOTAL"), cs["running_total"], "total"))
    return rows

# ---------------------------------------------------------------------- items

def item_rows(report):
    """Item state carried in the milestone report (status, assignee, dates,
    cost impact on the report's cost basis). Costs are SUMMED per item across
    rows. Parents with options don't appear — only their options do."""
    acc = {}
    for r in report["rows"]:
        if r["source"] != "ITEM" or not r.get("itemDetails"):
            continue
        d = r["itemDetails"]
        dt = r["derivedTotals"] or {}
        tot = 0.0
        for k in ("pending", "accepted", "rejected"):
            if dt.get(k) and dt[k].get("total") is not None:
                tot += dt[k]["total"]
        it = acc.get(d["itemID"])
        if it is None:
            it = acc[d["itemID"]] = {"id": d["itemID"], "number": d.get("number") or "", "name": d["name"].strip(),
                                     "status": d["status"], "assignee": d.get("assigneeName"), "assignee_email": None,
                                     "updated": d.get("updateTime"), "created": d.get("createdAt"), "due": d.get("dueDate"),
                                     "cost": 0.0, "cost_lo": 0.0, "cost_hi": 0.0, "is_option": d.get("itemType") == "OPTION",
                                     "categories": r["categories"], "visibility": d.get("visibility"), "options": [], "milestone_id": None}
        it["cost"] += tot
        it["cost_lo"] = it["cost_hi"] = it["cost"]
    return list(acc.values())


def items_catalog(items_list, report=None, details=None):
    """Merge items-for-project pages with report state and get-item details.

    items_list: concatenated `items[]` (cost as decimal strings in whole
    units; CostScalar or CostRange; carries status, assignee, dueDate,
    scheduleImpact and categories on current connector versions).
    report: detailed milestone report (adds status/assignee for the active
    milestone). details: list of get-item results (adds activity links and,
    on older connectors, schedule impact, due date and categories)."""
    state = {i["id"]: i for i in item_rows(report)} if report else {}
    det = {}
    for d in details or []:
        d = unwrap_item(d)
        det[d["id"]] = d
    out = []
    for it in items_list:
        c = it.get("cost") or {}
        if "min" in c or "max" in c:            # CostRange (with or without __typename)
            lo, hi = amount(c.get("min")), amount(c.get("max"))
        else:                                   # CostScalar
            lo = hi = amount(c.get("value"))
        st = state.get(it["id"], {})
        dd = det.get(it["id"], {})
        assignee = (dd.get("assignee") or it.get("assignee") or {})
        status = dd.get("status") or it.get("status") or st.get("status")
        out.append({"id": it["id"], "number": it.get("number") or "", "name": it["name"].strip(),
                    "cost_lo": lo, "cost_hi": hi, "cost": hi if abs(hi) >= abs(lo) else lo,
                    "milestone_id": (it.get("milestone") or it.get("currentMilestone") or {}).get("id"),
                    "is_option": bool(it.get("parentID")), "parent_id": it.get("parentID"), "options": it.get("options") or [],
                    "status": status, "assignee": assignee.get("name") or st.get("assignee"),
                    "assignee_email": assignee.get("email"), "updated": dd.get("updateTime") or it.get("updateTime") or st.get("updated"),
                    "due": dd.get("dueDate") or it.get("dueDate") or st.get("due"), "schedule": dd.get("scheduleImpact") or it.get("scheduleImpact"),
                    "activity_ids": dd.get("activityIDs") or [], "categories": dd.get("categories") or it.get("categories") or st.get("categories", []),
                    "url": it.get("url")})
    return out


def cost_impact_label(it, signed=True):
    """Cost Impact: '−$1.8M to +$2.0M' for ranges, '−$10.6M' for scalars."""
    if abs(it["cost_hi"] - it["cost_lo"]) < 0.5:
        return money(it["cost_hi"], signed)
    return f"{money(it['cost_lo'], signed)} to {money(it['cost_hi'], signed)}"


def schedule_impact_label(si):
    """Schedule Impact from get-item: '−100 d · critical path', 'TBD', 'N/A', '—'."""
    if not si:
        return "—"
    t = si.get("type") or ""
    if t.endswith("TBD"):
        return "TBD"
    if t.endswith("NA"):
        return "N/A"
    d = si.get("days")
    if d is None:
        return "—"
    s = f"{d:+d} d".replace("-", "−")
    return s + (" · CP" if si.get("criticalPath") else "")   # CP = critical path; say so in the subtitle


def due_cell(it, as_of):
    """Due Date cell: the date, in Join's item-pastdue coral when pending and past due."""
    if not it.get("due"):
        return "—"
    d = fmt_date(it["due"])
    return f'<span class="pastdue">{d}</span>' if is_past_due(it, as_of) else d


def is_past_due(it, as_of):
    return bool(it.get("due")) and it.get("status") == "PENDING" and parse_dt(it["due"]) < as_of


def top_decisions(catalog, milestone_id=None, n=8, statuses=("PENDING", None)):
    """Parent-level pending items with the largest Cost Impact (options fold
    into their parent; a parent's range is its Cost Impact)."""
    pool = [i for i in catalog if not i["is_option"] and i["status"] in statuses
            and (milestone_id is None or i["milestone_id"] in (milestone_id, None))]
    return sorted(pool, key=lambda i: -max(abs(i["cost_lo"]), abs(i["cost_hi"])))[:n]


def items_by(items, keyfn):
    g = defaultdict(list)
    for i in items:
        g[keyfn(i)].append(i)
    return dict(g)


def category_of(item, categorization_name=None, values=None):
    for c in item.get("categories", []):
        if categorization_name and c.get("categorization", {}).get("name", "").lower() == categorization_name.lower():
            return c["number"] or c["name"]
        if values and (c["number"] in values or c.get("name") in values):
            return c["number"] or c["name"]
    return "Unassigned"


def item_key_for_axis(axis):
    """Item-side grouping function matching a breakdown axis label from
    pick_breakdown_axis(): 'UniFormat' / 'MasterFormat' map the item's UF/MF
    category to the same Level-1 label the estimate rollup uses; any other
    axis name is a custom categorization looked up by name."""
    if axis == "UniFormat":
        return lambda i: by_uniformat_l1({"categories": [{"number": c["number"]} for c in i.get("categories", [])]})
    if axis == "MasterFormat":
        return lambda i: by_masterformat_l1({"categories": [{"number": c["number"]} for c in i.get("categories", [])]})
    return lambda i: category_of(i, axis)


def company_of(email, mapping=None):
    """Company from an assignee's email domain — 'mia.polk@masterbuilder.business'
    -> 'Masterbuilder'. Pass mapping={'masterbuilder.business': 'Master Builder Co.'}
    after confirming names with the user."""
    if not email or "@" not in email:
        return "Unassigned"
    dom = email.split("@", 1)[1].lower()
    if mapping and dom in mapping:
        return mapping[dom]
    stem = dom.split(".")[0]
    return stem.capitalize()


def pick_company_axis(categorizations):
    """Work in flight groups by company. If the project has a categorization
    that names companies (Responsible Party, Responsibility, Company, Firm,
    Subcontractor, Trade Partner), use it; otherwise fall back to the
    assignee's email domain. Returns the categorization name or 'company'."""
    for c in categorizations.get("items", []):
        n = c["categorization"]["name"]
        if re.search(r"responsib|company|firm|subcontractor|trade partner|vendor|organi[sz]ation", n, re.I):
            return n
    return "company"


def work_in_flight(catalog, as_of, mapping=None, by="company"):
    """Rows for the Work in Flight table, grouped by company (default) or by a
    categorization such as 'Responsible Party' (by='Responsible Party').
    Each: {group, pending, past_due, cost_impact, updated_30d}."""
    def key(i):
        return company_of(i.get("assignee_email"), mapping) if by == "company" else category_of(i, by)
    g = defaultdict(lambda: {"pending": 0, "past_due": 0, "cost_impact": 0.0, "updated_30d": 0})
    for i in catalog:
        if i["is_option"] or i["status"] != "PENDING":
            continue
        row = g[key(i)]
        row["pending"] += 1
        row["cost_impact"] += i["cost"]
        if is_past_due(i, as_of):
            row["past_due"] += 1
        if i.get("updated") and (as_of - parse_dt(i["updated"])).days <= 30:
            row["updated_30d"] += 1
    rows = [dict(group=k, **v) for k, v in g.items()]
    return sorted(rows, key=lambda r: (-r["pending"], r["group"]))

# ------------------------------------------------------------------ gap analysis

def gap_analysis(est_rows, bud_rows, keyfn, catalog, cat_of, activities, as_of, horizon_days=90, n=8):
    """Where decisions can most move the needle. decide_by in the past sets past_due. Per category on the chosen axis:
    Estimate, Budget, Delta (Budget − Estimate), pending Cost Impact range
    (variability), and the nearest due date / linked activity ('decide by').
    Ranked by |Delta| + range width, with soon-to-be-committed categories
    pulled up. Returns rows sorted by that score."""
    est = dict(rollup(est_rows, keyfn)); bud = dict(rollup(bud_rows, keyfn))
    pend = [i for i in catalog if not i["is_option"] and i["status"] == "PENDING"]
    act_by_id = {a["id"]: a for a in activities if parse_dt(a["startDate"]) >= as_of}   # past meetings are not deadlines
    horizon = as_of + timedelta(days=horizon_days)
    rows = []
    cats = set(est) | set(bud) | {cat_of(i) for i in pend}
    for cat in sorted(cats, key=natural_key):
        e, b = est.get(cat, 0.0), bud.get(cat, 0.0)
        items = [i for i in pend if cat_of(i) == cat]
        lo = sum(min(i["cost_lo"], 0) for i in items); hi = sum(max(i["cost_hi"], 0) for i in items)
        dates = [parse_dt(i["due"]) for i in items if i.get("due")]
        for i in items:
            for aid in i.get("activity_ids", []):
                if aid in act_by_id:
                    dates.append(parse_dt(act_by_id[aid]["startDate"]))
        decide_by = min(dates) if dates else None
        soon = decide_by is not None and as_of <= decide_by <= horizon
        past_due = decide_by is not None and decide_by < as_of
        score = abs(b - e) + (hi - lo) + (0.25 * abs(b - e) if (soon or past_due) else 0)
        rows.append({"category": cat, "estimate": e, "budget": b, "delta": b - e, "pending_low": lo, "pending_high": hi,
                     "pending_count": len(items), "decide_by": decide_by, "soon": soon, "past_due": past_due, "score": score})
    rows = [r for r in rows if (r["pending_count"] or abs(r["delta"]) >= 0.5) and r["category"] != OWNER_COSTS]
    return sorted(rows, key=lambda r: -r["score"])[:n]

UNGROUPED = {"Unassigned", "Uncategorized", "Not Assigned", "Unspecified", "None", ""}


def _is_ungrouped(label):
    return str(label).strip().lower() in {u.lower() for u in UNGROUPED} or bool(re.search(r"not assigned|unassigned|uncategori", str(label), re.I))


def gap_axis_check(est_rows, bud_rows, keyfn, catalog=None, cat_of=None, max_ungrouped=0.5, min_budgeted=0.5):
    """Is a Gap Analysis on this axis worth a panel? Returns (ok, reason).

    It is NOT when the estimate and the budget don't share a meaningful
    categorization: no budget lines at all; more than half of the estimate
    (or of the pending items) lands in Unassigned / Uncategorized; fewer
    than two real categories; or most categories that carry estimate have a
    zero Budget (the Delta column would just mirror the Estimate). When it
    returns False, use Cost trend by milestone or Decisions by area instead
    and say why in delivery."""
    est = [(k, v) for k, v in rollup(est_rows, keyfn) if k != OWNER_COSTS]
    bud = dict(rollup(bud_rows, keyfn))
    if not bud_rows or not any(abs(v) >= 0.5 for v in bud.values()):
        return False, f"no {T('TARGET')} lines on the milestone"
    tot = sum(v for _, v in est) or 1.0
    ungrouped = sum(v for k, v in est if _is_ungrouped(k))
    if ungrouped / tot > max_ungrouped:
        return False, f"{100*ungrouped/tot:.0f}% of the estimate is Unassigned/Uncategorized on this axis"
    real = [(k, v) for k, v in est if not _is_ungrouped(k)]
    if len(real) < 2:
        return False, "fewer than two categories on this axis"
    budgeted = sum(1 for k, v in real if abs(bud.get(k, 0.0)) >= 0.5)
    if budgeted < min_budgeted * len(real):
        return False, f"only {budgeted} of {len(real)} categories carry a {T('TARGET')}"
    if catalog is not None and cat_of is not None:
        pend = [i for i in catalog if not i["is_option"] and i["status"] == "PENDING"]
        if pend:
            un = sum(1 for i in pend if _is_ungrouped(cat_of(i)))
            if un / len(pend) > max_ungrouped:
                return False, f"{un} of {len(pend)} pending items have no category on this axis"
    return True, ""


def gap_table(rows, wrap=False):
    """Gap Analysis panel body from gap_analysis() rows. Columns that are
    empty for every row are dropped (except Decide by — a deadline column
    stays even when blank). Names truncate rather than wrap."""
    out = []
    for r in rows:
        when = r["decide_by"].strftime("%d %b %Y") if r["decide_by"] else "—"
        if r["past_due"]:
            when += ' <span class="chip pastdue">Past Due</span>'
        elif r["soon"]:
            when += ' <span class="chip pending">Soon</span>'
        out.append([esc(r["category"]), f'<span class="{gap_class(r["delta"])}">{money(r["delta"], signed=True)}</span>',
                    f'{money(r["pending_low"], signed=True)} to {money(r["pending_high"], signed=True)} <span class="muted">({r["pending_count"]})</span>', when])
    return table(["Category", f"{T('DELTA')} to {T('TARGET')}", "Pending Cost Impact", "Decide by"], out, num_cols=(1, 2), wrap=wrap)


# ------------------------------------------------------------ decisions by area

AREA_AXIS_RE = r"\bPIT\b|TVD|cluster|location|building|area|phase|zone|department|program|wing|site|increment|package"


def pick_area_axis(categorizations, catalog):
    """Grouping axis for Decisions by Area, in order of preference: an
    organizational categorization the project defined (PIT, TVD Cluster,
    Location, Building, Area, Phase, Increment, Bid/Work Package, …) that at
    least half of the pending items carry → UniFormat Level 1 → a Bid Package
    categorization → MasterFormat Level 1. Returns (label, item_keyfn) or
    (None, None). Item categories come from get-item details."""
    pend = [i for i in catalog if not i["is_option"] and i["status"] == "PENDING"]
    if not pend:
        return None, None

    def coverage(keyfn):
        return sum(1 for i in pend if not _is_ungrouped(keyfn(i))) / len(pend)

    names = [c["categorization"]["name"] for c in categorizations.get("items", [])]
    org = [n for n in names if re.search(AREA_AXIS_RE, n, re.I) and not re.search(r"package", n, re.I)]
    for n in org:
        f = item_key_for_axis(n)
        if coverage(f) >= 0.5:
            return n, f
    f = item_key_for_axis("UniFormat")
    if coverage(f) >= 0.5:
        return "UniFormat Level 1", f
    for n in [n for n in names if re.search(r"bid|work package|package", n, re.I)]:
        f = item_key_for_axis(n)
        if coverage(f) >= 0.5:
            return n, f
    f = item_key_for_axis("MasterFormat")
    if coverage(f) >= 0.5:
        return "MasterFormat Level 1", f
    best = max(org + names, key=lambda n: coverage(item_key_for_axis(n)), default=None)
    return (best, item_key_for_axis(best)) if best else (None, None)


def schedule_days(it):
    si = it.get("schedule") or {}
    t = si.get("type") or ""
    if t.endswith("TBD") or t.endswith("NA") or si.get("days") is None:
        return None
    return si["days"]


def decisions_by_area(catalog, keyfn, as_of, milestone_id=None, n=9):
    """One row per area: pending count, pending Cost Impact range
    (sum of deducts … sum of adds), largest Schedule Impact in days (with
    critical-path flag) when any item carries one, and the next Due Date
    among the area's pending items (earliest; Past Due when already passed).
    Sorted alphanumerically by area, Unassigned last."""
    pend = [i for i in catalog if not i["is_option"] and i["status"] == "PENDING"
            and (milestone_id is None or i["milestone_id"] in (milestone_id, None))]
    groups = items_by(pend, keyfn)
    rows = []
    for area, items in groups.items():
        lo = sum(min(i["cost_lo"], 0) for i in items); hi = sum(max(i["cost_hi"], 0) for i in items)
        days = [(abs(schedule_days(i)), schedule_days(i), bool((i.get("schedule") or {}).get("criticalPath"))) for i in items if schedule_days(i) is not None]
        tbd = any(((i.get("schedule") or {}).get("type") or "").endswith("TBD") for i in items)
        mx = max(days) if days else None
        dues = sorted(parse_dt(i["due"]) for i in items if i.get("due"))
        nxt = next((d for d in dues if d >= as_of), dues[0] if dues else None)
        rows.append({"area": area, "pending": len(items), "pending_low": lo, "pending_high": hi,
                     "max_schedule_days": mx[1] if mx else None, "max_schedule_cp": mx[2] if mx else False, "schedule_tbd": tbd,
                     "next_due": nxt, "next_due_past": bool(nxt and nxt < as_of), "items": sorted(items, key=lambda i: -max(abs(i["cost_lo"]), abs(i["cost_hi"])))})
    rows.sort(key=lambda r: (_is_ungrouped(r["area"]), natural_key(r["area"])))
    return rows[:n]


def decisions_by_area_table(rows, axis_label, as_of):
    """Area · Pending · Cost Impact (pending range) · Schedule Impact (the
    largest among the area's items, '−100 d · CP' or 'TBD') · Next Due (the
    earliest upcoming Due Date; coral when already Past Due). Short headers so
    the area names don't truncate; the subtitle spells them out. Schedule
    Impact is dropped when no item in any area carries one; Next Due stays
    even when every cell is blank (a deadline column is always shown)."""
    out = []
    for r in rows:
        rng = (f'{money(r["pending_low"], signed=True)} to {money(r["pending_high"], signed=True)}'
               if r["pending_low"] < -0.5 and r["pending_high"] > 0.5 else money(r["pending_high"] if r["pending_high"] > 0.5 else r["pending_low"], signed=True))
        if r["max_schedule_days"] is not None:
            sched = f'{r["max_schedule_days"]:+d} d'.replace("-", "−") + (" · CP" if r["max_schedule_cp"] else "")
        else:
            sched = "TBD" if r["schedule_tbd"] else "—"
        due = "—"
        if r["next_due"]:
            due = r["next_due"].strftime("%d %b %Y")
            if r["next_due_past"]:
                due = f'<span class="pastdue">{due}</span>'
        out.append([esc(r["area"]), str(r["pending"]), rng, sched, due])
    return table([axis_label, "Pending", "Cost Impact", "Schedule Impact", "Next Due"], out,
                 num_cols=(1, 2), nowrap_cols=(3, 4), keep_cols=("Next Due",))


# ------------------------------------------------------------- recent activity

HISTORY_EVENT_LABEL = {"CREATE_ITEM": "New item", "CHANGE_STATUS": "Status changed", "CHANGE_COST": "Cost Impact changed",
                       "CHANGE_MILESTONE": "Moved milestone", "CHANGE_ESTIMATE": "Estimate changed", "CHANGE_DUE_DATE": "Due Date changed",
                       "CHANGE_SCHEDULE_IMPACT": "Schedule Impact changed", "CHANGE_ASSIGNEE": "Reassigned", "CREATE_OPTION": "Option added",
                       "ADD_COMMENT": "Comment", "CHANGE_ACTIVITIES": "Linked to timeline", "ITEM_DELETED": "Deleted"}
SIGNIFICANT_EVENTS = ("CREATE_ITEM", "CHANGE_STATUS", "CHANGE_COST", "CHANGE_MILESTONE", "CHANGE_ESTIMATE", "CHANGE_DUE_DATE",
                      "CHANGE_SCHEDULE_IMPACT", "CREATE_OPTION")


def _ev_field(ev, *names):
    for n in names:
        v = ev.get(n)
        if v not in (None, ""):
            return v
    return None


def history_events(history_pages):
    """Flatten get-item-history pages (project-wide or per item) into
    {time, type, item_id, item_number, item_name, text}. Tolerant of field
    naming: type from eventType/type, time from timestamp/createdAt/time,
    item from item{id,number,name} or itemID."""
    out = []
    for page in history_pages:
        evs = page if isinstance(page, list) else (page.get("events") or page.get("history") or page.get("edits") or [])
        for ev in evs:
            t = parse_dt(_ev_field(ev, "timestamp", "createdAt", "time", "occurredAt", "date"))
            typ = str(_ev_field(ev, "eventType", "type", "kind") or "UNKNOWN_EVENT").upper()
            item = ev.get("item") if isinstance(ev.get("item"), dict) else {}
            out.append({"time": t, "type": typ, "item_id": item.get("id") or _ev_field(ev, "itemID", "itemId"),
                        "item_number": item.get("number") or _ev_field(ev, "itemNumber", "number"), "item_name": item.get("name") or _ev_field(ev, "itemName"),
                        "text": _ev_field(ev, "description", "summary", "details", "text") or "", "raw": ev})
    return [e for e in out if e["time"]]


def recent_activity(catalog, activities, as_of, risks=None, history=None, weeks=2, min_rows=6, max_weeks=4, n=10):
    """Rows for the Recent Activity panel: item changes and timeline events in
    the last `weeks` weeks (widened one week at a time, up to max_weeks, until
    at least min_rows are found). Newest first, one row per item (its latest
    significant edit). Each row: {date, kind, text, detail, url_key, id}.
    kind ∈ item-created · item-status · item-updated · risk-created ·
    risk-updated · event · milestone · phase-start · phase-end.

    history: get-item-history pages for the PROJECT (since = as_of − 4 weeks),
    via history_events(). With it, rows say what changed (status, Cost
    Impact, milestone, Due Date …); without it, item createdAt/updateTime are
    used and the row just says Updated. Items carry their current status and
    Cost Impact so the reader sees what moved. Returns (rows, weeks_used)."""
    by_id = {i["id"]: i for i in catalog}
    evs = [e for e in history_events(history or []) if e["type"] in SIGNIFICANT_EVENTS or e["type"] == "CHANGE_STATUS"]

    def build(wk):
        since = as_of - timedelta(weeks=wk)
        rows, seen = [], set()
        for e in sorted(evs, key=lambda e: -e["time"].timestamp()):
            if e["time"] < since or e["time"] > as_of or e["item_id"] in seen:
                continue
            i = by_id.get(e["item_id"])
            if i is not None and i["is_option"]:
                continue
            seen.add(e["item_id"])
            label = HISTORY_EVENT_LABEL.get(e["type"], e["type"].replace("_", " ").capitalize())
            if e["type"] == "CHANGE_STATUS" and i:
                label = f'Now {STATUS_LABEL.get(i["status"], i["status"] or "")}'
            elif e["type"] == "CREATE_ITEM":
                label = "New"
            cur = cost_impact_label(i) if i else (e["text"] or "")
            name = f'{(i or {}).get("number") or e["item_number"] or ""}. {(i or {}).get("name") or e["item_name"] or ""}'.strip(". ")
            rows.append({"date": e["time"], "kind": "item-created" if e["type"] == "CREATE_ITEM" else ("item-status" if e["type"] == "CHANGE_STATUS" else "item-updated"),
                         "id": e["item_id"], "url_key": "item", "text": name, "detail": f'{label} · {cur}'.strip(" ·")})
        if not evs:
            for i in catalog:
                if i["is_option"]:
                    continue
                cr, up = parse_dt(i.get("created")), parse_dt(i.get("updated"))
                if cr and since <= cr <= as_of:
                    rows.append({"date": cr, "kind": "item-created", "id": i["id"], "url_key": "item",
                                 "text": f'{i["number"]}. {i["name"]}', "detail": f'New · {cost_impact_label(i)}'})
                elif up and since <= up <= as_of:
                    rows.append({"date": up, "kind": "item-updated", "id": i["id"], "url_key": "item",
                                 "text": f'{i["number"]}. {i["name"]}', "detail": f'Updated · {cost_impact_label(i)}'})
        for a in activities:
            s, e = parse_dt(a["startDate"]), parse_dt(a["endDate"])
            k = classify_activity(a)
            if k in ("milestone", "event") and since <= s <= as_of:
                rows.append({"date": s, "kind": k, "id": a["id"], "url_key": "timeline", "text": a["name"], "detail": "Milestone" if k == "milestone" else "Event"})
            elif k == "phase":
                if since <= s <= as_of:
                    rows.append({"date": s, "kind": "phase-start", "id": a["id"], "url_key": "timeline", "text": a["name"], "detail": f'Started · ends {fmt_date(a["endDate"])}'})
                if since <= e <= as_of:
                    rows.append({"date": e, "kind": "phase-end", "id": a["id"], "url_key": "timeline", "text": a["name"], "detail": "Ended"})
        for r in risks or []:
            cr, up = parse_dt(r.get("createdAt")), parse_dt(r.get("updatedAt") or r.get("updateTime"))
            if cr and cr >= since:
                rows.append({"date": cr, "kind": "risk-created", "id": r["id"], "url_key": "risk", "text": f'{r.get("number", "")}. {r["name"]}'.lstrip(". "),
                             "detail": f'New risk · Risk Score {(r.get("impact") or 0) * (r.get("likelihood") or 0) or "TBD"}'})
            elif up and up >= since:
                rows.append({"date": up, "kind": "risk-updated", "id": r["id"], "url_key": "risk", "text": f'{r.get("number", "")}. {r["name"]}'.lstrip(". "),
                             "detail": f'Risk updated · {STATUS_LABEL.get(r.get("status"), "")}'})
        return sorted(rows, key=lambda r: -r["date"].timestamp())
    wk = weeks
    rows = build(wk)
    while len(rows) < min_rows and wk < max_weeks:
        wk += 1
        rows = build(wk)
    return rows[:n], wk


def activity_html(rows, urls, as_of=None):
    """Recent Activity body in the timeline's visual language: date · what
    (linked into Join) · muted detail. Milestones blue diamond, events coral,
    item changes yellow (Join's item-upcoming), risks slate."""
    out = ['<div class="timeline activity">']
    for r in rows:
        u = urls.get(r["url_key"])
        href = u(r["id"]) if callable(u) else u
        cls = {"milestone": "milestone", "event": "event", "phase-start": "event", "phase-end": "event"}.get(r["kind"], "risk" if r["kind"].startswith("risk") else "item")
        out.append(f'<div class="tl-row {cls}"><div class="date">{r["date"].strftime("%d %b %Y")}</div>'
                   f'<div class="what">{link(href, r["text"])}<span class="muted"> · {esc(r["detail"])}</span></div></div>')
    out.append("</div>")
    return "".join(out)


def has_future_activities(activities, as_of):
    return any(parse_dt(a["endDate"]) >= as_of for a in activities)


# --------------------------------------------------------------- cost trend

def milestone_trend(milestones, reports_by_milestone, costs_by_milestone=None):
    """Points for the Cost Trendline, oldest first: one per non-draft milestone.
    reports_by_milestone: {milestone_id: detailed report} for milestones that
    have an estimate; milestones without a report (e.g. a future GMP) appear
    with estimate=None so they still show on the x axis, as in the app.
    Estimate/Budget are all-in sums of the report rows; Running Total adds the
    milestone's accepted items."""
    pts = []
    for m in sorted(milestones, key=lambda m: m["date"]):
        if m.get("isDraft"):
            continue
        rep = (reports_by_milestone or {}).get(m["id"])
        if rep:
            est = sum(row_total(r) for r in report_rows(rep, "MILESTONE_ESTIMATE"))
            bud = sum(row_total(r) for r in report_rows(rep, "MILESTONE_BUDGET")) or None
            acc = accepted_changes(item_rows(rep))
            pts.append({"id": m["id"], "name": m["name"], "date": m["date"], "estimate": est, "running": est + acc, "budget": bud})
        else:
            pts.append({"id": m["id"], "name": m["name"], "date": m["date"], "estimate": None, "running": None, "budget": None})
    return pts


def _nice_ticks(lo, hi, n=5):
    import math
    span = (hi - lo) or 1.0
    raw = span / max(n - 1, 1)
    mag = 10 ** math.floor(math.log10(raw))
    step = min((s for s in (1, 2, 2.5, 5, 10) if s * mag >= raw), default=10) * mag
    start = math.floor(lo / step) * step
    ticks = []
    v = start
    while v <= hi + step * 0.5:
        ticks.append(v)
        v += step
    return ticks


def trendline_svg(points, width=470, height=260, legend=True):
    """Inline SVG in the style of the app's Cost Trendline: dotted black
    Estimate, solid black Running Total, blue Budget (legend labels in the
    project's terminology), dots and value labels at each milestone, grey
    mesh lines, rotated milestone names."""
    vals = [v for p in points for v in (p["estimate"], p["running"], p["budget"]) if v is not None]
    if not vals or len(points) < 2:
        return '<p class="empty">Not enough milestones with estimates for a trendline.</p>'
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.25 or hi * 0.05
    ticks = _nice_ticks(lo - pad, hi + pad)
    y0, y1 = ticks[0], ticks[-1]
    ml, mr, mt, mb = 44, 20, 16, 44
    xs = [ml + i * (width - ml - mr) / (len(points) - 1) for i in range(len(points))]
    Y = lambda v: mt + (y1 - v) / (y1 - y0) * (height - mt - mb)
    fmt = lambda v: (f"{v/1e9:.1f}B" if abs(v) >= 1e9 else f"{v/1e6:.1f}M".replace(".0M", "M"))
    out = [f'<svg class="trend" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']
    for tv in ticks:
        out.append(f'<line class="mesh" x1="{ml}" x2="{width-mr}" y1="{Y(tv):.1f}" y2="{Y(tv):.1f}"/>'
                   f'<text class="tick" x="{ml-6}" y="{Y(tv)+4:.1f}" text-anchor="end">{fmt(tv)}</text>')
    out.append(f'<line class="axis" x1="{ml}" x2="{width-mr}" y1="{height-mb:.1f}" y2="{height-mb:.1f}"/>')
    for x, p in zip(xs, points):
        out.append(f'<text class="xlab" transform="translate({x:.1f},{height-mb+14}) rotate(-20)" text-anchor="end">{esc(p["name"])}</text>')
    def path(key, cls):
        pts = [(x, p[key]) for x, p in zip(xs, points) if p[key] is not None]
        if len(pts) >= 2:
            out.append(f'<path class="{cls}" d="M' + " L".join(f"{x:.1f},{Y(v):.1f}" for x, v in pts) + '"/>')
        return pts
    ep = path("estimate", "estimate"); bp = path("budget", "budget"); rp = path("running", "running")
    for x, v in bp:
        out.append(f'<circle class="dot budget" cx="{x:.1f}" cy="{Y(v):.1f}" r="4.5"/><text class="budget" x="{x:.1f}" y="{Y(v)+20:.1f}" text-anchor="middle">{fmt(v)}</text>')
    for (x, v), (_, r) in zip(ep, rp):
        out.append(f'<circle class="dot" cx="{x:.1f}" cy="{Y(v):.1f}" r="4.5"/>')
        if abs(v - r) > (y1 - y0) * 0.02:   # estimate label only when it separates from running total
            out.append(f'<text x="{x:.1f}" y="{Y(v)-9:.1f}" text-anchor="middle">{fmt(v)}</text>')
    for x, v in rp:
        out.append(f'<circle class="dot" cx="{x:.1f}" cy="{Y(v):.1f}" r="4.5"/><text x="{x:.1f}" y="{Y(v)+18:.1f}" text-anchor="middle">{fmt(v)}</text>')
    out.append("</svg>")
    svg = "".join(out)
    if legend:
        svg = (f'<div class="trend-legend"><span><i class="estimate"></i>{esc(T("ESTIMATE"))}</span>'
               f'<span><i></i>{esc(T("RUNNING_TOTAL"))}</span><span><i class="budget"></i>{esc(T("TARGET"))}</span></div>') + svg
    return svg


def trend_table(points):
    """Milestone · Date · Estimate · Running Total · Budget · Gap rows to pair with the chart (labels from T())."""
    rows, classes = [], []
    for p in points:
        if p["estimate"] is None:
            rows.append([esc(p["name"]), fmt_date(p["date"]), "—", "—", "—", "—"]); classes.append("")
            continue
        gap = (p["budget"] - p["running"]) if p["budget"] else None
        rows.append([esc(p["name"]), fmt_date(p["date"]), money(p["estimate"]), money(p["running"]), money(p["budget"]) if p["budget"] else "—",
                     f'<span class="gap">{money(gap, signed=True)}</span>' if gap is not None else "—"]); classes.append("")
    return table(["Milestone", "Date", T("ESTIMATE"), T("RUNNING_TOTAL"), T("TARGET"), T("GAP")], rows, num_cols=(2, 3, 4, 5), row_classes=classes)


# ---------------------------------------------------------------------- risks

def risk_urgency(score):
    if score is None or score <= 0 or score > 25:
        return "Undetermined"
    return "Low" if score <= 5 else ("Medium" if score <= 14 else "High")


def open_risks(risks):
    rs = [dict(r, score=(r.get("impact") or 0) * (r.get("likelihood") or 0)) for r in risks if r["status"] == "OPEN"]
    return sorted(rs, key=lambda r: (-r["score"], -amount(r.get("romCost"))))


def risk_cost_impact_total(risks):
    """Sum of the Cost Impact (romCost, whole units) of the open risks."""
    return sum(amount(r.get("romCost")) for r in risks if r["status"] == "OPEN")


risk_exposure_cents = risk_cost_impact_total   # legacy name


LIKELIHOOD_LABEL = {1: "Rare", 2: "Unlikely", 3: "Possible", 4: "Likely", 5: "Almost Certain"}
IMPACT_LABEL = {1: "Insignificant", 2: "Minor", 3: "Moderate", 4: "Major", 5: "Severe"}


def risk_table(rs, urls, n=8):
    """Risk summary rows. Default columns: Risk · Risk Score · Cost Impact.
    When no listed risk carries a Cost Impact (ROM cost unset on all of
    them) the column is replaced by the two factors that make up the score,
    in Join's words: Likelihood and Impact (label + 1–5). The pruning in
    table() also drops any other all-blank column."""
    rs = rs[:n]
    have_cost = any(r.get("romCost") not in (None, "", "0", 0) for r in rs)
    rows = []
    for r in rs:
        name = link(urls["risk"](r["id"]), f"{r['number']}. {r['name']}")
        if have_cost:
            rows.append([name, urgency_chip(r["score"]), money_str(r["romCost"])])
        else:
            L, I = r.get("likelihood") or 0, r.get("impact") or 0
            rows.append([name, f'{LIKELIHOOD_LABEL.get(L, "—")} <span class="muted">{L or ""}</span>'.strip(),
                         f'{IMPACT_LABEL.get(I, "—")} <span class="muted">{I or ""}</span>'.strip(), urgency_chip(r["score"])])
    if have_cost:
        return table(["Risk", "Risk Score", "Cost Impact"], rows, num_cols=(2,))
    return table(["Risk", "Likelihood", "Impact", "Risk Score"], rows, nowrap_cols=(1, 2, 3))

# ------------------------------------------------------------------- timeline

def classify_activity(a):
    if a.get("milestoneID"):
        return "milestone"
    return "event" if a["startDate"] == a["endDate"] else "phase"


def timeline_window(activities, as_of, past=3, future=7):
    acts = sorted(activities, key=lambda a: a["startDate"])
    done = [a for a in acts if parse_dt(a["endDate"]) < as_of]
    upcoming = [a for a in acts if parse_dt(a["endDate"]) >= as_of]
    return done[-past:], upcoming[:future]


def next_milestone_or_event(activities, as_of):
    """The next milestone if one is scheduled, else the next single-day event."""
    up = [a for a in activities if parse_dt(a["startDate"]) >= as_of]
    up.sort(key=lambda a: a["startDate"])
    for a in up:
        if a.get("milestoneID"):
            return a
    for a in up:
        if classify_activity(a) == "event":
            return a
    return up[0] if up else None

# ----------------------------------------------------------------- HTML blocks

def esc(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def link(url, text):
    return f'<a href="{url}">{esc(text)}</a>' if url else esc(text)


STATUS_LABEL = {"PENDING": "Pending", "ACCEPTED": "Accepted", "INCORPORATED": "Incorporated", "REJECTED": "Rejected",
                "NOTCHOSEN": "Not Chosen", "NOTAPPLICABLE": "Not Applicable", "OPEN": "Open", "CLOSED": "Closed"}


def chip(status):
    s = (status or "").upper()
    return f'<span class="chip {s.lower()}">{STATUS_LABEL.get(s, esc(status))}</span>'


def urgency_chip(score):
    u = risk_urgency(score)
    return f'<span class="chip {u.lower()}">{score if score else "TBD"}</span>'


BLANK_CELLS = {"", "—", "-", "–", "n/a", "na", "none", "null", "not set"}
ALWAYS_KEEP = ("Due Date", "Decide by", "Next Due Date", "Next Due", "Deadline")


def _plain(c):
    return re.sub(r"<[^>]+>", "", str(c or "")).replace("&nbsp;", " ").replace("&amp;", "&").strip()


def _cell_text(c):
    return _plain(c).lower()


def prune_columns(headers, rows, keep_cols=(), num_cols=(), nowrap_cols=()):
    """Drop columns whose every cell is blank / — / N/A. Deadline columns
    (Due Date, Decide by, Next Due Date) are always kept, as is any header in
    keep_cols; a Schedule Impact column stays when any cell reads TBD or a
    number. Returns (headers, rows, num_cols, nowrap_cols) re-indexed."""
    if not rows:
        return headers, rows, num_cols, nowrap_cols
    keep = set(ALWAYS_KEEP) | set(keep_cols)
    keep_idx = []
    for i, h in enumerate(headers):
        htxt = _cell_text(h)
        if any(_cell_text(k) == htxt for k in keep):
            keep_idx.append(i); continue
        cells = [_cell_text(r[i]) if i < len(r) else "" for r in rows]
        if all(c in BLANK_CELLS for c in cells):
            continue
        keep_idx.append(i)
    if len(keep_idx) == len(headers):
        return headers, rows, num_cols, nowrap_cols
    remap = {old: new for new, old in enumerate(keep_idx)}
    return ([headers[i] for i in keep_idx], [[r[i] if i < len(r) else "" for i in keep_idx] for r in rows],
            tuple(remap[i] for i in num_cols if i in remap), tuple(remap[i] for i in nowrap_cols if i in remap))


def table(headers, rows, num_cols=(), row_classes=None, wrap=False, nowrap_cols=(), prune=True, keep_cols=()):
    """Join-style list table. Cells never wrap: the first column truncates
    with an ellipsis (full text in the title tooltip), other columns stay on
    one line — so pick fewer rows over wrapped ones. wrap=True is the
    exception for prose-like tables. Columns that are blank for every row
    are dropped (prune=True) except deadline columns and keep_cols; see
    prune_columns()."""
    if prune:
        headers, rows, num_cols, nowrap_cols = prune_columns(headers, rows, keep_cols, num_cols, nowrap_cols)

    def cls_for(i):
        return "num" if i in num_cols else ("nw" if i in nowrap_cols else "")
    th = "".join(f'<th class="{cls_for(i)}">{h}</th>' for i, h in enumerate(headers))
    body = ""
    for j, r in enumerate(rows):
        cls = f' class="{row_classes[j]}"' if row_classes and row_classes[j] else ""
        tds = ""
        for i, c in enumerate(r):
            title = f' title="{esc(_plain(c))}"' if i == 0 and not wrap and len(_plain(c)) > 40 else ""
            tds += f'<td class="{cls_for(i)}"{title}>{c}</td>'
        body += f"<tr{cls}>{tds}</tr>"
    return f'<table class="list{" wrap" if wrap else ""}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def bars(pairs, budget=None, total=None, fmt=money, legend=True, gap_px=7):
    """Horizontal bars in the order given (alphanumeric from rollup()). Budget
    ticks in blue-500 when a budget map is passed. No folding: if the list
    won't fit, use buildup_html() instead."""
    pairs = [(l, v) for l, v in pairs if abs(v) >= 0.5]
    mx = max([abs(v) for _, v in pairs] + [abs(b) for b in (budget or {}).values()] + [1])
    total = total or sum(v for _, v in pairs)
    out = [f'<div class="bars" style="gap:{gap_px}px">']
    for label, v in pairs:
        tick = ""
        if budget and label in budget and budget[label]:
            tick = f'<div class="fill budget" style="width:{100*abs(budget[label])/mx:.1f}%"></div>'
        out.append(f'<div class="bar-row"><div class="lbl" title="{esc(label)}">{esc(label)}</div>'
                   f'<div class="track"><div class="fill" style="width:{100*abs(v)/mx:.1f}%"></div>{tick}</div>'
                   f'<div class="num">{fmt(v)} <span class="muted">{pct(abs(v), total)}</span></div></div>')
    out.append("</div>")
    if legend:
        out.append(f'<div class="legend"><span><i></i>{esc(T("ESTIMATE"))}</span>' + (f'<span><i class="budget"></i>{esc(T("TARGET"))}</span>' if budget else "") + "</div>")
    return "".join(out)


def buildup_html(rows):
    out = ['<div class="buildup">']
    for label, v, cls in rows:
        out.append(f'<div class="row {cls}"><span>{esc(label)}</span><span class="num">{money(v, signed=(label=="Accepted Changes"))}</span></div>')
    out.append("</div>")
    return "".join(out)


def timeline_html(done, upcoming, as_of=None):
    """Timeline rows. Dates never wrap (the date column sizes to its longest
    value); names truncate with an ellipsis. Phases that started before today
    but are still running show their full span, both years when they differ."""
    out = ['<div class="timeline">']
    for a in done:
        out.append(f'<div class="tl-row past {classify_activity(a)}"><div class="date">{fmt_date(a["startDate"])}</div><div class="what" title="{esc(a["name"])}">{esc(a["name"])}</div></div>')
    if as_of:
        out.append(f'<div class="tl-row today"><div class="date">{as_of.strftime("%d %b %Y")}</div><div class="what">Today</div></div>')
    for a in upcoming:
        span = fmt_span(a["startDate"], a["endDate"])
        cnt = f' <span class="muted">· {a["itemCount"]} items</span>' if a.get("itemCount") else ""
        out.append(f'<div class="tl-row {classify_activity(a)}"><div class="date">{span}</div><div class="what" title="{esc(a["name"])}">{esc(a["name"])}{cnt}</div></div>')
    out.append("</div>")
    return "".join(out)


def risk_matrix(risks):
    """Likelihood (rows, 5 at top) × Impact (cols) grid of open-risk counts,
    shaded by Join's urgency thresholds."""
    grid = defaultdict(int)
    for r in risks:
        grid[(r.get("likelihood") or 0, r.get("impact") or 0)] += 1
    out = ['<div class="matrix">']
    for L in range(5, 0, -1):
        out.append(f'<div class="axis">L{L}</div>')
        for I in range(1, 6):
            n = grid.get((L, I), 0)
            out.append(f'<div class="cell {risk_urgency(L*I).lower()}">{n if n else ""}</div>')
    out.append('<div class="axis"></div>' + "".join(f'<div class="axis">I{i}</div>' for i in range(1, 6)))
    out.append("</div>")
    return "".join(out)

# ----------------------------------------------------------------- Join links

def join_urls(project_id):
    base = f"https://app.join.build/{project_id}"
    return {
        "project": base,
        "items": f"{base}/items",
        "item": lambda item_id: f"{base}/items/{item_id}",
        "risks": f"{base}/risks",
        "risk": lambda risk_id: f"{base}/risks/{risk_id}",
        "milestones": f"{base}/milestones",
        "milestone": lambda ms_id: f"{base}/milestones/{ms_id}",
        "timeline": f"{base}/timeline",
    }
