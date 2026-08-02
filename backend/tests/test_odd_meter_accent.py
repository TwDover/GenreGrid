# GenreGrid — a style-based MIDI generator.
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Odd-meter accent shaping.

An odd bar (5/8, 7/8, ...) is felt in mixed 2- and 3-eighth groups (7/8 =
2+2+3). `apply_odd_meter_accent` gives each group's head a velocity boost and
its tail a duck — the additive-meter analogue of compound's triplet lilt, but
velocity-only (no timing swing, since a 2-group has no middle eighth to push).
Must be a no-op in every meter that isn't odd.
"""
import copy

import pytest

from app.core.meter import parse_meter
from app.services.midi_writer import NoteEvent
from app.services.humanize import (
    apply_odd_meter_accent, odd_meter_group_position, ODD_ACCENT_DEFAULT,
)


def _hit(start, vel=100):
    return NoteEvent(36, start, 0.1, vel, 9)


def test_odd_meters_flagged():
    for sig in ("5/8", "7/8", "8/8", "10/8", "11/8"):
        assert parse_meter(sig).is_odd
    for sig in ("4/4", "3/4", "2/4", "6/8", "9/8", "12/8", "1/8", "2/8", "3/8", "4/8"):
        assert not parse_meter(sig).is_odd


def test_group_position_matches_the_grouping():
    m = parse_meter("7/8")   # 2+2+3, group heads at 0.0, 1.0, 2.0
    assert odd_meter_group_position(0.0, m) == (0, 2)
    assert odd_meter_group_position(0.5, m) == (1, 2)
    assert odd_meter_group_position(1.0, m) == (0, 2)
    assert odd_meter_group_position(2.0, m) == (0, 3)
    assert odd_meter_group_position(2.5, m) == (1, 3)
    assert odd_meter_group_position(3.0, m) == (2, 3)
    # wraps into the next bar's first group
    assert odd_meter_group_position(3.5, m) == (0, 2)


def test_group_heads_are_accented_and_tails_ducked():
    m = parse_meter("7/8")   # 2+2+3 -> group heads at 0.0, 1.0, 2.0
    ev = {"drums": [_hit(0.0), _hit(0.5), _hit(1.0), _hit(1.5), _hit(2.0), _hit(2.5), _hit(3.0)]}
    apply_odd_meter_accent(ev, m, ODD_ACCENT_DEFAULT)
    by_start = {round(e.start, 3): e.velocity for e in ev["drums"]}
    assert by_start[0.0] > by_start[0.5]     # group-of-2 head > tail
    assert by_start[1.0] > by_start[1.5]     # group-of-2 head > tail
    assert by_start[2.0] > by_start[3.0] > by_start[2.5]   # group-of-3 head > pickup > middle


@pytest.mark.parametrize("sig", ["4/4", "3/4", "2/4", "6/8", "9/8", "12/8"])
def test_non_odd_meters_untouched(sig):
    m = parse_meter(sig)
    ev = {"drums": [_hit(0.0), _hit(0.5), _hit(1.0)]}
    before = copy.deepcopy(ev)
    apply_odd_meter_accent(ev, m, ODD_ACCENT_DEFAULT)
    assert [(e.start, e.velocity) for e in ev["drums"]] == \
           [(e.start, e.velocity) for e in before["drums"]], f"{sig} should be a no-op"


def test_amount_zero_is_a_noop_even_in_odd_meter():
    m = parse_meter("7/8")
    ev = {"drums": [_hit(0.0), _hit(2.5)]}
    before = copy.deepcopy(ev)
    apply_odd_meter_accent(ev, m, 0.0)
    assert [(e.start, e.velocity) for e in ev["drums"]] == \
           [(e.start, e.velocity) for e in before["drums"]]


def test_only_drums_are_accented():
    m = parse_meter("7/8")
    ev = {"drums": [_hit(0.0)], "melody": [NoteEvent(72, 0.0, 0.5, 80, 2)]}
    apply_odd_meter_accent(ev, m, ODD_ACCENT_DEFAULT)
    assert ev["melody"][0].velocity == 80


def test_timing_never_moves():
    """Unlike compound swing, odd-meter accent is velocity-only."""
    m = parse_meter("5/8")
    ev = {"drums": [_hit(0.0), _hit(0.5), _hit(1.0), _hit(1.5), _hit(2.0)]}
    before = [e.start for e in ev["drums"]]
    apply_odd_meter_accent(ev, m, ODD_ACCENT_DEFAULT)
    assert [e.start for e in ev["drums"]] == before
