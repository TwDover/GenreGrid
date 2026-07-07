# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Regression tests for musical behavior: section-aware drums, harmonic
correctness, song endings, tempo maps, and section arrangement rules."""
import random

import mido
import pytest

from app.core.constants import DRUM_MAP
from app.theory.chords import roman_to_chord
from app.generators.drums import generate_drums
from app.generators.chords import generate_chords, resolve_progression
from app.services.style_loader import load_style
from app.models.schemas import BuildSongRequest, SongSectionDef, RegenerateSongPartRequest
from app.api.routes_generate import build_song, regenerate_song_part
from app.core.arrangement import _song_tempo_map
from app.core.config import EXPORTS_DIR


def _style(style_id="lofi"):
    return {**load_style(style_id), "_humanize_scale": 0.5}


# ── Harmony correctness ───────────────────────────────────────────────────────

def test_pentatonic_degrees_match_diatonic_roots():
    """Unflatted VI/VII in a 5-note scale must not alias onto I/ii roots."""
    for roman in ("I", "ii", "VI", "VII"):
        assert roman_to_chord(roman, "C", "pentatonic_minor") == \
               roman_to_chord(roman, "C", "minor"), f"{roman} aliased in pentatonic_minor"


def test_harmony_complexity_drives_chords_per_bar():
    """harmony_complexity above 0.6 must produce two chord changes per bar."""
    random.seed(3)
    evts = generate_chords(_style(), "C", "minor", 2, 0.4, 0.3,
                           ["i", "VI", "III", "VII"], ["i", "VI", "III", "VII"],
                           harmony_complexity=0.8)
    # With 2 chords/bar the second chord of bar 1 starts near beat 2
    assert any(1.8 <= e.start <= 2.3 for e in evts), \
        "expected a chord change near beat 2 with harmony_complexity=0.8"


def test_prev_voicing_seeds_voice_leading():
    """A supplied prev_voicing must pull the first chord's voicing toward it."""
    prog = ["i", "VI", "III", "VII"]
    resolved = resolve_progression(prog, "minor", 0.3)
    random.seed(7)
    free = generate_chords(_style(), "C", "minor", 1, 0.3, 0.2, prog, resolved)
    random.seed(7)
    seeded = generate_chords(_style(), "C", "minor", 1, 0.3, 0.2, prog, resolved,
                             prev_voicing=[67, 72, 76])
    first_free   = sorted({e.pitch for e in free   if e.start < 0.5})
    first_seeded = sorted({e.pitch for e in seeded if e.start < 0.5})
    # Same pitch classes (same chord), but voiced differently because of the seed
    assert {p % 12 for p in first_free} == {p % 12 for p in first_seeded}


# ── Section-aware drums ───────────────────────────────────────────────────────

def test_intro_drums_have_no_snare():
    random.seed(11)
    evts = generate_drums(_style(), 4, 0.6, 0.4, is_loop=True, section_type="intro")
    assert not any(e.pitch == DRUM_MAP["snare"] for e in evts)


def test_chorus_opens_with_crash():
    random.seed(11)
    evts = generate_drums(_style(), 8, 0.6, 0.4, is_loop=True, section_type="chorus")
    assert any(e.pitch == DRUM_MAP["crash"] and abs(e.start) < 0.2 for e in evts)


def test_bridge_is_half_time():
    """Bridge snare sits on beat 3 (beat-in-bar 2.0), never on beats 2/4."""
    random.seed(11)
    evts = generate_drums(_style(), 4, 0.6, 0.4, is_loop=True, section_type="bridge")
    snare_beats = {round(e.start % 4, 1) for e in evts if e.pitch == DRUM_MAP["snare"]}
    assert not ({1.0, 3.0} & snare_beats), f"backbeat snares in half-time bridge: {snare_beats}"


def test_build_roll_into_chorus():
    """The last bar before a chorus gets a snare-roll build for any style."""
    random.seed(11)
    evts = generate_drums(_style(), 4, 0.6, 0.4, is_loop=True,
                          section_end_bars=[3], section_type="verse",
                          next_section_type="chorus")
    roll = [e for e in evts if e.pitch == DRUM_MAP["snare"] and 15.4 <= e.start < 16.1]
    assert len(roll) >= 6, f"expected a snare-roll build, got {len(roll)} hits"


# ── Tempo map ─────────────────────────────────────────────────────────────────

def test_tempo_map_chorus_push_and_ritardando():
    secs = [
        {"start_bar": 0,  "bars": 4, "section_type": "intro"},
        {"start_bar": 4,  "bars": 8, "section_type": "chorus"},
        {"start_bar": 12, "bars": 4, "section_type": "outro"},
        {"start_bar": 16, "bars": 1, "section_type": "ending"},
    ]
    points = _song_tempo_map(secs, 100, ending_bars=1)
    bpms = [b for _, b in points]
    assert points[0] == (0.0, 100.0)
    assert any(b > 100 for b in bpms), "no chorus push"
    assert bpms[-1] < 100 * 0.8, "no final ritardando"


# ── Full song structure ───────────────────────────────────────────────────────

