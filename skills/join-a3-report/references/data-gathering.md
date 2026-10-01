# Gathering data from the Join connector

Tools are named here by their bare Join MCP names (`project-costs`, …). The
prefix your client adds depends on how Join is connected (e.g.
`mcp__plugin_join_join__` when it comes from this plugin, something else for
a claude.ai connector), so match on the suffix. Save each result verbatim
to a JSON file in a work directory (`project.json`, `costs.json`,
`items-1.json`, …). `join_data.load()` reads raw tool JSON and the
`{"contents":[{"text":…}]}` resource wrapper alike. Never reuse a shared
scratch path between runs — copy large results into your own work dir.

## Units

| Source | Money unit |
|---|---|
| `list-my-projects`, `search-projects` (`budget`, `estimate`) | string, US cents |
| `project-costs` (`total`, `breakdown[].cost`) | string, US cents |
| `items-for-project` (`cost.value`, `cost.min/max`) | string, US cents |
| `risks-for-project` (`romCost`) | string, US cents, may be null |
| Detailed milestone report resource (`costDetail.total`, `derivedTotals.*`) | **float dollars** |

`cents()`, `money_cents()`, `money()` in `join_data` handle each.

## Cost basis — all-in

`project-costs` returns the active milestone's **Project Total** (`total`)
with a `breakdown` of `DirectCostsAndAllocatedMarkups` (Cost of
Construction) and, when the project carries them, `OwnerCosts`. The project
record's `estimate` / `budget` are Cost of Construction only.

The detailed milestone report in its **default cost mode** (allocated
markups, owner costs included) puts estimate lines, budget lines and item
rows on the same all-in basis: `MILESTONE_ESTIMATE` rows sum to
`project-costs.total`; `MILESTONE_BUDGET` rows sum to the all-in Budget
(which exceeds `project.budget` when owner-cost budget lines exist); item
rows' `derivedTotals` are the items' all-in Cost Impact. `cost_summary()`
computes Estimate, Accepted Changes, Running Total, Pending Adds/Deducts,
Potential Range and Gap from these. Sanity-check: estimate rollup ==
`cost_summary()["estimate"]` to the dollar.

For the cost **buildup** (Direct Costs / Markups / …) fetch a second report
with `costMode.markupMode: "SEPARATED_MARKUPS"`; `buildup()` splits rows by
`lineType`.

If a report call is refused for role reasons, retry with
`markupMode: "NO_MARKUPS"` or `includeOwnerCosts: false` and state the basis
in the cost section's subtitle.

## Call sequence

1. **Project record** — `list-my-projects` (paginate on `cursor`) or
   `search-projects {query}`. Keep `id`, `name`, `type`, `budget`,
   `estimate`, `projectLeadName`, `url`.
2. **`project-costs {projectID}`** → `total`, `milestoneId` (active
   milestone), `breakdown[]`.
3. **`milestones-for-project {projectID}`** → `milestones[]` (`id`, `name`,
   `date`, `designPhase.name`, `itemsCount`); match `costs.milestoneId`.
4. **`get-detailed-milestone-report {projectID, milestoneID}`** → a
   `resourceURI`; read it with `ReadMcpResourceTool` (server: whichever
   one serves the Join tools). It is large; when the tool result is spilled to a
   file, copy that file into your work dir. Rows: `source`
   (`MILESTONE_ESTIMATE` | `MILESTONE_BUDGET` | `ITEM`), `lineType`
   (`DIRECT_COST` | `OWNER_COST` | markup types), `categories[]` (`number`,
   `name`, `level`, `parentID`; **no categorization id**), `costDetail.total`,
   `derivedTotals`, `itemDetails` (`itemID`, `number`, `name`, `status`,
   `itemType`, `parentItemNumber`, `assigneeName`, `updateTime`, `createdAt`,
   `dueDate`, `visibility`).
