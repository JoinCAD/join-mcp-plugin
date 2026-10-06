#!/usr/bin/env python3
"""Risk & contingency model for a Join project.

Ports the logic of the Join web app's Cost Risk Calculator and adds
per-item / per-risk overrides plus a Monte Carlo simulation.

Two ways to use it:

    # 1. as a library while you interview the user
    import sys; sys.path.insert(0, "<skill>/scripts")
    from risk_model import *
    inputs = load_inputs("work")            # saved connector output (see references/data-gathering.md)
    print(readiness(inputs))                # contingency / risks / cost-impact gates
    print(candidates_markdown(inputs))      # top pending adds & deducts, risks by expected cost — paste into your question

    # 2. as a CLI once assumptions.json is written
    python risk_model.py work/assumptions.json work/model.json

Money: every connector tool returns money in WHOLE CURRENCY UNITS — the
list/cost tools and get-contingency-report as decimal strings
("1495000.00", "-90405.87"), the milestone report resource as plain numbers.
Nothing is in cents. `load_inputs` reads the project's `currency` and
`money()` formats in it ($, £, €, …).

Terminology: a project can rename Estimate, Budget, Running Total, Gap and
the other cost concepts, and Join shows the renamed labels throughout that
project. Save `terminology-for-project` as `terms.json`; `load_inputs` picks
it up, the report prints the project's labels, and `T("TARGET")` gives you
the right word when you write to the user.

Contingency: `get-contingency-report` (saved as `contingency.json`) carries
each contingency's starting amount, pending and accepted draws, and the
amount REMAINING. The model backs the remaining amount out of the Running
Total to get Base Cost; the SEPARATED_MARKUPS milestone report's contingency
lines (starting amounts) are the fallback when the contingency report is
not available to the user's role.
"""
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# -------------------------------------------------------------- terminology
# Concept keys and default labels exactly as terminology-for-project returns them.
DEFAULT_TERMS = {
    "ESTIMATE": "Estimate", "TARGET": "Budget", "DELTA": "Delta", "RUNNING_TOTAL": "Running Total", "GAP": "Gap",
    "DIRECT_COST": "Direct Costs", "MARKUP": "Markups", "COST_OF_CONSTRUCTION": "Cost of Construction",
    "PROJECT_TOTAL": "Project Total", "PROJECT_RUNNING_TOTAL": "Project Running Total",
}
TERMS = dict(DEFAULT_TERMS)


def set_terms(terms):
    """Install a project's terminology: the terminology-for-project result
    ({"terms": {...}}), a bare {concept: label} dict, or None for defaults.
    Blank or unknown labels fall back to the default."""
    global TERMS
    t = (terms or {}).get("terms", terms) if isinstance(terms, dict) else {}
    TERMS = {k: (str((t or {}).get(k) or "").strip() or v) for k, v in DEFAULT_TERMS.items()}
    return TERMS


def T(concept):
    """The project's label for a concept: T("TARGET") → 'Budget' or 'Target Value'."""
    return TERMS.get(concept) or DEFAULT_TERMS[concept]


def renamed_terms():
    """{concept: (default, project label)} for every concept the project renamed."""
    return {k: (DEFAULT_TERMS[k], TERMS[k]) for k in DEFAULT_TERMS if TERMS[k] != DEFAULT_TERMS[k]}


def terminology_note():
    """One sentence for the delivery, or '' when the project uses the defaults."""
    r = renamed_terms()
    if not r:
        return ""
    parts = [f'the {d} "{p}"' for d, p in r.values()]
    body = ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1]
    return f"This project calls {body}; the report uses those labels."

# ----------------------------------------------------------------- currency
CURRENCY_SYMBOLS = {"USD": "$", "CAD": "CA$", "AUD": "A$", "NZD": "NZ$", "SGD": "S$", "HKD": "HK$", "MXN": "MX$",
                    "GBP": "£", "EUR": "€", "JPY": "¥", "CNY": "¥", "INR": "₹", "KRW": "₩", "ILS": "₪", "PHP": "₱",
                    "CHF": "CHF ", "SEK": "kr ", "NOK": "kr ", "DKK": "kr ", "ZAR": "R", "BRL": "R$", "AED": "AED ", "SAR": "SAR "}
CURRENCY = {"code": "USD", "symbol": "$"}


