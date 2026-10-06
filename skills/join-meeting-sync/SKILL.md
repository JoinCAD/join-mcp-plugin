---
name: join-meeting-sync
description: Reconcile a meeting transcript or minutes (Teams, Zoom, Google Meet, Otter, or typed notes) with a Join construction project. Finds the project, reads item history from the meeting's start until now, matches each decision and action to Join items, asks the user about every difference between what was said and what Join records, applies only confirmed changes (status, chosen option, assignee, due date, milestone, name, description) with the meeting's context as item comments, links to the Join page for anything the connector can't change, and drafts a summary of decisions and changes that flags where Join differs from what was said. Use it whenever someone shares a transcript, minutes or action items from an OAC, design, owner or cost meeting and wants Join checked, updated or summarized against it — "update Join from this meeting", "did we capture today's OAC decisions", "sync the minutes with Join" — even if they don't say "sync".
---

# Join meeting sync

A meeting decides things; Join records them. This skill compares the two:
what was said, what Join holds now, and what changed in Join since the
meeting started. It asks the user about every difference and writes only
what the user confirms. The user decides; the skill reports.

Tools are named by their bare Join MCP names (`get-item-history`, …); match
on the suffix whatever prefix your client adds. `references/join-connector.md`
has each tool's fields, what the connector can and can't change, side
effects, and Join URLs. `references/summary.md` has the summary template.

## Rules

- **Report, don't judge.** Restate what was said and what Join records. No
  opinion on any decision, no recommendations, no "this pushes the project
  over budget" — in chat, in comments, or in the summary.
- **Explicit decisions only.** A decision is something stated as decided
  ("accept 8.3", "we're rejecting #2", "Ben owns it, due the 14th").
  Proposals, "let's price it" and "we'll think about it" are discussion:
  report them, change nothing. Unsure whether it was decided → ask.
- **Nothing written without a yes.** Every update, comment, new item and new
  risk is shown verbatim and confirmed before the first write. A
  confirmation covers that list only.
- **Never overwrite a later change silently.** If Join was changed after the
  meeting started to something other than what was said, that is a
  difference to ask about.
- **Join's words.** Item, Option, Status (Pending, Accepted, Rejected,
  Incorporated, Not Applicable, Not Chosen), Assignee, Due Date, Milestone,
  Cost Impact, Schedule Impact, Timeline, Risk. Item numbers as Join shows
  them (#8, #8.3).
- **The project's words for cost concepts.** A project can rename Estimate,
  Budget, Delta, Running Total, Gap, Direct Costs, Markups, Cost of
  Construction, Project Total and Project Running Total, and Join shows its
  labels everywhere. Use them in chat, comments and the summary (from
  `work/terms.json`, step 2): a team whose Join says "Target Value" should
  not read "Budget". The tools' field names stay the defaults.
- **Link every item** you name, in chat and in the summary.
- **Unattended** (no one to answer): do steps 1–5 and 9 only. Write nothing
  to Join; the summary lists the proposed changes as not applied.

## Workflow

1. Read the meeting.
2. Find the project; fix the window.
3. Pull Join state.
4. Extract decisions; match them to items.
5. Compare and classify.
6. Ask about differences.
7. Confirm the change plan, then apply.
8. Hand over what the connector can't do.
9. Draft the summary.

Work in a directory with a `work/` folder and run the scripts from there.
Save tool results to JSON files in `work/`. When the client spills a large
result to a file, copy that file. When you write one out yourself, you may
drop fields the scripts don't read (an item needs `id`, `number`, `name`,
`status`, `visibility`, `assignee`, `dueDate`, `cost`, `currentMilestone`,
`options`, `parentID`, `url`; keep history events whole).

### 1. Read the meeting

Files (`.vtt`, `.srt`, `.docx`, `.txt`, `.md`) go through:

```bash
python <skill>/scripts/transcript.py meeting.vtt --out work/transcript.txt
```

It merges cue fragments into speaker turns (`[0:12:03] Ana Ruiz: …`),
writes "Ruiz, Ana" as "Ana Ruiz", lists speakers by words spoken, and
repeats the title, date and duration lines it finds (Teams, Meet and Otter
headers, WebVTT NOTE lines). Re-run with `--start 2026-09-30T09:00-04:00`
once the start is known: turns get wall-clock times and the header prints
the start in UTC. Minutes and notes pass through unchanged. Pasted text
needs no script.

Note the title, date, start time and time zone, attendees, project names or
addresses, and every item number or name mentioned. Spoken numbers arrive
as words ("item eight", "eight point three"). A cost concept may be said in
the project's label ("Target Value") or the default ("budget"); both mean
the same concept.

### 2. Project and window

- **Project.** `search-projects` with the names from the title and
  transcript, else `list-my-projects`. More than one plausible match → ask.
  Keep its `id`, `url` and `currency`.
- **Terms.** `terminology-for-project {projectID}` → `work/terms.json`,
  before you describe the project to the user, so you use its words from
  the start.
- **Start.** From the transcript header, the file name, the invite, or the
  user. Most VTT and SRT files carry offsets only. Time zone: as written,
  else ask.
