# Join connector reference for meeting sync

Bare tool names; your client adds a prefix. A cost is either `{value}` or a
range `{min, max}`, as a string in one of two units:

- `items-for-project` and the other list tools: whole units of the project's
  currency, two decimals (`"-86366.80"`). The currency is `currency` on the
  project record.
- `get-item-history` (`oldCost`, `newCost`): hundredths (`"-8636680"` is the
  same −86,366.80).

A decimal point means whole units; `history_digest.py` reads both.

## Reads

| Tool | Use | Notes |
|---|---|---|
| `search-projects {query}` / `list-my-projects` | Find the project. | Paginated on `cursor`. Each project has a `url`. |
| `get-item-history {projectID, since}` | Which items changed in the window. | Newest first, 25 per page. Follow `cursor` until absent, even when `stoppedEarly` is true. `since` is inclusive; pass an instant with a time and offset. |
| `get-item-history {itemID}` | The record of one item's edits, and its state at the start. | Newest first, 25 per page. Without `since` it reaches back before the window. |
| `items-for-project {projectID, milestone: "all", includeDrafts: true, filters}` | Item state now; resolve history `itemID`s. | `filters`: `updatedAfter` (edited since; comments count), `numbers` (with their options), `nameContains`, `statuses`, `assignees`. 50 per page; repeat the same arguments with each `cursor`. Options are rows with `parentID`. Each row has `url`. Rows carry every category, so an unfiltered page of a large project can exceed 100K characters. |
| `search-items {query, filters: {projectNames}}` | Find items by number, name, description, categories. | Every word must match: search one or two distinctive words. Item type and cost can differ from `items-for-project`; take state from there. |
| `get-item {itemID}` | Full detail of a matched item. | Description, options (id, number, name, status), `scheduleImpact`, categories, `activityIDs`, assignee, due date. No cost: use `items-for-project`. |
| `comments-for-item {itemID}` | Is the meeting already noted? | Oldest first, paginated. |
| `milestones-for-project {projectID}` | Milestone names and IDs for moves. | |
| `risks-for-project {projectID, riskType}` | Risks named in the meeting. | `PROJECT` and `COMPANY` are separate registers. |
| `collaborators-for-project {projectID}` | Assignee emails. | Not on every connector version. |
| `terminology-for-project {projectID}` | The project's labels for cost concepts. | `{"terms": {ESTIMATE, TARGET, DELTA, RUNNING_TOTAL, GAP, DIRECT_COST, MARKUP, COST_OF_CONSTRUCTION, PROJECT_TOTAL, PROJECT_RUNNING_TOTAL}}`; defaults Estimate, Budget, Delta, Running Total, Gap, Direct Costs, Markups, Cost of Construction, Project Total, Project Running Total. Item fields (Status, Cost Impact, …) aren't renamable. Other tools keep the default names in fields and descriptions. |
| `current-user` | The account name writes are attributed to. | Name only. |

### Reading the edit log

- An edit names its item by `itemID` only.
- `eventTypes` can list several kinds on one edit. `eventContent` fields are
  null unless their kind is listed; `oldCost` and `newCost` are cost objects
  (`{"value": "0"}`) on every edit.
- **The project-wide log is not the record.** It reports `oldCost` as
  `{"value": "0"}` on every cost edit, can list cost edits that the item's
  own log doesn't have, and can give the same edit a different `id`. Use it to
  find items; use each item's log for what changed and what it was before.
- `CHANGE_STATUS` carries the new status only; the status before is the
  previous `CHANGE_STATUS` in the item's log.
- `ADD_COMMENT` carries no text: read it with `comments-for-item`.
- Edits are attributed to an account, and `current-user` gives only its
  name. Edits by that account before this session are real edits (possibly
  by someone else on a shared login): report them like anyone else's. The
  sync's own writes are the ones its `update-item` and `add-comment-to-item`
  results confirm.

## Writes

### `update-item {projectID, itemID, …}`

Sets `status`, `name`, `description` (plain text), `number`, `dueDate`
(`YYYY-MM-DD`), `assigneeEmail`, `milestoneID`; clears with `clearAssignee`,
`clearDueDate`, `clearDescription`, `clearNumber`. Writes only fields that
differ and returns `updated` (what it wrote) and the stored item. A failed
call can leave earlier fields written; the error names them.

Status rules:

- Item without options: any status.
- Item with options: between Pending, Rejected and Not Applicable, or between
  Accepted and Incorporated. To accept it, set the chosen **option** to
  Accepted: the item becomes Accepted and its other Pending options Not
  Chosen. Setting the accepted option back to Pending returns the item and
  its other options to Pending.
- Not Chosen applies only to an option whose item is Accepted or
  Incorporated.

Side effects:

- `assigneeEmail` must belong to a project collaborator, or nothing is
  written. Assigning emails the assignee.
- A milestone move removes the item and its options from meetings in the old
  milestone. Options move only with their item.
- Writes can notify project collaborators.

### `add-comment-to-item {projectID, itemID, comment}`

Plain text, attributed to the current user, visible to everyone with access
to the item. Join shows URLs in it as links. No mentions. Can't be edited or deleted through the connector.

### `create-item {projectID, name, description, milestoneID?}`

Creates a private draft in the active milestone (or `milestoneID`), visible
only to the user until published in Join. Number, assignee and due date
follow with `update-item`.

### `create-risk {projectID, name, description, impact, likelihood}`

Impact and Likelihood 1–5. Visible to the project team at once. Cost
Impact, assignee and response plan are set in the app.

## Manual: changes made in the app

| Change | Page |
|---|---|
| Cost Impact, item estimate, cost range | `https://app.join.build/{projectID}/items/{itemID}/estimate` |
| Schedule Impact, categories | `…/items/{itemID}` |
| Create, attach or detach options | `…/items/{itemID}` |
| Publish or share a draft item | `…/items/{itemID}` |
| Link an item to a timeline event or meeting | `…/items/{itemID}` |
| Attachments; edit or delete a comment | `…/items/{itemID}` |
| Risk status, Likelihood, Impact, Cost Impact, response plan, assignee | `…/risks/{riskID}` |
| Add a collaborator (before assigning them) | `…/team/teammates` |
| Timeline events, phases, dates | `…/timeline` |
| Milestones | `…/milestones` |

## Join URLs

Project `https://app.join.build/{projectID}` · items `…/items` · item or
option `…/items/{itemID}` · item estimate `…/items/{itemID}/estimate` ·
item activity `…/items/item-activity` · risks `…/risks` · risk
`…/risks/{riskID}` · milestone `…/milestones/{milestoneID}` · timeline
`…/timeline` · team `…/team/teammates`. Items-list rows carry their own
`url`.
