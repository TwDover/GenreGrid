# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Roadmap v3 item 10.2 — the scorer measures the bar the music is actually in.

`quality.py` hard-coded a 4-beat bar, so in 3/4, 6/8 or 7/8 every bar-relative
measurement landed in the wrong place: the 16-step rhythm vectors folded bar 2
onto the tail of bar 1, hook self-similarity compared arbitrary 4-beat windows,
and density divided by a beat count no bar had. The measured effect was total:
non-4/4 rhythm scored 0.51 against 0.92 in 4/4, nothing went green, and every
case burned the full 5-attempt search budget chasing noise.

Two invariants are pinned here:
  * meter-native binning — hand-placed events land in the slots they occupy;
  * 4/4 is untouched — `bar_beats == 4.0` collapses every formula to the old
    arithmetic, so omitting `meter` and passing `Meter(4, 4)` must agree exactly.
"""
import pytest

from app.core.meter import Meter, backbeat_beats, parse_meter
from app.generators.drums import generate_drums
from app.core.constants import DRUM_MAP, DRUM_CHANNEL
from app.services.generation import _chord_tones_by_bar
from app.services.midi_writer import NoteEvent
from app.services.quality import (
    _build_chord_map, _density_fit, _extract_steps, _hook_score, _rhythm_fit,
    extract_rhythm_patterns, score_generation,
)
from app.services.style_loader import load_style

M44, M34, M68, M78, M54 = (Meter(4, 4), Meter(3, 4), Meter(6, 8),
                           Meter(7, 8), Meter(5, 4))


def _style(style_id="rock"):
    return {**load_style(style_id), "_humanize_scale": 0.5}


def _kick(beat: float) -> NoteEvent:
    return NoteEvent(DRUM_MAP["kick"], beat, 0.25, 100, DRUM_CHANNEL)


def _snare(beat: float) -> NoteEvent:
    return NoteEvent(DRUM_MAP["snare"], beat, 0.25, 100, DRUM_CHANNEL)


# ── step vectors bin on the real bar ──────────────────────────────────────────

@pytest.mark.parametrize("meter,expected_steps", [
    (M44, 16), (M34, 12), (M68, 12), (M78, 14), (M54, 20),
])
def test_step_vector_is_one_bar_long_in_this_meter(meter, expected_steps):
    assert meter.steps_per_bar == expected_steps
    vec = _extract_steps([_kick(0.0)], DRUM_MAP["kick"], 1, DRUM_CHANNEL, meter)
    assert len(vec) == expected_steps


def test_downbeat_kicks_land_on_step_zero_in_three_four():
    """The bug in one line: in 3/4 the bar-2 downbeat sits at beat 3.0, which a
    4-beat grid called step 12 of bar 0 — a hit on the '4-and' of a bar that has
    no beat 4. All four downbeats must pile onto step 0."""
    downbeats = [_kick(b * 3.0) for b in range(4)]

    correct = _extract_steps(downbeats, DRUM_MAP["kick"], 4, DRUM_CHANNEL, M34)
    assert correct[0] == 1.0
    assert sum(correct[1:]) == 0.0

    smeared = _extract_steps(downbeats, DRUM_MAP["kick"], 4, DRUM_CHANNEL, M44)
    assert smeared[0] < 1.0, "the 4/4 grid should be the one that scatters them"


def test_seven_eight_bar_two_is_not_folded_into_bar_one():
    """7/8 bars are 3.5 beats; the second bar starts at 3.5, which the 4/4 grid
    binned as step 14 of bar 0 instead of step 0 of bar 1."""
    events = [_kick(0.0), _kick(3.5), _kick(7.0)]
    vec = _extract_steps(events, DRUM_MAP["kick"], 3, DRUM_CHANNEL, M78)
    assert vec[0] == 1.0

    off_beat = _extract_steps(events, DRUM_MAP["kick"], 3, DRUM_CHANNEL, M44)
    assert off_beat[0] == pytest.approx(1 / 3)


def test_events_past_the_bar_count_are_dropped_on_the_real_bar_length():
    """`bars` is a count of this meter's bars, so the window is bars*bar_beats."""
    # Beat 6.0 is bar 3 of a 3/4 piece — outside a 2-bar window.
    vec = _extract_steps([_kick(0.0), _kick(6.0)], DRUM_MAP["kick"], 2,
                         DRUM_CHANNEL, M34)
    assert vec[0] == 1.0 and sum(vec) == 1.0


# ── rhythm fit ────────────────────────────────────────────────────────────────

