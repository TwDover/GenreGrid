# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Targeted repair (roadmap v3 item 11.4): fix what the scorer flagged.

The quality search used to re-roll the *entire* attempt up to five times hoping
the dice landed better, even when the scorer said exactly one dimension was
short. This turns a single red dimension into the cheapest edit that addresses
it: re-roll only the part responsible (the `part_salts` lever `_run_attempt`
already has), or — for `mix`, which is a balance problem and not a note problem
— rescale one part's velocities with no regeneration at all.

`plan_repair` is a pure function of the score dict plus the events it scored,
so the same attempt always yields the same repair. That is what lets a replay
(`fixed_section_seeds`, regenerate-part) re-derive a build's repairs from the
winning seed alone instead of having to record them.
"""
from dataclasses import dataclass, field

# Velocity ratios the mix scorer wants (see quality._mix_balance). A repair aims
# at a comfortable middle of each green band, not at its edge, so a small
# scoring difference either way still lands inside.
_MELODY_OVER_CHORDS_TARGET = 0.50    # green from ~0.43, capped at 0.58
_BASS_OVER_CHORDS_TARGET   = 1.20    # green band 0.55 – 2.5
# A repair may not rewrite the arrangement's dynamics wholesale: past roughly
# these bounds the "fix" is louder than the problem.
_MIN_TRIM, _MAX_TRIM = 0.55, 1.80
# A mix term at or above this is not what is holding the dimension back.
_GREEN_TERM = 0.82


@dataclass(frozen=True)
class Repair:
    """One cheap edit aimed at one red dimension."""
    dimension: str
    kind: str                                    # "reroll" | "velocity"
    part: str
    kwargs: dict = field(default_factory=dict)   # passed straight to _run_attempt

    def describe(self) -> str:
        if self.kind == "velocity":
            return f"{self.dimension}: {self.part} × {self.kwargs['velocity_trim'][self.part]:.2f}"
        return f"{self.dimension}: re-roll {self.part}"


# Which part owns each dimension. Measured on the arrangement sweep (306 repairs)
# against the ~43% chance a plain re-roll of the same attempt lands green:
#
#   density    → re-roll the flagged part   52% converted  (27 tries)  KEPT
#   rhythm     → re-roll drums               3% converted (267 tries)  DROPPED
#   separation → re-roll chords              8% converted  (12 tries)  DROPPED
#
# A repair only earns its run when it beats the re-roll it replaces. `rhythm`
# scores the generated drums against the style's own reference patterns, so a
# re-roll barely moves it — when a style's rhythm reads red it stays red, which
# is a scorer/generator mismatch to chase separately, not something one more
# roll of the dice fixes. `harmonic` is absent for the reason the roadmap gave:
# harmony is shared, so there is no single part to re-roll.
_DIMENSION_PART: dict[str, str] = {}

# How far below the green line a dimension can be and still be worth repairing.
# Measured: of 165 repairs attempted on gaps wider than this, exactly zero went
# green — past a certain distance the part isn't unlucky, it's wrong.
_MAX_GAP = 0.06

# `density` names its offender in the flag text (quality._density_fit).
_DENSITY_FLAG_PART = (
    ("Melody is", "melody"),
    ("Bass is",   "bass"),
)


def _avg_velocity(events) -> float | None:
    return (sum(e.velocity for e in events) / len(events)) if events else None


def _melody_term(r: float) -> float:
    """quality._mix_balance's melody/chords term, so repair and scorer agree
    about which of the two ratios is the one dragging `mix` down."""
    if r < 0.30:
        return 0.35
    if r > 2.0:
        return 0.55
    return min(1.0, 0.30 + r * 1.20)


def _bass_term(r: float) -> float:
    return 0.40 if r < 0.55 else 0.45 if r > 2.5 else 0.88


def _mix_trim(events: dict) -> tuple[str, float] | None:
    """Which part is out of balance, and what to multiply its velocities by.

    Melody/chords is repaired by moving the MELODY and bass/chords by moving the
    BASS — always the part in the numerator. Trimming the chords instead would
    fix one ratio by breaking the other, since both are measured against them.
    The weaker of the two terms is the one repaired: a marginal melody ratio
    must not shadow a genuinely broken bass.
    """
    m = _avg_velocity(events.get("melody") or [])
    c = _avg_velocity(events.get("chords") or [])
    b = _avg_velocity(events.get("bass") or [])
    if not c:
        return None

    candidates = []
    if m is not None:
        r = m / c
        candidates.append((_melody_term(r), "melody", _MELODY_OVER_CHORDS_TARGET / r))
    if b is not None:
        r = b / c
        candidates.append((_bass_term(r), "bass", _BASS_OVER_CHORDS_TARGET / r))
    if not candidates:
        return None
    score, part, factor = min(candidates)
    return (part, factor) if score < _GREEN_TERM else None


def plan_repair(
    quality_raw: dict | None,
    events: dict,
    dims: tuple[str, ...],
    threshold: float,
    salt: int = 1,
) -> Repair | None:
    """The repair for this attempt, or None if there isn't a cheap one.

    Returns a repair only when **exactly one** gated dimension is short: two or
    more red dimensions mean the attempt is broadly wrong rather than one part
    misbehaving, and re-rolling the whole thing is the honest response.
    """
    if not quality_raw:
        return None
    red = [d for d in dims if quality_raw.get(d, 0.0) < threshold]
    if len(red) != 1:
        return None
    dim = red[0]
    if threshold - quality_raw.get(dim, 0.0) > _MAX_GAP:
        return None

    if dim == "mix":
        trim = _mix_trim(events)
        if trim is None:
            return None
        part, factor = trim
        factor = max(_MIN_TRIM, min(_MAX_TRIM, factor))
        if abs(factor - 1.0) < 0.02 or not events.get(part):
            return None
        return Repair(dim, "velocity", part, {"velocity_trim": {part: round(factor, 3)}})

    part = _DIMENSION_PART.get(dim)
    if part is None and dim == "density":
        flags = quality_raw.get("flags") or []
        part = next((p for prefix, p in _DENSITY_FLAG_PART
                     if any(f.startswith(prefix) for f in flags)), None)
    if part is None or not events.get(part):
        return None
    return Repair(dim, "reroll", part, {"part_salts": {part: salt}})
