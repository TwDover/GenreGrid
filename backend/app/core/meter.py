# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Time-signature model — everything the generators and services need to place
events in a bar of any meter.

All positions in GenreGrid are expressed in QUARTER-NOTE beats (a note's
``.start`` is in quarter-beats, and BPM is the quarter-note tempo). So the one
quantity that varies with meter is ``bar_beats`` — the bar length in
quarter-beats — and every ``bars * 4`` in the codebase becomes
``bars * meter.bar_beats``. For 4/4, ``bar_beats == 4.0``, so all arithmetic is
unchanged and output stays byte-identical (the project's gating invariant).

Meters split into:
  • simple   (x/4, x/2): one felt beat per denominator unit, 16th-note feel.
  • compound (6/8, 9/8, 12/8): felt beats are dotted quarters (3 eighths each).
  • odd      (5/8, 7/8, …): eighths grouped irregularly (7/8 = 2+2+3).
"""
from __future__ import annotations

from dataclasses import dataclass

# How the N eighths of an x/8 bar split into felt beats. Compound meters are all
# 3s; odd meters mix. Anything not listed falls back to 3s with the remainder last.
_EIGHTH_GROUPINGS: dict[int, list[int]] = {
    5: [2, 3], 6: [3, 3], 7: [2, 2, 3], 8: [3, 3, 2],
    9: [3, 3, 3], 10: [3, 3, 2, 2], 11: [3, 3, 3, 2], 12: [3, 3, 3, 3],
}


def _eighth_grouping(num: int) -> list[int]:
    if num in _EIGHTH_GROUPINGS:
        return list(_EIGHTH_GROUPINGS[num])
    groups, rem = [], num
    while rem > 3:
        groups.append(3)
        rem -= 3
    if rem:
        groups.append(rem)
    return groups or [num]


@dataclass(frozen=True)
class Meter:
    """A time signature. Defaults to 4/4 so `Meter()` is a no-op everywhere."""
    numerator: int = 4
    denominator: int = 4

    @property
    def bar_beats(self) -> float:
        """Bar length in quarter-note beats. 4/4→4.0, 3/4→3.0, 6/8→3.0, 7/8→3.5."""
        return self.numerator * 4.0 / self.denominator

    @property
    def step(self) -> float:
        """Fine subdivision grid unit in quarter-beats (a 16th note)."""
        return 0.25

    @property
    def steps_per_bar(self) -> int:
        """16th-note steps in a bar. 4/4→16, 3/4→12, 6/8→12, 7/8→14."""
        return int(round(self.bar_beats / self.step))

    @property
    def is_compound(self) -> bool:
        """Compound meters (6/8, 9/8, 12/8) — dotted-quarter beats, triplet feel."""
        return self.denominator == 8 and self.numerator in (6, 9, 12)

    @property
    def is_simple(self) -> bool:
        return self.denominator in (2, 4) or (self.denominator == 8 and not self.is_compound)

    @property
    def pulse(self) -> float:
        """Nominal felt-beat spacing in quarter-beats (compound → dotted quarter,
        1.5). Irregular meters vary — use `pulse_positions` for exact placement."""
        return 1.5 if self.is_compound else 4.0 / self.denominator

    @property
    def pulse_positions(self) -> list[float]:
        """Felt-beat start positions within a bar, in quarter-beats.
        4/4→[0,1,2,3], 3/4→[0,1,2], 6/8→[0,1.5], 7/8→[0,1.0,2.0] (2+2+3)."""
        if self.denominator == 8:
            out: list[float] = []
            eighth = 0
            for g in _eighth_grouping(self.numerator):
                out.append(eighth * 0.5)   # an eighth is 0.5 quarter-beats
                eighth += g
            return out
        unit = 4.0 / self.denominator      # quarter for x/4, half for x/2
        return [i * unit for i in range(self.numerator)]

    def __str__(self) -> str:
        return f"{self.numerator}/{self.denominator}"


DEFAULT_METER = Meter(4, 4)

_ALLOWED_DENOMINATORS = (2, 4, 8, 16)


def parse_meter(s: str | Meter | None) -> Meter:
    """Parse "N/D" into a Meter, clamped to sane bounds. Bad input → 4/4."""
    if isinstance(s, Meter):
        return s
    if not s:
        return DEFAULT_METER
    try:
        num_s, den_s = str(s).split("/")
        num, den = int(num_s), int(den_s)
    except (ValueError, AttributeError):
        return DEFAULT_METER
    if den not in _ALLOWED_DENOMINATORS or not (1 <= num <= 32):
        return DEFAULT_METER
    return Meter(num, den)