def set_currency(code):
    """Format money in the project's currency (project record `currency`).
    Unknown codes print as 'CODE 1.2M'."""
    code = (code or "USD").upper()
    CURRENCY["code"] = code
    CURRENCY["symbol"] = CURRENCY_SYMBOLS.get(code, code + " ")
    return CURRENCY

# ------------------------------------------------------------------ defaults
# Straight from the Join web app's Cost Risk Calculator. Probability, in %,
# that a risk with the given Likelihood (1 Rare … 5 Almost Certain)
# materialises.
RISK_SCENARIOS = {
    "optimistic": {1: 5, 2: 15, 3: 25, 4: 40, 5: 55},
    "likely": {1: 10, 2: 30, 3: 50, 4: 70, 5: 90},
    "pessimistic": {1: 20, 2: 50, 3: 75, 4: 90, 5: 100},
}
SCENARIO_LABELS = {"optimistic": "Optimistic", "likely": "Likely", "pessimistic": "Pessimistic", "custom": "Custom"}
LIKELIHOOD_LABELS = {1: "Rare", 2: "Unlikely", 3: "Possible", 4: "Likely", 5: "Almost Certain"}
IMPACT_LABELS = {1: "Insignificant", 2: "Minor", 3: "Moderate", 4: "Major", 5: "Severe"}

DEFAULT_ASSUMPTIONS = {
    "adds_pct": 40,                 # app default: Probability – Adds
    "deducts_pct": 50,              # app default: Probability – Deducts
    "risk_scenario": "likely",      # optimistic | likely | pessimistic | custom
    "risk_probabilities": None,     # {1..5: pct} — filled from the scenario unless custom
    "items": {},                    # {"<item number or id>": "accepted" | "rejected"}
    "risks": {},                    # {"<risk number or id>": "certain" | "excluded" | {"cost": 250000} | {"probability": 65}}
    "costless_risk_method": "pct_of_running_total",   # or "fixed" or "exclude"
    "impact_pct": {1: 0.1, 2: 0.5, 3: 1.0, 4: 2.5, 5: 5.0},          # % of Running Total by Impact score
    "impact_dollars": {1: 25000, 2: 100000, 3: 250000, 4: 1000000, 5: 2500000},
    "contingency_override": None,   # dollars, only when Join carries no contingency lines
    "include_company_risks": False,  # project register only unless the user asks for company-level risks too
    "trials": 10000,
    "seed": 42,
    "notes": [],
}

# ------------------------------------------------------------------- loading

def load(path):
    """Load a saved tool result; unwraps the ReadMcpResourceTool envelope."""
    d = json.loads(Path(path).read_text())
    if isinstance(d, dict) and "contents" in d:
        d = json.loads(d["contents"][0]["text"])
    return d


def amount(x):
    """Connector money → float in whole units: '1495000.00' → 1495000.0; None/'' → 0.0."""
    return float(x) if x not in (None, "") else 0.0


cents = amount   # legacy name from when the connector returned cents; nothing is divided any more


def money(value, signed=False):
    """$1.2B / $209.8M / $531K / $2,013 — the app's short cost format, in the
    project's currency symbol (set_currency / load_inputs)."""
    if value is None:
        return "—"
    sym = CURRENCY["symbol"]
    neg = value < 0
    a = abs(value)
    if a >= 1e9:
        s = f"{sym}{a/1e9:.2f}B".replace(".00B", "B")
    elif a >= 1e6:
        s = f"{sym}{a/1e6:.2f}M".replace(".00M", "M")
        if s.endswith("0M") and "." in s:
            s = s[:-2] + "M"
    elif a >= 1e3:
        s = f"{sym}{a/1e3:.0f}K"
    else:
        s = f"{sym}{a:,.0f}"
    if neg:
        return "−" + s
    return ("+" + s) if signed and value > 0 else s


def pct(x, digits=0):
    return f"{x:.{digits}f}%"


def _pages(workdir, stem, key):
    out = []
    for p in sorted(Path(workdir).glob(f"{stem}*.json")):
        out.extend(load(p).get(key, []))
    return out


def project_record(d, project_id=None):
    """The one project record from a saved list-my-projects / search-projects
    page (`projects[]`) or an already-bare record."""
    if isinstance(d, dict) and "projects" in d:
        ps = d["projects"]
        return next((p for p in ps if p["id"] == project_id), ps[0] if ps else {})
    return d or {}


