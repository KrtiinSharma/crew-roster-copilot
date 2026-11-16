# Crew Roster Copilot — Plan 1: Optimiser Core

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tested Python library that generates the fictional airline, builds duties, solves a DGCA-legal 7-day pilot roster with CP-SAT, re-plans after disruptions with minimum changes, and provides a greedy baseline and crew sizing.

**Architecture:** Two-step optimisation (spec §5). Step 1 groups out-and-back *turns* into duties with a CP-SAT set-partitioning model. Step 2 assigns pilots to duties with a CP-SAT model. A separate legality checker (`roster/check.py`) is the single source of truth for rule breaches; solver output, greedy output and change explanations all go through it. Times are integer **minutes from roster start** (day 0, 00:00 IST); history uses negative times.

**Tech Stack:** Python 3.11, uv, pydantic v2, PyYAML, Google OR-Tools CP-SAT (snake_case API, ortools ≥ 9.10), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-11-16-crew-roster-copilot-design.md`

## Plan series

| Plan | Covers (spec build order) | When written |
|---|---|---|
| **1 — Optimiser core (this file)** | steps 1–5 + crew sizing | now |
| 2 — Agent + API | steps 6–7 (LangGraph tools/number check, FastAPI) | after Plan 1 is merged |
| 3 — Frontend | step 8 (React roster grid, disruption panel, chat) | after Plan 2 |
| 4 — Evaluation + deployment | steps 9–10 (benchmarks, agent eval, Cloud Run, Pages, README) | after Plan 3 |

Each later plan is written with superpowers:writing-plans against the code Plan 1 actually produced.

## Global Constraints

- Python `>=3.11, <3.13`; manage everything with `uv` (`uv add`, `uv run`); never `pip install`.
- API keys only in `.env` (gitignored); never print, echo or commit them. Plan 1 needs no keys.
- The app's airline is the fictional **"Skyline Air"**; no IndiGo name, logo or colours in code-facing UI strings.
- Pilots only, one fleet (A320), bases `DEL` and `BOM`, 7-day roster, 80 pilots (40 per base, 20 CPT + 20 FO; raised from 60 during Task 4, owner-approved).
- Every flight is part of a **turn** (base → outstation → base). Duties are 1–2 turns (≤ 4 flights) starting and ending at the same base. No overnights away from base.
- Simplifications that must stay consistent between solver and checker: a duty belongs to the calendar day of its report time; weekly rest = 2 consecutive calendar days with no duty touching them in every 7-day window; consecutive nights = night duties on consecutive calendar days; the solver also enforces at most one duty per pilot per calendar day (operational rule, not checked as DGCA).
- The owner's laptop is slow. Every solve in tests uses `time_limit ≤ 10`. Tests that take > 10 s are marked `@pytest.mark.slow` and excluded by default.
- Each task ends with a commit **and a push** to `origin main`.
- Commit messages end with: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## File map

```
src/crew_roster/
  models.py              DAY, Role, ROLES, is_night, Frozen, Flight, Turn, Pilot, Duty, Airline, Roster, Violation
  data/__init__.py       re-exports generate + constants
  data/airline.py        Skyline Air generator (network templates, pilots, history, leave)
  rules/__init__.py      Ruleset, load, RULESETS
  rules/dgca_current.yaml
  rules/dgca_dec2025_exemption.yaml
  problem.py             Problem, build_problem
  duties/__init__.py     re-exports
  duties/builder.py      make_duty, candidate_chains, build
  roster/__init__.py     re-exports
  roster/check.py        WINDOWS, duty_violations, pilot_violations, check
  roster/solver.py       SolveResult, solve, W_UNCOVERED, W_CHANGE
  roster/diff.py         count_changes, Change, diff
  roster/cache.py        cache_path, load_base_roster
  roster/base_rosters/   dgca_current.json, dgca_dec2025_exemption.json (generated, committed)
  roster/replan.py       Replan, replan
  roster/greedy.py       greedy_repair
  roster/sizing.py       Sizing, min_pilots_needed
  disrupt/__init__.py    PilotSick, FlightDelay, FlightCancel, Disruption, apply, known_at, lock_time
  cli.py                 crew-solve command
tests/
  conftest.py            session fixtures: airline, problem, base_result
  factories.py           mk_duty, mk_pilot, mk_problem, mk_roster, mk_history
  test_data.py  test_rules.py  test_check.py  test_duties.py  test_solver.py
  test_disrupt.py  test_replan.py  test_greedy.py  test_sizing.py
```

---

### Task 1: Dependencies, core models and the Skyline Air generator

**Files:**
- Modify: `pyproject.toml` (dependencies via `uv add`, pytest markers)
- Create: `src/crew_roster/models.py`, `src/crew_roster/data/__init__.py`, `src/crew_roster/data/airline.py`
- Test: `tests/conftest.py`, `tests/test_data.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `crew_roster.models`: `DAY = 1440`; `Role = Literal["CPT","FO"]`; `ROLES = ("CPT","FO")`; `is_night(start:int, end:int, night_start:int, night_end:int) -> bool`; pydantic frozen models `Flight(id, turn_id, day, origin, dest, dep, arr)` with `.block`; `Turn(id, base, dest, day, out_id, back_id)` with `.flight_ids`; `Pilot(id, name, rank, base, unavailable_days: frozenset[int])`; `Duty(id, base, report, release, flight_time, landings, night, turn_ids, flight_ids)` with `.day`, `.length`, `.touched_days()`; `Airline(name, days, bases, airports, flights: dict, turns: dict, pilots: list, history: dict[str, list[Duty]])`; `Roster(assignments: dict[str, dict[str, str]])` with `.get(duty_id, role)`, `.with_slot(duty_id, role, pilot_id|None)`, `.duties_of(pilot_id) -> list[tuple[str,str]]`, `.slots() -> list[tuple[str,str,str]]`; `Violation(rule, pilot_id, duty_id, day, value, limit, message)`.
  - `crew_roster.data.generate(seed=7, days=7, pilots_per_base=30, history_days=27) -> Airline`; constants `AIRPORTS`, `BASES`, `TURN_TEMPLATES`, `GROUND_MIN`, `block_time(a, b)`.

- [ ] **Step 1: Add dependencies and pytest markers**

```bash
uv add "pydantic>=2.7" "pyyaml>=6" "ortools>=9.10"
```

Then append to the existing `[tool.pytest.ini_options]` table in `pyproject.toml` so it reads:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
markers = ["slow: takes more than ~10 s on a slow laptop (run with -m slow)"]
addopts = "-m 'not slow'"
```

- [ ] **Step 2: Write the failing tests**

`tests/conftest.py`:

```python
import pytest

from crew_roster.data import generate


@pytest.fixture(scope="session")
def airline():
    return generate()
```

`tests/test_data.py`:

```python
from crew_roster.data import BASES, GROUND_MIN, TURN_TEMPLATES, generate
from crew_roster.models import DAY, Duty, Roster, is_night


def test_generator_is_deterministic():
    assert generate().model_dump() == generate().model_dump()


def test_flights_form_out_and_back_turns(airline):
    per_day = 2 * sum(len(t) for t in TURN_TEMPLATES.values())
    assert len(airline.flights) == per_day * airline.days
    assert 40 <= per_day <= 46
    for turn in airline.turns.values():
        out, back = (airline.flights[f] for f in turn.flight_ids)
        assert out.origin == turn.base == back.dest
        assert out.dest == back.origin == turn.dest
        assert back.dep - out.arr == GROUND_MIN


def test_sixty_pilots_split_by_base_and_rank(airline):
    assert len(airline.pilots) == 60
    for base in BASES:
        ranks = [p.rank for p in airline.pilots if p.base == base]
        assert ranks.count("CPT") == 15 and ranks.count("FO") == 15
    assert len({p.id for p in airline.pilots}) == 60


def test_history_is_in_the_past_and_has_weekly_rest(airline):
    for p in airline.pilots:
        hist = airline.history[p.id]
        assert hist, p.id
        assert all(h.release <= 0 for h in hist)
        busy = {k for h in hist for k in h.touched_days()}
        for t in range(-21, 0):
            assert any(s not in busy and s + 1 not in busy for s in range(t - 6, t)), (p.id, t)
        assert sum(h.flight_time for h in hist if h.day >= -27) < 100 * 60


def test_some_pilots_have_leave(airline):
    on_leave = [p for p in airline.pilots if p.unavailable_days]
    assert len(on_leave) == 6
    assert all(0 <= d < airline.days for p in on_leave for d in p.unavailable_days)


def test_is_night_and_duty_helpers():
    assert is_night(23 * 60, 30 * 60, 0, 360)            # 23:00 -> 06:00 next day
    assert is_night(5 * 60, 9 * 60, 0, 360)              # report 05:00
    assert not is_night(6 * 60, 18 * 60, 0, 360)         # 06:00 -> 18:00
    d = Duty(id="X", base="DEL", report=DAY + 22 * 60, release=2 * DAY + 2 * 60,
             flight_time=200, landings=2, night=True)
    assert d.day == 1 and d.length == 240 and list(d.touched_days()) == [1, 2]