def test_style_references_are_refit_the_way_the_generators_read_them():
    """`kick_pattern` / `chord_rhythm` are 16-step 4/4 vectors, but a 3/4
    generation still plays them — the drum generator drops entries past the bar
    end, the chord generator indexes modulo the pattern. The reference must be
    refit the same way, not compared to an unmodified 16-step bar."""
    from app.services.quality import _fit_reference
    ref = list(range(16))

    assert _fit_reference(ref, 12, wrap=False) == [float(i) for i in range(12)]
    assert _fit_reference(ref, 12, wrap=True) == [float(i) for i in range(12)]
    # A 5/4 bar is longer than the pattern: the kick simply has nothing out
    # there, while the chord comp wraps back to the pattern's head.
    assert _fit_reference(ref, 20, wrap=False)[16:] == [0.0] * 4
    assert _fit_reference(ref, 20, wrap=True)[16:] == [0.0, 1.0, 2.0, 3.0]
    # Identity at 16 steps — this is why 4/4 is untouched.
    assert _fit_reference(ref, 16, wrap=False) == _fit_reference(ref, 16, wrap=True) \
        == [float(i) for i in range(16)]


def test_rhythm_still_discriminates_in_non_four_four():
    """Refitting matters because skipping the step patterns entirely would leave
    the backbeat as the only reference — and every generation would score 1.0,
    giving the search no signal at all in non-4/4."""
    style = _style("rock")
    on_pattern  = [_kick(b * 3.0) for b in range(4)]
    off_pattern = [_kick(b * 3.0 + 0.75) for b in range(4)]
    assert _rhythm_fit(on_pattern, [], style, 4, M34)[0] > \
           _rhythm_fit(off_pattern, [], style, 4, M34)[0]


def test_backbeat_reference_follows_the_meter_not_the_authored_beats():
    """rock authors snare on beats 2 and 4; a 6/8 bar has neither. The generator
    plays the second dotted-quarter pulse, and the scorer must expect it there."""
    style = _style("rock")
    on_pulse  = [_kick(b * 3.0) for b in range(4)] + [_snare(b * 3.0 + 1.5) for b in range(4)]
    on_beat_2 = [_kick(b * 3.0) for b in range(4)] + [_snare(b * 3.0 + 1.0) for b in range(4)]

    assert _rhythm_fit(on_pulse, [], style, 4, M68)[0] > \
           _rhythm_fit(on_beat_2, [], style, 4, M68)[0]


def test_scorer_expects_the_backbeat_the_drum_generator_plays():
    """The shared `backbeat_beats` rule is the point: generator and scorer cannot
    drift, because scoring a 7/8 groove against a 4/4 backbeat was half of why
    every non-4/4 case failed the rhythm dimension."""
    import random
    style = _style("rock")
    for meter in (M34, M68, M78, M54):
        random.seed(4242)
        events = generate_drums(style, 4, 0.5, 0.4, meter=meter)
        snares = [e for e in events
                  if e.pitch in (DRUM_MAP["snare"], DRUM_MAP["clap"])]
        expected = [(b - 1.0) % meter.bar_beats
                    for b in backbeat_beats(meter, style["drums"]["snare_standard_beats"])]
        landed = [e.start % meter.bar_beats for e in snares]
        # Humanised microtiming moves onsets a few ms; the scorer's 16th-note
        # binning absorbs that, so match at the same resolution.
        assert any(abs(l - x) < 0.125 for l in landed for x in expected), \
            f"{meter}: no snare on the expected backbeat {expected}, got {sorted(set(landed))}"


# ── other bar-relative dimensions ─────────────────────────────────────────────

def test_density_divides_by_the_real_beat_count():
    """A 3/4 bar is 3 beats, not 4 — dividing by 4 reported every 3/4 melody as
    25% sparser than it is, pushing the search toward over-dense lines."""
    style = _style("rock")
    melody = [NoteEvent(60 + i % 5, i * 0.5, 0.5, 90, 2) for i in range(24)]

    s34, _ = _density_fit(melody, [], style, 4, 0.5, M34)
    s44, _ = _density_fit(melody, [], style, 4, 0.5, M44)
    assert s34 != s44


def test_hook_bars_are_this_meters_bars():
    """A figure repeated every 3 beats is a repeated bar in 3/4 and nothing in
    particular in 4/4, so self-similarity must rise when the meter is right."""
    figure = [0.0, 0.5, 1.5, 2.0]
    notes = [NoteEvent(60 + int(o * 2) % 4, bar * 3.0 + o, 0.5, 90, 2)
             for bar in range(4) for o in figure]

    s34, _ = _hook_score(notes, M34)
    s44, _ = _hook_score(notes, M44)
    assert s34 is not None and s44 is not None
    assert s34 > s44


