# Join design language and terminology

Extracted from the Join web application so the report looks and
reads like a Join page. The template (`assets/template.html`) already applies
all of this; use this file when you author section content or extend the
template, so new elements stay consistent.

## Typography

Font: **Red Hat Text** for body and small type, **Red Hat Display** for titles
and large numbers (`--font-display`). Both are SIL Open Font License, loaded
from Google Fonts by `assets/template.html`, and fall back to Helvetica Neue /
Helvetica / sans-serif when offline. They stand in for Join's application
font, Larsseit, which this plugin can't redistribute. Letter-spacing 0.0119em
everywhere. Numbers use `font-variant-numeric: lining-nums tabular-nums`.

Join's type scale (px, line-height, weight) — the template maps report
elements onto these:

| Class | Size / LH / Weight | Used for |
|---|---|---|
| heading1 | 28 / 32 / 500 | project name |
| heading2 | 21 / 28 / 500 | — |
| heading3 | 16 / 24 / 700 | section titles |
| body1 | 16 / 24 / 400 | — |
| body2 | 14 / 24 / 400 | story text |
| body3 | 12 / 16 / 400 | subtitles, notes |
| label | 12 / 16 / 400 | metric labels |
| table-header | 14 / 16 / 700 | table headers |
| table-text / table-number | 14 / 16 / 400 | table cells |
| print-paragraph | 12 / 16 / 400 | print body |
| print-label | 10 / 14 / 400 | print small labels |

Join's own print reports use a 10px body, black text, weight 300–400, thin
`#D0D5D7` dividers, and a header of *project name* over *milestone: report
name* with a banner image on the right. Bold is 700; medium (500) is used for
headings, not for emphasis in body text.

## Colors

Brand: yellow `#FFCF5D` · coral `#ED6864` · sand `#EAE7DB` · orange `#DE7C1D`
· slate `#3C4746` · light gray `#D8DADA`.

Greys: 100 `#F6F7F9` · 200 `#E7EAEF` · 300 `#D0D5D7` · 400 `#9B9B9B` ·
500 `#686B6C` · 600 `#494B4B`.

Semantic tokens (light theme) the template exposes as CSS variables:

| Variable | Value | Meaning in Join |
|---|---|---|
| `--type-primary` | `#000` | body text |
| `--type-muted` | `#9B9B9B` | secondary text |
| `--type-link` | `#4B71A9` (blue-500) | links |
| `--type-error` | `#E11E29` (red-500) | errors, over budget |
| `--type-success` | `#6AAF6F` (green-500) | under budget |
| `--type-warning` | `#F6B901` (yellow-400) | warnings |
| `--border-default` | `#D0D5D7` | rules, table borders |
| `--border-separator` | `#E7EAEF` | row separators |
| `--border-brand` | `#FFCF5D` | brand accent rule |
| `--bg-1` | `#F6F7F9` | panel background |
| `--entity-estimate` | `#000` | estimate bars/lines |
| `--entity-budget` | `#4B71A9` | budget bars/lines |
| `--entity-markups` | `#157E84` | markups |
| `--entity-owner-cost` | `#62AEB7` | owner costs |
| `--entity-milestone` | `#4B71A9` | milestone markers |
| `--entity-event` | `#ED6864` | timeline events |
| `--entity-today` | `#5CD746` | today marker |
| `--entity-item-pastdue` | `#ED6864` | past-due items |
| `--entity-item-upcoming` | `#F6B901` | upcoming items |
| `--entity-risk-high` | `#E11E29` | risk score ≥ 15 |
| `--entity-risk-med` | `#F6B901` | risk score 6–14 |
| `--entity-risk-low` | `#6AAF6F` | risk score 1–5 |
| `--entity-risk-tbd` | `#686B6C` | undetermined |
| `--entity-risk-closed` | `#D0D5D7` | closed |
| `--chart-pending-area` | `#f6b90199` | pending cost band |

Item status colors (chip text / tint background):

| Status | Label | Color | Tint |
|---|---|---|---|
| PENDING | Pending | `#F6B901` | `#FEF8E6` |
| ACCEPTED | Accepted | `#6AAF6F` | `#F0F7F1` |
| INCORPORATED | Incorporated | `#08493B` | `#E6EDEB` |
| REJECTED | Rejected | `#E11E29` | `#FCE9EA` |
| NOTCHOSEN | Not Chosen | `#9B9B9B` | `#E7EAEF` |
| NOTAPPLICABLE | Not Applicable | `#9B9B9B` | `#E7EAEF` |

## Terminology (use these words, nothing else)

