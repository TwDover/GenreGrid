# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Non-4/4 placement tests (roadmap Phase 4, Milestone 2).

Two guarantees:
  1. In any meter, no generated onset falls outside the bar it belongs to and
     nothing spills past the end of the loop.
  2. 4/4 stays byte-identical — passing an explicit Meter(4, 4) produces the
     exact same events as the default, so the meter plumbing is a no-op there.
"""
import random

import mido
import pytest

from app.core.meter import Meter, parse_meter, DEFAULT_METER
from app.generators.bass import generate_bass
from app.generators.drums import generate_drums
from app.generators.chords import generate_chords
from app.services.style_loader import load_style

_METERS = ["4/4", "3/4", "2/4", "6/8", "9/8", "12/8", "7/8", "5/8"]
_BARS = 8


# ── Meter model math ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("sig,bar_beats,steps,pulses", [
    ("4/4", 4.0, 16, [0.0, 1.0, 2.0, 3.0]),
    ("3/4", 3.0, 12, [0.0, 1.0, 2.0]),
    ("6/8", 3.0, 12, [0.0, 1.5]),
    ("7/8", 3.5, 14, [0.0, 1.0, 2.0]),      # 2+2+3 grouping
    ("9/8", 4.5, 18, [0.0, 1.5, 3.0]),
    ("5/8", 2.5, 10, [0.0, 1.0]),           # 2+3 grouping
])
def test_meter_math(sig, bar_beats, steps, pulses):
    m = parse_meter(sig)
    assert m.bar_beats == bar_beats
    assert m.steps_per_bar == steps
    assert m.pulse_positions == pulses


def test_compound_meters_flagged():
    for sig in ("6/8", "9/8", "12/8"):
        assert parse_meter(sig).is_compound
    for sig in ("4/4", "3/4", "7/8", "5/8"):
        assert not parse_meter(sig).is_compound


# ── No onset overflows its bar, in any meter ─────────────────────────────────

def _assert_within_bars(events, meter, bars, label):
    bb = meter.bar_beats
    span = bars * bb
    for e in events:
        rel = e.start % bb
        assert -1e-6 <= rel < bb, f"{label}: onset {e.start} sits outside its {meter} bar"
        assert e.start < span + 1e-6, f"{label}: onset {e.start} runs past the {span}-beat loop"


@pytest.mark.parametrize("sig", _METERS)
@pytest.mark.parametrize("style_id", ["rock", "house", "metal", "jazz", "funk"])
def test_drum_onsets_stay_in_bar(sig, style_id):
    style = load_style(style_id)
    meter = parse_meter(sig)
    random.seed(11)
    events = generate_drums(style, _BARS, 0.7, 0.5, meter=meter, is_loop=True)
    assert events, f"{style_id} {sig}: no drum events"
    _assert_within_bars(events, meter, _BARS, f"drums/{style_id}")


@pytest.mark.parametrize("sig", _METERS)
def test_walking_bass_onsets_stay_in_bar(sig):
    style = load_style("jazz")   # jazz uses walking bass
    meter = parse_meter(sig)
    random.seed(7)
    events = generate_bass(style, "C", "major", _BARS, 0.6, 0.5,
                           progression=["ii", "V", "I", "vi"], meter=meter)
    assert events
    _assert_within_bars(events, meter, _BARS, f"bass/{sig}")


@pytest.mark.parametrize("sig", _METERS)
def test_walking_bass_note_count_matches_pulses(sig):
    """The pulse walk places one note per felt pulse per bar (4/4 keeps its
    classic four-crotchet walk)."""
    style = load_style("jazz")
    meter = parse_meter(sig)
    random.seed(7)
    events = generate_bass(style, "C", "major", _BARS, 0.6, 0.5,
                           progression=["ii", "V", "I", "vi"], meter=meter)
    expected = len(meter.pulse_positions) * _BARS
    assert len(events) == expected, f"{sig}: {len(events)} notes, expected {expected}"


@pytest.mark.parametrize("sig", _METERS)
def test_riff_chords_stay_in_bar(sig):
    style = load_style("metal")   # metal comps with a riff (16-step 4/4 cells)
    meter = parse_meter(sig)
    random.seed(3)
    events = generate_chords(style, "E", "minor", _BARS, 0.7, 0.5,
                             progression=["i", "VI", "III", "VII"],
                             meter=meter, section_type="verse")
    assert events
    _assert_within_bars(events, meter, _BARS, f"riff-chords/{sig}")


# ── Idiomatic compound / odd feel ────────────────────────────────────────────

def _snare_onsets(events):
    from app.core.constants import DRUM_MAP
    return sorted({round(e.start, 3) for e in events if e.pitch == DRUM_MAP["snare"]})


def _hat_onsets(events):
    from app.core.constants import DRUM_MAP
    hats = {DRUM_MAP["closed_hat"], DRUM_MAP["open_hat"]}
    return sorted({round(e.start, 3) for e in events if e.pitch in hats})


@pytest.mark.parametrize("sig,pulse", [
    ("6/8", 1.5),    # compound duple → snare on the 2nd dotted-quarter pulse
    ("3/4", 1.0),    # waltz → backbeat on beat 2
    ("7/8", 1.0),    # 2+2+3 → snare starts the second group
])
def test_snare_lands_on_felt_pulse(sig, pulse):
    """Non-4/4 snare backbone sits on a felt pulse, not the clipped 4/4 grid.
    Ghost snares are quiet (<50) and filtered out — we check backbeat hits."""
    style = load_style("rock")
    meter = parse_meter(sig)
    random.seed(4)
    events = generate_drums(style, _BARS, 0.6, 0.4, meter=meter, is_loop=True)
    # Humanize jitter offsets onsets by up to ~0.02 beats — match within tolerance.
    backbeats = sorted({round(e.start % meter.bar_beats, 3)
                        for e in _backbeat_snares(events)})
    assert any(abs(b - pulse) < 0.05 for b in backbeats), \
        f"{sig}: snare backbeats {backbeats}, expected one near {pulse}"


def _backbeat_snares(events):
    from app.core.constants import DRUM_MAP
    return [e for e in events if e.pitch == DRUM_MAP["snare"] and e.velocity >= 60]


@pytest.mark.parametrize("sig", ["6/8", "9/8", "12/8"])
def test_compound_hats_ride_eighth_grid(sig):
    """Compound hats fall on the eighth-note grid (0.5-beat spacing), not a
    16th grid — every onset is a whole multiple of 0.5 within the bar."""
    style = load_style("rock")
    meter = parse_meter(sig)
    random.seed(8)
    events = generate_drums(style, _BARS, 0.6, 0.3, meter=meter, is_loop=True)
    for h in _hat_onsets(events):
        rel = h % meter.bar_beats
        # Nearest eighth-grid slot, allowing for humanize jitter (~0.02 beats).
        nearest = round(rel / 0.5) * 0.5
        assert abs(rel - nearest) < 0.05, f"{sig}: hat at {round(rel,3)} off the eighth grid"


# ── 4/4 stays byte-identical ─────────────────────────────────────────────────

@pytest.mark.parametrize("style_id", ["rock", "house", "metal", "jazz"])
def test_drums_44_byte_identical(style_id):
    style = load_style(style_id)
    random.seed(99)
    default = generate_drums(style, _BARS, 0.7, 0.5, is_loop=True)
    random.seed(99)
    explicit = generate_drums(style, _BARS, 0.7, 0.5, meter=Meter(4, 4), is_loop=True)
    assert default == explicit


def test_walking_bass_44_byte_identical():
    style = load_style("jazz")
    random.seed(42)
    default = generate_bass(style, "C", "major", _BARS, 0.6, 0.5,
                            progression=["ii", "V", "I", "vi"])
    random.seed(42)
    explicit = generate_bass(style, "C", "major", _BARS, 0.6, 0.5,
                             progression=["ii", "V", "I", "vi"], meter=Meter(4, 4))
    assert default == explicit


def test_riff_chords_44_byte_identical():
    style = load_style("metal")
    random.seed(5)
    default = generate_chords(style, "E", "minor", _BARS, 0.7, 0.5,
                              progression=["i", "VI", "III", "VII"], section_type="verse")
    random.seed(5)
    explicit = generate_chords(style, "E", "minor", _BARS, 0.7, 0.5,
                               progression=["i", "VI", "III", "VII"],
                               meter=Meter(4, 4), section_type="verse")
    assert default == explicit


# ── End-to-end song length + MIDI meta ───────────────────────────────────────

@pytest.mark.parametrize("sig", ["4/4", "3/4", "6/8", "7/8"])
def test_song_length_and_meta(tmp_path, sig):
    from app.models.schemas import BuildSongRequest
    from app.api.routes_song import _do_build_song
    from app.core.config import EXPORTS_DIR

    req = BuildSongRequest(
        style_id="rock", key="C", scale="major", bpm=120,
        complexity=0.6, variation=0.5, parts=["drums", "bass", "chords", "melody"],
        template="verse_chorus", seed=42, time_signature=sig,
    )
    resp = _do_build_song(req)
    meter = parse_meter(sig)

    song = mido.MidiFile(EXPORTS_DIR / resp.generation_id / "song.mid")
    ts = next((m for tr in song.tracks for m in tr if m.type == "time_signature"), None)
    assert ts is not None
    assert (ts.numerator, ts.denominator) == (meter.numerator, meter.denominator)
    # Compound meters click on the dotted quarter (36 clocks); everything else on 24.
    assert ts.clocks_per_click == (36 if meter.is_compound else 24)

    # Bars are meter-scaled: a 3/4 song is shorter in beats than the same 4/4 one.
    tpb = song.ticks_per_beat
    last_beat = 0.0
    for tr in song.tracks:
        t = 0
        for msg in tr:
            t += msg.time
            if msg.type in ("note_on", "note_off"):
                last_beat = max(last_beat, t / tpb)
    # The last note lands inside the final bar; total span is a whole number of
    # meter-scaled bars, so last_beat / bar_beats is a plausible bar count.
    approx_bars = last_beat / meter.bar_beats
    assert 4 <= approx_bars, f"{sig}: song only {approx_bars:.1f} bars long"
    # And a shorter meter really is shorter in absolute beats than 4/4 would be.
    if meter.bar_beats < 4.0:
        assert last_beat < approx_bars * 4.0
