# Crew Roster Copilot — Design

**Date:** 2026-11-16 · **Status:** approved design, pre-implementation

## 1. Purpose

A portfolio project showing **optimisation**, **LLM tool use / agents** and **evaluation**. An optimiser
builds a 7-day pilot roster for a small fictional airline under India's DGCA flight duty time
limitations (FDTL), re-plans with as few changes as possible when disruptions hit, and an LLM agent
explains changes and answers what-if questions by calling the optimiser, never by inventing numbers.

**Motivation (README only):** IndiGo's late-Nov / Dec-2025 cancellations, which the airline attributed
to misjudging crew needs under Phase 2 of the revised FDTL rules (effective 1 Nov 2025), the DGCA's
temporary exemption on night-duty rules, and IndiGo's Feb-2025 IIT Delhi partnership on AI for
disruption management. The app runs a **fictional airline, "Skyline Air"**, with no IndiGo name,
logo or colours in the UI, and a "not affiliated" note in the README.

**Constraints:** free or near-free (Groq free tier, Cloud Run free tier, ≤ $0.50 of Anthropic
credit, spent only after asking). Keys only in `.env` / Cloud Run secrets. The owner's laptop is
slow: any local job longer than ~1 minute is announced first and run in the background.

**Done =** a live React site + Cloud Run API, both evaluations written up in `docs/results/RESULTS.md`,
a README, every feature committed and pushed.

## 2. Architecture

```
src/crew_roster/
  data/       fictional airline generator (seeded): airports, flights, pilots + history
  rules/      DGCA limits as YAML rulesets + loader
  duties/     step 1: flights -> out-and-back duties (CP-SAT set partitioning)
  roster/     step 2: CP-SAT pilot assignment, re-plan, legality checker, greedy baseline
  disrupt/    disruption types and how they modify the problem
  agent/      LangGraph agent, tools, number-check guard
  api/        FastAPI app
  eval/       optimiser benchmark, agent evaluation, report writer
frontend/     React + Vite + Tailwind (GitHub Pages)
scripts/      deploy_cloudrun.py
tests/
```

**Central rule:** a single legality checker, `roster/check.py`, separate from the solver, decides
whether a roster breaks a rule. The solver's output, the greedy baseline, tests and agent
explanations all go through it. Reasons given to users come from checker output, not the LLM.

**Main interfaces** (all plain dataclasses / pydantic models):

| Function | Returns |
|---|---|
| `data.generate(seed) -> Airline` | airports, flights + turns (7 days), pilots with 27-day history |
| `rules.load(name) -> Ruleset` | `"dgca_current"` or `"dgca_dec2025_exemption"` |
| `duties.build(turns, flights, ruleset) -> list[Duty]` | every flight in exactly one duty |
| `problem.build_problem(airline, ruleset) -> Problem` | duties + pilots + history + ruleset |
| `roster.solve(problem, base=None, locked_before=None, time_limit=10) -> SolveResult` | roster, uncovered slots, stats |
| `roster.check(problem, roster) -> list[Violation]` | empty list = legal |
| `roster.diff(problem, old, new) -> list[Change]` | each change with checker reason codes |
| `disrupt.apply(problem, disruptions) -> Problem` | modified copy; never mutates input |
| `roster.greedy_repair(problem, base, locked_before) -> SolveResult` | baseline |

## 3. Data: "Skyline Air"

- Bases **DEL** and **BOM**. Other airports: BLR, HYD, MAA, CCU, GOI, PNQ. Block times are
  realistic and fixed in a table (e.g. DEL–BOM 2h10).
- ~40 flights/day × 7 days, published as rotations out of each base, so out-and-back duties exist.
  Includes a few departures in 00:00–06:00 so the night rules matter.
- 80 A320 pilots: 40 per base, half captains (CPT) and half first officers (FO) (raised from 60: with 30 per base the DGCA weekly-rest rule left 7 duty slots uncrewable; 38 per base is the minimum, 40 leaves slack for disruptions). Each pilot has a
  27-day synthetic history (flight hours, duty hours, end time of last duty, consecutive nights,
  last 48h rest) so 7-day and 28-day rolling limits matter from day 1, plus a few pre-booked leave days.
