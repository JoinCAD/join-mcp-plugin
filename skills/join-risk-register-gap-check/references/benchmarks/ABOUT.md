# About the theme-mix tables

Each file is one theme mix: `all-join-projects.txt`, plus one per sector that has its own mix. A row is a theme and the share of a well-populated register's risks that typically fall in it. `scripts/gapcheck.py` multiplies these shares by the target register size (50, or the project's own count if larger) to get a per-theme target.

The shares are aggregate figures from anonymized Join risk registers. The files contain no customer, project or risk text. When the mix was built:
- test projects, template or checklist rows, value-engineering alternates and unclassifiable entries were excluded;
- each remaining risk was given one of the 20 themes in `../themes.md`;
- a sector got its own table only where no single company's data could be identified, and otherwise uses the all-projects mix.

To refresh, rebuild the shares from a newer register export the same way. Keep the file format and the theme names unchanged, and check that `gapcheck.py` still runs against each file.