def test_chord_map_slots_span_the_real_bar():
    cmap = _build_chord_map(["i", "iv"], "C", "minor", 2, 0.5, M34)
    assert [(s, e) for s, e, _ in cmap] == [(0.0, 3.0), (3.0, 6.0)]


def test_chord_tones_bin_by_the_real_bar():
    """The arpeggio reads its chord tones from this map; in 3/4 the second bar's
    voicing was being filed under bar 0."""
    notes = [(0.0, 60), (0.0, 64), (3.0, 62), (3.0, 65)]
    tones = _chord_tones_by_bar(notes, 2, M34)
    assert tones == [[0, 4], [2, 5]]


# ── 4/4 stays exactly as it was ───────────────────────────────────────────────

def test_explicit_four_four_equals_the_default_everywhere():
    """The gating invariant: `bar_beats == 4.0` collapses every new formula to
    the old arithmetic, so a 4/4 caller sees byte-identical numbers."""
    style = _style("rock")
    drums  = [_kick(b * 4.0) for b in range(4)] + [_snare(b * 4.0 + 1.0) for b in range(4)]
    chords = [NoteEvent(60, b * 4.0, 2.0, 80, 0) for b in range(4)]
    melody = [NoteEvent(60 + i % 7, i * 0.5, 0.5, 90, 2) for i in range(32)]
    bass   = [NoteEvent(40, b * 2.0, 1.0, 100, 1) for b in range(8)]
    events = {"drums": drums, "chords": chords, "melody": melody, "bass": bass}

    assert _extract_steps(drums, DRUM_MAP["kick"], 4, DRUM_CHANNEL) == \
           _extract_steps(drums, DRUM_MAP["kick"], 4, DRUM_CHANNEL, M44)
    assert _rhythm_fit(drums, chords, style, 4) == _rhythm_fit(drums, chords, style, 4, M44)
    assert _density_fit(melody, bass, style, 4, 0.5) == _density_fit(melody, bass, style, 4, 0.5, M44)
    assert _hook_score(melody) == _hook_score(melody, M44)
    assert _build_chord_map(["i", "iv"], "C", "minor", 4, 0.5) == \
           _build_chord_map(["i", "iv"], "C", "minor", 4, 0.5, M44)
    assert extract_rhythm_patterns(events, 4) == extract_rhythm_patterns(events, 4, M44)
    assert score_generation(events, style, "C", "minor", 4, ["i", "iv"], 0.5) == \
           score_generation(events, style, "C", "minor", 4, ["i", "iv"], 0.5, meter=M44)


def test_backbeat_beats_leaves_four_four_alone():
    assert backbeat_beats(M44, [2, 4]) == [2.0, 4.0]
    assert backbeat_beats(M44) == [2.0, 4.0]
    # Half-time sections keep their authored beat in any meter.
    assert backbeat_beats(M68, [3], half_time=True) == [3.0]


@pytest.mark.parametrize("meter,expected", [
    (M44, [2.0, 4.0]),      # unchanged
    (M34, [2.0]),           # beat 4 overflows the bar; centre pulse remains
    (M68, [2.5]),           # the second dotted-quarter pulse (beat 1.5, 1-indexed)
    (M78, [2.0]),           # 2+2+3 -> the middle group
])
def test_backbeat_lands_on_felt_pulses(meter, expected):
    assert backbeat_beats(meter, [2, 4]) == pytest.approx(expected)


# ── strong beats for melodic runs ─────────────────────────────────────────────

@pytest.mark.parametrize("meter,expected", [
    (M44, [0.0, 2.0]),      # unchanged — bebop/approach runs still fire on 1 and 3
    (M34, [0.0]),           # 1.5 is not a felt pulse in 3/4
    (M68, [0.0, 1.5]),      # both dotted-quarter beats
    (Meter(12, 8), [0.0, 3.0]),
    (M78, [0.0]),
    (M54, [0.0]),
])
def test_strong_positions(meter, expected):
    assert meter.strong_positions == pytest.approx(expected)


