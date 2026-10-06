# The model, in one page

The question the report answers: **is the contingency the project carries
enough to cover where the project will land?** "Where it will land" combines
what is known (the Estimate, Accepted Changes, the Running Total) with
assumptions about what is not (which pending items get accepted, which risks
materialise). Everything assumed is written on page 1 so the room can argue
about the assumptions rather than the arithmetic.

## Definitions (whole units of the project's currency)

| Symbol | Meaning |
|---|---|
| RT | Running Total = Estimate + Accepted Changes (Join's number; the project may call these "Baseline Estimate", "Target Value", … — the report uses its labels) |
| K | Contingency held = Σ `remaining` of the contingencies in the active milestone (get-contingency-report: starting less accepted draws); fallback when that report is unavailable: Σ contingency markup lines of the milestone estimate (starting amounts) |
| B | Base Cost = RT − K — the cost if nothing else happens and the remaining contingency is untouched |
| aᵢ | Cost Impact of pending item i (max of a range for adds, min for deducts; midpoint for the expected value), gross of any pending contingency draw |
| pᵢ | probability item i is accepted: `adds_pct` for adds, `deducts_pct` for deducts, 100 / 0 when carried as Accepted / Rejected |
| cⱼ | Cost Impact of open risk j (from Join, set by the user, or assumed from the Impact score) |
| qⱼ | probability risk j occurs: from the Likelihood table of the chosen scenario, or 100 / 0 when carried as Certain / Excluded, or a number the user gives |

The contingency lines are *inside* the Estimate, hence inside RT. The app's
dashboard draws the base bar at RT and stacks contingency on top; this report
backs contingency out instead (B = RT − K) so that the Running Total line is
literally "the point at which contingency is used up". State this on page 1
(the builder does) because someone comparing to the dashboard will notice
the base chip differs by K.

K is the *remaining* balance, not the starting one: an accepted item that
drew on contingency sits in Accepted Changes at its net cost (often zero)
and has already reduced the balance, so RT − remaining is the true
unreserved cost. A pending item that draws on contingency likewise shows a
net Cost Impact in Join; the model carries it gross (net − pending draw) so
that when the simulation accepts it, the outcome moves by what the
contingency would actually pay out. Page 1 lists the starting amount,
accepted draws and pending draws so the arithmetic can be checked against
the Contingency & Allowance Report in Join.

## Waterfall (page 2) — the app's `buildWaterfall`, ported

Bars walk from B: expected adds Σ pᵢ·aᵢ (adds), expected deducts Σ pᵢ·aᵢ
(deducts, negative), expected risks Σ qⱼ·cⱼ. Each bar's hatched extent is the
full amount if everything in it happens (Pending Adds, Pending Deducts, Σ cⱼ).

- **Projected** = B + expected adds + expected deducts + expected risks.
- **vs Running Total** ("headroom") = RT − Projected. Positive: contingency
  left if expectations hold. Negative: shortfall beyond contingency.
- **vs Budget** = Budget − Projected.
- **Full exposure** = B + Pending Adds + Σ cⱼ (every add, every risk, no deducts).
- **Contingency needed to reach Projected** = Projected − B; compared with K
  on page 2: sufficient when ≤ K, otherwise the shortfall (Projected − RT) is
  "more contingency needed".
- **Risk scenarios** (model.json `scenarios`) re-run the walk with the
  Optimistic / Likely / Pessimistic tables. They are for the conversation
  ("how much does the probability table matter?"), not printed on the report.

Likelihood → probability (as in the Join web app's Cost Risk Calculator):

| Likelihood | Optimistic | Likely | Pessimistic |
|---|---|---|---|
| 1 Rare | 5% | 10% | 20% |
| 2 Unlikely | 15% | 30% | 50% |
| 3 Possible | 25% | 50% | 75% |
| 4 Likely | 40% | 70% | 90% |
| 5 Almost Certain | 55% | 90% | 100% |

App defaults: adds 40%, deducts 50%, scenario Likely.

## Monte Carlo (page 3) — occurrence only

`trials` (default 10,000) independent draws. In each: every live pending
item is accepted with probability pᵢ (a range item then draws uniformly
between its min and max, a fixed item takes its Cost Impact); every live risk
occurs with probability qⱼ at cost cⱼ. Outcome = B + Σ accepted + Σ occurred.
Magnitudes do not vary beyond ranges, so the mean outcome equals Projected
(to sampling error) and the distribution shows only *which combinations*
land where. This is deliberate: it keeps page 3 consistent with page 2 and
avoids inventing cost distributions the register does not contain.

Reported: mean, std, min/max, P5…P95, histogram (40 bins, coloured by
whether the bin is within RT), cumulative curve, and

- **P(≤ RT)** — share of trials the contingency held covers;
- **P(≤ Budget)**;
- **P(> B)** = 100 − P(≤ B) — share of trials that draw on contingency at all;
- **Additional contingency needed at P10…P95** = max(0, percentile − RT),
  and the total contingency that implies, K + additional, as a % of B.

The seed is fixed (42) so a rerun with the same assumptions reproduces the
same numbers; it is recorded in model.json, not on the report.

## Risks without a Cost Impact

Default `costless_risk_method: pct_of_running_total` with Impact →
0.1 / 0.5 / 1 / 2.5 / 5 % of RT (Insignificant → Severe). Alternatives:
`fixed` with `impact_dollars` (whole units of the project's currency, the
name notwithstanding), or `exclude`. Whatever is used, page 1 lists the
resulting figure per risk with the chip *Assumed*, and the user can replace
any of them with `{"cost": <amount>}` in `assumptions.risks`.

## assumptions.json

```json
{
  "workdir": "work",
  "adds_pct": 40,
  "deducts_pct": 50,
  "risk_scenario": "likely",
  "risk_probabilities": null,
  "items": {"77": "rejected", "79": "accepted"},
  "risks": {"5": "certain", "1": "excluded", "2": {"cost": 750000}, "4": {"probability": 65}},
  "costless_risk_method": "pct_of_running_total",
  "impact_pct": {"1": 0.1, "2": 0.5, "3": 1.0, "4": 2.5, "5": 5.0},
  "impact_dollars": {"1": 25000, "2": 100000, "3": 250000, "4": 1000000, "5": 2500000},
  "contingency_override": null,
  "include_company_risks": false,
  "project_id": null,
  "trials": 10000,
  "seed": 42,
  "notes": ["#77 carried as rejected: owner confirmed cast-in-place on 25 Sep."]
}
```

Keys in `items` / `risks` are item or risk **numbers** (as shown in Join) or
ids. `project_id` only matters when `project.json` is a list page holding
several projects. Amounts (`cost`, `contingency_override`, `impact_dollars`)
are whole units of the project's currency. `risk_scenario: "custom"` uses `risk_probabilities` as given. Every
field is optional; omitted fields take the defaults above. `notes` are
printed verbatim under Basis — use them for the *why* behind each override,
in the user's words.
