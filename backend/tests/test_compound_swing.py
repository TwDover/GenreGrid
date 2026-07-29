# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Compound-meter triplet swing.

A compound bar (6/8, 9/8, 12/8) lilts: the dotted-quarter pulse head is strong,
the middle eighth sits back and soft, the third is a light pickup. `apply_compound_swing`
adds that (a middle-eighth timing push + a per-triplet velocity contour) on top of the
straight, on-grid placement the generators emit. It must be a no-op in every other meter.
"""
import copy

import pytest

from app.core.meter import Meter, parse_meter
from app.services.midi_writer import NoteEvent
from app.services.humanize import (
    apply_compound_swing, compound_eighth, compound_swing_delay, COMPOUND_SWING_DEFAULT,
)


def _kick(start, vel=100):
    return NoteEvent(36, start, 0.1, vel, 9)


def test_eighth_classification():
    # head / middle / pickup within a dotted-quarter pulse, and wrap into next pulse
    assert compound_eighth(0.0) == 0
    assert compound_eighth(0.5) == 1
    assert compound_eighth(1.0) == 2
    assert compound_eighth(1.5) == 0     # next pulse head
    assert compound_eighth(2.0) == 1     # next pulse middle


def test_only_middle_eighth_is_pushed_late():
    d = compound_swing_delay
    assert d(0, 1.0) == 0.0
    assert d(2, 1.0) == 0.0
    assert d(1, 1.0) > 0.0
    assert d(1, 0.5) == pytest.approx(d(1, 1.0) / 2)   # scales linearly with amount


def test_compound_swing_delays_middle_eighth_and_shapes_velocity():
    m = parse_meter("6/8")
    # one kick on each eighth of the first pulse
    ev = {"drums": [_kick(0.0), _kick(0.5), _kick(1.0)]}
    apply_compound_swing(ev, m, COMPOUND_SWING_DEFAULT)
    head, mid, pick = ev["drums"]
    # timing: only the middle eighth moves, and it moves LATE
    assert head.start == 0.0
    assert pick.start == 1.0
    assert mid.start > 0.5
    assert mid.start == pytest.approx(0.5 + compound_swing_delay(1, COMPOUND_SWING_DEFAULT))
    # velocity contour: head strongest, middle ducked below the pickup
    assert head.velocity > pick.velocity > mid.velocity


def test_all_parts_lilt_together():
    """A bass note and a kick on the same middle eighth shift by the same amount
    (positional swing → the band rolls together), but only drums are re-velocitied."""
    m = parse_meter("9/8")
    ev = {"drums": [_kick(0.5)], "bass": [NoteEvent(40, 0.5, 0.9, 90, 1)]}
    apply_compound_swing(ev, m, 0.7)
    assert ev["drums"][0].start == pytest.approx(ev["bass"][0].start)
    assert ev["bass"][0].velocity == 90         # melodic parts keep their velocity


def test_middle_eighth_never_crosses_the_barline():
    m = parse_meter("6/8")                       # bar_beats 3.0; last middle eighth at 2.5
    ev = {"drums": [_kick(2.5)]}
    apply_compound_swing(ev, m, 1.0)             # max swing
    assert ev["drums"][0].start < 3.0


@pytest.mark.parametrize("sig", ["4/4", "3/4", "2/4", "7/8", "5/8"])
def test_non_compound_meters_untouched(sig):
    m = parse_meter(sig)
    ev = {"drums": [_kick(0.5), _kick(1.0)], "melody": [NoteEvent(72, 0.5, 0.5, 80, 2)]}
    before = copy.deepcopy(ev)
    apply_compound_swing(ev, m, COMPOUND_SWING_DEFAULT)
    for part in ev:
        assert [(e.start, e.velocity) for e in ev[part]] == \
               [(e.start, e.velocity) for e in before[part]], f"{sig} should be a no-op"


def test_amount_zero_is_a_noop_even_in_compound():
    ev = {"drums": [_kick(0.5)]}
    before = copy.deepcopy(ev)
    apply_compound_swing(ev, Meter(6, 8), 0.0)
    assert ev["drums"][0].start == before["drums"][0].start
    assert ev["drums"][0].velocity == before["drums"][0].velocity
