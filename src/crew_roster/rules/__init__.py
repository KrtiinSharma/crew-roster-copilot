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
        name=raw["name"],
        label=raw["label"],
        max_ft_per_duty=v("max_ft_per_duty"),
        max_fdp_by_landings={int(k): _amount(h, fdp["unit"]) for k, h in fdp["value"].items()},
        night_start=_clock(night[0]),
        night_end=_clock(night[1]),
        night_max_fdp=v("night_max_fdp"),
        night_max_landings=v("night_max_landings"),
        max_consecutive_nights=v("max_consecutive_nights"),
        min_rest=v("min_rest"),
        weekly_rest=v("weekly_rest"),
        ft_7d=v("ft_7d"),
        ft_28d=v("ft_28d"),
        duty_7d=v("duty_7d"),
        duty_28d=v("duty_28d"),
        sources={k: item["source"] for k, item in lim.items()},
    )