def test_roster_helpers_are_immutable():
    r = Roster(assignments={"D1": {"CPT": "A"}})
    r2 = r.with_slot("D1", "FO", "B")
    assert r.get("D1", "FO") is None and r2.get("D1", "FO") == "B"
    assert r2.duties_of("B") == [("D1", "FO")]
    assert r2.with_slot("D1", "CPT", None).with_slot("D1", "FO", None).assignments == {}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_data.py -q`
Expected: FAIL / ERROR with `ModuleNotFoundError: No module named 'crew_roster.data'`.

- [ ] **Step 4: Write `src/crew_roster/models.py`**

```python
"""Core data types. Times are integer minutes from roster start (day 0, 00:00 IST)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

DAY = 24 * 60
Role = Literal["CPT", "FO"]
ROLES: tuple[Role, Role] = ("CPT", "FO")


def is_night(start: int, end: int, night_start: int, night_end: int) -> bool:
    """True if [start, end) overlaps the nightly window [night_start, night_end) on any day."""
    for k in range(start // DAY - 1, (end - 1) // DAY + 1):
        lo, hi = k * DAY + night_start, k * DAY + night_end
        if start < hi and end > lo:
            return True
    return False


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Flight(Frozen):
    id: str
    turn_id: str
    day: int
    origin: str
    dest: str
    dep: int
    arr: int

    @property
    def block(self) -> int:
        return self.arr - self.dep


class Turn(Frozen):
    id: str
    base: str
    dest: str
    day: int
    out_id: str
    back_id: str

    @property
    def flight_ids(self) -> tuple[str, str]:
        return (self.out_id, self.back_id)


class Pilot(Frozen):
    id: str
    name: str
    rank: Role
    base: str
    unavailable_days: frozenset[int] = frozenset()


class Duty(Frozen):
    id: str
    base: str
    report: int
    release: int
    flight_time: int
    landings: int
    night: bool
    turn_ids: tuple[str, ...] = ()
    flight_ids: tuple[str, ...] = ()

    @property
    def day(self) -> int:
        return self.report // DAY

    @property
    def length(self) -> int:
        return self.release - self.report

    def touched_days(self) -> range:
        return range(self.report // DAY, (self.release - 1) // DAY + 1)


class Airline(Frozen):
    name: str
    days: int
    bases: tuple[str, ...]
    airports: dict[str, str]
    flights: dict[str, Flight]
    turns: dict[str, Turn]
    pilots: list[Pilot]
    history: dict[str, list[Duty]]


class Roster(Frozen):
    """duty_id -> {role: pilot_id}. Missing role = slot not crewed."""

    assignments: dict[str, dict[str, str]] = {}

    def get(self, duty_id: str, role: str) -> str | None:
        return self.assignments.get(duty_id, {}).get(role)

    def with_slot(self, duty_id: str, role: str, pilot_id: str | None) -> Roster:
        new = {k: dict(v) for k, v in self.assignments.items()}
        crew = new.setdefault(duty_id, {})
        if pilot_id is None:
            crew.pop(role, None)
        else:
            crew[role] = pilot_id
        if not crew:
            new.pop(duty_id)
        return Roster(assignments=new)

    def duties_of(self, pilot_id: str) -> list[tuple[str, str]]:
        return [(d, r) for d, crew in self.assignments.items() for r, p in crew.items()
                if p == pilot_id]

    def slots(self) -> list[tuple[str, str, str]]:
        return [(d, r, p) for d, crew in self.assignments.items() for r, p in crew.items()]


class Violation(Frozen):
    rule: str
    pilot_id: str | None = None
    duty_id: str | None = None
    day: int | None = None
    value: int = 0
    limit: int = 0
    message: str = ""
```

- [ ] **Step 5: Write `src/crew_roster/data/airline.py` and `data/__init__.py`**

`src/crew_roster/data/airline.py`:

```python
"""Fictional airline 'Skyline Air': a seeded domestic A320 network out of DEL and BOM."""

from __future__ import annotations

import random

from crew_roster.models import DAY, Airline, Duty, Flight, Pilot, Turn

AIRPORTS = {"DEL": "Delhi", "BOM": "Mumbai", "BLR": "Bengaluru", "HYD": "Hyderabad",
            "MAA": "Chennai", "CCU": "Kolkata", "GOI": "Goa", "PNQ": "Pune"}
BASES = ("DEL", "BOM")
BLOCK_MIN = {("BOM", "DEL"): 130, ("BLR", "DEL"): 165, ("DEL", "HYD"): 135,
             ("CCU", "DEL"): 135, ("DEL", "GOI"): 150, ("DEL", "PNQ"): 125,
             ("DEL", "MAA"): 170, ("BOM", "GOI"): 70, ("BOM", "HYD"): 85,
             ("BLR", "BOM"): 100, ("BOM", "PNQ"): 50, ("BOM", "CCU"): 160}
GROUND_MIN = 45  # turnaround at the outstation
# (outstation, departure HH:MM from base) — repeated every day
TURN_TEMPLATES = {
    "DEL": [("BOM", "06:00"), ("BLR", "06:30"), ("HYD", "08:00"), ("CCU", "10:00"),
            ("GOI", "12:00"), ("PNQ", "14:00"), ("BOM", "16:30"), ("MAA", "18:00"),
            ("BLR", "23:30")],
    "BOM": [("GOI", "06:00"), ("HYD", "07:00"), ("BLR", "07:30"), ("DEL", "08:00"),
            ("PNQ", "09:50"), ("GOI", "12:00"), ("HYD", "13:30"), ("PNQ", "16:00"),
            ("CCU", "17:00"), ("DEL", "19:00"), ("HYD", "23:45"), ("GOI", "04:15")],
}
FLIGHT_NO_START = {"DEL": 101, "BOM": 501}
SURNAMES = ["Rao", "Iyer", "Sharma", "Verma", "Nair", "Menon", "Gupta", "Kapoor", "Reddy",
            "Das", "Bose", "Singh", "Patel", "Shah", "Joshi", "Kulkarni", "Pillai", "Mehta",
            "Chopra", "Malhotra", "Banerjee", "Mishra", "Agarwal", "Saxena", "Bhat", "Kaur",
            "Gill", "Naidu", "Desai", "Rathore"]
INITIALS = "ABDGKMNPRSV"


def block_time(a: str, b: str) -> int:
    return BLOCK_MIN[tuple(sorted((a, b)))]


def _clock(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _history(rng: random.Random, pid: str, base: str, n_days: int) -> list[Duty]:
    """4 days on / 2 days off with a random phase, so every 7-day window has 2 free days."""
    phase = rng.randrange(6)
    out = []
    for day in range(-n_days, 0):
        if (day + phase) % 6 >= 4:
            continue
        report = day * DAY + rng.choice([300, 360, 420, 480, 540])
        ft = rng.randrange(180, 331, 15)
        length = ft + 120 + rng.choice([0, 30, 60])
        out.append(Duty(id=f"H-{pid}{day}", base=base, report=report, release=report + length,
                        flight_time=ft, landings=rng.choice([2, 4]), night=False))
    return out


def generate(seed: int = 7, days: int = 7, pilots_per_base: int = 30,
             history_days: int = 27) -> Airline:
    rng = random.Random(seed)
    flights: dict[str, Flight] = {}
    turns: dict[str, Turn] = {}
    for base in BASES:
        for i, (dest, hhmm) in enumerate(TURN_TEMPLATES[base]):
            no = FLIGHT_NO_START[base] + 2 * i
            blk = block_time(base, dest)
            for day in range(days):
                tid = f"T-{base}{i:02d}-D{day}"
                dep = day * DAY + _clock(hhmm)
                out = Flight(id=f"SK{no}-D{day}", turn_id=tid, day=day, origin=base,
                             dest=dest, dep=dep, arr=dep + blk)
                back_dep = out.arr + GROUND_MIN
                back = Flight(id=f"SK{no + 1}-D{day}", turn_id=tid, day=day, origin=dest,
                              dest=base, dep=back_dep, arr=back_dep + blk)
                flights[out.id], flights[back.id] = out, back
                turns[tid] = Turn(id=tid, base=base, dest=dest, day=day,
                                  out_id=out.id, back_id=back.id)

    combos = [f"{i}. {s}" for i in INITIALS for s in SURNAMES]
    names = iter(rng.sample(combos, len(BASES) * pilots_per_base))
    pilots: list[Pilot] = []
    history: dict[str, list[Duty]] = {}
    for base in BASES:
        for rank, tag, title in (("CPT", "C", "Capt."), ("FO", "F", "FO")):
            for j in range(1, pilots_per_base // 2 + 1):
                pid = f"{base}-{tag}{j:02d}"
                pilots.append(Pilot(id=pid, name=f"{title} {next(names)}", rank=rank, base=base))
                history[pid] = _history(rng, pid, base, history_days)

    index = {p.id: i for i, p in enumerate(pilots)}
    for base in BASES:
        for pid in rng.sample([p.id for p in pilots if p.base == base], 3):
            start = rng.randrange(0, days - 2)
            off = frozenset(range(start, min(start + rng.choice([2, 3]), days)))
            pilots[index[pid]] = pilots[index[pid]].model_copy(update={"unavailable_days": off})

    return Airline(name="Skyline Air", days=days, bases=BASES, airports=AIRPORTS,
                   flights=flights, turns=turns, pilots=pilots, history=history)
```

`src/crew_roster/data/__init__.py`:

```python
from crew_roster.data.airline import (
    AIRPORTS,
    BASES,
    GROUND_MIN,
    TURN_TEMPLATES,
    block_time,
    generate,
)

__all__ = ["AIRPORTS", "BASES", "GROUND_MIN", "TURN_TEMPLATES", "block_time", "generate"]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_data.py -q`
Expected: `7 passed`.

- [ ] **Step 7: Lint, commit, connect GitHub and push**

```bash
uv run ruff check src tests && uv run ruff format src tests
git add -A
git commit -m "feat: core models and Skyline Air data generator" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

If `git remote` prints nothing, ask the owner to create an empty GitHub repo named `crew-roster-copilot` (no README), then:

```bash
git remote add origin https://github.com/KrtiinSharma/crew-roster-copilot.git
git push -u origin main
```

Otherwise just `git push`.

---

### Task 2: DGCA rulesets, Problem, and the legality checker

**Files:**
- Create: `src/crew_roster/rules/__init__.py`, `src/crew_roster/rules/dgca_current.yaml`, `src/crew_roster/rules/dgca_dec2025_exemption.yaml`, `src/crew_roster/problem.py`, `src/crew_roster/roster/__init__.py`, `src/crew_roster/roster/check.py`
- Test: `tests/factories.py`, `tests/test_rules.py`, `tests/test_check.py`

**Interfaces:**
- Consumes: `crew_roster.models` (Task 1).
- Produces:
  - `crew_roster.rules`: `RULESETS = ("dgca_current", "dgca_dec2025_exemption")`; `Ruleset` (all limits in **minutes** or counts: `max_ft_per_duty, max_fdp_by_landings: dict[int,int], night_start, night_end, night_max_fdp, night_max_landings, max_consecutive_nights, min_rest, weekly_rest, ft_7d, ft_28d, duty_7d, duty_28d, sources: dict[str,str], name, label`); `load(name="dgca_current") -> Ruleset` (raises `ValueError` on unknown name).
  - `crew_roster.problem.Problem(ruleset, duties, pilots, history={}, turns={}, flights={}, sick: dict[str, frozenset[int]]={}, horizon_days=7)` with `.pilot_map()`, `.duty_map()`, `.unavailable_days(pilot) -> frozenset[int]`.
  - `crew_roster.roster.check`: `WINDOWS` (tuple of `(rule, span_days, duty_attr)`), `duty_violations(duty, ruleset) -> list[Violation]`, `pilot_violations(problem, roster, pilot_id) -> list[Violation]`, `check(problem, roster) -> list[Violation]`. Rule names: `max_ft_per_duty, max_landings, max_fdp, night_max_fdp, night_max_landings, min_rest, ft_7d, ft_28d, duty_7d, duty_28d, weekly_rest, consecutive_nights, unavailable, sick, wrong_rank, wrong_base, unknown_duty, unknown_pilot`.

- [ ] **Step 1: Verify the limit values against the DGCA text**

Fetch DGCA CAR Section 7, Series J, Part III (latest revision, flight duty time limitations for flight crew) from dgca.gov.in. Use the web-fetch agent if there is no WebFetch tool. Check these values (2-pilot operations): max flight time per FDP (expected 8 h), max FDP by number of landings (expected 13 h for 1–2 landings, falling by 30 min per extra landing to 11 h at 6), night window (00:00–06:00), night FDP cap (10 h), night landings (2), consecutive night duties (2), minimum rest (≥ 12 h and ≥ preceding duty), weekly rest (48 h), flight time 35 h / 7 days and 100 h / 28 days, duty 60 h / 7 days and 190 h / 28 days. Write the CAR paragraph number into each `source` below. If the CAR gives a different value, use the CAR value and update `tests/test_rules.py` to match. If the PDF can't be fetched, keep these values with source `"as reported: Business Standard 8 Jan 2024; to verify against CAR 7-J-III"` and note it for the README's "Rule assumptions" section (Plan 4).

- [ ] **Step 2: Write the failing tests**

`tests/factories.py`:

```python
"""Tiny hand-built problems for unit tests (no generator, no history unless given)."""

from crew_roster.models import DAY, Duty, Pilot, Roster, is_night
from crew_roster.problem import Problem
from crew_roster.rules import load


def hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def mk_duty(id, day, start, hours, ft_hours=None, landings=2, base="DEL"):
    report = day * DAY + hm(start)
    release = report + round(hours * 60)
    ft = round((ft_hours if ft_hours is not None else max(hours - 1.5, 0.5)) * 60)
    return Duty(id=id, base=base, report=report, release=release, flight_time=ft,
                landings=landings, night=is_night(report, release, 0, 360))


def mk_pilot(id, rank="CPT", base="DEL", off=()):
    return Pilot(id=id, name=id, rank=rank, base=base, unavailable_days=frozenset(off))


def mk_history(pid, days, hours, ft_hours, start="06:00"):
    return {pid: [mk_duty(f"H{k}", k, start, hours, ft_hours=ft_hours) for k in days]}


def mk_problem(duties, pilots, history=None, ruleset="dgca_current", sick=None, horizon=7):
    return Problem(ruleset=load(ruleset), duties=duties, pilots=pilots, history=history or {},
                   sick={k: frozenset(v) for k, v in (sick or {}).items()}, horizon_days=horizon)


def mk_roster(assignments):
    return Roster(assignments=assignments)
```

`tests/test_rules.py`:

```python
import pytest

from crew_roster.rules import RULESETS, load


def test_both_rulesets_load_in_minutes():
    cur, exm = load("dgca_current"), load("dgca_dec2025_exemption")
    assert set(RULESETS) == {"dgca_current", "dgca_dec2025_exemption"}
    assert cur.max_ft_per_duty == 8 * 60
    assert cur.min_rest == 12 * 60
    assert cur.ft_7d == 35 * 60 and cur.ft_28d == 100 * 60
    assert cur.duty_7d == 60 * 60 and cur.duty_28d == 190 * 60
    assert (cur.night_start, cur.night_end) == (0, 360)
    assert cur.night_max_landings == 2 and exm.night_max_landings == 6
    assert cur.max_consecutive_nights == 2
    assert cur.max_fdp_by_landings[1] >= cur.max_fdp_by_landings[6]
    assert set(cur.sources) >= {"max_ft_per_duty", "min_rest", "weekly_rest", "night_window"}


def test_unknown_ruleset_is_rejected():
    with pytest.raises(ValueError):
        load("nope")
```

`tests/test_check.py`:

```python
from factories import mk_duty, mk_history, mk_pilot, mk_problem, mk_roster

from crew_roster.roster.check import check

CPT = mk_pilot("P1")


def rules_of(violations):
    return {v.rule for v in violations}


def run(duties, pilots=(CPT,), role="CPT", pid="P1", **kw):
    p = mk_problem(list(duties), list(pilots), **kw)
    return check(p, mk_roster({d.id: {role: pid} for d in duties}))


def series(days, start="06:00", hours=9, ft_hours=7):
    return [mk_duty(f"D{k}", k, start, hours, ft_hours=ft_hours) for k in days]


def test_legal_day_duty_has_no_violations():
    assert run([mk_duty("D1", 1, "06:00", 8, ft_hours=6)]) == []


def test_flight_time_per_duty_over_8h():
    assert "max_ft_per_duty" in rules_of(run([mk_duty("D1", 1, "06:00", 10, ft_hours=8.5)]))


def test_fdp_limit_shrinks_with_landings():
    assert "max_fdp" in rules_of(run([mk_duty("D1", 1, "06:00", 12.5, ft_hours=7, landings=4)]))
    assert "max_fdp" not in rules_of(run([mk_duty("D1", 1, "06:00", 12.5, ft_hours=7)]))


def test_night_landings_current_vs_exemption():
    d = mk_duty("D1", 1, "23:00", 8, ft_hours=5, landings=4)
    assert "night_max_landings" in rules_of(run([d]))
    assert "night_max_landings" not in rules_of(run([d], ruleset="dgca_dec2025_exemption"))


def test_night_duty_period_cap():
    assert "night_max_fdp" in rules_of(run([mk_duty("D1", 1, "22:00", 10.5, ft_hours=6)]))


def test_min_rest_12h():
    d1 = mk_duty("D1", 1, "06:00", 10, ft_hours=6)  # release 16:00
    assert "min_rest" in rules_of(run([d1, mk_duty("D2", 2, "02:00", 6, ft_hours=4)]))
    assert "min_rest" not in rules_of(run([d1, mk_duty("D2", 2, "05:00", 6, ft_hours=4)]))


def test_rest_at_least_previous_duty_length():
    d1 = mk_duty("D1", 1, "06:00", 13, ft_hours=7)  # release 19:00 -> needs 13 h
    assert "min_rest" in rules_of(run([d1, mk_duty("D2", 2, "07:30", 6, ft_hours=4)]))
    assert "min_rest" not in rules_of(run([d1, mk_duty("D2", 2, "08:00", 6, ft_hours=4)]))


def test_flight_time_35h_in_7_days():
    assert "ft_7d" in rules_of(run(series([0, 1, 2, 3, 4], ft_hours=7.5)))
    assert "ft_7d" not in rules_of(run(series([0, 1, 2, 3, 4], ft_hours=7)))


def test_duty_60h_in_7_days():
    assert "duty_7d" in rules_of(run(series(range(6), hours=10.5, ft_hours=5)))
    assert "duty_7d" not in rules_of(run(series(range(5), hours=11, ft_hours=5)))


ON_DAYS = [d for d in range(-27, 0) if d % 6 not in (0, 1)]  # 19 history duties


def test_flight_time_100h_in_28_days_counts_history():
    hot = mk_history("P1", ON_DAYS, hours=8, ft_hours=6)    # 114 h
    cool = mk_history("P1", ON_DAYS, hours=8, ft_hours=4.5)  # 85.5 h
    assert "ft_28d" in rules_of(run(series([0]), history=hot))
    assert "ft_28d" not in rules_of(run(series([0]), history=cool))


def test_duty_190h_in_28_days_counts_history():
    hot = mk_history("P1", ON_DAYS, hours=10.5, ft_hours=4)  # 199.5 h
    cool = mk_history("P1", ON_DAYS, hours=9, ft_hours=4)    # 171 h
    assert "duty_28d" in rules_of(run(series([0]), history=hot))
    assert "duty_28d" not in rules_of(run(series([0]), history=cool))


def test_weekly_rest_needs_two_consecutive_free_days():
    assert "weekly_rest" in rules_of(run(series([0, 1, 2, 3, 4], ft_hours=5)))
    assert "weekly_rest" not in rules_of(run(series([0, 1, 2, 3, 6], ft_hours=5)))


def test_max_two_consecutive_night_duties():
    def nights(days):
        return [mk_duty(f"N{k}", k, "23:00", 7, ft_hours=5) for k in days]

    assert "consecutive_nights" in rules_of(run(nights([0, 1, 2])))
    assert "consecutive_nights" not in rules_of(run(nights([0, 1, 3])))


def test_leave_and_sick_days():
    d = mk_duty("D1", 2, "06:00", 8, ft_hours=6)
    assert "unavailable" in rules_of(run([d], pilots=[mk_pilot("P1", off=[2])]))
    assert "sick" in rules_of(run([d], sick={"P1": [2]}))


def test_rank_must_match_role():
    d = mk_duty("D1", 2, "06:00", 8, ft_hours=6)
    assert "wrong_rank" in rules_of(run([d], pilots=[mk_pilot("F1", rank="FO")], pid="F1"))
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_rules.py tests/test_check.py -q`
Expected: ERROR with `ModuleNotFoundError: No module named 'crew_roster.problem'` (or `crew_roster.rules`).

- [ ] **Step 4: Write the rulesets**

`src/crew_roster/rules/dgca_current.yaml` (replace `source` text with the CAR paragraph found in Step 1):

```yaml
name: dgca_current
label: "DGCA FDTL, current rules (Phase 2 in force from 1 Nov 2025)"
limits:
  max_ft_per_duty: {value: 8, unit: h, source: "CAR 7-J-III: max flight time, 2-pilot operations"}
  max_fdp_by_landings:
    value: {1: 13, 2: 13, 3: 12.5, 4: 12, 5: 11.5, 6: 11}
    unit: h
    source: "CAR 7-J-III: max FDP table by number of landings"
  night_window: {value: ["00:00", "06:00"], unit: clock, source: "CAR 7-J-III (2024 revision): night = 0000-0600"}
  night_max_fdp: {value: 10, unit: h, source: "CAR 7-J-III: FDP encroaching night"}
  night_max_landings: {value: 2, unit: count, source: "CAR 7-J-III: max landings in a night duty (was 6)"}
  max_consecutive_nights: {value: 2, unit: count, source: "CAR 7-J-III: max consecutive night duties"}
  min_rest: {value: 12, unit: h, source: "CAR 7-J-III: rest >= preceding duty, minimum 12 h"}
  weekly_rest: {value: 48, unit: h, source: "CAR 7-J-III: 48 h weekly rest incl. two local nights (was 36 h)"}
  ft_7d: {value: 35, unit: h, source: "CAR 7-J-III: cumulative flight time, 7 consecutive days"}
  ft_28d: {value: 100, unit: h, source: "CAR 7-J-III: cumulative flight time, 28 consecutive days"}
  duty_7d: {value: 60, unit: h, source: "CAR 7-J-III: cumulative duty, 7 consecutive days"}
  duty_28d: {value: 190, unit: h, source: "CAR 7-J-III: cumulative duty, 28 consecutive days"}
```

`src/crew_roster/rules/dgca_dec2025_exemption.yaml` (same limits except `night_max_landings`; keep any `source` corrections from Step 1 in sync):

```yaml
name: dgca_dec2025_exemption
label: "Dec-2025 temporary exemption (night landings up to 6; as reported, valid to 10 Feb 2026)"
limits:
  max_ft_per_duty: {value: 8, unit: h, source: "CAR 7-J-III: max flight time, 2-pilot operations"}
  max_fdp_by_landings:
    value: {1: 13, 2: 13, 3: 12.5, 4: 12, 5: 11.5, 6: 11}
    unit: h
    source: "CAR 7-J-III: max FDP table by number of landings"
  night_window: {value: ["00:00", "06:00"], unit: clock, source: "CAR 7-J-III (2024 revision): night = 0000-0600"}
  night_max_fdp: {value: 10, unit: h, source: "CAR 7-J-III: FDP encroaching night"}
  night_max_landings: {value: 6, unit: count, source: "DGCA one-time exemption, 5-6 Dec 2025 (Business Today, 5 Dec 2025)"}
  max_consecutive_nights: {value: 2, unit: count, source: "CAR 7-J-III: max consecutive night duties"}
  min_rest: {value: 12, unit: h, source: "CAR 7-J-III: rest >= preceding duty, minimum 12 h"}
  weekly_rest: {value: 48, unit: h, source: "CAR 7-J-III: 48 h weekly rest incl. two local nights (was 36 h)"}
  ft_7d: {value: 35, unit: h, source: "CAR 7-J-III: cumulative flight time, 7 consecutive days"}
  ft_28d: {value: 100, unit: h, source: "CAR 7-J-III: cumulative flight time, 28 consecutive days"}
  duty_7d: {value: 60, unit: h, source: "CAR 7-J-III: cumulative duty, 7 consecutive days"}
  duty_28d: {value: 190, unit: h, source: "CAR 7-J-III: cumulative duty, 28 consecutive days"}
```

- [ ] **Step 5: Write `src/crew_roster/rules/__init__.py`**

```python
"""DGCA rulesets, loaded from YAML and converted to minutes / counts."""

from __future__ import annotations

from importlib.resources import files

import yaml
from pydantic import BaseModel, ConfigDict

RULESETS = ("dgca_current", "dgca_dec2025_exemption")


class Ruleset(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    label: str
    max_ft_per_duty: int
    max_fdp_by_landings: dict[int, int]
    night_start: int
    night_end: int
    night_max_fdp: int
    night_max_landings: int
    max_consecutive_nights: int
    min_rest: int
    weekly_rest: int
    ft_7d: int
    ft_28d: int
    duty_7d: int
    duty_28d: int
    sources: dict[str, str]


def _amount(value, unit: str) -> int:
    if unit == "h":
        return round(float(value) * 60)
    if unit == "count":
        return int(value)
    raise ValueError(f"unknown unit {unit!r}")


def _clock(text: str) -> int:
    h, m = str(text).split(":")
    return int(h) * 60 + int(m)


def load(name: str = "dgca_current") -> Ruleset:
    if name not in RULESETS:
        raise ValueError(f"unknown ruleset {name!r}; choose from {RULESETS}")
    text = files("crew_roster.rules").joinpath(f"{name}.yaml").read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    lim = raw["limits"]

    def v(key: str) -> int:
        return _amount(lim[key]["value"], lim[key]["unit"])

    fdp = lim["max_fdp_by_landings"]
    night = lim["night_window"]["value"]
    return Ruleset(
        name=raw["name"], label=raw["label"],
        max_ft_per_duty=v("max_ft_per_duty"),
        max_fdp_by_landings={int(k): _amount(h, fdp["unit"]) for k, h in fdp["value"].items()},
        night_start=_clock(night[0]), night_end=_clock(night[1]),
        night_max_fdp=v("night_max_fdp"), night_max_landings=v("night_max_landings"),
        max_consecutive_nights=v("max_consecutive_nights"), min_rest=v("min_rest"),
        weekly_rest=v("weekly_rest"), ft_7d=v("ft_7d"), ft_28d=v("ft_28d"),
        duty_7d=v("duty_7d"), duty_28d=v("duty_28d"),
        sources={k: item["source"] for k, item in lim.items()},
    )
```

- [ ] **Step 6: Write `src/crew_roster/problem.py`**

```python
"""A rostering problem: duties to crew, pilots, their history, and the ruleset."""

from __future__ import annotations

from crew_roster.models import Duty, Flight, Frozen, Pilot, Turn
from crew_roster.rules import Ruleset


class Problem(Frozen):
    ruleset: Ruleset
    duties: list[Duty]
    pilots: list[Pilot]
    history: dict[str, list[Duty]] = {}
    turns: dict[str, Turn] = {}
    flights: dict[str, Flight] = {}
    sick: dict[str, frozenset[int]] = {}
    horizon_days: int = 7

    def pilot_map(self) -> dict[str, Pilot]:
        return {p.id: p for p in self.pilots}

    def duty_map(self) -> dict[str, Duty]:
        return {d.id: d for d in self.duties}

    def unavailable_days(self, pilot: Pilot) -> frozenset[int]:
        return pilot.unavailable_days | self.sick.get(pilot.id, frozenset())
```

- [ ] **Step 7: Write `src/crew_roster/roster/check.py` and `roster/__init__.py`**

`src/crew_roster/roster/check.py`:

```python
"""The single legality checker. Independent of the solver; everything is verified here."""

from __future__ import annotations

from crew_roster.models import Duty, Roster, Violation
from crew_roster.problem import Problem
from crew_roster.rules import Ruleset

WINDOWS = (("ft_7d", 7, "flight_time"), ("ft_28d", 28, "flight_time"),
           ("duty_7d", 7, "length"), ("duty_28d", 28, "length"))


def duty_violations(duty: Duty, rs: Ruleset) -> list[Violation]:
    """Rules that depend only on the duty itself (no pilot can make it legal)."""
    out: list[Violation] = []

    def add(rule: str, value: int, limit: int, message: str) -> None:
        out.append(Violation(rule=rule, duty_id=duty.id, day=duty.day, value=value,
                             limit=limit, message=message))

    if duty.flight_time > rs.max_ft_per_duty:
        add("max_ft_per_duty", duty.flight_time, rs.max_ft_per_duty, "flight time in one duty")
    top = max(rs.max_fdp_by_landings)
    if duty.landings > top:
        add("max_landings", duty.landings, top, "landings in one duty")
    elif duty.length > rs.max_fdp_by_landings[duty.landings]:
        add("max_fdp", duty.length, rs.max_fdp_by_landings[duty.landings],
            f"duty period with {duty.landings} landings")
    if duty.night:
        if duty.length > rs.night_max_fdp:
            add("night_max_fdp", duty.length, rs.night_max_fdp, "night duty period")
        if duty.landings > rs.night_max_landings:
            add("night_max_landings", duty.landings, rs.night_max_landings,
                "landings in a night duty")
    return out


def pilot_violations(problem: Problem, roster: Roster, pilot_id: str) -> list[Violation]:
    rs, horizon = problem.ruleset, problem.horizon_days
    pilot = problem.pilot_map()[pilot_id]
    duties = problem.duty_map()
    sick = problem.sick.get(pilot_id, frozenset())
    off = problem.unavailable_days(pilot)
    out: list[Violation] = []

    def add(rule, duty_id=None, day=None, value=0, limit=0, message=""):
        out.append(Violation(rule=rule, pilot_id=pilot_id, duty_id=duty_id, day=day,
                             value=value, limit=limit, message=message))

    mine: list[Duty] = []
    for did, role in roster.duties_of(pilot_id):
        d = duties.get(did)
        if d is None:
            add("unknown_duty", did)
            continue
        mine.append(d)
        if role != pilot.rank:
            add("wrong_rank", did, d.day, message=f"{pilot.rank} rostered as {role}")
        if d.base != pilot.base:
            add("wrong_base", did, d.day, message=f"{pilot.base} pilot on a {d.base} duty")
        if d.day in off:
            add("sick" if d.day in sick else "unavailable", did, d.day,
                message=f"not available on day {d.day}")

    timeline = sorted(problem.history.get(pilot_id, []) + mine, key=lambda d: (d.report, d.id))
    for a, b in zip(timeline, timeline[1:]):
        need, gap = max(rs.min_rest, a.length), b.report - a.release
        if gap < need:
            add("min_rest", b.id, b.day, gap, need, f"rest before duty {b.id}")

    for t in range(horizon):
        for rule, span, attr in WINDOWS:
            lo = t - span + 1
            total = sum(getattr(d, attr) for d in timeline if lo <= d.day <= t)
            limit = getattr(rs, rule)
            if total > limit:
                add(rule, None, t, total, limit, f"{span}-day total ending day {t}")

    busy = {k for d in timeline for k in d.touched_days()}
    for t in range(horizon):
        if not any(s not in busy and s + 1 not in busy for s in range(t - 6, t)):
            add("weekly_rest", None, t, 0, rs.weekly_rest,
                f"no 2 consecutive free days in the 7 days ending day {t}")

    nights = {d.day for d in timeline if d.night}
    k = rs.max_consecutive_nights
    for t in range(-k, horizon - k):
        if all(day in nights for day in range(t, t + k + 1)):
            add("consecutive_nights", None, t + k, k + 1, k,
                f"{k + 1} night duties in a row ending day {t + k}")
    return out


def check(problem: Problem, roster: Roster) -> list[Violation]:
    duties, pilots = problem.duty_map(), problem.pilot_map()
    out: list[Violation] = []
    for did in roster.assignments:
        if did in duties:
            out += duty_violations(duties[did], problem.ruleset)
    for pid in sorted({p for _, _, p in roster.slots()}):
        if pid not in pilots:
            out.append(Violation(rule="unknown_pilot", pilot_id=pid))
            continue
        out += pilot_violations(problem, roster, pid)
    return out
```

`src/crew_roster/roster/__init__.py`:

```python
from crew_roster.roster.check import WINDOWS, check, duty_violations, pilot_violations

__all__ = ["WINDOWS", "check", "duty_violations", "pilot_violations"]
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/test_rules.py tests/test_check.py -q`
Expected: `17 passed`.

- [ ] **Step 9: Commit and push**

```bash
uv run ruff check src tests && uv run ruff format src tests
git add -A
git commit -m "feat: DGCA rulesets and independent legality checker" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

### Task 3: Duty builder (step 1 optimisation)

**Files:**
- Create: `src/crew_roster/duties/__init__.py`, `src/crew_roster/duties/builder.py`
- Modify: `src/crew_roster/problem.py` (add `build_problem`), `tests/conftest.py` (add `problem` fixture)
- Test: `tests/test_duties.py`

**Interfaces:**
- Consumes: `Turn`, `Flight`, `Duty`, `is_night` (Task 1); `Ruleset`, `duty_violations` (Task 2).
- Produces:
  - `crew_roster.duties`: `MIN_SIT = 40`, `MAX_SIT = 180`, `REPORT_BEFORE = 60`, `RELEASE_AFTER = 30`; `make_duty(duty_id, base, turns: list[Turn], flights: dict[str, Flight], rs) -> Duty`; `candidate_chains(turns, flights, rs) -> list[tuple[Turn, ...]]`; `build(turns: list[Turn], flights: dict[str, Flight], rs, time_limit=10.0) -> list[Duty]`. Duty ids look like `"BOM-D3-02"` (base, report day, sequence) and are sorted by `(report, id)`.
  - `crew_roster.problem.build_problem(airline, ruleset) -> Problem`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/conftest.py`:

```python
from crew_roster.problem import build_problem
from crew_roster.rules import load


@pytest.fixture(scope="session")
def problem(airline):
    return build_problem(airline, load("dgca_current"))
```

`tests/test_duties.py`:

```python
from crew_roster.duties import MIN_SIT
from crew_roster.problem import build_problem
from crew_roster.roster.check import duty_violations
from crew_roster.rules import load


def test_every_turn_in_exactly_one_duty(problem, airline):
    seen = [t for d in problem.duties for t in d.turn_ids]
    assert sorted(seen) == sorted(airline.turns)


def test_duties_are_legal_and_well_formed(problem):
    assert len({d.id for d in problem.duties}) == len(problem.duties)
    for d in problem.duties:
        assert duty_violations(d, problem.ruleset) == [], d.id
        fl = [problem.flights[f] for f in d.flight_ids]
        assert fl[0].origin == d.base == fl[-1].dest
        assert d.report == fl[0].dep - 60 and d.release == fl[-1].arr + 30
        assert d.landings == len(fl) <= 4
        assert all(b.dep - a.arr >= MIN_SIT for a, b in zip(fl, fl[1:]))


def test_builder_merges_some_turns(problem, airline):
    assert len(problem.duties) < len(airline.turns)


def test_exemption_allows_merging_night_turns(airline):
    cur = build_problem(airline, load("dgca_current"))
    exm = build_problem(airline, load("dgca_dec2025_exemption"))
    assert len(exm.duties) < len(cur.duties)
    assert any(d.night and d.landings > 2 for d in exm.duties)
    assert not any(d.night and d.landings > 2 for d in cur.duties)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_duties.py -q`
Expected: ERROR with `ModuleNotFoundError: No module named 'crew_roster.duties'`.

- [ ] **Step 3: Write `src/crew_roster/duties/builder.py` and `duties/__init__.py`**

`src/crew_roster/duties/builder.py`:

```python
"""Step 1: group out-and-back turns into duties with the fewest duties (CP-SAT set partitioning)."""

from __future__ import annotations

from collections import defaultdict

from ortools.sat.python import cp_model

from crew_roster.models import Duty, Flight, Turn, is_night
from crew_roster.rules import Ruleset

MIN_SIT = 40    # minutes between arriving at base and the next departure in the same duty
MAX_SIT = 180   # longer sits are not worth pairing
REPORT_BEFORE = 60
RELEASE_AFTER = 30


def make_duty(duty_id: str, base: str, turns: list[Turn], flights: dict[str, Flight],
              rs: Ruleset) -> Duty:
    turns = sorted(turns, key=lambda t: flights[t.out_id].dep)
    fl = [flights[f] for t in turns for f in t.flight_ids]
    report, release = fl[0].dep - REPORT_BEFORE, fl[-1].arr + RELEASE_AFTER
    return Duty(id=duty_id, base=base, report=report, release=release,
                flight_time=sum(f.block for f in fl), landings=len(fl),
                night=is_night(report, release, rs.night_start, rs.night_end),
                turn_ids=tuple(t.id for t in turns), flight_ids=tuple(f.id for f in fl))


def candidate_chains(turns: list[Turn], flights: dict[str, Flight],
                     rs: Ruleset) -> list[tuple[Turn, ...]]:
    """Every single turn, plus every legal pair of turns from the same base."""
    # Imported here, not at module top: crew_roster.roster imports replan -> disrupt -> duties,
    # so a top-level import would be circular.
    from crew_roster.roster.check import duty_violations

    chains: list[tuple[Turn, ...]] = [(t,) for t in turns]
    by_base: dict[str, list[Turn]] = defaultdict(list)
    for t in turns:
        by_base[t.base].append(t)
    for base, ts in by_base.items():
        ts.sort(key=lambda t: (flights[t.out_id].dep, t.id))
        for a in ts:
            a_end = flights[a.back_id].arr
            for b in ts:
                if MIN_SIT <= flights[b.out_id].dep - a_end <= MAX_SIT:
                    if not duty_violations(make_duty("tmp", base, [a, b], flights, rs), rs):
                        chains.append((a, b))
    return chains


def build(turns: list[Turn], flights: dict[str, Flight], rs: Ruleset,
          time_limit: float = 10.0) -> list[Duty]:
    chains = candidate_chains(turns, flights, rs)
    m = cp_model.CpModel()
    y = [m.new_bool_var(f"chain{i}") for i in range(len(chains))]
    cover = defaultdict(list)
    for i, chain in enumerate(chains):
        for t in chain:
            cover[t.id].append(y[i])
    for t in turns:
        m.add_exactly_one(cover[t.id])
    m.minimize(sum(y))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.max_time_in_seconds = time_limit
    status = solver.solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"duty builder: {solver.status_name(status)}")

    picked = [chains[i] for i in range(len(chains)) if solver.value(y[i])]
    drafts = sorted((make_duty("tmp", c[0].base, list(c), flights, rs) for c in picked),
                    key=lambda d: (d.base, d.report, d.turn_ids))
    seq: dict[tuple[str, int], int] = defaultdict(int)
    duties = []
    for d in drafts:
        seq[d.base, d.day] += 1
        duties.append(d.model_copy(update={"id": f"{d.base}-D{d.day}-{seq[d.base, d.day]:02d}"}))
    return sorted(duties, key=lambda d: (d.report, d.id))
```

`src/crew_roster/duties/__init__.py`:

```python
from crew_roster.duties.builder import (
    MAX_SIT,
    MIN_SIT,
    RELEASE_AFTER,
    REPORT_BEFORE,
    build,
    candidate_chains,
    make_duty,
)

__all__ = ["MAX_SIT", "MIN_SIT", "RELEASE_AFTER", "REPORT_BEFORE", "build",
           "candidate_chains", "make_duty"]
```

- [ ] **Step 4: Add `build_problem` to `src/crew_roster/problem.py`**

Append:

```python
def build_problem(airline, ruleset: Ruleset) -> Problem:
    from crew_roster.duties import build  # local import avoids a cycle via roster.check

    duties = build(list(airline.turns.values()), airline.flights, ruleset)
    return Problem(ruleset=ruleset, duties=duties, pilots=airline.pilots,
                   history=airline.history, turns=airline.turns, flights=airline.flights,
                   horizon_days=airline.days)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_duties.py -q`
Expected: `4 passed` (a few seconds).

- [ ] **Step 6: Commit and push**

```bash
uv run ruff check src tests && uv run ruff format src tests
git add -A
git commit -m "feat: CP-SAT duty builder (turns -> duties)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

### Task 4: Roster solver (step 2 optimisation), cache and `crew-solve`

**Files:**
- Create: `src/crew_roster/roster/solver.py`, `src/crew_roster/roster/diff.py`, `src/crew_roster/roster/cache.py`, `src/crew_roster/cli.py`, `src/crew_roster/roster/base_rosters/dgca_current.json`, `src/crew_roster/roster/base_rosters/dgca_dec2025_exemption.json`
- Modify: `src/crew_roster/roster/__init__.py`, `tests/conftest.py`, `pyproject.toml` (`[project.scripts]`)
- Test: `tests/test_solver.py`

**Interfaces:**
- Consumes: `Problem` (Task 2), `check`, `duty_violations`, `WINDOWS` (Task 2), `build_problem` (Task 3), `generate` (Task 1).
- Produces:
  - `crew_roster.roster.solver`: `W_UNCOVERED = 10_000_000`, `W_CHANGE = 10_000`; `SolveResult(roster, uncovered: list[tuple[str,str]], illegal_duties: list[str], status: str, seconds: float, changes: int = 0, pilots_used: dict[str,int] = {})`; `solve(problem, base: Roster|None = None, locked_before: int|None = None, time_limit=10.0, minimise_pilots=False, change_weight=W_CHANGE, workers=8) -> SolveResult`.
  - `crew_roster.roster.diff.count_changes(problem, base, new) -> int` (base slots on still-existing duties whose pilot differs).
  - `crew_roster.roster.cache`: `CACHE_DIR`, `cache_path(ruleset_name) -> Path`, `load_base_roster(problem, time_limit=10.0) -> Roster`.
  - CLI `crew-solve [--ruleset NAME] [--time-limit S] [--save]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/conftest.py`:

```python
from crew_roster.roster.solver import solve


@pytest.fixture(scope="session")
def base_result(problem):
    return solve(problem, time_limit=10)
```

`tests/test_solver.py`:

```python
import pytest
from factories import mk_duty, mk_pilot, mk_problem, mk_roster

from crew_roster.data import generate
from crew_roster.models import DAY
from crew_roster.problem import build_problem
from crew_roster.roster import cache
from crew_roster.roster.check import check
from crew_roster.roster.solver import solve
from crew_roster.rules import load

PILOTS = [mk_pilot("C1"), mk_pilot("C2"), mk_pilot("C3"),
          mk_pilot("F1", rank="FO"), mk_pilot("F2", rank="FO"), mk_pilot("F3", rank="FO")]


def test_solver_respects_rest_and_reports_shortage():
    d1 = mk_duty("D1", 0, "06:00", 10, ft_hours=6)   # release 16:00
    d2 = mk_duty("D2", 1, "02:00", 6, ft_hours=4)    # only 10 h later
    p = mk_problem([d1, d2], PILOTS)
    res = solve(p, time_limit=5)
    assert res.uncovered == [] and check(p, res.roster) == []
    assert res.roster.get("D1", "CPT") != res.roster.get("D2", "CPT")

    short = mk_problem([d1, d2], [PILOTS[0], PILOTS[3], PILOTS[4]])  # one captain
    res = solve(short, time_limit=5)
    assert [r for _, r in res.uncovered] == ["CPT"]
    assert check(short, res.roster) == []


def test_unavailable_pilot_is_not_used():
    d = mk_duty("D1", 2, "06:00", 8, ft_hours=6)
    p = mk_problem([d], [mk_pilot("C1", off=[2]), mk_pilot("C2"), mk_pilot("F1", rank="FO")])
    assert solve(p, time_limit=5).roster.get("D1", "CPT") == "C2"


def test_illegal_duty_is_left_uncovered():
    bad = mk_duty("BAD", 1, "06:00", 10, ft_hours=9)  # 9 h flight time
    res = solve(mk_problem([bad], PILOTS), time_limit=5)
    assert res.illegal_duties == ["BAD"] and len(res.uncovered) == 2


def test_resolve_from_base_changes_nothing():
    duties = [mk_duty(f"D{k}", k, "06:00", 8, ft_hours=6) for k in range(3)]
    p = mk_problem(duties, PILOTS)
    first = solve(p, time_limit=5)
    again = solve(p, base=first.roster, time_limit=5)
    assert again.changes == 0 and again.roster == first.roster


def test_locked_duties_keep_their_crew():
    duties = [mk_duty(f"D{k}", k, "06:00", 8, ft_hours=6) for k in range(3)]
    p = mk_problem(duties, PILOTS)
    manual = mk_roster({f"D{k}": {"CPT": "C3", "FO": "F3"} for k in range(3)})
    assert check(p, manual) == []
    res = solve(p, base=manual, locked_before=DAY, change_weight=0, time_limit=5)
    assert res.roster.assignments["D0"] == {"CPT": "C3", "FO": "F3"}


def test_base_roster_is_legal_and_fully_crewed(problem, base_result):
    assert check(problem, base_result.roster) == []
    assert base_result.uncovered == []


def test_cache_round_trip(problem, base_result, tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    cache.cache_path(problem.ruleset.name).write_text(base_result.roster.model_dump_json())
    assert cache.load_base_roster(problem) == base_result.roster


@pytest.mark.slow
def test_solve_is_deterministic(problem, base_result):
    assert solve(problem, time_limit=10).roster == base_result.roster


@pytest.mark.slow
def test_exemption_roster_is_legal():
    p = build_problem(generate(), load("dgca_dec2025_exemption"))
    res = solve(p, time_limit=10)
    assert check(p, res.roster) == [] and res.uncovered == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_solver.py -q`
Expected: ERROR with `ModuleNotFoundError: No module named 'crew_roster.roster.solver'`.

- [ ] **Step 3: Write `src/crew_roster/roster/diff.py` (count only; Task 5 extends it)**

```python
"""Comparing rosters."""

from __future__ import annotations

from crew_roster.models import Roster
from crew_roster.problem import Problem


def count_changes(problem: Problem, base: Roster, new: Roster) -> int:
    """Base slots on duties that still exist whose pilot is different (or now empty)."""
    ids = {d.id for d in problem.duties}
    return sum(1 for did, role, pid in base.slots() if did in ids and new.get(did, role) != pid)
```

- [ ] **Step 4: Write `src/crew_roster/roster/solver.py`**

```python
"""Step 2: CP-SAT pilot assignment — base roster, minimum-change re-plan, crew sizing.

