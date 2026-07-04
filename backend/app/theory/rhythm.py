# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Rhythm utilities — beat/subdivision helpers."""


def subdivisions_per_bar(time_sig_num: int = 4, subdivision: int = 16) -> int:
    """Number of subdivisions in one bar."""
    return time_sig_num * (subdivision // 4)


def beats_to_ticks(beats: float, ticks_per_beat: int = 480) -> int:
    return int(beats * ticks_per_beat)


def sixteenth_to_ticks(sixteenths: float, ticks_per_beat: int = 480) -> int:
    return int(sixteenths * ticks_per_beat / 4)


def apply_swing(tick: int, swing: float, ticks_per_beat: int = 480) -> int:
    """Push the 'and' of each beat toward a triplet position (swing feel).

    Uses a linear taper: the exact 'and' (beat+0.5) gets the full shift; notes
    further into the second eighth get proportionally less, so nothing overshoots
    the next beat even at high swing values.
    """
    if swing < 0.01:
        return tick
    eighth = ticks_per_beat // 2
    beat_pos = tick % ticks_per_beat
    if beat_pos >= eighth:
        pos_in_second_eighth = beat_pos - eighth          # 0 at "and", eighth-1 approaching next beat
        proximity = 1.0 - pos_in_second_eighth / eighth   # 1.0 → 0.0
        shift = int(swing * eighth / 3 * proximity)
        return tick + shift
    return tick
