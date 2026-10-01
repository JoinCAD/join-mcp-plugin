#!/usr/bin/env python3
"""Risk & contingency model for a Join project.

Ports the logic of the app's Cost Risk Calculator (komodo-ui
`DashboardCharts/CostRiskCalculator`: waterfallModel.ts, useChartData.ts)
and adds per-item / per-risk overrides plus a Monte Carlo simulation.

Two ways to use it:

    # 1. as a library while you interview the user
    import sys; sys.path.insert(0, "<skill>/scripts")
    from risk_model import *
    inputs = load_inputs("work")            # saved connector output (see references/data-gathering.md)
    print(readiness(inputs))                # contingency / risks / cost-impact gates
    print(candidates_markdown(inputs))      # top pending adds & deducts, risks by expected cost — paste into your question

    # 2. as a CLI once assumptions.json is written
    python risk_model.py work/assumptions.json work/model.json

Money: connector list/cost tools return STRINGS OF US CENTS; the detailed
milestone report resource returns FLOAT DOLLARS. Everything here is dollars
once loaded.
"""
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# ------------------------------------------------------------------ defaults
# Straight from the app (useChartData.ts / types.ts). Probability, in %, that a
# risk with the given Likelihood (1 Rare … 5 Almost Certain) materialises.
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


def cents(x):
    return (float(x) if x not in (None, "") else 0.0) / 100.0


def money(dollars, signed=False):
    """$1.2B / $209.8M / $531K / $2,013 — the app's short cost format."""
    if dollars is None:
        return "—"
    neg = dollars < 0
    a = abs(dollars)
    if a >= 1e9:
        s = f"${a/1e9:.2f}B".replace(".00B", "B")
    elif a >= 1e6:
        s = f"${a/1e6:.2f}M".replace(".00M", "M")
        if s.endswith("0M") and "." in s:
            s = s[:-2] + "M"
    elif a >= 1e3:
        s = f"${a/1e3:.0f}K"
    else:
        s = f"${a:,.0f}"
    if neg:
        return "−" + s
    return ("+" + s) if signed and dollars > 0 else s


def pct(x, digits=0):
    return f"{x:.{digits}f}%"


def _pages(workdir, stem, key):
    out = []
    for p in sorted(Path(workdir).glob(f"{stem}*.json")):
        out.extend(load(p).get(key, []))
    return out


def load_inputs(workdir):
    """Read the saved connector files in `workdir` (names from references/data-gathering.md)."""
    w = Path(workdir)
    project = load(w / "project.json")
    costs = load(w / "costs.json")
    report = load(w / "report.json")
    milestones = load(w / "milestones.json").get("milestones", []) if (w / "milestones.json").exists() else []
    items = normalize_items(_pages(w, "items", "items"))
    risks = normalize_risks(_pages(w, "risks", "risks"))
    ms = next((m for m in milestones if m["id"] == costs.get("milestoneId")), None)
    return {
        "project": project, "costs": costs, "report": report, "milestones": milestones,
        "milestone": ms, "items": items, "risks": risks,
        "contingencies": contingency_lines(report), "allowances": allowance_lines(report),
    }


def normalize_items(rows):
    """Item rows only (options are folded into their parent item's cost/status)."""
    out, seen = [], set()
    for it in rows:
        if it.get("parentID") or it.get("itemType") == "OPTION":
            continue
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        c = it.get("cost") or {}
        if "value" in c and c["value"] is not None:
            lo = hi = cents(c["value"])
        else:
            lo, hi = cents(c.get("min")), cents(c.get("max"))
            if lo > hi:
                lo, hi = hi, lo
        out.append({
            "id": it["id"], "number": str(it.get("number", "")), "name": it.get("name", ""),
            "status": it.get("status"), "cost_lo": lo, "cost_hi": hi, "cost": (lo + hi) / 2,
            "is_range": abs(hi - lo) > 0.005, "url": it.get("url"),
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
            "rom_cost": cents(r["romCost"]) if r.get("romCost") not in (None, "") else None,
            "url": r.get("url"),
        })
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
    """Join's cost summary in dollars: Estimate · Accepted Changes · Running
    Total · Pending Adds / Deducts · Budget · Gap, plus contingency held."""
    costs, project, items = inputs["costs"], inputs["project"], inputs["items"]
    estimate = cents(costs["total"])                                  # Project Total, all-in
    budget_rows = sum((r["costDetail"]["total"] or 0.0) for r in inputs["report"]["rows"]
                      if r.get("source") == "MILESTONE_BUDGET" and r.get("isCountedInTotals", True))
    budget = budget_rows or cents(project.get("budget") or 0)
    ms_id = costs.get("milestoneId")
    # items-for-project's default "active" view already lists exactly the items the
    # active milestone counts (including ones still sitting in an earlier milestone),
    # so do not filter by milestone here — trust the view the app uses.
    accepted = sum(i["cost"] for i in items if i["status"] == "ACCEPTED")
    pending = [i for i in items if i["status"] == "PENDING"]
    adds = [i for i in pending if i["cost_hi"] > 0]
    deducts = [i for i in pending if i["cost_lo"] < 0]
    running = estimate + accepted
    contingency = sum(c["amount"] for c in inputs["contingencies"])
    return {
        "estimate": estimate, "accepted_changes": accepted, "running_total": running,
        "budget": budget, "gap": (budget - running) if budget else None,
        "pending_adds": sum(i["cost_hi"] for i in adds), "pending_adds_count": len(adds),
        "pending_deducts": sum(i["cost_lo"] for i in deducts), "pending_deducts_count": len(deducts),
        "pending_count": len(pending),
        "contingency": contingency, "contingency_lines": inputs["contingencies"],
        "allowances": sum(a["amount"] for a in inputs["allowances"]),
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
            "amount": cs["contingency"], "lines": cs["contingency_lines"],
            "message": ("Contingency held: " + ", ".join(f"{c['name']} {money(c['amount'])}" for c in cs["contingency_lines"])
                        if cs["contingency"] > 0 else
                        "No contingency lines in the active milestone estimate. Contingencies are milestone markups with "
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
                        "cost from the Impact score as a % of Running Total (0.1 / 0.5 / 1 / 2.5 / 5 %); show the user the "
                        "resulting dollars and let them set a ROM per risk or exclude it."),
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
    L += [f"- #{i['number']} {i['name']} — {money(i['cost_hi'], True)}" + (" (range)" if i["is_range"] else "") for i in c["adds"]] or ["- none"]
    L += ["", "**Largest pending deducts**", ""]
    L += [f"- #{i['number']} {i['name']} — {money(i['cost_lo'], True)}" + (" (range)" if i["is_range"] else "") for i in c["deducts"]] or ["- none"]
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
        "project": {k: inputs["project"].get(k) for k in ("id", "name", "type", "url", "projectLeadName")},
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
    inputs = load_inputs(workdir)
    model = build_model(inputs, a)
    Path(sys.argv[2]).write_text(json.dumps(model, indent=1, default=str))
    wf, mc, cs = model["waterfall"], model["monte_carlo"], model["cost_summary"]
    print(f"Running Total {money(cs['running_total'])} · contingency {money(cs['contingency'])} · budget {money(cs['budget']) if cs['budget'] else '—'}")
    print(f"Projected {money(wf['projected'])} (Δ {money(wf['delta'], True)}) · headroom {money(wf['headroom'], True)}")
    print(f"MC: P50 {money(mc['percentiles'][50])} · P80 {money(mc['percentiles'][80])} · P(≤ Running Total) {mc['p_within_contingency']:.0f}%")
    print(f"wrote {sys.argv[2]}")


if __name__ == "__main__":
    main()
