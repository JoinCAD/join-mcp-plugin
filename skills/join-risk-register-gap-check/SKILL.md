---
name: join-risk-register-gap-check
description: Check a Join project's risk register for gaps. Classifies every risk into 20 standard construction risk themes, compares the register with a well-populated one (50+ risks in the typical theme mix for the project's sector), flags themes that are missing or light, proposes three simple starter risks for each and offers to add them to the project in Join. Use it whenever someone asks whether a Join risk register or risk log is complete, what risks a project might be missing, or wants suggested risks to add to a Join project, even if they don't say "gap" or "benchmark".
---

# Join risk register gap check

This skill helps a project team see what its Join risk register is missing. The yardstick is a **well-populated register**, one that tracks 50 or more risks spread across the themes that matter for this kind of project. Every project is best served by a register like that. A register with 20 risks is still missing around 30, and a project with no risks tracked is missing dozens. The output is a short gap check and a set of concrete starter risks the team can add with one confirmation.

`references/themes.md` holds the 20 themes, the two excluded categories and the tie-breakers; read it before classifying. `references/starter-risks.md` is the library of starter risks. `references/benchmarks/` holds the theme-mix tables, and `scripts/gapcheck.py` does the arithmetic, so results are consistent from run to run.

## Step 1: Get the project from Join

This skill works through the Join connector. If its tools aren't available, or they ask for authorization, tell the user the Join connector needs to be connected or re-authorized in their connector settings, and stop there. Don't attempt the analysis from memory or ask for a file instead.

1. **Find the project.** Use `search-projects` with the name the user gave, or `list-my-projects` if they didn't name one (follow the `cursor` for more pages). If more than one project plausibly matches, ask which one. Each project record carries an `id` (needed by every other call) and a `type`.
2. **Pull the shared register.** Call `risks-for-project` with `riskType: "PROJECT"` and follow the `cursor` until you have every risk. This is the project's shared register, and it's where `create-risk` adds new risks. Join also has a `COMPANY` register that only the user's own company can see. Leave it out unless the user asks for it; if they do, read it with a second call and count it alongside.
3. **Get descriptions only where you need them.** The list returns names, numbers, status and scores, but no descriptions. Most risk names are descriptive enough to classify, so start from the names. Call `get-risk` only for the ones you can't place confidently, such as a one-word name like "Schedule" or a name that could fit two themes. Each call is a separate round trip, so a handful is normal and fetching the whole register is wasteful.
4. **Count every risk, whatever its status.** A closed or retired risk still shows the team considered that theme. If some are closed, mention how many in the report.

An empty register is common, and it's a valid starting point. Run the check as normal; the whole well-populated register is the gap.

## Step 2: Classify each risk

Assign every risk one theme from `references/themes.md`, by root cause rather than incidental keywords. Classification is the step that most affects the result. An earlier keyword-based approach was wrong about 40% of the time ("structural steel lead times" is procurement, not structure), so read each risk and decide what it is really about.

VE alternates, placeholders and pre-bid checklist questions go under the two excluded labels in `themes.md`. They aren't project risks, so they don't count toward the register.

Save the result as `classified.json` in a scratch folder. For an empty register that's just `[]`.

```json
[{"id": "…", "name": "Switchgear lead time", "theme": "Procurement & Long-Lead"}, …]
```

For registers with more than ~150 risks, classify in batches and append to the file. The whole register still needs to be classified.

## Step 3: Pick the theme mix and run the comparison

**Choose the mix table.** `references/benchmarks/` has six tables. Each gives the share of a well-populated register's risks that typically fall in each theme. Five sectors have their own mix; everything else uses **All Join projects**. Match on the Join `type`, using the project name when the type is too broad to tell:

| Mix file | Typical Join types |
|---|---|
| `healthcare.txt` | Healthcare, Hospital, Medical Office Building, Mental Health, Senior Living, Non-Acute Care |
| `higher-education.txt` | Higher Education, College, University, Community College, Student Housing |
| `industrial-manufacturing.txt` | Industrial, Manufacturing, Warehouse, Distribution, Consumer Products, Food & Beverage |
| `sports-arts-entertainment.txt` | Entertainment, Stadium, Sports, Athletic, Theater, Museum, Arts & Cultural |
| `commercial-office.txt` | Commercial and Retail, Office, Tenant Improvement, Retail, Core and Shell, Interiors |
| `all-join-projects.txt` | Everything else, including K-12, labs and life sciences, data centers, energy, water, transportation, hotels, residential and mixed use, government and civic, "Other" |

