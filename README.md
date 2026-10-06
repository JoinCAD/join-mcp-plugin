# Join plugin

[Join](https://join.build) aligns owners, design teams, and contractors within
a unified system of record for preconstruction and the design phase. By
integrating real-time cost and schedule data with design evolution, Join
provides the decision intelligence necessary to manage risk on complex projects
and ensure predictable project delivery at scale.

This plugin connects Claude and Codex to your project- and company-level Join
data, produces custom reports from it, and checks it against what was decided
in your meetings. It bundles two things:

- **The Join MCP server** (`https://api.join.build/mcp/join`). It lets the
  agent read and update the Join data your account can access: projects,
  milestones, cost totals and reports, items and options, risks, comments,
  item history, images and assets.
- **Skills** that teach the agent Join-specific workflows on top of those
  tools.

## Skills

| Skill | What it does |
|---|---|
| [`join-a3-report`](skills/join-a3-report/SKILL.md) | Builds a one-page A3 executive snapshot of a Join project: an HTML report styled like the Join app that prints to a single A3 PDF, with links back into Join. |
| [`join-risk-contingency-report`](skills/join-risk-contingency-report/SKILL.md) | Builds a Risk & Contingency Analysis of a Join project, answering "is the contingency we carry enough?": documented assumptions, a Cost Risk Calculator waterfall, a Monte Carlo range of outcomes, and an appendix of open risks. Prints to a Letter-landscape PDF. |
| [`join-risk-register-gap-check`](skills/join-risk-register-gap-check/SKILL.md) | Checks a Join project's risk register for gaps: classifies each risk into 20 construction risk themes, compares the register with a well-populated one (50+ risks in the typical theme mix for its sector), flags themes that are missing or light, and offers to add three simple starter risks for each. |
| [`join-meeting-sync`](skills/join-meeting-sync/SKILL.md) | Reconciles a meeting transcript or minutes (Teams, Zoom, Meet, Otter, notes) with a Join project: matches decisions to items, compares them with item history since the meeting started, asks about every difference, applies only confirmed updates with the meeting's context as comments, links to Join for changes it can't make, and drafts a summary that flags where Join differs from what was said. |

## Install

### Claude Code

```bash
claude plugin marketplace add JoinCAD/join-mcp-plugin
```

```bash
claude plugin install join@join
```

Then run `/mcp` and sign in to the `join` server when prompted.

### OpenAI Codex

```bash
codex plugin marketplace add JoinCAD/join-mcp-plugin
```

Then install the `join` plugin from the Codex plugin browser and sign in to
Join when prompted.

## Data and network use

- **Join MCP server.** All Join data is read from and written to
  `https://api.join.build/mcp/join`. You sign in with your own Join account
  through OAuth, and the server only returns what that account can see. The
  plugin stores no credentials; your client keeps the OAuth token. Write
  tools (creating or updating items and risks, adding comments) change data
  in Join and run only when you or the agent call them.
- **Skill scripts** in `skills/*/scripts/` are plain Python that run on your
  machine. They read the tool results the agent saved locally (and, for
  `join-meeting-sync`, the transcript file you give it) and write local
  files, such as `report.html` and `report.pdf`. The Python itself
  makes no network requests. `check_fit.py` and `render_pdf.py` render PDFs
  with Playwright's headless Chromium, which fetches the report font (see
  below); if Chromium isn't installed, the agent may ask to run
  `pip install playwright && playwright install chromium`, which downloads
  from PyPI and Playwright's CDN.
- **Fonts.** Reports are set in Red Hat Text (SIL Open Font License), which
  the HTML loads from Google Fonts (`fonts.googleapis.com` and
  `fonts.gstatic.com`) whenever a report is opened or rendered to PDF. That
  request sends Google only the usual browser details, such as IP address
  and user agent, and no Join data. Without network access, reports fall
  back to Helvetica.
- Reports link back to `https://app.join.build`, and nothing is uploaded
  anywhere else.

See Join's [privacy policy](https://join.build/privacy/) and
[terms of use](https://join.build/terms-of-use/).

## Repository layout

```
join-mcp-plugin/
├── .claude-plugin/
│   ├── plugin.json          # Claude plugin manifest
│   └── marketplace.json     # makes this repo its own Claude marketplace
├── .codex-plugin/
│   └── plugin.json          # Codex plugin manifest
├── .agents/plugins/
│   └── marketplace.json     # makes this repo its own Codex marketplace
├── .mcp.json                # Join MCP server (shared by Claude and Codex)
├── assets/                  # plugin icons
├── skills/
│   └── <skill-name>/SKILL.md
├── LICENSE                  # Apache-2.0
└── README.md
```

## Adding a skill

1. Create `skills/<skill-name>/SKILL.md` with `name` and `description`
   front matter. Both plugin manifests pick up everything under `skills/`.
2. Refer to Join tools by their bare names (`project-costs`,
   `items-for-project`, …). Each client adds its own prefix; in Claude Code,
   tools from this plugin are named `mcp__plugin_join_join__<tool>`.
3. Keep every file except images and fonts under 256 KiB, and commit no
   `.DS_Store` or other OS files.
4. Raise `version` in both `.claude-plugin/plugin.json` and
   `.codex-plugin/plugin.json`, then run:

```bash
claude plugin validate .
```

## License

[Apache-2.0](LICENSE)
