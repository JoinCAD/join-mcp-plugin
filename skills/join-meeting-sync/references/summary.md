# Meeting summary

A draft the user sends to the meeting's attendees. It states what was decided
and what Join records, and flags every place they differ. Facts only: no
assessment of any decision, no recommendations, no next steps beyond the
actions stated in the meeting.

## Rules

- Every item links to its Join page; the header links the project.
- Each change says who made it and when: "this sync" for the session's own
  writes, otherwise the editor's name and time from the edit log.
- **Differs from what was said** comes first after the header whenever it
  has entries, each marked ⚠ with both sides quoted and how it was left.
- Quotes are short and attributed (speaker, transcript offset).
- Times in the meeting's time zone. Join's status names, and the project's
  labels for cost concepts (`terms.json`): its Budget may be "Target Value".
- Leave out empty sections, and the Minutes link when there is none.
  Changes not applied (declined, failed, or an unattended run) say so.

## Template

```markdown
# <Meeting title> — decisions and Join updates

[<Project>](<project url>) · <date>, <start>–<end> <tz> · [Minutes](<minutes link>) · Join checked <date time tz>
Attendees: <names as in the transcript>

## ⚠ Differs from what was said
- **[#14 Roof drain upgrade](<url>)** — Meeting: "We're rejecting 14" (Ana Ruiz, 0:41:10).
  Join: Accepted (Ben Harris, 30 Sep 16:02). Left as Accepted.

## Decisions and actions
| Item | Said in the meeting | Join now | Change |
|---|---|---|---|
| [#8 Evaluate external shading](<url>) | Accept option 8.3 (Mia Polk, 0:00:14) | Accepted, option 8.3 | Status, by this sync; comment with minutes link added |
| [#8 Evaluate external shading](<url>) | Ben Harris to issue revised drawings by 14 Oct | Due Date 14 Oct 2026 | Due Date, by Ben Harris 30 Sep 15:10 |
| [#2 ADA facilities](<url>) | Reject (Ben Harris, 0:07:30) | Rejected | Already recorded |

## Still to do in Join
- [#8 item estimate](<url>/estimate): Cost Impact for option 8.3, +$12,400 per Ben Harris (0:22:40).

## Discussed, no decision
- [#5 Lobby finishes](<url>): pricing requested from the GC (Ana Ruiz, 0:30:05).

## Changed in Join since the meeting, not discussed
- [#1 Alternate Curtain Wall Design](<url>): Cost Impact $0 → −$41,966 (John Join, 30 Sep 19:32).

## Not matched to a Join item
- "Add a roof hatch at stair 2" (Ana Ruiz, 0:52:10): created as draft item [Roof hatch at stair 2](<url>).
```
