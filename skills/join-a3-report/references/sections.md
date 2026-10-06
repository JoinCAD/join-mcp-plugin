# Section catalog

Each panel is roughly 128 mm × 100 mm of content at Join's 14px table type:
about 8 single-line table rows, up to ~16 bar rows (`bars(..., gap_px=3)`
for long lists), 9 timeline rows. Every section has a title, a one-line
subtitle stating the basis or filter, and a link into Join. No footnotes
inside panels — if a number needs explaining, explain it in the subtitle or
don't show it.

**Data rows do not wrap.** `table()` keeps every cell on one line: the first
column truncates with an ellipsis (the full text sits in a tooltip), the
other columns never break, and the timeline's date column sizes itself to
its longest range ("01 Dec 2025 – 30 Jun 2027") so names truncate instead.
Fix a truncated table by dropping rows or a column, or shortening a header —
not by wrapping. The one deliberate exception is `table(..., wrap=True)` for
Top Decisions when item names would otherwise be cut below ~30 characters:
the Item column may then take two lines (clamped), and 5–6 rows fit.
`check_fit.py` lists any cell that wrapped anyway.

**Empty columns disappear.** `table()` drops a column whose every cell is
blank, "—" or N/A (`prune_columns()`), so a Cost Impact column that no risk
fills or a Budget column on a project with no budget lines simply isn't
rendered — pick a fallback that carries information instead (see Risk
summary). Two kinds of column are always kept even when blank, because the
absence is itself the message: **deadline columns** (Due Date, Decide by,
Next Due) and a **Schedule Impact column that reads TBD** (TBD is a value in
Join; a column of N/A or unset is not and is dropped).

Use Join's words (`references/join-design.md`): Cost Impact, not "swing" or
"exposure"; Running Total, not "projected cost"; Gap, not "variance". Where
the project has renamed a concept, use its label: the helpers do this through
`T()` once `configure(project, terms)` has run, and anything you write in a
subtitle yourself should too — `f"By Location · {T('ESTIMATE')} vs {T('TARGET')}"`,
not a hard-coded "Estimate vs Budget".

## Cost breakdown

**Needs:** `MILESTONE_ESTIMATE` and `MILESTONE_BUDGET` rows; categorizations;
get-item details for the axis values. **Link:** the milestone page or a
saved milestone summary report.

Axis, in order of preference: a **location / programmatic-area**
categorization (Location, Building, Area, Department, Phase, Program) → then
a **system** breakdown (UniFormat Level 1) → then trade (MasterFormat Level 1).
`pick_breakdown_axis()` applies this order and checks the axis actually
covers the estimate lines. Categories are listed in **alphanumeric order**,
never by size, and never folded into "All other".

```python
axis, keyfn = pick_breakdown_axis(categorizations, details, est_rows)
pairs = rollup(est_rows, keyfn); bud = dict(rollup(bud_rows, keyfn))
if len(pairs) <= 5:    body = breakdown_table(pairs, bud, cs)                 # Estimate · Budget · Delta + buildup rows
elif len(pairs) <= 16: body = bars(pairs, budget=bud, total=cs["estimate"])  # bars with budget ticks
else:                  body = buildup_html(buildup(cs, report_sep))          # too many categories: buildup only
```

Owner Costs lines roll up as their own "Owner Costs" row so the panel totals
to Project Total. If the category list has more than ~16 rows it will not fit; then show the
**buildup** instead — Direct Costs, Markups, Cost of Construction, Owner
Costs, Project Total, Accepted Changes, Project Running Total — using a
second milestone report fetched with `markupMode: SEPARATED_MARKUPS`.
Subtitle states the axis and basis, e.g. "By Location · Estimate vs Budget,
incl. Owner Costs" — built with `T("ESTIMATE")` / `T("TARGET")` so a project
that says "Baseline Estimate vs Target Budget" reads that way.

## Gap Analysis

