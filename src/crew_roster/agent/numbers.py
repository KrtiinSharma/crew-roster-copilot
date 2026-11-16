"""Number check: every number in an answer must come from a tool, the question or the prompt."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import BaseModel

ID = re.compile(r"\b[A-Za-z]+\d*(?:-[A-Za-z]*\d+)+\b")  # DEL-C04, SK115-D2, BOM-D3-05:CPT
HM = re.compile(r"\b(\d{1,3})\s*h\s*(\d{2})\b")          # 8h30
CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\b")              # 06:15
NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")              # 35, 7.5 (not the 3 in D3)
TRIVIAL = {0.0, 1.0}
TOLERANCE = 0.051  # allows rounding to one decimal place


def extract(text: str) -> list[tuple[str, float]]:
    text = ID.sub(" ", text)
    found: list[tuple[int, str, float]] = []
    for rx in (HM, CLOCK):
        for m in rx.finditer(text):
            found.append((m.start(), m.group(0), int(m.group(1)) + int(m.group(2)) / 60))
        text = rx.sub(lambda m: " " * len(m.group(0)), text)  # keep positions for ordering
    found += [(m.start(), m.group(0), float(m.group(0))) for m in NUM.finditer(text)]
    return [(tok, val) for _, tok, val in sorted(found)]


class NumberCheck(BaseModel):
    ok: bool
    ungrounded: list[str]


def check_numbers(answer: str, sources: Sequence[str],
                  convertible: Sequence[str] = ()) -> NumberCheck:
    """`sources` (tool outputs, prompt) ground their numbers as-is: tools already give hours.
    `convertible` (the user's question) also grounds minute/hour conversions of its numbers."""
    pool: set[float] = set()
    for src in sources:
        pool |= {v for _, v in extract(src)}
    for src in convertible:
        for _, v in extract(src):
            pool |= {v, v / 60, v * 60}
    bad = [tok for tok, v in extract(answer)
           if v not in TRIVIAL and not any(abs(v - g) < TOLERANCE for g in pool)]
    return NumberCheck(ok=not bad, ungrounded=bad)
