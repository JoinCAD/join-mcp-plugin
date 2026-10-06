---
name: "join-a3-report"
description: Build a one-page A3 executive snapshot of a Join construction project — an HTML report styled like the Join app that prints to a single A3 PDF, with a branded header (project, Running Total, Budget, Gap, Pending Adds/Deducts, risks, next milestone), six sections in three columns (cost breakdown, gap analysis, risks, timeline or recent activity, top decisions, decisions by area, work in flight, cost trend by milestone, image), and links back into Join. Use this whenever a user asks for a custom report, A3, one-pager, snapshot, status report, executive summary, steering-committee or sponsor update, board pack page, or "where are we" overview for a project in Join — even if they don't say "A3" or "report". Also use it when they ask to "put together something for the owner / exec sponsor" about a Join project.
---

# Join A3 project snapshot

An A3 is a single sheet that lets someone who is *not* in the project every
day — usually an executive sponsor inside the owner organization — see in two
minutes where the project stands and where decisions can move the number.
The sheet is what they get; they will not open Join to check. So: correct
numbers on an all-in basis, Join's own words, no commentary, and a link for
every claim.

The sheet **describes**; it does not recommend. There is no next-steps,
story or scenario section — Join's numbers, Join's words, and links.

## Workflow

1. Identify the project and the reader.
2. Pull the data from Join into files (`references/data-gathering.md`).
3. Recommend six sections; ask the user once for overrides, logos, company names.
4. Compute with `scripts/join_data.py`; author `spec.json`.
5. `build_report.py` → `check_fit.py` → screenshot → iterate.
6. Deliver the HTML and PDF; close by asking for the data the project lacks.

Read `references/sections.md` at step 3 (the catalog and recommendation
table) and `references/join-design.md` before authoring anything the helpers
don't already produce (it holds Join's colors, type scale and terminology).
Fetch the project's terminology (step 2) before you first describe its
numbers to the user, so you use its words from the start.

## 1. Project and reader

Find the project with `list-my-projects` or `search-projects`; if several
match, confirm rather than guess. The default reader is an owner-side
executive sponsor. That sets the tone (plain language) and the section
choice (decisions and gaps over estimate detail).

## 2. Gather

Follow `references/data-gathering.md`. Save every tool result to a file in
a work directory; you will rebuild several times while fitting the page.
Always fetch the timeline, both risk registers and the project-wide
`get-item-history` for the last four weeks — they decide which sections the
sheet gets, and what you ask for at the end.

Four facts about the data that produce wrong sheets when missed:

- **Units and currency.** Every tool returns money in whole currency units
  — decimal strings like `"33554413.16"` from the list and cost tools,
  plain numbers from the milestone report resource. Nothing is in cents, so
  nothing gets divided by 100. The project record's `currency` (USD, GBP,
  EUR, …) decides the symbol; `configure(project, terms)` sets it and
  `money()` prints £ or € where the project does.
- **Terminology.** A project can rename its cost concepts, and Join then
  shows the renamed labels everywhere in that project. Fetch
  `terminology-for-project` with the project record and pass it to
  `configure()`; every label the helpers render then uses the project's
  words, and `T("TARGET")`, `T("ESTIMATE")`, … give you the word for any
  text you write yourself. Use the same words when you talk to the user
  about the project — a sponsor whose Join says "Target Value" should not
  read "Budget" on the sheet or hear it from you. `terminology_note()`
  gives a one-liner for the delivery when a project has renamed something.
- **Basis.** Use **all-in costs** (Project Total / Project Running Total,
  including Owner Costs) wherever the project carries owner costs. Fetch the
  milestone report in its default cost mode (allocated markups, owner costs
  included) so items and estimate lines are on the same basis;
  `cost_summary()` reconciles them and tells you whether the Budget in Join
  includes owner costs.
