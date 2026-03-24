from app.generators.drums import generate_drums
from app.core.constants import DRUM_CHANNEL


def test_generate_drums_returns_events():
    style = {
        "drums": {
            "hat_density": 0.8,
            "triplet_probability": 0.0,
            "snare_standard_beats": [2, 4],
            "swing": 0.0,
        }
    }
    events = generate_drums(style, bars=4, complexity=0.5, variation=0.3)
    assert len(events) > 0
    for ev in events:
        assert ev.channel == DRUM_CHANNEL


def test_drums_always_has_kick_on_beat_one():
    style = {
        "drums": {
            "hat_density": 0.0,
            "triplet_probability": 0.0,
            "snare_standard_beats": [],
            "swing": 0.0,
        }
    }
    events = generate_drums(style, bars=2, complexity=0.0, variation=0.0)
    kick_pitch = 36
    kick_starts = [ev.start for ev in events if ev.pitch == kick_pitch]
    assert 0.0 in kick_starts
    assert 4.0 in kick_starts
