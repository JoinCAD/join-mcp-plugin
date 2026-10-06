# Gathering data from the Join connector

Tools are named here by their bare Join MCP names (`project-costs`, …). The
prefix your client adds depends on how Join is connected (e.g.
`mcp__plugin_join_join__` when it comes from this plugin, something else for
a claude.ai connector), so match on the suffix. Save each result verbatim
to a JSON file in a work directory (`project.json`, `costs.json`,
`items-1.json`, …). `join_data.load()` reads raw tool JSON and the
`{"contents":[{"text":…}]}` resource wrapper alike. Never reuse a shared
scratch path between runs — copy large results into your own work dir.

## Units and currency

Every tool returns money in **whole currency units** — never cents:

| Source | Shape |
|---|---|
| `list-my-projects`, `search-projects` (`budget`, `estimate`) | decimal string, e.g. `"32319922.33"` |
| `project-costs` (`total`, `breakdown[].cost`) | decimal string |
| `items-for-project` (`cost.value`, `cost.min/max`) | decimal string, signed (`"-39336.84"` is a deduct) |
| `risks-for-project` (`romCost`) | decimal string or null |
| `get-contingency-report` (`starting`, `pending`, `accepted`, `remaining`, draw `amount`) | decimal string |
| Detailed milestone report resource (`costDetail.total`, `derivedTotals.*`) | plain number |

`amount()` parses any of them; `money()` / `money_str()` format. Do not
divide anything by 100 — a sheet whose Running Total reads $330K on a $33M
project is the sign that something did.

The project record carries `currency` (`"USD"`, `"GBP"`, …; also on the
contingency report). `configure(project, terms)` sets it so `money()` prints
£ or € where the project does; it never converts between currencies.

## Terminology

A project can rename its cost concepts, and Join then shows the renamed
labels throughout that project. `terminology-for-project {projectID}`
returns `{"terms": {ESTIMATE, TARGET, DELTA, RUNNING_TOTAL, GAP, DIRECT_COST,
MARKUP, COST_OF_CONSTRUCTION, PROJECT_TOTAL, PROJECT_RUNNING_TOTAL}}` with
the labels in use (defaults: Estimate, Budget, Delta, Running Total, Gap,
Direct Costs, Markups, Cost of Construction, Project Total, Project Running
Total). Save it as `terms.json` and pass it to `configure()`; every label
`join_data` renders — header metrics, table headers, legends, buildup rows —
then uses the project's words, and `T("TARGET")` gives you the right word for
anything you write yourself. The other tools keep using the default names in
their field names and descriptions (`budget`, `estimate`, `MILESTONE_BUDGET`);
only what the reader sees changes.

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
   `search-projects {query}`. Keep `id`, `name`, `type`, `currency`,
   `budget`, `estimate`, `projectLeadName`, `url`. Save the page as
   `project.json`; `project_record(load(...), projectID)` picks the record.
2. **`terminology-for-project {projectID}`** → `terms.json`. Read it before
   you talk about the numbers: if `TARGET` is "Target Value", say "Target
   Value" to the user from here on, not "Budget".
3. **`project-costs {projectID}`** → `total`, `milestoneId` (active
   milestone), `breakdown[]`.
4. **`milestones-for-project {projectID}`** → `milestones[]` (`id`, `name`,
   `date`, `designPhase.name`, `itemsCount`); match `costs.milestoneId`.
5. **`get-detailed-milestone-report {projectID, milestoneID}`** → a
   `resourceURI`; read it with `ReadMcpResourceTool` (server: whichever
   one serves the Join tools). It is large; when the tool result is spilled to a
   file, copy that file into your work dir. Rows: `source`
   (`MILESTONE_ESTIMATE` | `MILESTONE_BUDGET` | `ITEM`), `lineType`
   (`DIRECT_COST` | `OWNER_COST` | markup types), `categories[]` (`number`,
   `name`, `level`, `parentID`; **no categorization id**), `costDetail.total`,
   `derivedTotals`, `itemDetails` (`itemID`, `number`, `name`, `status`,
   `itemType`, `parentItemNumber`, `assigneeName`, `updateTime`, `createdAt`,
   `dueDate`, `visibility`).