From Join's terminology defaults and their in-app definitions. Ten of these
concepts can be **renamed per project** (Join's project settings), and the
app then shows the project's label everywhere — the dashboard, the items
list, the printed reports. `terminology-for-project` returns the labels in
use, keyed by concept: ESTIMATE, TARGET (Budget), DELTA, RUNNING_TOTAL, GAP,
DIRECT_COST, MARKUP, COST_OF_CONSTRUCTION, PROJECT_TOTAL,
PROJECT_RUNNING_TOTAL. A report that says "Budget" to a team whose Join says
"Target Value" reads as if it came from somewhere else, so the renamed label
is the right word in the report *and* in the conversation about it. The
scripts apply them through `T(concept)`; the table below gives the defaults
and marks the renamable concepts with their key.

| Term | Definition |
|---|---|
| **Estimate** `ESTIMATE` | The baseline estimate for the project in a milestone. Items are changes relative to it. |
| **Budget** `TARGET` | The target amount allocated for the project. |
| **Delta** `DELTA` | Budget − Estimate. Negative if the estimate is over budget. |
| **Accepted Changes** | Total value of accepted items. |
| **Running Total** `RUNNING_TOTAL` | Estimate + accepted items: the real-time project cost. |
| **Pending Adds / Pending Deducts** | Value of pending items with positive / negative cost impact — changes yet to be finalized. |
| **Potential Range** | Running Total + all pending deducts … Running Total + all pending adds. |
| **Gap** `GAP` | Budget − Running Total: the change still needed to meet budget. **Negative when over budget.** |
| **Gap Trending Minimum / Maximum** | Gap if all pending deducts / adds are accepted. |
| **Direct Costs** `DIRECT_COST` | Materials, labor, equipment. |
| **Markups** `MARKUP` | Indirect, below-the-line costs. |
| **Cost of Construction** `COST_OF_CONSTRUCTION` | All costs excluding Owner Costs. |
| **Owner Costs** | Costs carried by the owner outside the construction contract. |
| **Project Total** `PROJECT_TOTAL` | All costs including Owner Costs. |
| **Project Running Total** `PROJECT_RUNNING_TOTAL` | Running Total including Owner Costs. |
| **Item** / **Option** | A scope decision / one alternative within an item. |
| **Cost Impact** | An item's or risk's effect on cost. Never "swing", "exposure", "delta" (for items) or "savings" as a column name. |
| **Schedule Impact** | An item's effect on schedule, in days; may be on the critical path, TBD or N/A. |
| **Due Date** / **Past Due** | An item's decision deadline / an item whose due date has passed while still pending. |
| **Assignee** | The person an item or risk is assigned to. |
| **Milestone** | A design/estimate issuance (e.g. 100% DD). The **active milestone** is the current one. |
| **Timeline** | Milestones, phases, events and tasks with dates. |
| **Risk** | Register entry with **Likelihood** (1 Rare · 2 Unlikely · 3 Possible · 4 Likely · 5 Almost Certain), **Impact** (1 Insignificant · 2 Minor · 3 Moderate · 4 Major · 5 Severe), **Risk Score** (= Likelihood × Impact), **Cost Impact** (ROM cost, may be unset) and a **Response Plan**. Status **Open** / **Closed**. When Cost Impact is unset across the register, show Likelihood and Impact — the factors of the score — not a column of dashes. |
| **Risk urgency** | Score 1–5 Low · 6–14 Medium · 15–25 High · otherwise Undetermined. |
| **Categorization** | A labeling scheme (UniFormat, MasterFormat, Location, …); a **Category** is one value in it. |
| **Scenario** | A what-if combination of item decisions. |
| **Contingency** / **Allowance** | Reserves carried as milestone markups and drawn down by items; `get-contingency-report` gives each one's starting, pending, accepted and remaining amounts. |

Money is formatted in the project's currency (`currency` on the project
record: $, £, €, …), short form as in the app ($1.2B / $209.8M / $531K).
Sign convention on the sheet: cost impacts are shown with their sign
(−$1.2M is a deduct, +$800K an add). Gap and Delta follow Join: negative
means over budget. They are set in `--type-muted` grey exactly as the Gap
row in the app's cost summary — never red or green; the sign carries the
meaning. Accepted Changes and deducts are green (`--type-success`), as in
the app; adds stay in the default text color.

## Layout conventions borrowed from Join

- Cost summary block order: Estimate · Accepted Changes · Running Total ·
  Pending Adds/Deducts · Potential Range · Gap — each in the project's own
  label where it has renamed one (a project that says "Baseline Estimate"
  and "Target Budget" in the app gets those words here too, from
  `terminology-for-project`). The Cost Trendline legend uses the same three
  labels: Estimate · Running Total · Budget as the project names them.
- Cost Trendline: dotted black baseline estimate, solid black running total
  (2px), blue-500 budget (2px), 4.5px dots, 11px value labels, grey-300 mesh
  lines and axis, milestone names rotated on the x axis. `trendline_svg()`
  reproduces it.
- Tables: header row 14/16/700 with a `--border-default` bottom rule; cells
  14/16/400 with `--border-separator` rules; numbers right-aligned, tabular.
  Rows are single-line as in the app's Items list: names truncate with an
  ellipsis, numbers and dates never break. Columns with no data are not
  drawn (except deadline columns and Schedule Impact = TBD).
- Timeline rows: one grid so dates align; the date column is as wide as
  its longest range and never wraps; activity names truncate.
- Footer: the creation timestamp and the Join logo, nothing else — no
  "from Join data", no "prepared by".
- Status shown as an icon + label in Join; on paper the template uses a
  small tinted chip with the label.
- Links are `--type-link`, no underline until hover.
- Bars: estimate/running total in black, budget in blue-500 as a tick or a
  second bar; markups teal; owner costs `#62AEB7`.
