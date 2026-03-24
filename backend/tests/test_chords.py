import pytest
from app.theory.chords import roman_to_chord
from app.generators.chords import generate_chords


def test_roman_major_triad():
    notes = roman_to_chord("I", "C", "major", octave=4)
    assert len(notes) == 3
    assert notes[0] == 60  # C4


def test_roman_minor_triad():
    notes = roman_to_chord("i", "C", "minor", octave=4)
    assert len(notes) == 3
    assert notes[0] == 60


def test_roman_with_7th():
    notes = roman_to_chord("i", "C", "minor", octave=4, allow_7th=True)
    assert len(notes) == 4


def test_generate_chords_returns_events():
    style = {
        "progression_templates": [["i", "VI", "III", "VII"]],
        "chord_extensions": {"allow_7th": 0.0, "allow_9th": 0.0},
    }
    events = generate_chords(style, "C", "minor", bars=4, complexity=0.5, variation=0.3)
    assert len(events) > 0
    for ev in events:
        assert 0 <= ev.pitch <= 127
        assert ev.velocity > 0