def test_song_has_ending_bar_and_tempo_track():
    r = build_song(BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=90,
                                    template="compact",
                                    parts=["chords", "bass", "melody", "drums"], seed=31))
    assert r.sections[-1].section_type == "ending"
    assert r.total_bars == 41  # compact template (40) + ending bar

    d = EXPORTS_DIR / r.generation_id
    mid = mido.MidiFile(str(d / "chords.mid"))
    tempos = [msg for tr in mid.tracks for msg in tr if msg.type == "set_tempo"]
    assert len(tempos) > 1, "stems should carry the tempo map, not a single tempo"

    # The ending bar carries a held tonic chord in the chords stem
    tpb = mid.ticks_per_beat
    ending_beat = 40 * 4
    notes = []
    for tr in mid.tracks:
        t = 0
        for msg in tr:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0 and t / tpb >= ending_beat - 0.5:
                notes.append(msg.note % 12)
    assert 0 in notes, "ending bar should land on the tonic (C)"


@pytest.fixture(scope="module")
def song_vc():
    """One verse_chorus build shared by the gear-change/tease/quality tests.

    use_priors=False keeps this hermetic: the mining tests install corpus
    priors into the shared library, which would otherwise change what this
    build generates depending on test execution order.
    """
    return build_song(BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=90,
                                       template="verse_chorus",
                                       parts=["chords", "bass", "melody", "drums"],
                                       seed=53, chorus_key_shift=0, final_chorus_lift=2,
                                       use_priors=False))


def _note_ons(gen_id: str, part: str) -> list[tuple[float, int]]:
    mid = mido.MidiFile(str(EXPORTS_DIR / gen_id / f"{part}.mid"))
    tpb = mid.ticks_per_beat
    out = []
    for tr in mid.tracks:
        t = 0
        for msg in tr:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                out.append((t / tpb, msg.note))
    return out


def _section_events(song, gen_id, part, name):
    s = next(x for x in song.sections if x.name == name)
    a, b = s.start_bar * 4, (s.start_bar + s.bars) * 4
    return {(round(t - a, 2), p) for t, p in _note_ons(gen_id, part) if a <= t < b}


def test_final_chorus_gear_change(song_vc):
    """The last chorus plays the chorus theme lifted by final_chorus_lift semitones."""
    c1 = _section_events(song_vc, song_vc.generation_id, "melody", "Chorus")
    c2 = _section_events(song_vc, song_vc.generation_id, "melody", "Chorus 2")
    lifted = {(t, p + 2) for t, p in c1}
    overlap = len(c2 & lifted) / max(1, len(lifted))
    assert overlap >= 0.5, f"final chorus doesn't carry the lifted theme (overlap {overlap:.2f})"
    # And it should NOT still be in the original key
    same_key = len(c2 & c1) / max(1, len(c1))
    assert same_key < overlap, "final chorus melody was not transposed"


def test_intro_teases_chorus_hook(song_vc):
    """The intro melody is a thinned copy of the chorus hook (home key)."""
    intro = _section_events(song_vc, song_vc.generation_id, "melody", "Intro")
    chorus = _section_events(song_vc, song_vc.generation_id, "melody", "Chorus")
    assert intro, "intro should carry the hook tease"
    matched = sum(1 for ev in intro if ev in chorus)
    assert matched / len(intro) >= 0.8, "intro melody should come from the chorus hook"


def test_sections_carry_quality(song_vc):
    non_ending = [s for s in song_vc.sections if s.section_type != "ending"]
    assert all(s.quality is not None and 0.0 <= s.quality <= 1.0 for s in non_ending)


def test_custom_template_build_and_regen():
    custom = [
        SongSectionDef(section_type="verse", bars=4, parts_mode="no_arp"),
        SongSectionDef(section_type="chorus", bars=4, parts_mode="full"),
        SongSectionDef(section_type="outro", bars=2, parts_mode="melodic"),
    ]
    r = build_song(BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=90,
                                    template="custom", custom_template=custom,
                                    parts=["chords", "bass", "melody", "drums"], seed=9))
    assert [s.bars for s in r.sections] == [4, 4, 2, 1]   # + ending bar
    assert r.total_bars == 11
    # Part regeneration must work against the persisted custom template
    fi = regenerate_song_part(RegenerateSongPartRequest(generation_id=r.generation_id, part="drums"))
    assert fi.part == "drums"


def test_pads_and_counter_melody_arrangement_rules():
    """Pads only in chorus/bridge; counter-melody only in the final chorus."""
    r = build_song(BuildSongRequest(style_id="lofi", key="C", scale="major", bpm=90,
                                    template="verse_chorus",
                                    parts=["chords", "bass", "melody", "drums",
                                           "pads", "counter_melody"], seed=41))
    d = EXPORTS_DIR / r.generation_id
    secs = {s.name: (s.start_bar * 4, (s.start_bar + s.bars) * 4) for s in r.sections}

    def starts(part):
        mid = mido.MidiFile(str(d / f"{part}.mid"))
        tpb = mid.ticks_per_beat
        out = []
        for tr in mid.tracks:
            t = 0
            for msg in tr:
                t += msg.time
                if msg.type == "note_on" and msg.velocity > 0:
                    out.append(t / tpb)
        return out

    verse_lo, verse_hi = secs["Verse"]
    pad_starts = starts("pads")
    assert not any(verse_lo <= s < verse_hi - 0.2 for s in pad_starts), "pads leaked into the verse"

    c1_lo, c1_hi = secs["Chorus"]
    fc_lo, fc_hi = secs["Chorus 2"]
    cm_starts = starts("counter_melody")
    assert not any(c1_lo <= s < c1_hi - 0.2 for s in cm_starts), "counter-melody in first chorus"
    assert any(fc_lo <= s < fc_hi for s in cm_starts), "counter-melody missing from final chorus"