- **Minutes link.** Ask for a link to the shared meeting minutes (Teams,
  SharePoint, OneDrive, Google Docs, Confluence, …). It's optional: with none,
  skip everything below that uses it.
- Confirm the project and start, and ask for the link, in one question
  ("Ivy State University; OAC #9 started 30 Sep 2026 09:00 EDT? Is there a
  link to the shared minutes?"). If the start time is unknown, use the start
  of the meeting date in the user's time zone and say so in the summary.

The window is meeting start → now.

### 3. Pull Join state

Note the time first (`date -u +%FT%TZ`); step 7 pulls again from it.

1. `get-item-history {projectID, since: <start in UTC>}`, every page: follow
   `cursor` until it is absent, also when `stoppedEarly` is true →
   `work/history-1.json…`. This project-wide log says which items changed;
   it is not the record of how (step 4).
2. `items-for-project {projectID, milestone: "all", includeDrafts: true,
   filters: {updatedAfter: <start>}}`, every page →
   `work/items-updated-1.json…`: each item edited since the meeting started.
3. `items-for-project {projectID, milestone: "all", includeDrafts: true,
   filters: {numbers: [<each number mentioned>]}}` →
   `work/items-mentioned.json`. A number brings its item's options too.
4. `milestones-for-project {projectID}` → `work/milestones.json`;
   `current-user` → the account name writes are made as.
5. Digest:

   ```bash
   python <skill>/scripts/history_digest.py --since <start in UTC> \
     --history 'work/history-*.json' --item-history 'work/item-history-*.json' \
     --items 'work/items-*.json' --milestones work/milestones.json \
     --tz <meeting's time zone> --me "<current-user name>" \
     --currency <project's currency> --terms work/terms.json \
     --index work/items.md > work/digest.md
   ```

   `digest.md`, per item: its link, its state now, its state at the start
   for the fields edited since, and each edit in the window (when, who,
   what, in Join's labels), and any cost concept the project renames.
   `items.md`: one line per item and option
   (number, name, state, link), for matching. Run it again after step 4's
   per-item pulls.

### 4. Extract and match

Read the transcript once, end to end. Record in `work/decisions.md` each
decision, each action, and each discussion of an item without a decision:

- **said** — a short quote, speaker, timestamp
- **about** — item number, name or keywords
- **change** — status, option chosen, assignee, due date, milestone, name,
  description, number, Cost Impact, Schedule Impact, category, new item,
  risk, other, or none (discussion)
- **value** — Accepted, option 8.3, the assignee, 2026-10-14, 100% CD, …

Status words, when stated as decided about the item as a whole: approved /
accepted → Accepted; rejected / declined / "not doing it" → Rejected; "no
longer applies" / superseded → Not Applicable; "it's in the estimate" →
Incorporated; reopened → Pending. Choosing an option is accepting that
option. Choosing one side of an item without options ("go with triple" on
"Double vs triple glazing") is not a status: Unclear. Resolve relative
dates against the meeting date; when the words and the value disagree
("push it to the 30th" when the 30th is earlier), Unclear.

Match items, only on a clear fit:

1. Item number → `items.md`. Numbers are not unique (an item and an option
   can share one; check the "option of" mark and the name). More than one
   fit → Unclear.
2. Name → `items-for-project {filters: {nameContains: "<word>"}}`, then
   `search-items {query: "<one or two words>", filters: {projectNames:
   [<project>]}}` (it needs every word to match, and also searches
   descriptions and categories). Save each `items-for-project` result you
   use as `work/items-found-N.json`; fetch a `search-items` hit that way too
   (`filters: {numbers}`), since search results' item type and cost can
   differ from the item list.

Several candidates or a loose fit → Unclear. People: speakers are display
names; `update-item` takes a collaborator's email. Find it on items'
assignees and creators, in the history's users, or with
`collaborators-for-project` where the connector has it. Never guess an
email.

For each matched item, and each item in `digest.md` (all of them up to
about 15, else the matched ones):

- `get-item-history {itemID}` without `since`, paging until the oldest edit
  is before the start → `work/item-history-<number>.json`. Each item's own
  log is the record: the project-wide log reports every cost before a change
  as $0 and can list cost edits the item's log doesn't have.
- For matched items: `get-item` (description, options with IDs and statuses,
  Schedule Impact, categories) and `comments-for-item` (is the meeting
  already noted?).

Then re-run the digest.

### 5. Compare and classify

Compare each row with the item's state at the start, its edits in the
window, and its state now:

| Class | When | Then |
|---|---|---|
| Recorded | Join already shows it. | Summary only. |
| To update | Join doesn't show it; the connector can change it. | Change plan (7). |
| Differs | Join changed in the window to something other than what was said, or the meeting called something done that Join didn't show at the start. | Ask (6). |
| Manual | Join doesn't show it; the connector can't change it. | Hand over (8). |
| Unclear | Ambiguous item, decision, value or person. | Ask (6). |
| Not found | A decision or action with no item. | Ask (6): new draft item, an existing item, or leave out. |
| Discussed | No decision. Any actions said ("I'll ask the GC for pricing") go with it. | Summary only. |

Also list **changed in Join, not discussed**: items edited in the window
that no row refers to. Report them; act on none. Edits marked "(your
account)" are real edits: a shared login can't say by whom. Only the writes
made in step 7 are this sync's.

The connector changes Status, Name, Description, Number, Due Date, Assignee
and Milestone (`update-item`), adds comments, creates draft items and risks.
Cost Impact, Schedule Impact, categories, options, publishing drafts,
timeline links, attachments and risk edits are Manual
(`references/join-connector.md`).

### 6. Ask about differences

Use `AskUserQuestion` when available (up to four questions per call; batch
them), otherwise numbered questions in one message. One question per
Differs, Unclear or Not found row, each readable on its own:

> **[#14 Roof drain upgrade](…)** — Meeting: "We're rejecting 14" (Ana Ruiz,
> 0:41:10). Join: Accepted, set by Ben Harris 30 Sep 16:02. Which should
> Join show?
> - Leave Join as Accepted
> - Change Join to Rejected
> - Leave Join; flag the difference in the summary

For a Manual field, the middle option is "Change it in the app" (step 8).
The answer sets the row's class. Don't argue with it or weigh in.

### 7. Confirm, then apply

Before asking, pull `get-item-history {projectID}` again since the time
noted in step 3; a new edit on a planned item sends that row back to step 6.

Show the whole plan in one message:

1. A table: item (link), field, now → new, the meeting quote.
2. Each comment, verbatim.
3. With a minutes link: the offer to add it to every other item the meeting
   discussed (Recorded, Discussed, Manual, or left as is after step 6), as a
   short comment, with the count and the text. Comments on updated items
   already carry it.
4. New items and risks, verbatim.
5. The side effects that apply: assigning emails the assignee; accepting an
   option makes the item Accepted and its other Pending options Not Chosen;
   a milestone move drops the item from meetings in the old milestone; new
   items are private drafts until published in Join; comments are visible to
   everyone with access to the item and can't be edited or deleted from here;
   everyone on the item sees the minutes link, but only people with access to
   the document can open it.

Ask: apply all, choose, or none, and separately whether to add the minutes
link to the other items. Then apply exactly what was confirmed:

1. `update-item` once per item, all its fields together. Check `updated`
   lists the fields you sent; an empty list means Join already had them.
   On an error, stop: report the fields the error says were written and
   ask before going on.
2. `add-comment-to-item` on each updated item, after its update succeeds.
   Comment on the parent item for an option decision.
3. `create-item` and `create-risk`, then `update-item` on a new item for
   its number, assignee or due date.
4. If accepted, the minutes-link comment on each other discussed item.

**Comments** carry only what the meeting said about that item:

```
OAC #9, 30 Sep 2026 — Mia Polk (09:08): "Owner wants option three, the full coverage. So accept eight point three."
Also said: Ben Harris (09:08), revised cost for option 8.3 to go into the estimate.
Updated in Join from the meeting: option 8.3 Accepted.
Minutes: https://contoso.sharepoint.com/…/OAC-9-minutes.docx
```

The minutes-link comment on an item the sync doesn't update:

```
Discussed at OAC #9, 30 Sep 2026. Minutes: https://contoso.sharepoint.com/…/OAC-9-minutes.docx
```

Plain text (the connector posts it as typed); Join makes the URL clickable,
so give it in full, as the user gave it, on its own after "Minutes:". Short
quotes, attributed, with the meeting's clock time when known. No opinions. Nothing about other items
or people, no side remarks: every company on the project can read it. A
remark the user chose to flag only in the summary stays out of comments.
Skip the comment when the item's comments since the meeting already record
it, and the link when they already carry it. Items the sync doesn't update
get only the minutes-link comment, and only if the user accepts the offer.

### 8. Hand over what the connector can't do

For each Manual row and any write that failed, say exactly what to change
and link the page, using the option's own ID for an option (URLs in
`references/join-connector.md`):

> [#8.3 item estimate](https://app.join.build/{projectID}/items/{optionID}/estimate)
> — Cost Impact for option 8.3: +$12,400 per Ben Harris (0:08:41). Join
> shows +$71,295.

### 9. Draft the summary

Follow `references/summary.md`: **differences from what was said**
(flagged, first), decisions and actions with Join's state and who changed
it, what is left to do in Join, discussed without a decision, changed in
Join but not discussed, and not matched. Facts only, every item linked, who
and when for every change.

Give it in chat as Markdown, ready to paste into an email or Teams. Write it
to `meeting-sync-<meeting date>.md` when the user asks or a folder of theirs
is connected.

## Files

- `scripts/transcript.py` — VTT, SRT, DOCX, TXT or MD → speaker turns with offsets and wall-clock times; header facts; minutes pass through.
- `scripts/history_digest.py` — project-wide and per-item `get-item-history` pages + `items-for-project` pages → per item: state now, state at the start, edits in the window; `--index` writes a one-line-per-item index for matching.
- `references/join-connector.md` — tools, fields, units, edit-log caveats, status rules, side effects, what is Manual, Join URLs.
- `references/summary.md` — summary template and rules.