def load_inputs(workdir, project_id=None):
    """Read the saved connector files in `workdir` (names from
    references/data-gathering.md). Sets the currency from the project record
    and the terminology from terms.json when present. contingency.json
    (get-contingency-report, active milestone) is optional but preferred —
    see contingency_held()."""
    w = Path(workdir)
    costs = load(w / "costs.json")
    project = project_record(load(w / "project.json"), project_id or costs.get("projectId"))
    report = load(w / "report.json")
    milestones = load(w / "milestones.json").get("milestones", []) if (w / "milestones.json").exists() else []
    terms = load(w / "terms.json") if (w / "terms.json").exists() else None
    cont_report = load(w / "contingency.json") if (w / "contingency.json").exists() else None
    set_currency(project.get("currency") or (cont_report or {}).get("currency"))
    set_terms(terms)
    draws = pending_draws(cont_report, costs.get("milestoneId"))
    items = normalize_items(_pages(w, "items", "items"), draws)
    risks = normalize_risks(_pages(w, "risks", "risks"))
    ms = next((m for m in milestones if m["id"] == costs.get("milestoneId")), None)
    return {
        "project": project, "costs": costs, "report": report, "milestones": milestones,
        "milestone": ms, "items": items, "risks": risks, "terms": dict(TERMS), "currency": CURRENCY["code"],
        "contingency_report": cont_report,
        "contingencies": contingency_lines(report), "allowances": allowance_lines(report),
    }


def normalize_items(rows, draws=None):
    """Item rows only (options are folded into their parent item's cost/status).

    draws: {itemID: pending contingency draw (negative)} from pending_draws().
    An item that draws on a contingency shows its NET Cost Impact in Join —
    often 0.00 — because the draw offsets it. The model works against the
    contingency REMAINING, so such an item is carried at its gross cost
    (cost − draw): accepting it then consumes contingency in the simulation
    exactly as it would in Join. `draw` on the row records the adjustment."""
    out, seen = [], set()
    draws = draws or {}
    for it in rows:
        if it.get("parentID") or it.get("itemType") == "OPTION":
            continue
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        c = it.get("cost") or {}
        if "value" in c and c["value"] is not None:
            lo = hi = amount(c["value"])
        else:
            lo, hi = amount(c.get("min")), amount(c.get("max"))
            if lo > hi:
                lo, hi = hi, lo
        draw = draws.get(it["id"], 0.0) if it.get("status") == "PENDING" else 0.0
        lo, hi = lo - draw, hi - draw
        out.append({
            "id": it["id"], "number": str(it.get("number", "")), "name": it.get("name", ""),
            "status": it.get("status"), "cost_lo": lo, "cost_hi": hi, "cost": (lo + hi) / 2,
            "is_range": abs(hi - lo) > 0.005, "url": it.get("url"), "draw": draw,
            "milestone_id": (it.get("currentMilestone") or it.get("milestone") or {}).get("id"),
            "due_date": it.get("dueDate"), "assignee": (it.get("assignee") or {}).get("name"),
        })
    return out


def normalize_risks(rows):
    out, seen = [], set()
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        out.append({
            "id": r["id"], "number": str(r.get("number", "")), "name": r.get("name", ""),
            "type": r.get("type", "PROJECT"), "status": r.get("status"),
            "impact": r.get("impact"), "likelihood": r.get("likelihood"),
            "rom_cost": amount(r["romCost"]) if r.get("romCost") not in (None, "") else None,
            "url": r.get("url"),
        })
    return out


# --------------------------------------------------- contingency report

def _active_contingency_milestone(cont_report, milestone_id=None):
    if not cont_report:
        return None
    ms = cont_report.get("milestones") or []
    return (next((m for m in ms if m.get("milestoneID") == milestone_id), None)
            or next((m for m in ms if m.get("active")), None) or (ms[0] if ms else None))


def contingency_held(cont_report, milestone_id=None):
    """Contingency and allowance balances from get-contingency-report for the
    active milestone, in whole units. Each line: name, starting, pending,
    accepted (draws so far, negative), remaining (= what the project still
    holds — the figure the model uses), owner cost flag, type. Returns None
    when the report was not saved (role restriction)."""
    m = _active_contingency_milestone(cont_report, milestone_id)
    if m is None:
        return None
    lines = []
    for c in m.get("contingencies") or []:
        lines.append({"name": c.get("name"), "type": c.get("type"), "is_owner_cost": bool(c.get("ownerCost")),
                      "starting": amount(c.get("starting")), "pending": amount(c.get("pending")),
                      "accepted": amount(c.get("accepted")) + amount(c.get("incorporated")),
                      "remaining": amount(c.get("remaining")), "overdrawn": bool(c.get("overdrawn"))})
    return {"milestone_id": m.get("milestoneID"), "lines": lines,
            "contingencies": [l for l in lines if l["type"] == "CONTINGENCY"],
            "allowances": [l for l in lines if l["type"] == "ALLOWANCE"]}


