"""Fictional airline 'Skyline Air': a seeded domestic A320 network out of DEL and BOM."""

from __future__ import annotations

import random

from crew_roster.models import DAY, Airline, Duty, Flight, Pilot, Turn

AIRPORTS = {
    "DEL": "Delhi",
    "BOM": "Mumbai",
    "BLR": "Bengaluru",
    "HYD": "Hyderabad",
    "MAA": "Chennai",
    "CCU": "Kolkata",
    "GOI": "Goa",
    "PNQ": "Pune",
}
BASES = ("DEL", "BOM")
BLOCK_MIN = {
    ("BOM", "DEL"): 130,
    ("BLR", "DEL"): 165,
    ("DEL", "HYD"): 135,
    ("CCU", "DEL"): 135,
    ("DEL", "GOI"): 150,
    ("DEL", "PNQ"): 125,
    ("DEL", "MAA"): 170,
    ("BOM", "GOI"): 70,
    ("BOM", "HYD"): 85,
    ("BLR", "BOM"): 100,
    ("BOM", "PNQ"): 50,
    ("BOM", "CCU"): 160,
}
GROUND_MIN = 45  # turnaround at the outstation
# (outstation, departure HH:MM from base) — repeated every day
TURN_TEMPLATES = {
    "DEL": [
        ("BOM", "06:00"),
        ("BLR", "06:30"),
        ("HYD", "08:00"),
        ("CCU", "10:00"),
        ("GOI", "12:00"),
        ("PNQ", "14:00"),
        ("BOM", "16:30"),
        ("MAA", "18:00"),
        ("BLR", "23:30"),
    ],
    "BOM": [
        ("GOI", "06:00"),
        ("HYD", "07:00"),
        ("BLR", "07:30"),
        ("DEL", "08:00"),
        ("PNQ", "09:50"),
        ("GOI", "12:00"),
        ("HYD", "13:30"),
        ("PNQ", "16:00"),
        ("CCU", "17:00"),
        ("DEL", "19:00"),
        ("HYD", "23:45"),
        ("GOI", "04:15"),
    ],
}
FLIGHT_NO_START = {"DEL": 101, "BOM": 501}
SURNAMES = [
    "Rao",
    "Iyer",
    "Sharma",
    "Verma",
    "Nair",
    "Menon",
    "Gupta",
    "Kapoor",
    "Reddy",
    "Das",
    "Bose",
    "Singh",
    "Patel",
    "Shah",
    "Joshi",
    "Kulkarni",
    "Pillai",
    "Mehta",
    "Chopra",
    "Malhotra",
    "Banerjee",
    "Mishra",
    "Agarwal",
    "Saxena",
    "Bhat",
    "Kaur",
    "Gill",
    "Naidu",
    "Desai",
    "Rathore",
]
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
        out.append(
            Duty(
                id=f"H-{pid}{day}",
                base=base,
                report=report,
                release=report + length,
                flight_time=ft,
                landings=rng.choice([2, 4]),
                night=False,
            )
        )
    return out


def generate(
    seed: int = 7, days: int = 7, pilots_per_base: int = 40, history_days: int = 27
) -> Airline:
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
                out = Flight(
                    id=f"SK{no}-D{day}",
                    turn_id=tid,
                    day=day,
                    origin=base,
                    dest=dest,
                    dep=dep,
                    arr=dep + blk,
                )
                back_dep = out.arr + GROUND_MIN
                back = Flight(
                    id=f"SK{no + 1}-D{day}",
                    turn_id=tid,
                    day=day,
                    origin=dest,
                    dest=base,
                    dep=back_dep,
                    arr=back_dep + blk,
                )
                flights[out.id], flights[back.id] = out, back
                turns[tid] = Turn(
                    id=tid, base=base, dest=dest, day=day, out_id=out.id, back_id=back.id
                )

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

    return Airline(
        name="Skyline Air",
        days=days,
        bases=BASES,
        airports=AIRPORTS,
        flights=flights,
        turns=turns,
        pilots=pilots,
        history=history,
    )
