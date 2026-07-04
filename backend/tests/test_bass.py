# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
from app.generators.bass import generate_bass


def test_generate_bass_returns_events():
    style = {
        "progression_templates": [["i", "VI", "III", "VII"]],
        "bass": {"pattern_density": 0.5, "octave_jumps": 0.0, "sustain_bias": 0.6},
    }
    events = generate_bass(style, "C", "minor", bars=4, complexity=0.5, variation=0.3)
    assert len(events) > 0
    for ev in events:
        assert ev.pitch >= 24
        assert ev.pitch <= 60
        assert ev.channel == 1