def pending_draws(cont_report, milestone_id=None):
    """{itemID: Σ pending draw amount (negative)} across the CONTINGENCY lines
    of the active milestone. Allowance draws are left out: allowances are not
    part of the contingency the model tests, so an item drawing on one keeps
    the net Cost Impact Join shows."""
    m = _active_contingency_milestone(cont_report, milestone_id)
    out = {}
    for c in (m or {}).get("contingencies") or []:
        if c.get("type") != "CONTINGENCY":
            continue
        for d in c.get("draws") or []:
            if d.get("status") == "PENDING":
                out[d["itemID"]] = out.get(d["itemID"], 0.0) + amount(d.get("amount"))
    return out


def _markup_rows(report, display_type):
    return [r for r in report["rows"]
            if r.get("lineType") == "MARKUP" and r.get("isCountedInTotals", True)
            and (r.get("markupDetails") or {}).get("displayType") == display_type]


def contingency_lines(report):
    """Contingency markup lines of the milestone estimate (SEPARATED_MARKUPS report).
    These are the same lines the app's Contingency report calls `startingCost`."""
    return [{"name": (r.get("markupDetails") or {}).get("name") or r.get("description"),
             "amount": r["costDetail"]["total"] or 0.0,
             "is_owner_cost": r.get("lineType") == "OWNER_COST"}
            for r in _markup_rows(report, "CONTINGENCY")]


def allowance_lines(report):
    return [{"name": (r.get("markupDetails") or {}).get("name") or r.get("description"),
             "amount": r["costDetail"]["total"] or 0.0}
            for r in _markup_rows(report, "ALLOWANCE")]

# ------------------------------------------------------------- cost summary

def cost_summary(inputs):
    """Join's cost summary in whole currency units: Estimate · Accepted
    Changes · Running Total · Pending Adds / Deducts · Budget · Gap, plus the
    contingency held.

    Contingency comes from get-contingency-report when it was saved: the
    REMAINING amount (starting − accepted draws) is what the project still
    holds, and Base Cost = Running Total − remaining. Without it, the
    SEPARATED_MARKUPS report's contingency lines give the starting amount
    (`contingency_source` says which, so page 1 can say so)."""
    costs, project, items = inputs["costs"], inputs["project"], inputs["items"]
    estimate = amount(costs["total"])                                 # Project Total, all-in
    budget_rows = sum((r["costDetail"]["total"] or 0.0) for r in inputs["report"]["rows"]
                      if r.get("source") == "MILESTONE_BUDGET" and r.get("isCountedInTotals", True))
    budget = budget_rows or amount(project.get("budget") or 0)
    ms_id = costs.get("milestoneId")
    # items-for-project's default "active" view already lists exactly the items the
    # active milestone counts (including ones still sitting in an earlier milestone),
    # so do not filter by milestone here — trust the view the app uses.
    accepted = sum(i["cost"] for i in items if i["status"] == "ACCEPTED")
    pending = [i for i in items if i["status"] == "PENDING"]
    adds = [i for i in pending if i["cost_hi"] > 0]
    deducts = [i for i in pending if i["cost_lo"] < 0]
    running = estimate + accepted
    held = contingency_held(inputs.get("contingency_report"), ms_id)
    if held is not None and held["contingencies"]:
        lines = [{"name": l["name"], "amount": l["remaining"], "starting": l["starting"], "accepted": l["accepted"],
                  "pending": l["pending"], "is_owner_cost": l["is_owner_cost"]} for l in held["contingencies"]]
        contingency = sum(l["remaining"] for l in held["contingencies"])
        starting = sum(l["starting"] for l in held["contingencies"])
        drawn = sum(l["accepted"] for l in held["contingencies"])
        source = "remaining"
        allowances = sum(l["remaining"] for l in held["allowances"])
    else:
        lines = inputs["contingencies"]
        contingency = starting = sum(c["amount"] for c in lines)
        drawn = 0.0
        source = "starting" if lines else "none"
        allowances = sum(a["amount"] for a in inputs["allowances"])
    return {
        "estimate": estimate, "accepted_changes": accepted, "running_total": running,
        "budget": budget, "gap": (budget - running) if budget else None,
        "pending_adds": sum(i["cost_hi"] for i in adds), "pending_adds_count": len(adds),
        "pending_deducts": sum(i["cost_lo"] for i in deducts), "pending_deducts_count": len(deducts),
        "pending_count": len(pending),
        "pending_draws": -sum(i.get("draw", 0.0) for i in pending),   # gross-up carried in pending items, positive
        "contingency": contingency, "contingency_lines": lines,
        "contingency_source": source, "contingency_starting": starting, "contingency_drawn": drawn,
        "allowances": allowances,
        "milestone_id": ms_id,
    }