5. **`items-for-project {projectID}`** — paginate on `cursor`; concatenate
   `items[]`. Each: `id`, `number`, `name`, `cost` (`CostScalar.value` |
   `CostRange.min/max`), `milestone.id` (or `currentMilestone.id`),
   `options[]`, `parentID` (non-null ⇒ an option). The `cost` object may
   omit `__typename` — a range has `min`/`max`, a scalar has `value`
   (`items_catalog` handles both). Newer connector versions also return
   `status`, `assignee {name,email}`, `dueDate`, `categories`, `url`, and
   accept `milestone`, `filters`, `sortKey`, `limit`; use them when present,
   otherwise the report and get-item supply the same fields.
6. **`get-item {itemID}`** for **every pending item in the active
   milestone** (usually 10–40 calls) and any other item you feature. This is
   the only source of `scheduleImpact {type, criticalPath, days}`,
   `activityIDs`, `dueDate`, `assignee.email` (→ company) and
   `categories[]` with categorization **names** — all needed for Top
   decisions, Work in flight, Gap Analysis and the Location axis. Save each
   as `item-<id>.json` and pass the list to `items_catalog(..., details=)`.
7. **`risks-for-project {projectID, riskType}`** for `PROJECT` and
   `COMPANY`; concatenate. Each: `id`, `number`, `name`, `status`, `impact`,
   `likelihood`, `romCost` (Cost Impact; often null — `risk_table()` then
   shows Likelihood and Impact instead). `get-risk` adds `description`,
   `responsePlan`, `assignee`, `riskScore`, `categories`, `linkedItemIDs`.
   An empty register is a delivery note *and* the closing ask (see SKILL.md §6).
8. **`timeline-for-project {projectID}`** — paginate on `cursor`; load
   pages with `load_timeline()`. `timeline.activities[]`: `id`, `name`, `startDate`, `endDate`,
   `milestoneID` (non-null ⇒ milestone), `itemCount`. Single-day ⇒ event;
   ranged ⇒ phase/task. Check `has_future_activities(activities, as_of)`:
   False means the Timeline panel becomes Recent Activity and the closing
   ask includes timeline activities.
9. **`list-user-reports {projectID}`** → saved reports with `url` and
   `reportType` (`USER_REPORT_MSR`, `USER_REPORT_VARIANCE`,
   `USER_REPORT_ITEMS_LIST`). Link a section to a saved report when it shows
   the same view.
10. **`categorizations-for-project {projectID}`** → the schemes on the
    project. `pick_breakdown_axis()` looks here for a location /
    programmatic-area categorization; `pick_area_axis()` for an
    organizational one (PIT, TVD Cluster, Location, Building, Increment …).
11. **`get-item-history {projectID, since}`** — the project-wide edit log,
    newest first, paginate on `cursor`. Fetch with `since` = today − 4
    weeks (one to three pages on an active project); optionally narrow with
    `eventTypes: [CREATE_ITEM, CHANGE_STATUS, CHANGE_COST, CHANGE_MILESTONE,
    CHANGE_ESTIMATE, CHANGE_DUE_DATE, CHANGE_SCHEDULE_IMPACT, CREATE_OPTION]`.
    Save the pages and pass the list to `recent_activity(..., history=)`;
    `history_events()` reads the event type, time and item from each edit
    whatever the field names. Needed whenever Recent Activity is on the
    sheet — i.e. always when the timeline has nothing after today. Item
    `createdAt` / `updateTime` from items-for-project are the fallback.

## Rollups

Report rows don't say which categorization a category belongs to.
`join_data` disambiguates by number shape (UniFormat `A10`, MasterFormat
`033000`) and, for custom axes, by the set of values seen on get-item
results for that categorization (`categorization_values(details, "Location")`).
Estimate lines carrying a value no item carries land in "Unassigned"; if
that is more than a sliver, list the values with `distinct_categories()` and
pass the full set to `by_custom()`.

## Join URL patterns

`join_urls(project_id)`: project `https://app.join.build/{projectID}`; items
`…/items`, item `…/items/{itemID}`; risks `…/risks`, risk `…/risks/{riskID}`;
milestones `…/milestones`, milestone `…/milestones/{milestoneID}`; timeline
`…/timeline`. Saved reports: the `url` field from `list-user-reports`.

## Not available from the connector

Contingency and allowance balances, GSF / unit quantities, change orders,
schedule baselines, company names (only assignee emails), photos. Sections
needing these take user-supplied input or are left out.