Every hard constraint mirrors a rule in roster/check.py, so a solution is legal by construction;
check() still verifies it independently. Assignments on locked (already started) duties are
fixed; constraints that the locked part already breaks are not made worse, never infeasible.
"""

from __future__ import annotations

import time
from collections import defaultdict

from ortools.sat.python import cp_model

from crew_roster.models import DAY, ROLES, Duty, Frozen, Roster
from crew_roster.problem import Problem
from crew_roster.roster.check import WINDOWS, duty_violations
from crew_roster.roster.diff import count_changes

W_UNCOVERED = 10_000_000
W_CHANGE = 10_000


class SolveResult(Frozen):
    roster: Roster
    uncovered: list[tuple[str, str]]
    illegal_duties: list[str]
    status: str
    seconds: float
    changes: int = 0
    pilots_used: dict[str, int] = {}


def solve(problem: Problem, base: Roster | None = None, locked_before: int | None = None,
          time_limit: float = 10.0, minimise_pilots: bool = False,
          change_weight: int = W_CHANGE, workers: int = 8) -> SolveResult:
    t0 = time.perf_counter()
    rs, horizon = problem.ruleset, problem.horizon_days
    legal = [d for d in problem.duties if not duty_violations(d, rs)]
    illegal = [d.id for d in problem.duties if duty_violations(d, rs)]
    rank_of = {p.id: p.rank for p in problem.pilots}
    m = cp_model.CpModel()
    x: dict[tuple[str, str], cp_model.IntVar] = {}
    forced: set[tuple[str, str]] = set()
    mine: dict[str, list[Duty]] = defaultdict(list)

    def is_locked(d: Duty) -> bool:
        return locked_before is not None and d.report < locked_before

    for p in problem.pilots:
        off = problem.unavailable_days(p)
        for d in legal:
            if d.base != p.base or d.day in off:
                continue
            in_base = base is not None and base.get(d.id, p.rank) == p.id
            if is_locked(d) and not in_base:
                continue
            v = m.new_bool_var(f"x[{p.id},{d.id}]")
            x[p.id, d.id] = v
            mine[p.id].append(d)
            if is_locked(d):
                m.add(v == 1)
                forced.add((p.id, d.id))

    def add_le(terms: list[tuple[int, tuple[str, str]]], limit: int) -> None:
        terms = [(c, k) for c, k in terms if k in x and c]
        if sum(c for c, _ in terms) <= limit:
            return
        if sum(c for c, k in terms if k in forced) > limit:
            for _, k in terms:  # already broken by locked duties: just don't add more
                if k not in forced:
                    m.add(x[k] == 0)
            return
        m.add(sum(c * x[k] for c, k in terms) <= limit)

    # coverage (soft)
    by_slot: dict[tuple[str, str], list] = defaultdict(list)
    for (pid, did), v in x.items():
        by_slot[did, rank_of[pid]].append(v)
    u = {}
    for d in legal:
        for role in ROLES:
            u[d.id, role] = m.new_bool_var(f"u[{d.id},{role}]")
            m.add(sum(by_slot[d.id, role]) + u[d.id, role] == 1)

    for p in problem.pilots:
        ds = sorted(mine[p.id], key=lambda d: (d.report, d.id))
        hist = problem.history.get(p.id, [])

        def key(d: Duty, pid: str = p.id) -> tuple[str, str]:
            return (pid, d.id)

        for k in range(horizon):  # one duty per calendar day (operational rule)
            add_le([(1, key(d)) for d in ds if d.day == k], 1)

        if hist:  # rest after the last history duty
            last = max(hist, key=lambda h: h.release)
            need = max(rs.min_rest, last.length)
            for d in ds:
                if d.report - last.release < need:
                    add_le([(1, key(d))], 0)

        for i, a in enumerate(ds):  # rest between roster duties
            need = max(rs.min_rest, a.length)
            for b in ds[i + 1:]:
                if b.report - a.release >= need:
                    break
                add_le([(1, key(a)), (1, key(b))], 1)

        for t in range(horizon):  # rolling flight / duty time incl. history
            for rule, span, attr in WINDOWS:
                lo = t - span + 1
                used = sum(getattr(h, attr) for h in hist if lo <= h.day <= t)
                add_le([(getattr(d, attr), key(d)) for d in ds if lo <= d.day <= t],
                       getattr(rs, rule) - used)

        busy_hist = {k for h in hist for k in h.touched_days()}  # weekly rest
        touching: dict[int, list[Duty]] = defaultdict(list)
        for d in ds:
            for k in d.touched_days():
                touching[k].append(d)
        block: dict[int, object] = {}
        for s in range(-6, horizon - 1):
            days = (s, s + 1)
            if any(k in busy_hist for k in days):
                block[s] = False
                continue
            ds_touch = list({d.id: d for k in days for d in touching.get(k, [])}.values())
            if any(key(d) in forced for d in ds_touch):
                block[s] = False
            elif not ds_touch:
                block[s] = True
            else:
                o = m.new_bool_var(f"rest[{p.id},{s}]")
                for d in ds_touch:
                    m.add_implication(o, x[key(d)].Not())
                block[s] = o
        for t in range(horizon):
            opts = [block[s] for s in range(t - 6, t)]
            if any(o is True for o in opts):
                continue
            lits = [o for o in opts if o is not False]
            if lits:
                m.add_bool_or(lits)

        k_n = rs.max_consecutive_nights  # consecutive night duties
        hist_nights = {h.day for h in hist if h.night}
        for t in range(-k_n, horizon - k_n):
            window = range(t, t + k_n + 1)
            hn = sum(1 for day in window if day in hist_nights)
            add_le([(1, key(d)) for d in ds if d.night and d.day in window], k_n - hn)

    objective = [W_UNCOVERED * sum(u.values())]
    if minimise_pilots:
        for p in problem.pilots:
            if mine[p.id]:
                used = m.new_bool_var(f"used[{p.id}]")
                for d in mine[p.id]:
                    m.add_implication(x[p.id, d.id], used)
                objective.append(used)
    else:
        groups: dict[tuple[str, str], list] = defaultdict(list)
        for p in problem.pilots:
            tot = m.new_int_var(0, horizon * DAY, f"ft[{p.id}]")
            m.add(tot == sum(d.flight_time * x[p.id, d.id] for d in mine[p.id]))
            groups[p.base, p.rank].append(tot)
        for g in groups.values():
            hi = m.new_int_var(0, horizon * DAY, "")
            lo = m.new_int_var(0, horizon * DAY, "")
            m.add_max_equality(hi, g)
            m.add_min_equality(lo, g)
            objective.append(hi - lo)
    if base is not None and change_weight:
        legal_ids = {d.id for d in legal}
        kept = [x[pid, did] for did, _, pid in base.slots()
                if did in legal_ids and (pid, did) in x]
        objective.append(-change_weight * sum(kept))
        for (pid, did), v in x.items():
            m.add_hint(v, int(base.get(did, rank_of[pid]) == pid))
    m.minimize(sum(objective))

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = workers
    solver.parameters.interleave_search = workers > 1  # deterministic parallel search
    solver.parameters.random_seed = 0
    solver.parameters.max_deterministic_time = time_limit
    solver.parameters.max_time_in_seconds = 3 * time_limit  # safety net only
    status = solver.solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"roster solver: {solver.status_name(status)}")

    assignments: dict[str, dict[str, str]] = defaultdict(dict)
    for (pid, did), v in x.items():
        if solver.value(v):
            assignments[did][rank_of[pid]] = pid
    roster = Roster(assignments=dict(assignments))
    uncovered = sorted(k for k, v in u.items() if solver.value(v))
    uncovered += [(did, r) for did in illegal for r in ROLES]
    used_by_rank: dict[str, int] = defaultdict(int)
    for pid in {p for _, _, p in roster.slots()}:
        used_by_rank[rank_of[pid]] += 1
    return SolveResult(
        roster=roster, uncovered=uncovered, illegal_duties=illegal,
        status=solver.status_name(status), seconds=round(time.perf_counter() - t0, 3),
        changes=count_changes(problem, base, roster) if base is not None else 0,
        pilots_used=dict(used_by_rank),
    )
```

- [ ] **Step 5: Write `src/crew_roster/roster/cache.py` and update `roster/__init__.py`**

`src/crew_roster/roster/cache.py`:

```python
"""Base rosters are solved once and shipped as JSON so the API starts instantly."""

from __future__ import annotations

from pathlib import Path

from crew_roster.models import Roster
from crew_roster.problem import Problem
from crew_roster.roster.check import check
from crew_roster.roster.solver import solve

CACHE_DIR = Path(__file__).with_name("base_rosters")


def cache_path(ruleset_name: str) -> Path:
    return CACHE_DIR / f"{ruleset_name}.json"


def load_base_roster(problem: Problem, time_limit: float = 10.0) -> Roster:
    """Cached roster if it still fits this problem and is legal, else solve now."""
    path = cache_path(problem.ruleset.name)
    if path.exists():
        roster = Roster.model_validate_json(path.read_text(encoding="utf-8"))
        if set(roster.assignments) <= {d.id for d in problem.duties} and not check(problem, roster):
            return roster
    return solve(problem, time_limit=time_limit).roster
```

`src/crew_roster/roster/__init__.py`:

```python
from crew_roster.roster.cache import cache_path, load_base_roster
from crew_roster.roster.check import WINDOWS, check, duty_violations, pilot_violations
from crew_roster.roster.diff import count_changes
from crew_roster.roster.solver import W_CHANGE, W_UNCOVERED, SolveResult, solve

__all__ = ["W_CHANGE", "W_UNCOVERED", "WINDOWS", "SolveResult", "cache_path", "check",
           "count_changes", "duty_violations", "load_base_roster", "pilot_violations", "solve"]
```

- [ ] **Step 6: Run the fast tests**

Run: `uv run pytest tests/test_solver.py -q` (about 20–40 s on the owner's laptop)
Expected: `7 passed, 2 deselected`.

If `test_base_roster_is_legal_and_fully_crewed` fails **only** because `uncovered` is non-empty (`check` is clean), the network is too tight for 30 pilots per base. Remove `("BOM", "16:30")` from `TURN_TEMPLATES["DEL"]` and/or `("PNQ", "16:00")` from `TURN_TEMPLATES["BOM"]` in `data/airline.py`, one at a time, until it passes. Then re-run `tests/test_data.py` (per-day flight count must stay within 40–46). If `check` reports violations, that is a solver/checker mismatch bug: debug it with superpowers:systematic-debugging, don't tune data.

- [ ] **Step 7: Run the slow tests (tell the owner first: about 30–60 s)**

Run: `uv run pytest tests/test_solver.py -m slow -q`
Expected: `2 passed`. If `test_solve_is_deterministic` fails, set the `workers` default to `1` in `solve` (single-worker CP-SAT with a deterministic time limit is deterministic), then re-run Steps 6–7.

- [ ] **Step 8: Write `src/crew_roster/cli.py` and register it**

```python
"""crew-solve: solve the base roster for a ruleset and optionally cache it."""

from __future__ import annotations

import argparse

from crew_roster.data import generate
from crew_roster.problem import build_problem
from crew_roster.roster.cache import cache_path
from crew_roster.roster.check import check
from crew_roster.roster.solver import solve
from crew_roster.rules import RULESETS, load


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crew-solve")
    ap.add_argument("--ruleset", default="dgca_current", choices=RULESETS)
    ap.add_argument("--time-limit", type=float, default=10.0)
    ap.add_argument("--save", action="store_true", help="write the roster to the package cache")
    args = ap.parse_args(argv)

    problem = build_problem(generate(), load(args.ruleset))
    res = solve(problem, time_limit=args.time_limit)
    violations = check(problem, res.roster)
    print(f"{args.ruleset}: {len(problem.duties)} duties, {len(res.uncovered)} uncovered slots, "
          f"{len(violations)} violations, {res.status}, {res.seconds}s, used {res.pilots_used}")
    if args.save:
        path = cache_path(args.ruleset)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(res.roster.model_dump_json(indent=1), encoding="utf-8")
        print(f"saved {path}")
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

Add to `pyproject.toml`:

```toml
[project.scripts]
crew-solve = "crew_roster.cli:main"
```

Then:

```bash
uv sync
uv run crew-solve --save
uv run crew-solve --ruleset dgca_dec2025_exemption --save
```

Expected: each prints `0 uncovered slots, 0 violations` and `saved ...base_rosters\<name>.json`. The exemption run should show fewer duties than the current one.

- [ ] **Step 9: Commit and push**

```bash
uv run ruff check src tests && uv run ruff format src tests
git add -A
git commit -m "feat: CP-SAT roster solver, cached base rosters, crew-solve CLI" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

### Task 5: Disruptions, change explanations and minimum-change re-plan

**Files:**
- Create: `src/crew_roster/disrupt/__init__.py`, `src/crew_roster/roster/replan.py`
- Modify: `src/crew_roster/roster/diff.py` (add `Change`, `diff`), `src/crew_roster/roster/__init__.py`
- Test: `tests/test_disrupt.py`, `tests/test_replan.py`

**Interfaces:**
- Consumes: `make_duty` (Task 3), `solve`, `SolveResult`, `count_changes` (Task 4), `pilot_violations` (Task 2).
- Produces:
  - `crew_roster.disrupt`: `PilotSick(kind="sick", pilot_id, from_day, to_day)`, `FlightDelay(kind="delay", flight_id, minutes: 1..600)`, `FlightCancel(kind="cancel", flight_id)`, `Disruption` (discriminated union on `kind`), `apply(problem, disruptions) -> Problem` (never mutates; raises `ValueError` on unknown pilot or flight), `known_at(problem, disruption) -> int`, `lock_time(problem, disruptions) -> int | None`. A delay shifts the flight **and every later flight in the same duty** by the same minutes; a cancel removes the whole turn (both legs).
  - `crew_roster.roster.diff`: `Change(id, duty_id, role, old_pilot, new_pilot, reasons: list[Violation])`, `diff(problem, old, new) -> list[Change]`. Reason rules are checker rule names plus `"sick"` and `"knock_on"`.
  - `crew_roster.roster.replan`: `Replan(problem, result: SolveResult, changes: list[Change], locked_before: int | None)`, `replan(problem, base, disruptions, method="cpsat", time_limit=10.0) -> Replan` with methods `"cpsat"` and `"scratch"` (Task 6 adds `"greedy"`).

- [ ] **Step 1: Write the failing tests**

`tests/test_disrupt.py`:

```python
import pytest

from crew_roster.disrupt import FlightCancel, FlightDelay, PilotSick, apply, lock_time
from crew_roster.models import DAY


def test_apply_does_not_mutate(problem):
    before = problem.model_dump()
    apply(problem, [FlightDelay(flight_id="SK101-D2", minutes=90), PilotSick(
        pilot_id="DEL-C01", from_day=1, to_day=2)])
    assert problem.model_dump() == before


def test_delay_shifts_the_rest_of_the_duty(problem):
    d = next(d for d in problem.duties if "SK101-D2" in d.flight_ids)
    nd = apply(problem, [FlightDelay(flight_id="SK101-D2", minutes=90)]).duty_map()[d.id]
    assert nd.report == d.report + 90 and nd.release == d.release + 90


def test_cancel_removes_the_turn(problem):
    single = next(d for d in problem.duties if len(d.turn_ids) == 1)
    new = apply(problem, [FlightCancel(flight_id=single.flight_ids[0])])
    assert single.id not in new.duty_map()
    assert not set(single.flight_ids) & set(new.flights)

    double = next(d for d in problem.duties if len(d.turn_ids) == 2)
    new2 = apply(problem, [FlightCancel(flight_id=double.flight_ids[-1])])
    assert new2.duty_map()[double.id].landings == 2


def test_sick_marks_days_and_lock_time(problem):
    sick = PilotSick(pilot_id="BOM-F03", from_day=3, to_day=4)
    new = apply(problem, [sick])
    assert new.sick["BOM-F03"] == frozenset({3, 4})
    delay = FlightDelay(flight_id="SK101-D5", minutes=60)
    assert lock_time(problem, [sick, delay]) == 3 * DAY
    assert lock_time(problem, []) is None


def test_unknown_ids_are_rejected(problem):
    with pytest.raises(ValueError):
        apply(problem, [PilotSick(pilot_id="NOPE", from_day=1, to_day=1)])
    with pytest.raises(ValueError):
        apply(problem, [FlightCancel(flight_id="SK999-D1")])
```

`tests/test_replan.py`:

```python
import pytest

from crew_roster.disrupt import FlightCancel, FlightDelay, PilotSick
from crew_roster.models import DAY
from crew_roster.roster.check import check
from crew_roster.roster.replan import replan


def captain_on_day(problem, roster, day):
    did = next(d.id for d in problem.duties if d.day == day and roster.get(d.id, "CPT"))
    return roster.get(did, "CPT")


def test_sick_pilot_is_replaced_with_minimal_changes(problem, base_result):
    base = base_result.roster
    pid = captain_on_day(problem, base, 3)
    out = replan(problem, base, [PilotSick(pilot_id=pid, from_day=3, to_day=4)])
    roster, duties = out.result.roster, problem.duty_map()
    assert check(out.problem, roster) == []
    assert out.result.uncovered == []
    assert all(duties[d].day not in (3, 4) for d, _ in roster.duties_of(pid))
    for d in problem.duties:
        if d.report < 3 * DAY:
            assert roster.assignments.get(d.id) == base.assignments.get(d.id)
    assert any(v.rule == "sick" for c in out.changes for v in c.reasons)
    assert out.result.changes == len(out.changes) >= 1


def test_late_delay_is_repaired_legally(problem, base_result):
    out = replan(problem, base_result.roster, [FlightDelay(flight_id="SK115-D2", minutes=240)])
    assert check(out.problem, out.result.roster) == []
    assert out.result.uncovered == []
    for c in out.changes:
        assert c.reasons, c


def test_cancellation_needs_no_changes(problem, base_result):
    single = next(d for d in problem.duties if len(d.turn_ids) == 1 and d.day == 4)
    out = replan(problem, base_result.roster, [FlightCancel(flight_id=single.flight_ids[0])])
    assert check(out.problem, out.result.roster) == []
    assert out.result.changes == 0


@pytest.mark.slow
def test_scratch_changes_more_than_minimum_change(problem, base_result):
    pid = captain_on_day(problem, base_result.roster, 3)
    sick = [PilotSick(pilot_id=pid, from_day=3, to_day=4)]
    smart = replan(problem, base_result.roster, sick)
    scratch = replan(problem, base_result.roster, sick, method="scratch")
    assert check(scratch.problem, scratch.result.roster) == []
    assert scratch.result.changes >= smart.result.changes
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_disrupt.py tests/test_replan.py -q`
Expected: ERROR with `ModuleNotFoundError: No module named 'crew_roster.disrupt'`.

- [ ] **Step 3: Write `src/crew_roster/disrupt/__init__.py`**

```python
"""Disruptions and how they change a Problem. apply() always returns a new Problem."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import Field

