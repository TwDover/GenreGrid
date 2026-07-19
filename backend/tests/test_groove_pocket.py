# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""The shared groove pocket: the band must move TOGETHER.

Independent per-note jitter made parts smear against each other; the pocket
is one per-16th-slot offset table every part shares, seeded from the style id
so sections and regenerations reproduce it exactly.
"""
import random

from app.services.humanize import groove_pocket_table, apply_groove_pocket, apply_feel
from app.services.midi_writer import NoteEvent
from app.core.constants import DRUM_MAP


def test_pocket_table_is_deterministic_and_style_specific():
    a = groove_pocket_table({"id": "rnb"})
    b = groove_pocket_table({"id": "rnb"})
    assert a == b                       # crc32-seeded, not hash()-salted
    assert len(a) == 16
    assert groove_pocket_table({"id": "jazz"}) != a
    # Loose styles get a wider pocket than tight ones
    assert max(map(abs, groove_pocket_table({"id": "jazz"}))) > \
           max(map(abs, groove_pocket_table({"id": "techno"})))


def test_parts_share_the_pocket_and_rhythm_section_locks():
    style = {"id": "rnb"}
    table = groove_pocket_table(style)
    # kick and bass note on the same grid position must receive the SAME shift
    events = {
        "drums": [NoteEvent(36, 2.0, 0.1, 100, 9)],
        "bass":  [NoteEvent(40, 2.0, 0.9, 90, 1)],
        "melody": [NoteEvent(72, 2.0, 0.5, 80, 2)],
    }
    apply_groove_pocket(events, style)
    slot_off = table[8]   # beat 2.0 → slot 8
    assert abs(events["drums"][0].start - (2.0 + slot_off)) < 1e-9
    assert abs(events["bass"][0].start - (2.0 + slot_off)) < 1e-9
    assert events["drums"][0].start == events["bass"][0].start   # locked
    # melody rides the same pocket but looser (0.7 tightness)
    assert abs(events["melody"][0].start - (2.0 + slot_off * 0.7)) < 1e-9


def test_pocket_never_produces_negative_starts():
    style = {"id": "jazz", "_humanize_scale": 1.0}
    events = {"drums": [NoteEvent(36, 0.0, 0.1, 100, 9)],
              "bass": [NoteEvent(36, 0.0, 0.5, 90, 1)]}
    apply_groove_pocket(events, style)
    for part in events:
        for e in events[part]:
            assert e.start >= 0.0


def test_feel_profile_drags_backbeat_and_lags_bass():
    """A laid-back style (lofi) drags the snare backbeat behind the grid, pushes
    the hats ahead, and sits the bass behind the kick — systematic, not random."""
    style = {"id": "lofi", "_humanize_scale": 0.5}
    snare, kick, hat = DRUM_MAP["snare"], DRUM_MAP["kick"], DRUM_MAP["closed_hat"]
    events = {
        "drums": [NoteEvent(snare, 1.0, 0.1, 100, 9),   # beat 2 = backbeat (slot 4)
                  NoteEvent(kick, 0.0, 0.1, 110, 9),
                  NoteEvent(hat, 0.5, 0.1, 80, 9)],       # slot 2
        "bass":  [NoteEvent(40, 0.0, 0.9, 90, 1)],
    }
    handled = apply_feel(events, style)
    assert handled == {"drums", "bass"}
    snare_ev = next(e for e in events["drums"] if e.pitch == snare)
    hat_ev   = next(e for e in events["drums"] if e.pitch == hat)
    assert snare_ev.start > 1.0                 # backbeat drags LATE
    assert hat_ev.start < 0.5                    # hat pushes EARLY
    assert events["bass"][0].start > 0.0         # bass sits behind the kick


def test_feel_absent_style_is_untouched():
    """A style with no feel profile is placed by neither apply_feel nor a feel
    branch — byte-identical to pre-feel output."""
    style = {"id": "techno", "_humanize_scale": 0.5}
    before = [NoteEvent(DRUM_MAP["snare"], 1.0, 0.1, 100, 9)]
    events = {"drums": list(before), "bass": [NoteEvent(40, 0.0, 0.9, 90, 1)]}
    assert apply_feel(events, style) == set()
    assert events["drums"][0].start == 1.0 and events["drums"][0].velocity == 100
    assert events["bass"][0].start == 0.0


def test_mined_feel_derivation_recovers_offsets():
    """derive_feel turns per-voice microtiming into per-class timing offsets."""
    from app.mining.drums import empty_groove, analyze_drum_song, derive_feel
    from app.mining.midi_io import MidiSong, Note

    # Eight bars (>16 notes, the analyzer's floor): snare backbeats consistently
    # 0.03 beat late, kicks on the grid.
    notes = []
    for bar in range(8):
        notes.append(Note(pitch=36, start=bar * 4 + 0.0, duration=0.2, velocity=110, channel=9))
        notes.append(Note(pitch=38, start=bar * 4 + 1.0 + 0.03, duration=0.2, velocity=100, channel=9))
        notes.append(Note(pitch=38, start=bar * 4 + 3.0 + 0.03, duration=0.2, velocity=100, channel=9))
    g = empty_groove("t")
    analyze_drum_song(MidiSong(notes=notes, ppq=480, total_beats=32.0), g)
    feel = derive_feel(g)
    assert abs(feel["snare"]["timing"][4] - 0.03) < 1e-6    # beat 2 backbeat late
    assert abs(feel["kick"]["timing"][0]) < 1e-6            # kick on the grid


def test_chord_anticipation_pushes_changes_early():
    from app.generators.chords import generate_chords

    prog = ["i", "VI", "III", "VII"]
    base = {"id": "t", "chord_rhythm": [1] + [0] * 15}
    for prob, expect_push in ((1.0, True), (0.0, False)):
        random.seed(4)
        style = {**base, "chord_anticipation_prob": prob}
        events = generate_chords(style, "C", "minor", bars=4, complexity=0.5,
                                 variation=0.3, progression=prog, resolved_progression=prog)
        for bar in (1, 2, 3):   # chord changes at beats 4, 8, 12
            window_start = bar * 4.0
            earliest = min(e.start for e in events if window_start - 1.0 <= e.start < window_start + 1.0)
            if expect_push:
                assert abs(earliest - (window_start - 0.5)) < 0.1, \
                    f"bar {bar}: expected push to {window_start - 0.5}, earliest {earliest}"
            else:
                assert earliest > window_start - 0.15, \
                    f"bar {bar}: unexpected early hit at {earliest}"


def test_ensemble_pushes_land_together():
    """The push map is decided once and observed by BOTH the comp and the
    bass — a lone early comp against an on-grid bass reads as a mistake."""
    from app.generators.chords import generate_chords
    from app.generators.bass import generate_bass

    prog = ["i", "VI", "III", "VII"]
    pushes = {1, 3}   # windows at beats 4 and 12 anticipate (1 chord/bar grid)
    chord_style = {"id": "t", "chord_rhythm": [1] + [0] * 15}
    bass_style = {"id": "t", "bass": {"bass_style": "808"}}

    random.seed(8)
    chords = generate_chords(chord_style, "C", "minor", bars=4, complexity=0.5,
                             variation=0.3, progression=prog, resolved_progression=prog,
                             push_windows=pushes)
    random.seed(8)
    bass = generate_bass(bass_style, "C", "minor", bars=4, complexity=0.5,
                         variation=0.3, progression=prog, harmony_complexity=0.5,
                         push_windows=pushes)

    for w, window_start in ((1, 4.0), (3, 12.0)):
        push_t = window_start - 0.5
        assert any(abs(e.start - push_t) < 0.12 for e in chords), f"chords window {w}: no hit at {push_t}"
        assert any(abs(e.start - push_t) < 0.12 for e in bass), f"bass window {w}: no hit at {push_t}"
    # Non-pushed window 2: the chords' window-start hit stays on the grid.
    # (Bass patterns legitimately place hits at x.75 offsets, so only the
    # comp — whose rhythm here is strictly window-start hits — is asserted.)
    assert not any(7.3 < e.start < 7.7 for e in chords), "chords window 2 pushed unexpectedly"
    assert any(abs(e.start - 8.0) < 0.12 for e in chords), "chords window 2 lost its downbeat hit"


def test_chorus_melody_contract():
    """Choruses sustain more and sit higher than verses — the lift IS the
    chorus. Averaged across seeds since both behaviors are probabilistic."""
    from app.generators.melody import generate_melody

    style = {"id": "t", "melody": {"density": 0.6, "stepwise_motion": 0.7,
                                   "leap_probability": 0.15, "rest_probability": 0.2,
                                   "range": [60, 79], "phrase_climax_prob": 0.0}}
    prog = ["i", "VI", "III", "VII"]

    def _stats(section_type):
        durs, pitches = [], []
        for seed in range(8):
            random.seed(seed)
            evs = generate_melody(style, "C", "minor", bars=8, complexity=0.5,
                                  variation=0.3, progression=prog, is_loop=True,
                                  section_type=section_type)
            durs.extend(e.duration for e in evs)
            pitches.extend(e.pitch for e in evs)
        return sum(durs) / len(durs), sum(pitches) / len(pitches)

    v_dur, v_pitch = _stats("verse")
    c_dur, c_pitch = _stats("chorus")
    assert c_dur > v_dur, f"chorus notes should sustain more: {c_dur:.3f} vs {v_dur:.3f}"
    assert c_pitch > v_pitch + 0.5, f"chorus should sit higher: {c_pitch:.1f} vs {v_pitch:.1f}"
