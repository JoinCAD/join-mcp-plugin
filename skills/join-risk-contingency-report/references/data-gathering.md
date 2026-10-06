# Gathering the data from the Join connector

Tools are named here by their bare Join MCP names (`project-costs`, …). The
prefix your client adds depends on how Join is connected (e.g.
`mcp__plugin_join_join__` when it comes from this plugin, something else for
a claude.ai connector), so match on the suffix. Save every result verbatim
to the work directory under the file names below — `risk_model.load_inputs()`
reads exactly these, and you will rebuild the model several times while the
user adjusts assumptions. Large results are spilled to a file by the tool
runner; copy that file into the work dir rather than re-fetching.

| File | Tool | Notes |
|---|---|---|
| `project.json` | `list-my-projects` / `search-projects` — the page holding the project (or the one record) | `id`, `name`, `currency`, `budget`, `url`; `load_inputs` picks the record matching `costs.projectId` |
| `terms.json` | `terminology-for-project {projectID}` | the project's labels for Estimate, Budget, Running Total, Gap, … — the report and your conversation use them |
| `costs.json` | `project-costs {projectID}` | `total` = Estimate (Project Total, all-in), `milestoneId` = active milestone |
| `milestones.json` | `milestones-for-project {projectID}` | for the milestone name and date in the header |
| `contingency.json` | `get-contingency-report {projectID}` (default `milestone: "active"`) | each contingency's `starting`, `pending`, `accepted`, `remaining` and the item `draws` on it — the source of the contingency held. Refused for roles that cannot see markups; then the report below is the fallback |
| `report.json` | `get-detailed-milestone-report {projectID, milestoneID, costMode: {markupMode: "SEPARATED_MARKUPS", includeOwnerCosts: true}}` → `ReadMcpResourceTool` (server: whichever one serves the Join tools) on the returned `resourceURI` | **must be SEPARATED_MARKUPS** — the only mode in which contingency and allowance lines are rows of their own (the fallback source of contingency, and of the Budget lines) |
| `items-1.json`, `items-2.json`, … | `items-for-project {projectID, filters: {itemsOnly: true, statuses: ["PENDING", "ACCEPTED"]}, limit: 50}` paginating on `cursor` | default milestone `"active"`; one file per page. Only pending and accepted items enter the model, so the status filter turns a 274-item project from six pages into one or two |
| `risks-project.json` | `risks-for-project {projectID, riskType: "PROJECT"}` | paginate on `cursor` into `risks-project-2.json` … |
| `risks-company.json` | `risks-for-project {projectID, riskType: "COMPANY"}` | the caller's company register; often empty |

When a page comes back inline (small result) save the JSON exactly as
returned; when it is spilled to a file, copy that file. Either way the file
must be the tool's own JSON (`{"total": …, "items": [...]}`) — do not
re-type or trim fields, `normalize_items` reads several of them.

Optional: `get-risk {riskID}` for any risk you will discuss with the user
(description, response plan, assignee); `get-item {itemID}` for an item's
schedule impact or assignee when it comes up in the override conversation.

## Units, currency and terminology

Every tool returns money in **whole currency units**, never cents:
`list-my-projects`, `project-costs`, `items-for-project` (`cost.value` /
`cost.min` / `cost.max`), `risks-for-project` (`romCost`) and
`get-contingency-report` as decimal strings (`"1495000.00"`,
`"-90405.87"`); the milestone report resource as plain numbers. `amount()`
parses both; nothing is divided by 100. The project record's `currency`
(`USD`, `GBP`, `EUR`, …) sets the symbol `money()` prints; `load_inputs`
reads it. No conversion between currencies happens anywhere.

`terminology-for-project` returns `{"terms": {ESTIMATE, TARGET, DELTA,
RUNNING_TOTAL, GAP, DIRECT_COST, MARKUP, COST_OF_CONSTRUCTION, PROJECT_TOTAL,
PROJECT_RUNNING_TOTAL}}` — the labels this project shows (defaults Estimate,
Budget, Delta, Running Total, Gap, …). `load_inputs` installs them;
`T("TARGET")` returns the project's word, `renamed_terms()` lists what
differs from the defaults and `terminology_note()` is a sentence for the
delivery. Read `terms.json` before you first describe the numbers to the
user, so you say "Target Value" rather than "Budget" to a team whose Join
says "Target Value".

## Where each number comes from

- **Estimate** = `costs.total` (Project Total, all-in, allocated markups).
- **Accepted Changes** = Σ cost of items with status `ACCEPTED` in the active
  view (a range item counts its midpoint).
- **Running Total** = Estimate + Accepted Changes. Reconcile against the
  Running Total shown in the app if you can; a difference means an option
  or draft is being counted differently.
- **Contingency held** = Σ `remaining` of the `type: "CONTINGENCY"` lines
  in `contingency.json` for the active milestone — what the project still
  holds after the draws accepted so far (`starting` + `accepted` +
  `incorporated`; draws are negative). This is the figure the app's
  Contingency & Allowance Report shows as remaining, and `cost_summary()`
  reports `contingency_source: "remaining"` with `contingency_starting` and
  `contingency_drawn` alongside so page 1 can show the subtraction. When
  the contingency report is not available to the user's role, the fallback
  is Σ `costDetail.total` of `report.json` rows with `lineType: "MARKUP"`
  and `markupDetails.displayType: "CONTINGENCY"` — the starting amounts,
  with accepted draws not netted off (`contingency_source: "starting"`);
  say so in the delivery. `type: "ALLOWANCE"` lines are reported on page 1
  but not modeled.
- **Items that draw on contingency.** An item drawing on a contingency shows
  its *net* Cost Impact in Join (often `0.00`) because the draw offsets it.
  Since Base Cost backs out the *remaining* contingency, `normalize_items`
  carries a pending item at its gross cost (Cost Impact − its pending draw
  from `contingency.json`'s `draws[]`), so accepting it in the model
  consumes contingency just as it would in Join. `cost_summary()["pending_draws"]`
  is the total grossed up; page 1 shows it. Accepted draws need no
  adjustment — they are already inside both Accepted Changes and the
  remaining balance. Allowance draws are left at net.
- **Pending Adds / Pending Deducts** = Σ max / Σ min of `PENDING` items in
  the active view (gross of contingency draws, as above). Do **not** filter
  items by their `currentMilestone`: the active view deliberately includes
  pending items still sitting in an earlier milestone, and the app's
  Pending Adds count them.
- **Budget** (or whatever the project calls `TARGET`) = `MILESTONE_BUDGET`
  rows of the report if any (all-in), else `project.budget` (Cost of
  Construction).
- **Risks**: `status`, `likelihood` (1–5), `impact` (1–5), `romCost` = Cost
  Impact (often null). Only `OPEN` risks are modeled.

## Join URL patterns

Project `https://app.join.build/{projectID}`; items `…/items`, item
`…/items/{itemID}`; risks `…/risks`, risk `…/risks/{riskID}`; the dashboard
that hosts the Cost Risk Calculator is the project URL itself. Item and risk
rows carry a `url` field when the connector provides one.

## Success Hub pages to point people to

- Contingencies and allowances are milestone markups:
  https://success.join.build/en/knowledge/markups-in-milestones (and the
  overview https://success.join.build/en/knowledge/markups-overview). A
  contingency is a markup line whose display type is **Contingency**, added in
  the milestone estimate's *Milestone Markups, Contingencies, and Allowances*
  section.
- Risk register (creating, scoring, cost impact, response plans):
  https://success.join.build/en/knowledge/risk-register