def pending_items(inputs):
    return [i for i in inputs["items"] if i["status"] == "PENDING"]


def open_risks(inputs, include_company=True):
    return [r for r in inputs["risks"] if r["status"] == "OPEN"
            and (include_company or r["type"] == "PROJECT")]

# --------------------------------------------------------------- readiness

SUCCESS_HUB = {
    "contingency": "https://success.join.build/en/knowledge/markups-in-milestones",
    "markups": "https://success.join.build/en/knowledge/markups-overview",
    "risks": "https://success.join.build/en/knowledge/risk-register",
}


def readiness(inputs):
    """The three gates the skill checks before interviewing the user.
    Each entry: ok / message. The skill decides what to do with a failure."""
    cs = cost_summary(inputs)
    risks = open_risks(inputs)
    costless = [r for r in risks if not r["rom_cost"]]
    out = {
        "contingency": {
            "ok": cs["contingency"] > 0,
            "amount": cs["contingency"], "lines": cs["contingency_lines"], "source": cs["contingency_source"],
            "message": ((f"Contingency remaining {money(cs['contingency'])} of {money(cs['contingency_starting'])} starting "
                         f"({money(cs['contingency_drawn'], True)} accepted draws): "
                         + ", ".join(f"{c['name']} {money(c['amount'])}" for c in cs["contingency_lines"])
                         + (f". Pending items draw {money(cs['pending_draws'])} more; they are carried at gross cost." if cs["pending_draws"] else ""))
                        if cs["contingency"] > 0 and cs["contingency_source"] == "remaining" else
                        ("Contingency held (starting amounts from the milestone estimate; get-contingency-report was not saved, "
                         "so accepted draws are not netted off): " + ", ".join(f"{c['name']} {money(c['amount'])}" for c in cs["contingency_lines"]))
                        if cs["contingency"] > 0 else
                        "No contingency in the active milestone estimate. Contingencies are milestone markups with "
                        f"display type Contingency — see {SUCCESS_HUB['contingency']}. Ask for the amount held and record it "
                        "as an assumption (assumptions.contingency_override), or stop until it is entered in Join."),
        },
        "risks": {
            "ok": len(risks) > 0, "count": len(risks),
            "message": (f"{len(risks)} open risk(s) on the register."
                        if risks else
                        f"No open risks on the register — see {SUCCESS_HUB['risks']}. Offer to add risks with "
                        "`create-risk` (name, description, Impact 1–5, Likelihood 1–5) from a list the user gives you; "
                        "Cost Impact is then added in the app. Without risks the analysis covers pending items only."),
        },
        "cost_impacts": {
            "ok": len(costless) == 0, "costless": costless,
            "message": (("All open risks carry a Cost Impact." if risks else "No risks to check.")
                        if not costless else
                        f"{len(costless)} of {len(risks)} open risks have no Cost Impact in Join. The default assumes a "
                        f"cost from the Impact score as a % of {T('RUNNING_TOTAL')} (0.1 / 0.5 / 1 / 2.5 / 5 %); show the user the "
                        "resulting figures and let them set a ROM per risk or exclude it."),
        },
        "pending_items": {
            "ok": cs["pending_count"] > 0, "count": cs["pending_count"],
            "message": f"{cs['pending_count']} pending items ({money(cs['pending_adds'], True)} adds, {money(cs['pending_deducts'], True)} deducts).",
        },
    }
    return out


