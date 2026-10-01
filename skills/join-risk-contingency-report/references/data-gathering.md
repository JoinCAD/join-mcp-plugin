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
| `project.json` | `list-my-projects` / `search-projects` — the one project record | `id`, `name`, `budget`, `url` |
| `costs.json` | `project-costs {projectID}` | `total` = Estimate (Project Total, all-in), `milestoneId` = active milestone |
| `milestones.json` | `milestones-for-project {projectID}` | for the milestone name and date in the header |
| `report.json` | `get-detailed-milestone-report {projectID, milestoneID, costMode: {markupMode: "SEPARATED_MARKUPS", includeOwnerCosts: true}}` → `ReadMcpResourceTool` (server: whichever one serves the Join tools) on the returned `resourceURI` | **must be SEPARATED_MARKUPS** — that is the only mode in which contingency shows up as its own rows |
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

## Units

`list-my-projects`, `project-costs`, `items-for-project` (`cost.value` /
`cost.min` / `cost.max`) and `risks-for-project` (`romCost`) return money as
**strings of US cents**. The detailed milestone report resource returns
**float dollars**. `risk_model` converts everything to dollars on load.

## Where each number comes from

- **Estimate** = `costs.total` (Project Total, all-in, allocated markups).
- **Accepted Changes** = Σ cost of items with status `ACCEPTED` in the active
  view (a range item counts its midpoint).
- **Running Total** = Estimate + Accepted Changes. Reconcile against the
  Running Total shown in the app if you can; a difference means an option
  or draft is being counted differently.
- **Contingency held** = Σ `costDetail.total` of `report.json` rows with
  `lineType: "MARKUP"` and `markupDetails.displayType: "CONTINGENCY"`. These
  are the milestone's contingency markups — the same lines the app's
  Contingency report calls the *starting* amount. Draws against contingency
  that were made through items are already inside Accepted Changes; the
  connector does not expose the contingency report's used/remaining
  balances, so the analysis uses the starting amount and says so.
  `displayType: "ALLOWANCE"` rows are reported in the Basis block but not
  modeled. `displayType: "MARKUP"` rows are ordinary markups.
- **Pending Adds / Pending Deducts** = Σ max / Σ min of `PENDING` items in
  the active view. Do **not** filter items by their `currentMilestone`: the
  active view deliberately includes pending items still sitting in an
  earlier milestone, and the app's Pending Adds count them.
- **Budget** = `MILESTONE_BUDGET` rows of the report if any (all-in), else
  `project.budget` (Cost of Construction).
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