def test_bebop_runs_only_start_on_meter_strong_beats():
    """jazz melodies in 3/4 used to start descending runs wherever `% 4` happened
    to land: bar 2 begins at beat 3.0, so `3.0 % 4 == 3.0` — never a strong beat —
    while bar 3's beat 2 read as `8.0 % 4 == 0`, a phantom downbeat mid-bar."""
    import random
    from app.generators.melody import generate_melody

    def melody_with(bebop_prob, seed):
        style = {**load_style("jazz"), "_humanize_scale": 0.0}
        style["melody"] = {**style.get("melody", {}),
                           "bebop_run_prob": bebop_prob, "run_prob": 0.0,
                           "trill_prob": 0.0}
        random.seed(seed)
        return generate_melody(style, "C", "minor", 16, 0.5, 0.4,
                               ["i", "iv", "V", "i"], meter=M34)

    # Isolate the run notes by diffing against the same seed with runs disabled.
    # Only the first two bars are compared: past them the motif-block transform
    # rewrites bars wholesale, which would mix copied notes into the sample.
    heads: list[float] = []
    for seed in range(1, 60):
        without = {round(e.start, 3) for e in melody_with(0.0, seed) if e.start < 6.0}
        with_   = {round(e.start, 3) for e in melody_with(1.0, seed) if e.start < 6.0}
        for start in sorted(with_ - without):
            if round(start - 0.25, 3) not in with_:      # first note of the run
                heads.append(start % 3.0)

    assert heads, "the test needs bebop runs to actually fire"
    for h in heads:
        # Microtiming can nudge a downbeat just under the bar line, so measure
        # distance to a strong position the short way round the bar.
        dist = min(min(abs(h - p), abs(h - (3.0 - p))) for p in M34.strong_positions)
        assert dist < 0.06, f"bebop run starts at beat {h:.2f} of a 3/4 bar"


# ── library isolation ─────────────────────────────────────────────────────────

def test_library_only_blends_four_four_fingerprints():
    """A saved 3/4 generation's pattern is a 12-step bar; averaging it into the
    16-step 4/4 style reference would zero-pad a bar nobody played."""
    from app.services.library import _is_44_fingerprint
    assert _is_44_fingerprint({"patterns": {"kick_pattern": [0.0] * 16,
                                            "chord_pattern": [0.0] * 16}})
    assert not _is_44_fingerprint({"patterns": {"kick_pattern": [0.0] * 12,
                                                "chord_pattern": [0.0] * 12}})
    assert _is_44_fingerprint({})       # nothing to distort


def test_extract_patterns_are_meter_native():
    events = {"drums": [_kick(b * 3.0) for b in range(4)], "chords": []}
    pats = extract_rhythm_patterns(events, 4, M34)
    assert len(pats["kick_pattern"]) == 12
    assert pats["kick_pattern"][0] == 1.0


# ── end to end ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ts", ["3/4", "6/8", "7/8", "5/4"])
def test_generated_non_four_four_scores_are_not_noise(ts):
    """The measured outcome of the item: a real generation in a non-4/4 meter
    scores its rhythm on the grid it was played on, instead of the 0.51 noise
    floor the 4/4-only scorer produced."""
    from app.models.schemas import GenerateRequest
    from app.services.generation import _run_attempt

    req = GenerateRequest(style_id="rock", key="C", scale="minor", bpm=120,
                          bars=8, complexity=0.5, variation=0.4,
                          parts=["chords", "bass", "melody", "drums"],
                          time_signature=ts, mode="arrangement")
    style = _style("rock")
    _events, _cc, _pb, _prog, quality, _pats, _secs = _run_attempt(
        req, style, 20260804, False, style.get("groove_push", 0.0), False, False)
    assert quality is not None
    assert quality["rhythm"] > 0.6, f"{ts} rhythm still reads as noise"


@pytest.mark.parametrize("ts,bar_beats", [("4/4", 4.0), ("7/8", 3.5), ("3/4", 3.0)])
def test_regenerated_part_stays_in_the_songs_meter(ts, bar_beats, tmp_path):
    """`regenerate_part` took a `time_signature` and ignored it, so re-rolling one
    part of a 7/8 song wrote a 4/4 part over it — 32 beats of melody across 28
    beats of everything else."""
    import mido
    from fastapi.testclient import TestClient
    from app.core.config import EXPORTS_DIR
    from app.main import app

    client = TestClient(app)
    body = {"style_id": "rock", "key": "C", "scale": "minor", "bpm": 120, "bars": 8,
            "complexity": 0.5, "variation": 0.4, "time_signature": ts,
            "mode": "arrangement", "seed": 123}
    gen = client.post("/generate", json={**body, "parts": ["chords", "bass", "melody", "drums"]})
    assert gen.status_code == 200
    gen_id = gen.json()["generation_id"]

    regen = client.post("/regenerate-part",
                        json={**body, "generation_id": gen_id, "part": "melody"})
    assert regen.status_code == 200

    mid = mido.MidiFile(EXPORTS_DIR / gen_id / "melody.mid")
    assert [(m.numerator, m.denominator) for tr in mid.tracks for m in tr
            if m.type == "time_signature"] == [tuple(int(x) for x in ts.split("/"))]
    span = max(sum(m.time for m in tr) for tr in mid.tracks) / mid.ticks_per_beat
    assert span <= 8 * bar_beats + 0.1, "regenerated part overruns the song's bars"