from crew_roster.duties import make_duty
from crew_roster.models import DAY, Frozen
from crew_roster.problem import Problem


class PilotSick(Frozen):
    kind: Literal["sick"] = "sick"
    pilot_id: str
    from_day: int
    to_day: int


class FlightDelay(Frozen):
    kind: Literal["delay"] = "delay"
    flight_id: str
    minutes: int = Field(gt=0, le=600)


class FlightCancel(Frozen):
    kind: Literal["cancel"] = "cancel"
    flight_id: str


Disruption = Annotated[PilotSick | FlightDelay | FlightCancel, Field(discriminator="kind")]

DELAY_NOTICE = 120   # a delay becomes known 2 h before departure
CANCEL_NOTICE = 180  # a cancellation 3 h before


def known_at(problem: Problem, d: Disruption) -> int:
    if isinstance(d, PilotSick):
        return d.from_day * DAY
    dep = problem.flights[d.flight_id].dep
    return dep - (DELAY_NOTICE if isinstance(d, FlightDelay) else CANCEL_NOTICE)


def lock_time(problem: Problem, disruptions: Sequence[Disruption]) -> int | None:
    """Duties reporting before this minute have already started and keep their crew."""
    return min((known_at(problem, d) for d in disruptions), default=None)


def apply(problem: Problem, disruptions: Sequence[Disruption]) -> Problem:
    flights, turns = dict(problem.flights), dict(problem.turns)
    sick = dict(problem.sick)
    duties = {d.id: d for d in problem.duties}
    duty_of_turn = {t: d.id for d in problem.duties for t in d.turn_ids}
    pilot_ids = {p.id for p in problem.pilots}
    rs = problem.ruleset

    for dis in disruptions:
        if isinstance(dis, PilotSick):
            if dis.pilot_id not in pilot_ids:
                raise ValueError(f"unknown pilot {dis.pilot_id}")
            if dis.to_day < dis.from_day:
                raise ValueError("to_day must be >= from_day")
            days = frozenset(range(dis.from_day, dis.to_day + 1))
            sick[dis.pilot_id] = sick.get(dis.pilot_id, frozenset()) | days
            continue
        if dis.flight_id not in flights:
            raise ValueError(f"unknown or cancelled flight {dis.flight_id}")
        f = flights[dis.flight_id]
        did = duty_of_turn[f.turn_id]
        duty = duties[did]
        if isinstance(dis, FlightDelay):
            for fid in duty.flight_ids:
                g = flights[fid]
                if g.dep >= f.dep:
                    flights[fid] = g.model_copy(
                        update={"dep": g.dep + dis.minutes, "arr": g.arr + dis.minutes})
            duties[did] = make_duty(did, duty.base, [turns[t] for t in duty.turn_ids],
                                    flights, rs)
        else:
            turn = turns.pop(f.turn_id)
            for fid in turn.flight_ids:
                flights.pop(fid)
            remaining = [turns[t] for t in duty.turn_ids if t != turn.id]
            if remaining:
                duties[did] = make_duty(did, duty.base, remaining, flights, rs)
            else:
                del duties[did]

    return problem.model_copy(update={
        "flights": flights, "turns": turns, "sick": sick,
        "duties": sorted(duties.values(), key=lambda d: (d.report, d.id)),
    })


