# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Phrase-level melody planning: a section's melody gets a FORM before any
notes exist. Each 4-bar phrase receives a role from a form grammar (AABA,
ABAC, …), and the role decides its contour peak, register, density, cadence,
and whether it restates the seed motif. The note-level generator then fills
each phrase in — locally free, globally shaped."""
import random
from dataclasses import dataclass


@dataclass
class PhrasePlan:
    role: str            # "statement" | "restatement" | "contrast" | "climax" | "resolution"
    contour_peak: float  # 0-1 position within the phrase where the melodic high point lands
    register: float      # 0-1 target center within the available range
    density_mult: float  # multiplies the style's note density for this phrase
    cadence_open: bool   # True = half cadence (sd2/sd5), False = full close (tonic)
    replay_motif: float  # probability of restating the seed motif at the phrase start
    climax: bool         # phrase carries the section's high point (may use the high register)


# Role archetypes: how each role shapes its phrase.
_ROLE_SHAPES: dict[str, dict] = {
    #                  peak   register density  open   replay
    "statement":    dict(peak=0.55, reg=0.45, dens=1.00, open=True,  replay=0.00),
    "restatement":  dict(peak=0.55, reg=0.50, dens=1.00, open=False, replay=0.80),
    "contrast":     dict(peak=0.35, reg=0.62, dens=0.85, open=True,  replay=0.05),
    "climax":       dict(peak=0.62, reg=0.85, dens=1.15, open=True,  replay=0.35),
    "resolution":   dict(peak=0.30, reg=0.40, dens=0.80, open=False, replay=0.60),
}

# Form grammar by phrase count. Multiple options per count; one is drawn per
# section (seeded RNG upstream, so the choice is reproducible).
_FORMS: dict[int, list[list[str]]] = {
    1: [["statement"]],
    2: [["statement", "resolution"],
        ["statement", "restatement"]],
    3: [["statement", "restatement", "resolution"],
        ["statement", "contrast", "resolution"]],
    4: [["statement", "restatement", "contrast", "resolution"],   # AABA
        ["statement", "contrast", "restatement", "climax"],       # ABAC (climactic close)
        ["statement", "restatement", "climax", "resolution"]],    # AAB(climax)A'
}


def plan_phrases(num_phrases: int) -> list[PhrasePlan]:
    """Choose a form and expand it into per-phrase plans.

    Sections longer than 4 phrases tile the 4-phrase form, but exactly one
    phrase in the whole section carries the climax (the last "climax" slot,
    or the third quarter of the section when the form has none) so the section
    has a single high point instead of several competing ones.
    """
    if num_phrases <= 0:
        return []
    if num_phrases <= 4:
        roles = list(random.choice(_FORMS[num_phrases]))
    else:
        base = random.choice(_FORMS[4])
        roles = [base[i % 4] for i in range(num_phrases)]

    # Exactly one climax per section
    climax_idx = None
    for i in range(len(roles) - 1, -1, -1):
        if roles[i] == "climax":
            if climax_idx is None:
                climax_idx = i
            else:
                roles[i] = "restatement"
    if climax_idx is None and num_phrases >= 3:
        climax_idx = max(1, (num_phrases * 3) // 4 - 1)
        roles[climax_idx] = "climax"

    plans: list[PhrasePlan] = []
    for i, role in enumerate(roles):
        s = _ROLE_SHAPES[role]
        plans.append(PhrasePlan(
            role=role,
            contour_peak=min(0.9, max(0.15, s["peak"] + random.uniform(-0.08, 0.08))),
            register=min(1.0, max(0.0, s["reg"] + random.uniform(-0.06, 0.06))),
            density_mult=s["dens"],
            cadence_open=s["open"],
            replay_motif=s["replay"],
            climax=(i == climax_idx),
        ))
    # A phrase promoted to carry the climax adopts the climax shape even if its
    # role came from a non-climax form slot — the high point must actually be high.
    if climax_idx is not None:
        c = plans[climax_idx]
        c.register = max(c.register, 0.85)
        c.density_mult = max(c.density_mult, 1.1)
        c.contour_peak = min(0.75, max(0.5, c.contour_peak))
    # The section's last phrase always closes, whatever its role said.
    plans[-1].cadence_open = False
    return plans