- **Join's words, nothing else.** Estimate, Budget, Accepted Changes,
  Running Total, Pending Adds / Deducts, Potential Range, Gap (Budget −
  Running Total; negative when over budget), Cost Impact, Schedule Impact,
  Due Date, Past Due, Likelihood, Impact, Risk Score — with the project's
  renames applied to the first group as above. Definitions are in
  `join-design.md`. Don't invent synonyms — "swing", "exposure", "variance",
  "projected" are not Join words.

## 3. Recommend, then ask once

Header is fixed: **Project Running Total · Budget · Gap · Pending Deducts ·
Pending Adds** (labelled as the project names them), plus **Open Risks / Cost Impact** when the register has
entries and **Next Milestone / Event** when the timeline has one. Six panels
below. Default six: **Cost breakdown · Gap Analysis · Risk summary · Timeline
· Top decisions · Work in flight**; adjust from the data using the table at
the end of `sections.md`. Three of those adjustments are not optional:

- **Timeline → Recent Activity** when the timeline is empty or has nothing
  after today (`has_future_activities()`). Recent Activity lists what moved
  in the last 1–4 weeks — item status, cost, due-date and milestone changes
  from the edit log, timeline events that passed, risks added — each with the
  item's current Cost Impact. It is also the alternate for Work in flight.
- **Gap Analysis only when `gap_axis_check()` passes** — the estimate and the
  budget must share a meaningful categorization. No budget lines, most of
  the estimate or of the pending items in Unassigned, or zero budgets on most
  categories → not a gap analysis, however tidy the table looks. Try the
  other axes; otherwise Cost trend by milestone or Decisions by area.
- **Risk summary stays even when no risk has a Cost Impact**: `risk_table()`
  then shows Likelihood · Impact · Risk Score instead of a column of dashes.

One question round covering: the six sections (with a one-line rationale
each and the alternates), owner and preparer logo files, a custom image if
they want one, and the assignee email domains → company names for Work in
flight (skipped when the project has a Responsible Party categorization). If the user
isn't there (scheduled run, "just send it"), proceed with the recommendation
and say so in delivery.

## 4. Compute and author

Write a short script that imports `scripts/join_data.py`, calls
`configure(project, terms)` first (currency and terminology — every label
and figure after that depends on it), loads the saved files, computes each
section, and writes `spec.json` (shape documented at the top of
`build_report.py`). The helpers cover the repetitive parts: `configure`,
`project_record`, `T`, `terminology_note`, `cost_summary`, `header_metrics`, `pick_breakdown_axis`, `rollup`, `buildup`,
`items_catalog`, `top_decisions`, `work_in_flight`, `gap_axis_check`,
`gap_analysis`, `pick_area_axis`, `decisions_by_area`, `recent_activity`,
`milestone_trend`, `open_risks`, `timeline_window`, `has_future_activities`,
`next_milestone_or_event`, and the HTML blocks (`table`, `breakdown_table`,
`bars`, `buildup_html`, `gap_table`, `decisions_by_area_table`, `risk_table`,
`timeline_html`, `activity_html`, `trendline_svg`, `trend_table`,
`risk_matrix`, `chip`, `urgency_chip`).

Rules that keep the sheet trustworthy:

- **Describe, don't editorialize.** "Gap −$31.3M" is a fact. "Cost control
  has slipped" is not yours to say. No recommendations anywhere. Gap and
  Delta are muted grey like the app, never red — the sign says it.
- **Check status before you characterize.** INCORPORATED is not pending;
  CLOSED is not exposure. `get-item` every item you feature.
- **Categories in alphanumeric order**, never by size, never "All other".
  If a breakdown won't fit, show the buildup instead.
- **Group by how the project organizes itself.** Decisions by area and the
  breakdown use the project's own categorization — PIT, TVD Cluster,
  Location, Building, Increment — before UniFormat, Bid Package or
  MasterFormat (`pick_area_axis`, `pick_breakdown_axis`).