__all__ = ["CANCEL_NOTICE", "DELAY_NOTICE", "Disruption", "FlightCancel", "FlightDelay",
           "PilotSick", "apply", "known_at", "lock_time"]
```

- [ ] **Step 4: Extend `src/crew_roster/roster/diff.py` with `Change` and `diff`**

Replace the file with:

```python
"""Comparing rosters and explaining each change with checker reasons."""

from __future__ import annotations

from crew_roster.models import ROLES, Frozen, Roster, Violation
from crew_roster.problem import Problem
from crew_roster.roster.check import pilot_violations


class Change(Frozen):
    id: str
    duty_id: str
    role: str
    old_pilot: str | None
    new_pilot: str | None
    reasons: list[Violation]


def count_changes(problem: Problem, base: Roster, new: Roster) -> int:
    """Base slots on duties that still exist whose pilot is different (or now empty)."""
    ids = {d.id for d in problem.duties}
    return sum(1 for did, role, pid in base.slots() if did in ids and new.get(did, role) != pid)


def _key(v: Violation) -> tuple:
    return (v.rule, v.duty_id, v.day)


def _reasons(problem: Problem, old: Roster, new: Roster, duty_id: str, role: str,
             old_pid: str) -> list[Violation]:
    """Why old_pid could not keep this slot: what breaks if they did."""
    duty = problem.duty_map()[duty_id]
    if duty.day in problem.sick.get(old_pid, frozenset()):
        return [Violation(rule="sick", pilot_id=old_pid, duty_id=duty_id, day=duty.day,
                          message=f"reported sick for day {duty.day}")]
    trial = new
    old_slots = set(old.duties_of(old_pid))
    for slot in new.duties_of(old_pid):  # undo their new assignments, then give the slot back
        if slot not in old_slots:
            trial = trial.with_slot(*slot, None)
    trial = trial.with_slot(duty_id, role, old_pid)
    before = {_key(v) for v in pilot_violations(problem, new, old_pid)}
    found = [v for v in pilot_violations(problem, trial, old_pid) if _key(v) not in before]
    return found or [Violation(rule="knock_on", pilot_id=old_pid, duty_id=duty_id,
                               day=duty.day,
                               message="moved to free up cover or rebalance after the disruption")]


