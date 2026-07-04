# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
from app.generators.melody import generate_melody


def test_generate_melody_returns_events():
    style = {
        "melody": {
            "density": 0.5,
            "stepwise_motion": 0.7,
            "leap_probability": 0.1,
            "rest_probability": 0.2,
            "range": [60, 79],
        }
    }
    events = generate_melody(style, "C", "minor", bars=4, complexity=0.5, variation=0.3)
    assert len(events) > 0
    for ev in events:
        assert 0 <= ev.pitch <= 127
        assert ev.channel == 2
