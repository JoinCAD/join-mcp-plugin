---
name: join-risk-contingency-report
description: Build a Risk & Contingency Analysis for a Join construction project — a Join-styled HTML report (prints to a Letter-landscape PDF) answering "is the contingency we carry enough to cover where this project will land?". Page 1 documents the assumptions (base cost, items and risks carried as decided, assumed probabilities); page 2 is the Cost Risk Calculator waterfall with a walk from Base Cost to Projected and the contingency needed; page 3 is a Monte Carlo range of outcomes with additional contingency needed by confidence level; an appendix lists every open risk. Checks Join for contingency lines and costed risks first. Use it whenever someone asks about contingency adequacy, cost risk, risk exposure, "where will we land", expected value of pending items, a Monte Carlo or probabilistic cost analysis, a risk-adjusted forecast, or the Cost Risk Calculator for a Join project — even if they don't say "report".
---

# Join risk & contingency analysis

The project team is about to decide whether the contingency on the project
is enough. Join knows what has been decided (Estimate, Accepted Changes,
Running Total) and what is still open (pending items, the risk register).
What it does not know is what *will* happen — that is the team's judgment.
This report puts the two together: the facts from Join, the judgment as
explicit, arguable assumptions, and two views of the result — the expected
value (a waterfall like the app's Cost Risk Calculator) and the spread of
outcomes (a Monte Carlo). The room then argues about the assumptions, not the
arithmetic, and can see at a glance how often the contingency held covers the
outcome.

Read `references/model.md` once before the interview so you can explain the
math in your own words. `references/data-gathering.md` is the tool-by-tool
guide; `references/join-design.md` has Join's colors, type and terminology.

## Workflow

1. Identify the project; set up a work directory.
2. Pull the data from Join into files.
3. Check readiness: contingency lines, risks, Cost Impacts. Stop or adapt.
4. Interview: show the top pending items and risks, collect overrides and
   probabilities. Write `assumptions.json`.
5. Build: `risk_model.py` → `build_report.py` → `render_pdf.py`; look at the
   page previews.
6. Deliver the HTML and PDF, then offer the next assumption set and say what
   the project is missing in Join.

## 1. Project and scope

Find the project with `list-my-projects` or `search-projects`; if several
match, confirm before pulling anything. Ask nothing else yet — the useful
questions depend on what the data shows.

## 2. Gather

Follow `references/data-gathering.md` exactly: `project.json`, `costs.json`,
`milestones.json`, `report.json` (the detailed milestone report in
**SEPARATED_MARKUPS** mode — the only mode in which contingency lines are
visible), every page of `items-1.json…` (filtered to PENDING and ACCEPTED —
the only statuses the model uses, which keeps a big project to a page or
two), and both risk registers. Save the raw tool output verbatim, copying
spilled results rather than re-fetching; `risk_model.load_inputs("work")`
reads those files.

Then, in Python:

```python
import sys; sys.path.insert(0, "<skill>/scripts")
from risk_model import *
inputs = load_inputs("work")
cs = cost_summary(inputs)      # Estimate, Accepted Changes, Running Total, Budget, Pending Adds/Deducts, contingency
ready = readiness(inputs)      # the three gates below, with messages you can relay
print(candidates_markdown(inputs))   # top pending adds/deducts and risks by expected cost — for step 4
```

Sanity-check `cs["running_total"]` against the Running Total the user sees
in Join before going further. If it differs, an option or draft is being
counted differently — say so and fix it rather than carry a wrong base.

## 3. Readiness gates

The report is only as honest as the register behind it, so three checks come
before any assumptions:

**Contingency.** `ready["contingency"]["ok"]` is False when the active
milestone estimate has no markup line with display type Contingency. Tell the
user exactly that, link the Success Hub page
(https://success.join.build/en/knowledge/markups-in-milestones — contingencies
are markups added in the milestone estimate's *Milestone Markups,
Contingencies, and Allowances* section with display type **Contingency**),
and offer two ways forward: they enter it in Join and you re-pull, or they
tell you the amount held and you carry it as `contingency_override` — which
page 1 then flags as user-supplied. Never invent a contingency, and don't run
the analysis with zero contingency without saying that is what you are doing.

**Risks.** The analysis uses the project's own register (`riskType:
PROJECT`) by default. If the company register (`risks-company.json`) has open
risks, tell the user how many and ask whether to include them; only set
`include_company_risks: true` when they say yes (unattended: leave them out
and mention it in the delivery). No open project risks → link
https://success.join.build/en/knowledge/risk-register and offer to add risks
right now with `create-risk` (name, description, Impact 1–5, Likelihood 1–5)
from whatever list the user gives you; Cost Impact is entered in the app
afterwards. If they would rather proceed without, the report covers pending
items only and says so on page 1.

**Cost Impacts.** Risks without a Cost Impact in Join get an assumed cost
from their Impact score — by default 0.1 / 0.5 / 1 / 2.5 / 5 % of the
Running Total for Insignificant → Severe. Show the user the dollar this
produces for each such risk (`candidates_markdown` marks them *(assumed)*)
and offer the alternatives: a ROM figure per risk (`{"cost": …}` in
`assumptions.risks`), a fixed dollar ladder (`costless_risk_method: "fixed"`),
or excluding the risk. The assumed figures are printed on page 1 with the
chip *Assumed*, so a rough table is fine as long as nobody mistakes it for
Join data.

## 4. Interview

One or two rounds, no more; the report is meant to be re-run as the
conversation moves. Use `AskUserQuestion` when it is available, otherwise ask
in plain text. If nobody is there to answer (scheduled run, "just build it"),
use the defaults, say so at the top of the delivery, and list on page 1 that
no overrides were applied.

Round one, from `candidates_markdown(inputs)`:

- **Pending items to carry as decided.** Show the largest adds and the
  largest deducts (number, name, Cost Impact — ten of each by default) and
  ask which, if any, should be treated as Accepted or Rejected *for this
  analysis*. Everything else keeps the add/deduct probability. Ask for the
  reason in a few words; it goes into `notes` and prints under Adjustments
  on page 1, because "we assumed #77 is rejected" is only useful with "owner
  confirmed CIP on 25 Sep" next to it. Keep each note to one short line in
  the user's words — a statement of what was assumed and why, never a
  judgement of it. Notes are for item and risk overrides and for anything
  the page cannot show on its own (an unattended run, a user-supplied
  contingency); the probability tables speak for themselves, so no note
  names a scenario or characterises the probabilities as pessimistic or
  optimistic.
- **Risks to carry as certain or excluded.** Same shape: the open risks
  ranked by expected cost with Likelihood, Impact, Cost Impact and the
  probability the scenario gives them. Certain overrides the Likelihood to
  100%, Excluded to 0%; a specific probability is also allowed.
- **Probabilities.** Adds accepted (default 40%), deducts accepted (default
  50%), and the risk scenario — Optimistic, Likely (default) or Pessimistic,
  or a custom Likelihood → probability table. The defaults are the app's, so
  a user who has looked at the Cost Risk Calculator will recognise them.

Round two only if something in round one needs it (a costless risk they want
to price, a range item they want to pin). Then write `work/assumptions.json`
(shape in `references/model.md`).

## 5. Build and verify

```bash
python <skill>/scripts/risk_model.py work/assumptions.json work/model.json
python <skill>/scripts/build_report.py work/model.json work/report.html --created "29 Sep 2026, 14:02 PDT"
python <skill>/scripts/render_pdf.py work/report.html work/report.pdf
```

`render_pdf.py` fails if the PDF's page count differs from what the builder
laid out (three pages, plus the risks appendix — one page per 24 open
risks — and an items appendix when more than six items are carried as
decided) or any page's content is clipped, and writes `report-page1..N.png`.
Look at every preview yourself before delivering: the checker catches
geometry, not a histogram whose reference labels sit on top of each other or
an appendix where every Cost Impact reads *Assumed* because Join has none.
If page 1 overflows (many long notes), shorten the notes — never shrink the
template's type or edit the scripts for one report.

The pages, so you can describe them and spot a broken one:

- **1 · Assumptions.** One line saying the page details the assumptions
  that drive the rest of the report, a link to the project in Join, and
  three columns: *Base cost* (milestone, Running Total, contingency held,
  Base Cost, Budget, open risks, pending adds, pending deducts), *Adjustments*
  (pending items carried as decided, risks carried as decided, the user's
  reasons), *Assumed probabilities* (add / deduct acceptance, the risk
  probability by Likelihood, the Cost Impact ladder for risks without one).
  No contingency line detail, no Monte Carlo settings, no scenario names.
- **2 · Expected outcome.** The Cost Risk Calculator waterfall, a vertical
  walk (Base Cost + Expected Adds − Expected Deducts + Expected Risks =
  Projected, each with its formula), and a Contingency block: current
  remaining contingency, the amount needed to reach Projected, and one of two
  sentences — "Current remaining contingency is sufficient to cover expected
  project outcome." or "$X more contingency needed to bridge to expected
  project cost."
- **3 · Range of outcomes.** A two-sentence explanation of Monte Carlo with a
  link, the histogram, the share of trials within the Running Total, within
  Budget, and that draw on contingency at all, the confidence curve, and
  the confidence table: outcome, additional contingency needed (outcome −
  Running Total) and the total contingency that implies as a % of Base Cost.
- **Appendix · Risks modeled.** Every open risk with Likelihood, Impact,
  Cost Impact, where the cost came from, probability and expected cost.

What the pages must say, and how:

- **Join's words.** Estimate, Accepted Changes, Running Total, Pending Adds /
  Deducts, Budget, Gap, Cost Impact, Likelihood, Impact, Risk Score,
  Contingency. Not "exposure" as a column name, not "swing", not "forecast".
  The two report-specific terms — *Base Cost* (Running Total − contingency)
  and *Projected* — are the Cost Risk Calculator's own.
- **Base Cost backs contingency out.** The contingency lines are inside the
  Estimate, so Base Cost = Running Total − contingency and the Running Total
  line is where contingency runs out. The app's dashboard stacks contingency
  on top of the Running Total instead; page 1's Base cost column shows the
  subtraction so nobody is surprised that the base chip differs from the
  dashboard by the contingency amount.
- **Facts, not verdicts, and no editorializing.** "Projected exceeds the
  Running Total by $2.5M" and "the contingency held covers 18% of trials"
  are facts the page states; the Contingency block's two fixed sentences are
  the only conclusions the report draws. "Contingency is inadequate",
  "increase contingency to $4M", "a particularly pessimistic view" — the
  room's words, not yours; leave them out of the report and the delivery.
  Headroom and Gap are set in muted grey like the app, never red; the sign
  carries the meaning.
- **Every assumption on page 1**, including the defaults that were not
  changed, allowances noted as not modeled, and whether contingency came
  from Join or the user. Not on page 1: contingency line names, trial count
  and seed, the scenario name — a probability table is an assumption, the
  label someone gave it is commentary.

## 6. Deliver, then keep the conversation going

Deliver `report.html` (the Join mark inlined; Red Hat Text loads from Google Fonts)
and `report.pdf`, written where the user keeps their work when a folder is
connected, otherwise into the conversation. Two or three sentences: the
projected figure against the Running Total and Budget, the contingency
sentence from page 2, the share of trials the contingency covers, and which
assumptions drive it most (a single item carried as accepted or a costed
risk often explains most of the walk). Then offer to re-run with a different
assumption set — that is the normal next step in the meeting, and the build
takes seconds.

Close with the data ask when it applies: risks without a Cost Impact, an
empty register, no contingency lines, pending items with no cost. Say which
is missing and that entering it in Join (Risks page: Likelihood, Impact and
a ROM Cost Impact; milestone estimate: contingency markups) replaces the
assumed figures with Join data on the next run. Offer to create the risks
from a list if they give you one.

## Files

- `scripts/risk_model.py` — loaders, cost summary, readiness gates, candidate lists, assumptions, the ported waterfall and the Monte Carlo; CLI `assumptions.json → model.json`.
- `scripts/build_report.py` — `model.json → report.html`: three Letter-landscape pages plus the risks appendix, waterfall / histogram / cumulative SVGs drawn to match the app's Cost Risk Calculator, logo inlined.
- `scripts/render_pdf.py` — HTML → PDF via Playwright's Chromium; fails on overflow or wrong page count; writes page previews.
- `assets/template.html` — the page layout in Join's light theme; `assets/join-logo.svg` the Join mark.
- `references/model.md` — definitions, formulas, defaults, the `assumptions.json` shape.
- `references/data-gathering.md` — tool-by-tool guide, units, where each number comes from, Success Hub links.
- `references/join-design.md` — Join's colors, type scale and terminology.