def diff(problem: Problem, old: Roster, new: Roster) -> list[Change]:
    duties = problem.duty_map()
    changes: list[Change] = []
    for did in sorted(duties, key=lambda i: (duties[i].report, i)):
        for role in ROLES:
            o, n = old.get(did, role), new.get(did, role)
            if o == n:
                continue
            reasons = _reasons(problem, old, new, did, role, o) if o else []
            changes.append(Change(id=f"C{len(changes) + 1}", duty_id=did, role=role,
                                  old_pilot=o, new_pilot=n, reasons=reasons))
    return changes
```

- [ ] **Step 5: Write `src/crew_roster/roster/replan.py` and update `roster/__init__.py`**

`src/crew_roster/roster/replan.py`:

```python
"""Apply disruptions and re-plan from the current roster."""

from __future__ import annotations

from collections.abc import Sequence

from crew_roster.disrupt import Disruption, apply, lock_time
from crew_roster.models import Frozen, Roster
from crew_roster.problem import Problem
from crew_roster.roster.diff import Change, diff
from crew_roster.roster.solver import SolveResult, solve


class Replan(Frozen):
    problem: Problem
    result: SolveResult
    changes: list[Change]
    locked_before: int | None


def replan(problem: Problem, base: Roster, disruptions: Sequence[Disruption],
           method: str = "cpsat", time_limit: float = 10.0) -> Replan:
    new = apply(problem, disruptions)
    lock = lock_time(problem, disruptions)
    if method == "cpsat":
        result = solve(new, base=base, locked_before=lock, time_limit=time_limit)
    elif method == "scratch":
        result = solve(new, base=base, locked_before=lock, time_limit=time_limit,
                       change_weight=0)
    else:
        raise ValueError(f"unknown method {method!r}")
    return Replan(problem=new, result=result, changes=diff(new, base, result.roster),
                  locked_before=lock)