Some Join types are too broad to say much. "Education" could be a school or a university, and "Other", "Unassigned" or a blank type say nothing. In those cases look at the project name and description. "Lincoln Elementary" is K-12 and uses All Join projects; "State University Science Hall" is Higher Education. If you can't tell, ask the user what kind of building it is.

**Run it:**

```bash
python <skill>/scripts/gapcheck.py <skill>/references/benchmarks/<file> classified.json
```

The JSON it prints contains:
- `counted` and `not_counted`: the risks that count toward the register, and the excluded rows.
- `target_size` (50) and `short_by`: how many risks the register is short of a well-populated one.
- `table`: for every theme, this project's count and `target`, the number of risks a well-populated register would have in that theme. Targets scale with the register, so a register already past 50 is compared with its own size.
- `flags`: up to five themes, furthest short first. A theme is flagged when it's at least 1.5 risks short of its target: `missing` if none are logged, `light` if some are. Each flag comes with a plain-language reason.

Don't add flags of your own on top of the script's. Five well-chosen themes are a better starting point than a long list.

## Step 4: Sanity-check the flags

The script knows the typical mix, not the project. Before presenting, read each flag against what you know about the project from its name, type, description and existing risks:
- **Drop flags that clearly don't apply, and say so in one line.** Examples: Existing Conditions & Renovation on a project that is plainly ground-up new construction, or Seismic & Structural for a pure interior fit-out. With an empty register there's little to go on, so keep the flags unless the project name or type rules one out.
- **Drop flags covered under another theme.** If an existing risk arguably covers the theme even though you classified it elsewhere (a tie-breaker case), mention that rather than proposing more.

## Step 5: Propose three starter risks per flagged theme

For each remaining flag, choose three risks from `references/starter-risks.md` that fit the project and don't duplicate anything already on the register. You may adjust a word or two so they read naturally for the project type. Keep them generic and simple. Don't copy or paraphrase the project's own risks, and don't invent project-specific details such as costs, dates, names or quantities. The team should be able to adopt each one in seconds and then make it their own.

## Step 6: Report

Keep the report short and skimmable; the team will act on it, not study it. Use this structure:

```
## Risk register check: <Project name>

**Compared with:** a well-populated <sector> risk register — 50+ risks in the typical <sector> theme mix
[For All Join projects: "a well-populated risk register — 50+ risks in the typical theme mix across Join projects"]

**Register size:** <n> risks [<k> VE alternates / placeholders not counted] [<c> closed, still counted]. → <verdict>

**Where this register stands**
| Theme | This project | Well-populated register |
|---|---|---|
<the ~8 themes at the top of `table`, plus any flagged theme; show targets as whole numbers ("~7"), or "<1" below one>

**Themes that look light**
### <Theme> — <reason from the script>
1. **<Risk name>**: <description>
2. ...
3. ...
[repeat per flag]

[If you dropped any flags in Step 4, one line saying which and why.]

Want me to add these to <Project name> in Join? I'd add them at impact 3 / likelihood 3, a neutral starting score the team can adjust. They'll be visible to everyone on the project. I can add all <X>, or just the ones you pick.
```

Write the verdict from `short_by`:
- **No risks:** "No risks are tracked yet. A well-populated register tracks 50 or more, so this project is missing dozens."
- **Short of 50:** "A well-populated register tracks 50 or more, so this one is likely missing about <short_by>."
- **50 or more:** "Well populated."

When the register is short of 50, lead with that; it's the biggest gap, and the flagged themes show where to start filling it.

Two rules about how to talk about the comparison:
- **The only yardstick is a well-populated 50+ risk register.** Don't describe registers as small, large, typical or established, and don't compare the project with how many risks other projects log.
- **Say nothing about the data behind the mix tables.** Don't give the number of projects, companies or risks they came from. Never present a figure as if it came from a specific company or project. "The typical healthcare mix on Join" is the right level of detail.

## Step 7: Create the risks the user approves

Adding risks changes a shared project record that everyone on the project sees. So create them only after the user says yes, or if their original request already explicitly asked you to add the suggestions. Then:
- Call `create-risk` once per approved risk, with `projectID`, `name`, `description`, `impact` and `likelihood`.
- Join requires both scores. Use **impact 3 and likelihood 3** unless the user gave other values. Three is a neutral placeholder rather than a judgment about this project. Always tell the user which scores you used, so nobody mistakes a placeholder for an assessment. This holds even when they pre-approved the additions and never saw the offer.
- Afterwards, list what was created. If any call failed, list those and why.

If the user asks why a theme was or wasn't flagged, the script's `table` has each theme's count and target to explain it plainly.
