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
    id: str  # stable label, not day-authoritative: .day (from report) is authoritative
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
        return [
            (d, r) for d, crew in self.assignments.items() for r, p in crew.items() if p == pilot_id
        ]

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