- Generated from a fixed seed, so it is identical on every run.

## 4. Rules

YAML files in `rules/`: `dgca_current.yaml` and `dgca_dec2025_exemption.yaml`. Each limit has an
`id`, `value`, `unit` and `source` (CAR section / circular). Limits (2-pilot operations):

| id | meaning |
|---|---|
| `max_ft_per_duty` | max flight time in one duty |
| `max_fdp_by_landings` | max flight duty period, a table indexed by number of landings |
| `night_window` | 00:00–06:00 local |
| `night_max_fdp`, `night_max_landings` | night-duty caps (2 landings current; 6 under exemption) |
| `max_consecutive_nights` | 2 |
| `min_rest` | max(previous duty length, 12h) |
| `weekly_rest` | ≥ 48 consecutive hours off in any rolling 7 days |
| `ft_7d`, `ft_28d` | rolling flight-time limits (e.g. 35h, 100h) |
| `duty_7d`, `duty_28d` | rolling duty-time limits |

All values must be checked against the text of DGCA CAR Section 7, Series J, Part III (current
revision) before the checker is finished; the source of each one goes in the YAML. Where the CAR
is more complex than this model (e.g. augmented crew, split duty), the README says the
simplification plainly.

## 5. Optimiser

### Step 1: duty builder
List every chain of 1–4 flights that starts and ends at the same base, with a turnaround of at
least 40 min and within `max_fdp_by_landings` / `max_ft_per_duty`. CP-SAT set partitioning picks
chains covering every flight exactly once with the fewest duties. There are no overnights away
from base (a documented simplification). Each duty has report time (first departure −60 min),
release (last arrival +30 min), flight time, landings and a night flag.

### Step 2: roster assignment (CP-SAT)
- Variables: `x[p, d] ∈ {0,1}` for each pilot and duty at the pilot's base.
- Each duty needs 1 CPT and 1 FO. Coverage is **soft**: `uncovered[d, role]` with a large penalty,
  so a shortage gives "N duties can't be crewed" instead of no answer.
- Hard constraints: no overlap; rest gap ≥ `min_rest` between consecutive duties (pairwise
  conflicts for duty pairs that are too close); rolling 7/28-day flight and duty limits including
  history; weekly 48h rest; night landings and consecutive-night limits; leave days.
- Objective: minimise uncovered duties ≫ spread in flight time (max − min per base).
- Deterministic: fixed `random_seed`, set worker count, 10 s time limit. The base roster is
  solved once and cached as JSON.

### Re-plan
`disrupt.apply` → solve with `base` = current roster, `locked_before` = disruption time (duties
before it are fixed), a hint from the base roster, and objective priority
**uncovered ≫ changed assignments ≫ fairness**. The output is the new roster plus `list[Change]`
(duty, role, old pilot, new pilot, reason codes such as `SICK`, `FT_DUTY_EXCEEDED{value,limit}`,
`REST_SHORT{value,limit}`, `NIGHT_LANDINGS{...}`).

### Disruptions
- `PilotSick(pilot_id, from_day, to_day)`
- `FlightDelay(flight_id, minutes)` stretches the duty, which may push it into the night window or
  break a rest gap or FDP
- `FlightCancel(flight_id)` shrinks or removes the duty

### Greedy baseline
For each broken duty slot, in time order, take the first available pilot of the right base and
rank for whom `check` reports no violations.

### Crew sizing
`min_pilots_needed(base, ruleset)` finds the smallest pilot pool per base (subset of the generated
pilots, drawn in a fixed order) that covers all duties: a CP-SAT model minimising pilots used.

## 6. Agent (LangGraph)

**Tools** run on copies and never modify live state:
`get_roster(pilot?, day?)`, `pilot_status(pilot, day)` (hours used / remaining under each limit),
`what_if(disruptions, ruleset?)` (re-plan → changes, coverage, solve time),
`min_pilots_needed(base, ruleset)`, `explain_change(change_id)` (checker reasons).