```

`src/crew_roster/roster/__init__.py`:

```python
from crew_roster.roster.cache import cache_path, load_base_roster
from crew_roster.roster.check import WINDOWS, check, duty_violations, pilot_violations
from crew_roster.roster.diff import Change, count_changes, diff
from crew_roster.roster.replan import Replan, replan
from crew_roster.roster.solver import W_CHANGE, W_UNCOVERED, SolveResult, solve

__all__ = ["W_CHANGE", "W_UNCOVERED", "WINDOWS", "Change", "Replan", "SolveResult",
           "cache_path", "check", "count_changes", "diff", "duty_violations",
           "load_base_roster", "pilot_violations", "replan", "solve"]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_disrupt.py tests/test_replan.py -q` (about 30–60 s)
Expected: `8 passed, 1 deselected`.
Then (tell the owner first, about 30 s): `uv run pytest tests/test_replan.py -m slow -q` → `1 passed`.

- [ ] **Step 7: Run the whole fast suite, commit and push**

```bash
uv run pytest -q
uv run ruff check src tests && uv run ruff format src tests
git add -A
git commit -m "feat: disruptions, minimum-change re-plan and change reasons" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

---

### Task 6: Greedy baseline and crew sizing

**Files:**
- Create: `src/crew_roster/roster/greedy.py`, `src/crew_roster/roster/sizing.py`
- Modify: `src/crew_roster/roster/replan.py` (add `"greedy"` method), `src/crew_roster/roster/__init__.py`
- Test: `tests/test_greedy.py`, `tests/test_sizing.py`