**Needs:** estimate and budget rows on an axis (same axis as the breakdown,
or trade/system if that's where the variance is), item catalog with get-item
details (categories, due dates, activity links), timeline activities.
**Link:** items list.

Purpose: focus attention on the categories where decisions can most move
the number — largest Delta to Budget, widest pending Cost Impact range, and
anything the timeline says must be committed soon. Categories that have
pending items but no estimate line are included (Delta 0, Cost Impact
shown); only future activities count as deadlines.

**Only when the estimate and the budget share a meaningful categorization.**
Run `gap_axis_check()` first; it refuses the section when there are no
Budget lines, when more than half of the estimate (or of the pending items)
lands in Unassigned / Uncategorized on the axis, when fewer than two real
categories exist, or when most categories that carry estimate have a zero
Budget (every Delta would just mirror the Estimate). A table of "$0" Deltas
or an "Unassigned" row holding 26 of 27 items tells the sponsor nothing.
Try the other axes (Location → UniFormat → MasterFormat) before giving up;
if none passes, use Cost trend by milestone or Decisions by area and say
why in delivery.

```python
cat_of = item_key_for_axis(axis)
ok, why = gap_axis_check(est_rows, bud_rows, keyfn, catalog, cat_of)
if ok:
    rows = gap_analysis(est_rows, bud_rows, keyfn, catalog, cat_of, activities, as_of)
    body = gap_table(rows)   # Category · Delta to Budget · Pending Cost Impact (count) · Decide by (Past Due / Soon chips)
else:
    print("Gap Analysis skipped:", why)   # → Cost trend by milestone or Decisions by area
```

Subtitle: "Ranked by Delta to Budget and pending Cost Impact range". Delta
follows Join's sign (negative = over budget) and is shown in muted grey like
the Gap row in the app — never red.

## Risk summary

**Needs:** risks from both registers (`PROJECT` and `COMPANY`; the company
register is the preparer's own and is usually left off an owner-facing
sheet). **Link:** Risks.

```python
rs = open_risks(risks)
body = (risk_matrix(rs) if len(rs) >= 8 else "") + risk_table(rs, U)
```

`risk_table()` shows Risk · Risk Score · Cost Impact. When no listed risk
carries a Cost Impact (ROM cost unset on all of them — common on registers
kept for schedule or quality risks) it shows the two factors that make up
the score instead, in Join's words: **Risk · Likelihood · Impact · Risk
Score**, each factor as its label and 1–5 value (Likely 4 · Severe 5). A
column of "—" is never rendered. Risk Score = Likelihood × Impact; chips
use Join's urgency colors (Low ≤ 5, Medium ≤ 14, High ≥ 15). Empty register
→ swap the section, say so in delivery, and ask for risks at the end.

## Timeline

**Needs:** timeline activities. **Link:** Timeline.

```python
done, upcoming = timeline_window(activities, as_of, past=2, future=7)
body = timeline_html(done, upcoming, as_of)
```

Milestones get the blue diamond, events the coral dot, today the green dot.
Ranges render as "26 Jun – 15 Oct 2026" or, across years, "01 Dec 2025 –
30 Jun 2027", never wrapped. **If the timeline is empty or has nothing after
today (`has_future_activities()` is False), use Recent Activity in this slot
instead** and carry the fact into its subtitle ("no activities scheduled
after 16 Aug 2026") — a panel of three past milestones and "Today" is not a
timeline. Ask for timeline activities at the end of delivery.

## Recent Activity

**Needs:** item catalog with `createdAt` / `updateTime`; timeline
activities; risks; and, for rows that say *what* changed, the project-wide
edit log from `get-item-history {projectID, since: as_of − 4 weeks}`
(paginate; see `data-gathering.md`). **Link:** Timeline (or Items).

Purpose: what moved in the last 1–4 weeks — item status changes, new items,
Cost Impact / Due Date / milestone changes, milestones and events that
passed, phases that started or ended, risks added — each with the item's
current Cost Impact so the reader sees the money behind the change. This is
the default replacement for Timeline when nothing is scheduled after today,
and a good alternate for Work in flight on a project with few companies.

```python
rows, weeks = recent_activity(catalog, activities, as_of, risks=risks, history=history_pages)   # 2 weeks, widened to 4 until ≥ 6 rows
body = activity_html(rows, U)
subtitle = f"Item changes and timeline events in the last {weeks} weeks" + ("" if has_future_activities(activities, as_of) else f" · no activities scheduled after {fmt_date(last_end)}")
```

Newest first, one row per item (its latest significant edit), 8–10 rows.
Rows are facts from Join's edit log — "Now Accepted · −$1.2M", "New ·
+$466K", "Cost Impact changed · +$4.8M" — never a narrative of why.
Without the history pages the rows fall back to "Updated · Cost Impact"
from the items' own timestamps; say so in delivery if that is all you have.

## Top decisions

**Needs:** `items_catalog(items, report, details)` with get-item details for
the featured items (Schedule Impact and Due Date come only from get-item).
**Link:** items list, or a saved "Pending items" report.

```python
td = top_decisions(cat, milestone_id=active["id"], n=8)
rows = [[link(U["item"](i["id"]), f"{i['number']}. {i['name']}"),
         f'<span class="{impact_class(i["cost"])}">{cost_impact_label(i)}</span>',
         schedule_impact_label(i["schedule"]), due_cell(i, as_of)] for i in td]
body = table(["Item", "Cost Impact", "Schedule Impact", "Due Date"], rows, num_cols=(1,), nowrap_cols=(2, 3))
# names cut below ~30 characters? → wrap=True (two-line names, 5–6 rows) is the allowed exception
```

Options fold into their parent — the parent is the decision and its range
is the Cost Impact. Subtitle: "Pending · by Cost Impact · CP = critical path
· red date = Past Due". **Due Date always renders**, even when no item has
one — the blank column is the message. **Schedule Impact renders when any
item has a value or TBD**; a column of N/A or unset is dropped by
`table()`. If the panel clips, show fewer rows.

## Decisions by area

**Needs:** catalog with get-item categories; categorizations. **Link:** items list.

Pending decisions grouped by the way the project organizes itself. Axis
order (`pick_area_axis()`): an organizational categorization the project
defined — **PIT**, **TVD Cluster**, Location, Building, Area, Phase,
Increment, Zone, Department — that at least half of the pending items carry
→ UniFormat Level 1 → a Bid / Work Package categorization → MasterFormat
Level 1. One row per area:

```python
axis, akey = pick_area_axis(categorizations, catalog)
rows = decisions_by_area(catalog, akey, as_of, milestone_id=active["id"])
body = decisions_by_area_table(rows, axis, as_of)   # Area · Pending · Cost Impact (pending range) · Schedule Impact (largest) · Next Due
```

Columns: **Pending** count · **Cost Impact** — the pending range (sum of
deducts to sum of adds) · **Schedule Impact** — the largest among the area's
items, "−100 d · CP" or "TBD" (column dropped when no item carries one) ·
**Next Due** — the earliest upcoming Due Date, coral when already Past Due
(always shown). Areas in alphanumeric order, Unassigned last. Subtitle:
"Pending items by TVD Cluster · Cost Impact range · largest Schedule Impact
· next Due Date", plus "n of m pending have no TVD Cluster category" when
Unassigned is more than a sliver. For sponsors who think in buildings,
increments or clusters.

## Work in flight

**Needs:** catalog with assignee emails (from get-item details or the newer
items-for-project). **Link:** items list.

```python
axis = pick_company_axis(categorizations)                  # 'Responsible Party' if the project has one, else 'company'
rows = work_in_flight(cat, as_of, mapping=company_map, by=axis)
table(["Company", "Pending", "Past Due", "Cost Impact", "Updated 30d"], [[esc(r["group"]), r["pending"], r["past_due"] or "", money(r["cost_impact"], signed=True), r["updated_30d"]] for r in rows], num_cols=(1, 2, 3, 4))
```

Grouped by **company**, never by individual. Prefer a categorization that
names companies (Responsible Party etc.); otherwise company comes from the
assignee's email domain — confirm the domain → company names with the user
in the one question round. Past Due = pending items whose due date has passed.

## Cost trend by milestone

**Needs:** a detailed milestone report per non-draft milestone that has an
estimate (one `get-detailed-milestone-report` + resource read each; usually
3–5), plus the milestone list so future milestones without estimates (a GMP
that is set but not priced) still appear on the axis. **Link:** Milestones.

```python
pts = milestone_trend(milestones, {ms_id: report, ...})
body = trendline_svg(pts)                                    # chart in the app's Cost Trendline style; labels carry the numbers
# With three or fewer milestones there is room for the table too: trendline_svg(pts, height=200) + trend_table(pts)
```

The chart mirrors the app: dotted black Estimate, solid black Running
Total, blue Budget (legend in the project's labels), a dot and value label at each milestone,
grey mesh lines, milestone names on the x axis. Use it whenever the project
has three or more estimated milestones — it answers "is the Gap opening or
closing" faster than any table. Subtitle states the basis (all-in when
Owner Costs exist).

## Contingency

Only with user-supplied figures (the connector does not expose contingency
or allowances): starting amount, drawn, remaining, and the largest draws.
Use `bars()` with Join's contingency colors if you extend the template.

## Custom image

`<figure class="figure"><img src="data:…"><figcaption>…</figcaption></figure>`.
Inline the file as a data URI. Ask for the caption; never write one that
asserts something about the image.

## Recommendation logic

Default six: **Cost breakdown · Gap Analysis · Risk summary · Timeline · Top
decisions · Work in flight**. Adjust from the data:

| Signal | Change |
|---|---|
| No open risks | Risk → Cost trend by milestone (or Decisions by area); ask for risks at the end |
| Timeline empty or nothing after today | Timeline → **Recent Activity**; ask for timeline activities at the end |
| Open risks but no Cost Impact on any | Keep Risk summary; `risk_table()` shows Likelihood · Impact instead |
| < 5 pending items | Top decisions → Cost trend; Work in flight → Recent Activity |
| No budget on the project | Gap Analysis → Cost trend by milestone |
| `gap_axis_check()` fails on every axis (Unassigned-heavy, zero budgets) | Gap Analysis → Cost trend by milestone or Decisions by area |
| Multi-building / PIT / TVD Cluster / Location populated on items | Breakdown axis = that categorization; consider Decisions by area |
| User supplied a custom image | Add it, usually replacing Work in flight |
| User supplied contingency figures | Add Contingency |
| Reader is the CM / design team | Breakdown axis → trade |
| Three or more estimated milestones | Consider Cost trend by milestone in place of Work in flight |

Present the six with one line of rationale each, name the alternates, and
ask. There is no recommendations, next-steps, story or scenario section: the
sheet shows Join's numbers; the reader draws the conclusions.