**Graph:** `agent` (Groq `openai/gpt-oss-120b`) ⇄ `tools` → `number_check`. `number_check`
extracts numbers from the draft answer and requires each to appear (allowing for format
differences like 8.5 vs 8h30) in this turn's tool outputs or the user's question. On failure it
gives one retry with feedback, then shows the answer with a visible "unverified numbers" warning.
On HTTP 429 it falls back to `gpt-oss-20b`. Tool outputs are kept compact. LangSmith tracing is on.

**Change explanations:** checker reason codes → LLM writes one plain sentence per change → the
same number check is applied. If the LLM is unavailable, a template sentence is used.

## 7. API (FastAPI, stateless)

The browser holds the list of applied disruptions and the ruleset choice. The server recomputes
deterministically with an LRU cache.

| Endpoint | Purpose |
|---|---|
| `GET /roster?ruleset=` | base roster |
| `POST /replan {disruptions, ruleset}` | roster, changes, explanations, stats |
| `POST /chat {messages, disruptions, ruleset}` | answer + tool-call trace |
| `GET /rules` | ruleset values with sources |
| `GET /health` | health check |

Per-IP rate limit on `/chat` to protect the Groq quota. CORS is open only to the GitHub Pages
origin and localhost.

## 8. Frontend (React + Vite + Tailwind)

- **Roster grid:** one row per pilot, 7 day columns, duty blocks with route and hours; changed blocks
  highlighted; base filter.
- **Disruption panel:** pilot sick / delay flight / cancel flight; ruleset toggle (current vs
  Dec-2025 exemption); reset.
- **Numbers strip:** duties crewed, assignments changed, solve time, rule breaches (from checker).
- **Changes list** with plain-language explanations.
- **Chat panel** that shows each tool call and its duration.

## 9. Evaluation

**Optimiser benchmark** (`crew-eval optimiser`): 50 seeded disruptions (sick / delay / cancel,
small to large) × {CP-SAT re-plan, greedy, re-solve from scratch}. Metrics: checker violations,
uncovered duties, changed assignments, solve time. Plus crew-sizing per base, current vs
exemption. Output: `docs/results/optimiser.json` and a section of `RESULTS.md`. ~5–10 min locally,
announced and run in the background.

**Agent evaluation** (`crew-eval agent`, LangSmith experiments): ~40 questions with ground truth
**computed by running the tools**.
- Measured by code: tool-choice accuracy, argument accuracy, expected-number recall,
  number-grounding rate (the share of answer numbers found in tool outputs).
- LLM judge: Claude Haiku 5.5 (`claude-haiku-5-5`) on ~20 explanations, rating faithfulness to
  checker reasons and clarity. Under $0.50, run only after the owner approves.
- Compares gpt-oss-120b vs gpt-oss-20b. May be split across days for Groq's daily token limit.

## 10. Testing

pytest, tests written first:
- checker: a hand-built pass case and fail case for each rule
- duty builder: every flight covered exactly once, and every duty within limits
- solver: every result passes the checker, and the output is deterministic
- re-plan: locked duties unchanged; a sick pilot never flies during sick days
- disruptions: inputs are not mutated
- agent: number-check unit tests, and a graph test with a fake LLM
- API: tests with the fake LLM, so no network calls

## 11. Deployment and cost

- Backend: Docker → Cloud Run service `crew-roster-copilot` in the existing GCP project
  `annual-report-rag-krtiin`, min instances 0, 1 GiB, 2 vCPU, secrets via Secret Manager / env.
  Deploy script modelled on the previous project's `scripts/deploy_cloudrun.py`.
- Frontend: GitHub Pages, `VITE_API_URL` pointing at Cloud Run.
- Cost: Groq free; Cloud Run free tier; Claude judge < $0.50, approved first.

## 12. Build order (each step committed and pushed)

1. Project setup + data generator
2. Rules YAML + legality checker
3. Duty builder
4. Roster solver (base roster)
5. Disruptions + re-plan + greedy + diff
6. LangGraph agent + tools + number check
7. FastAPI
8. React frontend
9. Evaluations + RESULTS.md
10. Deployment + README

## 13. Out of scope

Cabin crew; multiple fleets; overnight layovers away from base; standby/reserve duty types;
augmented crews; pilot preferences/bidding; multi-week or monthly rosters; letting the agent
change the live roster.
