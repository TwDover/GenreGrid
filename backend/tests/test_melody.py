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