def candidates(inputs, n=10, assumptions=None):
    """Top-n pending adds and deducts by size, and open risks by expected cost,
    for the override questions."""
    a = merged_assumptions(assumptions or {})
    pend = pending_items(inputs)
    adds = sorted([i for i in pend if i["cost_hi"] > 0], key=lambda i: -i["cost_hi"])[:n]
    deducts = sorted([i for i in pend if i["cost_lo"] < 0], key=lambda i: i["cost_lo"])[:n]
    cs = cost_summary(inputs)
    rs = []
    for r in open_risks(inputs, a["include_company_risks"]):
        cost, src = assumed_risk_cost(r, cs["running_total"], a)
        p = risk_probability(r, a)
        rs.append({**r, "assumed_cost": cost, "cost_source": src, "probability": p,
                   "expected": (cost or 0) * p / 100})
    rs.sort(key=lambda r: -(r["expected"] or 0))
    return {"adds": adds, "deducts": deducts, "risks": rs}


def candidates_markdown(inputs, n=10, assumptions=None):
    c = candidates(inputs, n, assumptions)
    L = ["**Largest pending adds** (number · name · Cost Impact)", ""]
    def _tag(i):
        return (" (range)" if i["is_range"] else "") + (f" (gross; draws {money(-i['draw'])} from contingency)" if i.get("draw") else "")
    L += [f"- #{i['number']} {i['name']} — {money(i['cost_hi'], True)}{_tag(i)}" for i in c["adds"]] or ["- none"]
    L += ["", "**Largest pending deducts**", ""]
    L += [f"- #{i['number']} {i['name']} — {money(i['cost_lo'], True)}{_tag(i)}" for i in c["deducts"]] or ["- none"]
    L += ["", "**Open risks** (number · name · Likelihood · Impact · Cost Impact → probability · expected)", ""]
    for r in c["risks"]:
        cost = money(r["assumed_cost"]) if r["assumed_cost"] else "—"
        tag = "" if r["cost_source"] == "join" else f" ({r['cost_source']})"
        L.append(f"- #{r['number']} {r['name']} — L{r['likelihood']} {LIKELIHOOD_LABELS.get(r['likelihood'], '?')} · "
                 f"I{r['impact']} {IMPACT_LABELS.get(r['impact'], '?')} · {cost}{tag} → {r['probability']:.0f}% · {money(r['expected'])}")
    if not c["risks"]:
        L.append("- none")
    return "\n".join(L)

# ------------------------------------------------------------- assumptions

def merged_assumptions(a):
    m = json.loads(json.dumps(DEFAULT_ASSUMPTIONS))
    m.update({k: v for k, v in (a or {}).items() if v is not None or k in ("contingency_override", "risk_probabilities")})
    for k in ("impact_pct", "impact_dollars"):
        m[k] = {int(kk): float(vv) for kk, vv in m[k].items()}
    if m["risk_scenario"] != "custom" or not m.get("risk_probabilities"):
        m["risk_probabilities"] = dict(RISK_SCENARIOS.get(m["risk_scenario"], RISK_SCENARIOS["likely"]))
    else:
        m["risk_probabilities"] = {int(k): float(v) for k, v in m["risk_probabilities"].items()}
    return m


def _override_for(entity, table):
    for key in (entity["id"], entity["number"], f"#{entity['number']}"):
        if key in table:
            return table[key]
    return None


def assumed_risk_cost(risk, running_total, a):
    """(cost, source) — source is 'join', 'override', 'assumed' or 'excluded'."""
    ov = _override_for(risk, a["risks"])
    if isinstance(ov, dict) and ov.get("cost") is not None:
        return float(ov["cost"]), "override"
    if ov == "excluded":
        return 0.0, "excluded"
    if risk["rom_cost"]:
        return risk["rom_cost"], "join"
    if not risk.get("impact"):
        return 0.0, "excluded"
    if a["costless_risk_method"] == "fixed":
        return a["impact_dollars"].get(int(risk["impact"]), 0.0), "assumed"
    if a["costless_risk_method"] == "pct_of_running_total":
        return running_total * a["impact_pct"].get(int(risk["impact"]), 0.0) / 100.0, "assumed"
    return 0.0, "excluded"


def risk_probability(risk, a):
    ov = _override_for(risk, a["risks"])
    if ov == "certain":
        return 100.0
    if ov == "excluded":
        return 0.0
    if isinstance(ov, dict) and ov.get("probability") is not None:
        return float(ov["probability"])
    if not risk.get("likelihood"):
        return 0.0
    return float(a["risk_probabilities"].get(int(risk["likelihood"]), 0.0))