**Interfaces:**
- Consumes: `check`, `pilot_violations`, `duty_violations` (Task 2), `solve`, `SolveResult`, `count_changes` (Task 4), `replan` (Task 5).
- Produces:
  - `crew_roster.roster.greedy.greedy_repair(problem, base, locked_before=None) -> SolveResult` (status `"GREEDY"`).
  - `crew_roster.roster.sizing`: `Sizing(base, ruleset, duties, pilots_available: dict[str,int], pilots_needed: dict[str,int], uncovered: int, proven_optimal: bool, seconds: float)`, `min_pilots_needed(problem, base, time_limit=15.0) -> Sizing`.
  - `replan(..., method="greedy")`.

- [ ] **Step 1: Write the failing tests**

`tests/test_greedy.py`:

```python
from crew_roster.disrupt import PilotSick
from crew_roster.roster.check import check
from crew_roster.roster.replan import replan


def test_greedy_repair_is_legal_and_cpsat_covers_at_least_as_much(problem, base_result):
    base = base_result.roster
    did = next(d.id for d in problem.duties if d.day == 2 and base.get(d.id, "FO"))
    sick = [PilotSick(pilot_id=base.get(did, "FO"), from_day=2, to_day=4)]
    greedy = replan(problem, base, sick, method="greedy")
    smart = replan(problem, base, sick)
    assert greedy.result.status == "GREEDY"
    assert check(greedy.problem, greedy.result.roster) == []
    assert len(smart.result.uncovered) <= len(greedy.result.uncovered)


def test_greedy_keeps_a_legal_roster_unchanged(problem, base_result):
    out = replan(problem, base_result.roster, [], method="greedy")
    assert out.result.changes == 0 and out.changes == []
```

`tests/test_sizing.py`:

```python
import pytest
from factories import mk_duty, mk_pilot, mk_problem

from crew_roster.data import generate
from crew_roster.problem import build_problem
from crew_roster.roster.sizing import min_pilots_needed
from crew_roster.rules import load

PILOTS = [mk_pilot(f"C{i}") for i in range(3)] + [mk_pilot(f"F{i}", rank="FO") for i in range(3)]


def test_one_crew_can_fly_three_spread_out_duties():
    duties = [mk_duty(f"D{k}", k, "06:00", 8, ft_hours=6) for k in range(3)]
    s = min_pilots_needed(mk_problem(duties, PILOTS), "DEL", time_limit=5)
    assert s.pilots_needed == {"CPT": 1, "FO": 1} and s.uncovered == 0


def test_overlapping_duties_need_two_crews():
    duties = [mk_duty("A", 0, "06:00", 8, ft_hours=6), mk_duty("B", 0, "07:00", 8, ft_hours=6)]
    s = min_pilots_needed(mk_problem(duties, PILOTS), "DEL", time_limit=5)
    assert s.pilots_needed == {"CPT": 2, "FO": 2}


@pytest.mark.slow
def test_exemption_needs_no_more_pilots_than_current_rules():
    airline = generate()
    cur = min_pilots_needed(build_problem(airline, load("dgca_current")), "BOM")
    exm = min_pilots_needed(build_problem(airline, load("dgca_dec2025_exemption")), "BOM")
    assert cur.uncovered == exm.uncovered == 0
    assert sum(exm.pilots_needed.values()) <= sum(cur.pilots_needed.values())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_greedy.py tests/test_sizing.py -q`
Expected: FAIL with `ValueError: unknown method 'greedy'` and `ModuleNotFoundError: No module named 'crew_roster.roster.sizing'`.

- [ ] **Step 3: Write `src/crew_roster/roster/greedy.py`**

```python
"""Baseline: drop broken slots, then fill each empty slot with the first legal pilot."""

from __future__ import annotations

import time

from crew_roster.models import ROLES, Roster, Violation
from crew_roster.problem import Problem
from crew_roster.roster.check import duty_violations, pilot_violations
from crew_roster.roster.diff import count_changes
from crew_roster.roster.solver import SolveResult


def _keys(vs: list[Violation]) -> set[tuple]:
    return {(v.rule, v.duty_id, v.day) for v in vs}


def greedy_repair(problem: Problem, base: Roster,
                  locked_before: int | None = None) -> SolveResult:
    t0 = time.perf_counter()
    duties, pilots = problem.duty_map(), problem.pilot_map()
    rs = problem.ruleset
    legal_ids = {d.id for d in problem.duties if not duty_violations(d, rs)}

    def unlocked(did: str) -> bool:
        return locked_before is None or duties[did].report >= locked_before

    roster = Roster(assignments={d: dict(c) for d, c in base.assignments.items()
                                 if d in legal_ids})

    def drop_target(pid: str, vs: list[Violation]) -> tuple[str, str] | None:
        mine = sorted(roster.duties_of(pid), key=lambda s: duties[s[0]].report, reverse=True)
        for v in vs:
            if v.duty_id and (v.duty_id, pilots[pid].rank) in mine and unlocked(v.duty_id):
                return (v.duty_id, pilots[pid].rank)
            if v.day is not None:
                for did, role in mine:  # latest unlocked duty on or before the breach day
                    if duties[did].day <= v.day and unlocked(did):
                        return (did, role)
        return None

    for pid in sorted({p for _, _, p in roster.slots()}):
        while vs := pilot_violations(problem, roster, pid):
            target = drop_target(pid, vs)
            if target is None:
                break
            roster = roster.with_slot(*target, None)

    for d in sorted(problem.duties, key=lambda d: (d.report, d.id)):
        if d.id not in legal_ids or not unlocked(d.id):
            continue
        for role in ROLES:
            if roster.get(d.id, role):
                continue
            for p in sorted(pilots.values(), key=lambda p: p.id):
                if p.rank != role or p.base != d.base:
                    continue
                if any(duties[o].day == d.day for o, _ in roster.duties_of(p.id)):
                    continue
                before = _keys(pilot_violations(problem, roster, p.id))
                trial = roster.with_slot(d.id, role, p.id)
                if _keys(pilot_violations(problem, trial, p.id)) <= before:
                    roster = trial
                    break

    uncovered = [(d.id, r) for d in problem.duties for r in ROLES if roster.get(d.id, r) is None]
    return SolveResult(roster=roster, uncovered=uncovered,
                       illegal_duties=sorted(set(duties) - legal_ids), status="GREEDY",
                       seconds=round(time.perf_counter() - t0, 3),
                       changes=count_changes(problem, base, roster))
```

- [ ] **Step 4: Write `src/crew_roster/roster/sizing.py`**

```python
"""Crew sizing: the fewest pilots per rank at one base that still crew every duty."""

from __future__ import annotations

from collections import Counter

from crew_roster.models import Frozen
from crew_roster.problem import Problem
from crew_roster.roster.solver import solve


class Sizing(Frozen):
    base: str
    ruleset: str
    duties: int
    pilots_available: dict[str, int]
    pilots_needed: dict[str, int]
    uncovered: int
    proven_optimal: bool
    seconds: float


def min_pilots_needed(problem: Problem, base: str, time_limit: float = 15.0) -> Sizing:
    sub = problem.model_copy(update={
        "duties": [d for d in problem.duties if d.base == base],
        "pilots": [p for p in problem.pilots if p.base == base],
    })
    res = solve(sub, time_limit=time_limit, minimise_pilots=True)
    return Sizing(base=base, ruleset=problem.ruleset.name, duties=len(sub.duties),
                  pilots_available=dict(Counter(p.rank for p in sub.pilots)),
                  pilots_needed=res.pilots_used, uncovered=len(res.uncovered),
                  proven_optimal=res.status == "OPTIMAL", seconds=res.seconds)
```

- [ ] **Step 5: Add the greedy method and exports**

In `src/crew_roster/roster/replan.py`, add the import `from crew_roster.roster.greedy import greedy_repair` and the branch before `else:`:

```python
    elif method == "greedy":
        result = greedy_repair(new, base, locked_before=lock)
```

`src/crew_roster/roster/__init__.py`:

```python
from crew_roster.roster.cache import cache_path, load_base_roster
from crew_roster.roster.check import WINDOWS, check, duty_violations, pilot_violations
from crew_roster.roster.diff import Change, count_changes, diff
from crew_roster.roster.greedy import greedy_repair
from crew_roster.roster.replan import Replan, replan
from crew_roster.roster.sizing import Sizing, min_pilots_needed
from crew_roster.roster.solver import W_CHANGE, W_UNCOVERED, SolveResult, solve

__all__ = ["W_CHANGE", "W_UNCOVERED", "WINDOWS", "Change", "Replan", "Sizing", "SolveResult",
           "cache_path", "check", "count_changes", "diff", "duty_violations",
           "greedy_repair", "load_base_roster", "min_pilots_needed", "pilot_violations",
           "replan", "solve"]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_greedy.py tests/test_sizing.py -q`
Expected: `4 passed, 1 deselected`.
Then (tell the owner first, about 30–40 s): `uv run pytest tests/test_sizing.py -m slow -q` → `1 passed`.

- [ ] **Step 7: Full verification, commit and push**

```bash
uv run pytest -q
uv run ruff check src tests && uv run ruff format src tests
git add -A
git commit -m "feat: greedy repair baseline and crew sizing" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```

Expected: every fast test passes. Plan 1 is done; next, write Plan 2 (Agent + API) with superpowers:writing-plans.
