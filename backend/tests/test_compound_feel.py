# GenreGrid — a style-based MIDI generator.
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Meter-native feel velocity for compound meters.

`apply_feel`'s systematic groove contour was a 16-slot 4/4-shaped table read
through a naive per-bar fold — in a compound bar that put the mid-pulse eighth
on a slot meaning "the & of beat 2" in 4/4, not anything about the meter's
actual dotted-quarter pulses. For styles with a hand-authored archetype, a
compound bar now re-synthesises the SAME archetype params natively (per
pulse: head/middle/pickup), so the backbeat lands on the pulse that's actually
felt as the backbeat. `apply_compound_swing`'s generic contour must then skip
whatever `apply_feel` already placed natively, or the two stack.
"""
import pytest

from app.core.constants import DRUM_MAP
from app.core.feel import compound_feel
from app.core.meter import parse_meter
from app.services.humanize import apply_compound_swing, apply_feel, COMPOUND_SWING_DEFAULT
from app.services.midi_writer import NoteEvent


def _note(pitch, start, vel=100, channel=9):
    return NoteEvent(pitch, start, 0.1, vel, channel)


def test_compound_feel_table_shape():
    t = compound_feel("lofi", 2)   # 6/8: 2 dotted-quarter pulses, 3 eighths each
    assert t is not None
    assert len(t["kick"]["timing"]) == 6
    assert len(t["kick"]["velocity"]) == 6
    assert compound_feel("epic_orchestral", 2) is None   # no hand-authored archetype


def test_apply_feel_accents_the_native_backbeat_pulse():
    """In 6/8, the backbeat analog is the 2nd dotted-quarter pulse (start 1.5),
    not whatever a 16-slot 4/4 table happens to land on when folded onto a
    12-step bar."""
    style = {"id": "lofi", "_humanize_scale": 0.5}
    snare = DRUM_MAP["snare"]
    m = parse_meter("6/8")
    events = {
        "drums": [_note(snare, 0.0, 100), _note(snare, 1.5, 100)],
        "bass": [_note(40, 0.0, 90, 1)],
    }
    handled = apply_feel(events, style, meter=m)
    assert handled == {"drums", "bass"}
    on_pulse0, on_pulse1 = events["drums"]
    assert on_pulse1.start > 1.5                    # backbeat pulse drags late
    assert on_pulse0.start == pytest.approx(0.0, abs=1e-9)   # pulse-0 head stays put
    assert on_pulse1.velocity > on_pulse0.velocity   # backbeat accented; pulse-0 head is a ghost


@pytest.mark.parametrize("sig", ["4/4", "3/4", "7/8", "5/8"])
def test_non_compound_meters_keep_the_16_slot_table(sig):
    """Non-compound meters (simple or odd) are unaffected by the native-pulse
    branch — apply_feel still runs the generic 16-slot path there."""
    style = {"id": "lofi", "_humanize_scale": 0.5}
    m = parse_meter(sig)
    events = {"drums": [_note(DRUM_MAP["kick"], 0.0, 100)]}
    apply_feel(events, style, meter=m)
    assert 1 <= events["drums"][0].velocity <= 127


def test_feel_absent_style_stays_unhandled_in_compound_meter():
    style = {"id": "techno", "_humanize_scale": 0.5}   # no feel archetype
    m = parse_meter("6/8")
    events = {"drums": [_note(DRUM_MAP["kick"], 0.0, 100)]}
    assert apply_feel(events, style, meter=m) == set()
    assert events["drums"][0].start == 0.0 and events["drums"][0].velocity == 100


def test_compound_swing_skips_parts_feel_already_placed():
    """apply_compound_swing must not double-apply its generic contour on top
    of apply_feel's native compound contour for the same part."""
    style = {"id": "lofi", "_humanize_scale": 0.5}
    m = parse_meter("6/8")
    events = {"drums": [_note(DRUM_MAP["kick"], 0.5, 100)]}
    handled = apply_feel(events, style, meter=m)
    before = [(e.start, e.velocity) for e in events["drums"]]
    apply_compound_swing(events, m, COMPOUND_SWING_DEFAULT, skip=handled)
    after = [(e.start, e.velocity) for e in events["drums"]]
    assert before == after


def test_compound_swing_still_applies_when_not_skipped():
    m = parse_meter("6/8")
    events = {"drums": [_note(36, 0.5, 100)]}
    before = [(e.start, e.velocity) for e in events["drums"]]
    apply_compound_swing(events, m, COMPOUND_SWING_DEFAULT, skip=set())
    after = [(e.start, e.velocity) for e in events["drums"]]
    assert before != after