def item_probability(item, a):
    ov = _override_for(item, a["items"])
    if ov == "accepted":
        return 100.0
    if ov == "rejected":
        return 0.0
    return float(a["adds_pct"] if item["cost"] >= 0 else a["deducts_pct"])

# ------------------------------------------------------------------ model

def build_model(inputs, assumptions):
    a = merged_assumptions(assumptions)
    cs = cost_summary(inputs)
    if cs["contingency"] <= 0 and a.get("contingency_override"):
        cs["contingency"] = float(a["contingency_override"])
        cs["contingency_lines"] = [{"name": "Contingency (user-supplied)", "amount": cs["contingency"], "is_owner_cost": False}]
        cs["contingency_is_override"] = True
    rt = cs["running_total"]

    items = []
    for i in pending_items(inputs):
        p = item_probability(i, a)
        ov = _override_for(i, a["items"])
        # kind = which bar carries the item's expected value (by midpoint sign);
        # a range that spans zero still contributes its max to the adds extent
        # and its min to the deducts extent, as Join's Pending Adds / Deducts do.
        items.append({**i, "probability": p, "override": ov, "kind": "add" if i["cost"] >= 0 else "deduct",
                      "expected": p / 100 * i["cost"]})
    risks = []
    for r in open_risks(inputs, a["include_company_risks"]):
        cost, src = assumed_risk_cost(r, rt, a)
        p = risk_probability(r, a)
        risks.append({**r, "assumed_cost": cost, "cost_source": src, "probability": p,
                      "override": _override_for(r, a["risks"]), "expected": cost * p / 100})

    wf = waterfall(cs, items, risks)
    scen = {}
    for s in ("optimistic", "likely", "pessimistic"):
        a_s = dict(a, risk_scenario=s, risk_probabilities=None)
        a_s = merged_assumptions(a_s)
        rs = [{**r, "probability": risk_probability(r, a_s)} for r in risks]
        for r in rs:
            r["expected"] = r["assumed_cost"] * r["probability"] / 100
        w = waterfall(cs, items, rs)
        scen[s] = {"expected_risks": w["risks"]["expected"] - w["risks"]["baseline"],
                   "projected": w["projected"], "headroom": w["headroom"], "budget_gap": w["budget_gap"]}

    mc = monte_carlo(cs, items, risks, trials=int(a["trials"]), seed=int(a["seed"]))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project": {k: inputs["project"].get(k) for k in ("id", "name", "type", "url", "projectLeadName", "currency")},
        "currency": CURRENCY["code"], "terms": dict(TERMS),
        "milestone": inputs.get("milestone"),
        "assumptions": a,
        "cost_summary": cs,
        "items": items, "risks": risks,
        "waterfall": wf, "scenarios": scen, "monte_carlo": mc,
    }


def _bar(kind, baseline, expected_delta, extent_delta):
    return {"type": kind, "baseline": baseline, "expected": baseline + expected_delta, "extent": baseline + extent_delta}


def waterfall(cs, items, risks):
    """The app's buildWaterfall(), with base = Running Total − contingency so
    the Running Total line is where contingency runs out."""
    rt, cont = cs["running_total"], cs["contingency"]
    base_exp = rt - cont
    live_items = [i for i in items if i["override"] != "rejected"]
    adds = [i for i in live_items if i["kind"] == "add"]
    deds = [i for i in live_items if i["kind"] == "deduct"]
    live = [r for r in risks if r["probability"] > 0 and r["assumed_cost"] > 0]
    base = _bar("base", 0, base_exp, rt)
    b_adds = _bar("adds", base["expected"], sum(i["expected"] for i in adds),
                  sum(i["cost_hi"] for i in live_items if i["cost_hi"] > 0))          # Pending Adds
    b_deds = _bar("deducts", b_adds["expected"], sum(i["expected"] for i in deds),
                  sum(i["cost_lo"] for i in live_items if i["cost_lo"] < 0))          # Pending Deducts
    b_risk = _bar("risks", b_deds["expected"], sum(r["expected"] for r in live), sum(r["assumed_cost"] for r in live))
    projected = b_risk["expected"]
    return {
        "base": base, "adds": b_adds, "deducts": b_deds, "risks": b_risk,
        "projected": projected, "delta": projected - base_exp,
        "running_total": rt, "budget": cs["budget"] or None, "contingency": cont,
        "headroom": rt - projected,                        # contingency left if expectations hold (negative = short)
        "budget_gap": (cs["budget"] - projected) if cs["budget"] else None,
        "max_exposure": base_exp + sum(i["cost_hi"] for i in live_items if i["cost_hi"] > 0) + sum(r["assumed_cost"] for r in live),
        "min_exposure": base_exp + sum(i["cost_lo"] for i in live_items if i["cost_lo"] < 0),
    }