6. **`items-for-project {projectID}`** — paginate on `cursor` (`limit` up
   to 50); concatenate `items[]`. Each: `id`, `number`, `name`, `status`,
   `cost` (`{value}` | `{min, max}`, decimal strings), `currentMilestone.id`,
   `assignee {name, email}`, `dueDate`, `scheduleImpact {type, criticalPath,
   days}`, `categories[]` with categorization **names**, `options[]`,
   `parentID` (non-null ⇒ an option), `url`. `filters` (statuses, assignees,
   cost bounds, dates, `itemsOnly`), `sortKey` and `milestone` narrow the
   call; `items_catalog` reads all of these.
7. **`get-item {itemID}`** for the items you feature when you need
   `activityIDs` (links to timeline activities — the Gap Analysis "decide
   by" date) or the description. Everything else Top decisions, Work in
   flight and the Location axis need is already on the list rows. Save each
   as `item-<id>.json` and pass the list to `items_catalog(..., details=)`.
8. **`risks-for-project {projectID, riskType}`** for `PROJECT` and
   `COMPANY`; concatenate. Each: `id`, `number`, `name`, `status`, `impact`,
   `likelihood`, `romCost` (Cost Impact; often null — `risk_table()` then
   shows Likelihood and Impact instead). `get-risk` adds `description`,
   `responsePlan`, `assignee`, `riskScore`, `categories`, `linkedItemIDs`.
   An empty register is a delivery note *and* the closing ask (see SKILL.md §6).
9. **`timeline-for-project {projectID}`** — paginate on `cursor`; load
   pages with `load_timeline()`. `timeline.activities[]`: `id`, `name`, `startDate`, `endDate`,
   `milestoneID` (non-null ⇒ milestone), `itemCount`. Single-day ⇒ event;
   ranged ⇒ phase/task. Check `has_future_activities(activities, as_of)`:
   False means the Timeline panel becomes Recent Activity and the closing
   ask includes timeline activities.
10. **`list-user-reports {projectID}`** → saved reports with `url` and
   `reportType` (`USER_REPORT_MSR`, `USER_REPORT_VARIANCE`,
   `USER_REPORT_ITEMS_LIST`). Link a section to a saved report when it shows
   the same view.
11. **`categorizations-for-project {projectID}`** → the schemes on the
    project. `pick_breakdown_axis()` looks here for a location /
    programmatic-area categorization; `pick_area_axis()` for an
    organizational one (PIT, TVD Cluster, Location, Building, Increment …).
12. **`get-item-history {projectID, since}`** — the project-wide edit log,
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
`033000`) and, for custom axes, by the set of values seen on item rows for
that categorization (`categorization_values(items, "Location")` — the
items-for-project rows carry categorization names, as do get-item results).
Estimate lines carrying a value no item carries land in "Unassigned"; if
that is more than a sliver, list the values with `distinct_categories()` and
pass the full set to `by_custom()`.

## Join URL patterns

`join_urls(project_id)`: project `https://app.join.build/{projectID}`; items
`…/items`, item `…/items/{itemID}`; risks `…/risks`, risk `…/risks/{riskID}`;
milestones `…/milestones`, milestone `…/milestones/{milestoneID}`; timeline
`…/timeline`. Saved reports: the `url` field from `list-user-reports`.

## Also available

`get-contingency-report {projectID}` returns, per milestone, each
contingency and allowance's `starting`, `pending`, `accepted`, `remaining`
and the item `draws` against it (decimal strings), when the user's role may
see markups. The A3 has no default panel for it, but if the reader asks
about contingency, a Contingency row set (name · starting · remaining) fits
the Cost breakdown panel's style; label it with the project's words.

## Not available from the connector

GSF / unit quantities (other than the project record's `milestoneGSF`),
change orders, schedule baselines, company names (only assignee emails),
photos. Sections needing these take user-supplied input or are left out.
