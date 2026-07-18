# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Call-and-response: the arrangement must be a dialogue, not a monologue.

When the melody leaves a hole, another voice answers it with a lick shaped by
the song's melodic cell. The bass carries that answer in every build (Tier A);
the counter-melody carries a distinct answer where it's present (Tier B), and
when it does the bass stands down so they don't crowd the same gap.
"""
import random

from app.generators.answer import build_answer_phrase
from app.generators.counter_melody import generate_counter_melody
from app.generators.bass import generate_bass
from app.theory.chords import roman_to_chord
from app.services.midi_writer import NoteEvent

CELL = [1, 1, -2]   # up, up, down-a-third — a typical opening-motif contour
PROG = ["i", "VI", "III", "VII"]


def _chord_pcs(roman: str) -> set[int]:
    return {p % 12 for p in roman_to_chord(roman, "C", "minor", octave=4)}


# ── the shared answer-phrase builder ────────────────────────────────────────

def test_answer_lands_on_chord_tone_in_range_with_breath():
    notes = build_answer_phrase(CELL, "C", "minor", "i", 4.0, 7.5, lo=28, hi=52,
                                channel=1, base_vel=74, rng=random.Random(7))
    assert len(notes) >= 2
    assert all(28 <= n.pitch <= 52 for n in notes)            # stays in the given register
    assert all(4.0 <= n.start for n in notes)                  # never before the rest
    assert notes[-1].start + notes[-1].duration <= 7.5 - 0.2   # a breath before re-entry
    assert notes[-1].pitch % 12 in _chord_pcs("i")             # resolves onto the chord


def test_answer_is_empty_when_no_room_or_no_material():
    # rest too short for two eighths + a breath
    assert build_answer_phrase(CELL, "C", "minor", "i", 8.0, 9.0, 55, 74, 5, 80, random.Random(1)) == []
    # no cell / a shapeless (all-zero) cell carries nothing to answer with
    assert build_answer_phrase(None,  "C", "minor", "i", 4.0, 7.5, 28, 52, 1, 74, random.Random(1)) == []
    assert build_answer_phrase([0, 0], "C", "minor", "i", 4.0, 7.5, 28, 52, 1, 74, random.Random(1)) == []


def test_answer_is_deterministic():
    a = build_answer_phrase(CELL, "C", "minor", "VI", 4.0, 8.0, 53, 74, 5, 80, random.Random(9))
    b = build_answer_phrase(CELL, "C", "minor", "VI", 4.0, 8.0, 53, 74, 5, 80, random.Random(9))
    assert [(n.pitch, n.start, n.velocity) for n in a] == [(n.pitch, n.start, n.velocity) for n in b]


# ── Tier B: counter-melody dual mode ────────────────────────────────────────

def _verse_melody_with_hole():
    """A 2-bar phrase, a 4-beat rest (beats 2–6), then it resumes."""
    mel = [NoteEvent(67, 0.0, 0.5, 90, 2), NoteEvent(69, 0.5, 0.5, 88, 2),
           NoteEvent(71, 1.0, 0.5, 88, 2), NoteEvent(72, 1.5, 0.5, 86, 2)]
    mel += [NoteEvent(67, 6.0 + i * 0.5, 0.5, 88, 2) for i in range(4)]
    return mel


def test_counter_melody_answers_in_the_rest_not_over_the_lead():
    mel = _verse_melody_with_hole()
    rests = [(2.0, 6.0)]
    random.seed(3)
    cm = generate_counter_melody(mel, "C", "minor", 4, PROG, {"id": "t"},
                                 melody_rests=rests, cell=CELL, section_type="verse")
    assert cm, "answer mode produced nothing for a verse with a clear hole"
    # every answer note sits INSIDE the hole (the point: fill silence, not double the lead)
    for n in cm:
        assert 2.0 <= n.start < 6.0, f"answer note at {n.start} escaped the rest"
        assert n.channel == 5
    # and it resolves onto the sounding chord (i at beat 2 → bar 0)
    assert cm[-1].pitch % 12 in _chord_pcs("i")


def test_counter_melody_answer_needs_material():
    mel = _verse_melody_with_hole()
    # no rests, or no cell → the lead simply owns the space
    assert generate_counter_melody(mel, "C", "minor", 4, PROG, {"id": "t"},
                                   melody_rests=None, cell=CELL, section_type="verse") == []
    assert generate_counter_melody(mel, "C", "minor", 4, PROG, {"id": "t"},
                                   melody_rests=[(2.0, 6.0)], cell=None, section_type="verse") == []


def test_counter_melody_harmony_mode_unchanged_on_chorus_and_default():
    """Choruses (and the no-section-type default) keep the original harmony
    behavior: a note shadowing each structural lead note, not rest-filling."""
    mel = _verse_melody_with_hole()
    for stype in (None, "chorus"):
        random.seed(5)
        cm = generate_counter_melody(mel, "C", "minor", 4, PROG, {"id": "t"},
                                     melody_rests=[(2.0, 6.0)], cell=CELL, section_type=stype)
        assert cm, f"harmony mode ({stype}) produced nothing"
        # harmony rides the lead: every note lines up with a melody onset (the
        # harmony sits a hair — 0.012 beat — behind, so match within tolerance)...
        mel_starts = [m.start for m in mel]
        assert all(any(abs(n.start - ms) < 0.05 for ms in mel_starts) for n in cm)
        # ...so nothing lands in the hole (2–6) where the lead is silent
        assert not any(2.0 <= n.start < 6.0 for n in cm)


def test_counter_melody_answer_is_deterministic():
    mel = _verse_melody_with_hole()
    outs = []
    for _ in range(2):
        random.seed(11)
        outs.append(generate_counter_melody(mel, "C", "minor", 4, PROG, {"id": "t"},
                                            melody_rests=[(2.0, 6.0)], cell=CELL, section_type="verse"))
    assert [(n.pitch, n.start) for n in outs[0]] == [(n.pitch, n.start) for n in outs[1]]


# ── Tier A: bass floor answer ───────────────────────────────────────────────

def _bass_style():
    # minimal generic-bass style (no 808/walking override)
    return {"id": "t", "bass": {"pattern_density": 0.6}}


def test_bass_answer_uses_the_cell_when_present():
    """With a melodic cell the bass rest-fill traces the theme; without one it
    falls back to the old root→5th figure. The two must differ."""
    rests = [(4.0, 7.5)]
    kwargs = dict(progression=PROG, kick_times=None, melody_rests=rests,
                  harmony_complexity=0.5)
    random.seed(2)
    themed = generate_bass(_bass_style(), "C", "minor", 4, 0.5, 0.3,
                           cell_contour=CELL, **kwargs)
    random.seed(2)
    plain = generate_bass(_bass_style(), "C", "minor", 4, 0.5, 0.3,
                          cell_contour=None, **kwargs)
    fills_themed = [e for e in themed if e.start >= 4.0]
    fills_plain  = [e for e in plain if e.start >= 4.0]
    assert fills_themed, "no bass answer fired in the rest"
    # the cell path produces a different figure than the generic fallback
    assert [(e.pitch, round(e.start, 2)) for e in fills_themed] != \
           [(e.pitch, round(e.start, 2)) for e in fills_plain]
    # and every answer note stays in a sane bass register
    assert all(24 <= e.pitch <= 55 for e in fills_themed)