- **No empty columns.** `table()` drops a column that is blank, "—" or N/A in
  every row; choose a fallback that carries information (Likelihood · Impact
  for risks without Cost Impact). The exceptions that always render, blank or
  not, are deadline columns (Due Date, Decide by, Next Due) and a Schedule
  Impact column that reads TBD — there the blank is the fact.
- **No wrapped data rows.** Cells stay on one line; names truncate with an
  ellipsis, dates and numbers never break. Fit by dropping rows or a column,
  not by wrapping. `wrap=True` on Top Decisions (two-line item names) is the
  only exception, and `check_fit.py` reports any cell that wrapped.
- **Link everything**: section headers to the matching Join page (`join_urls()`
  or a saved report's `url`), every item and risk row to its own page, the
  header to the project.
- **Fill the panel, don't pad it.** ~8 rows per table panel. `check_fit.py`
  flags both clipped and sparse panels.
- **Footer** carries only the creation timestamp (`now_stamp()`) and the Join
  logo. No "from Join data", no "prepared by", no source notes, no
  disclaimers — `build_report.py` strips anything after the timestamp.

## 5. Build and verify

```bash
python <skill>/scripts/build_report.py spec.json report.html
python <skill>/scripts/check_fit.py report.html report.pdf
```

`check_fit.py` fails if the PDF is more than one A3 page or any panel clips,
lists panels under 55% full, and lists table or timeline cells that wrapped.
Fix by changing rows or columns, not the template's type sizes. Then look at
a screenshot yourself: the checker catches geometry, not a bar chart whose
labels are all "Unassigned" or a Gap table whose Deltas are all $0.

## 6. Deliver, then ask for what's missing

`report.html` (logos inlined; Red Hat Text loads from Google Fonts) and `report.pdf`.
One or two sentences: which sections and why, and anything about the data
the reader should know ("no activities scheduled after 16 Aug in Join";
"Gap Analysis left off — 26 of 27 pending items have no STRUCTURE
category"; `terminology_note()` when the project renames a term, so nobody
goes looking for a "Budget" column the sheet calls "Target Budget"). Offer
to drop in logo files if placeholders were used.

**End every delivery with the data ask**, when it applies. The sheet is
only as good as the register and the timeline behind it, so if the project
has no open risks, or no risk carries a Cost Impact, or the timeline has no
activities after today (or none at all), close with one short paragraph that
says exactly which of those is empty and that adding them in Join — risks
with Likelihood, Impact and a ROM Cost Impact on the Risks page; upcoming
milestones, events and phases on the Timeline page — will bring the Risk
summary, Timeline and header metrics onto the next run of this sheet. Offer
to create the risks or timeline activities from a list if they give you one
(`create-risk` exists; timeline activities are added in the app). Skip the
paragraph only when both are already populated.

## Files

- `scripts/build_report.py` — spec → self-contained HTML (template and logos inlined; footer = timestamp only).
- `scripts/check_fit.py` — HTML → one-page A3 PDF; fails on overflow, flags sparse panels and wrapped cells.
- `scripts/join_data.py` — loaders, `configure()` (currency + terminology), money, cost summary, rollups, item catalog, gap check and analysis, decisions by area, recent activity, risks, timeline, HTML blocks (column pruning, no-wrap tables), Join URLs.
- `assets/template.html` — the A3 layout in Join's light theme, with the Join mark (the Join web app's logo) inline in the footer.
- `assets/join-logo.svg` — the same Join mark as a standalone file (the template already has it inline; `logos.join` in the spec overrides it).
- `references/data-gathering.md` — tool-by-tool guide: fields, pagination, units and currency, terminology, cost modes, edit log.
- `references/sections.md` — section catalog (incl. Recent Activity, Decisions by area) and recommendation table.
- `references/join-design.md` — Join's colors, type scale, terminology (defaults, renamable concepts) and definitions.