def monte_carlo(cs, items, risks, trials=10000, seed=42):
    """Occurrence-only simulation: each pending item is accepted with its
    probability (range items draw uniformly between min and max when they
    hit); each risk occurs with its probability at its assumed cost.
    Outcome = base (Running Total − contingency) + accepted draws + risk draws."""
    rng = random.Random(seed)
    base = cs["running_total"] - cs["contingency"]
    it = [(i["probability"] / 100, i["cost_lo"], i["cost_hi"], i["is_range"]) for i in items if i["override"] != "rejected"]
    rk = [(r["probability"] / 100, r["assumed_cost"]) for r in risks if r["probability"] > 0 and r["assumed_cost"] > 0]
    outs = []
    for _ in range(trials):
        x = base
        for p, lo, hi, rng_item in it:
            if p >= 1 or rng.random() < p:
                x += rng.uniform(lo, hi) if rng_item else hi
        for p, c in rk:
            if p >= 1 or rng.random() < p:
                x += c
        outs.append(x)
    outs.sort()
    n = len(outs)

    def q(pp):
        k = (n - 1) * pp / 100
        f, c = math.floor(k), math.ceil(k)
        return outs[f] if f == c else outs[f] + (outs[c] - outs[f]) * (k - f)

    def prob_le(v):
        if v is None:
            return None
        import bisect
        return 100.0 * bisect.bisect_right(outs, v) / n

    mean = sum(outs) / n
    std = math.sqrt(sum((o - mean) ** 2 for o in outs) / n)
    rt, budget = cs["running_total"], cs["budget"] or None
    percentiles = {p: q(p) for p in (5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95)}
    # histogram: ~40 bins across the outcomes
    lo, hi = outs[0], outs[-1]
    bins = 40 if hi > lo else 1
    width = (hi - lo) / bins if bins > 1 else 1
    counts = [0] * bins
    for o in outs:
        k = min(bins - 1, int((o - lo) / width)) if bins > 1 else 0
        counts[k] += 1
    hist = [{"lo": lo + k * width, "hi": lo + (k + 1) * width, "count": c, "share": c / n} for k, c in enumerate(counts)]
    cdf = [{"x": q(pp), "p": pp} for pp in range(0, 101, 2)]
    return {
        "trials": trials, "seed": seed, "base": base,
        "mean": mean, "std": std, "min": lo, "max": hi,
        "percentiles": percentiles,
        "p_within_contingency": prob_le(rt),          # P(outcome ≤ Running Total)
        "p_within_budget": prob_le(budget),
        "p_within_base": prob_le(base),               # P(no draw on contingency at all)
        "contingency_needed": {p: percentiles[p] - base for p in (50, 80, 90, 95)},   # to be covered at that confidence
        "shortfall": {p: percentiles[p] - rt for p in (50, 80, 90, 95)},              # over the contingency held (negative = spare)
        "histogram": hist, "cdf": cdf,
    }

# --------------------------------------------------------------------- CLI

def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    a = json.loads(Path(sys.argv[1]).read_text())
    workdir = a.get("workdir") or Path(sys.argv[1]).parent
    inputs = load_inputs(workdir, a.get("project_id"))
    model = build_model(inputs, a)
    Path(sys.argv[2]).write_text(json.dumps(model, indent=1, default=str))
    wf, mc, cs = model["waterfall"], model["monte_carlo"], model["cost_summary"]
    print(f"{T('RUNNING_TOTAL')} {money(cs['running_total'])} · contingency {money(cs['contingency'])} ({cs['contingency_source']}) · {T('TARGET')} {money(cs['budget']) if cs['budget'] else '—'}")
    print(f"Projected {money(wf['projected'])} (Δ {money(wf['delta'], True)}) · headroom {money(wf['headroom'], True)}")
    print(f"MC: P50 {money(mc['percentiles'][50])} · P80 {money(mc['percentiles'][80])} · P(≤ {T('RUNNING_TOTAL')}) {mc['p_within_contingency']:.0f}%")
    print(f"wrote {sys.argv[2]}")


if __name__ == "__main__":
    main()
