# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Mine drum grooves (16-step patterns + swing) from a drum-MIDI corpus.

Designed for the Groove MIDI Dataset (real drummer performances on channel 9),
but works on any GM drum MIDI. Produces per-genre hit-probability vectors per
voice and derives the exact fields the drum generator already reads
(kick_pattern, snare_standard_beats, hat_density, swing) so a learned groove can
overlay a style with no generator changes.
"""
import math

from app.mining.midi_io import MidiSong, Note

_DRUM_CHANNEL = 9
_STEP = 0.25            # 16th note in beats
_STEPS = 16

# GM / Roland-TD drum pitch → voice (Groove MIDI uses a GM-compatible mapping)
_VOICE_PITCHES: dict[str, set[int]] = {
    "kick":       {35, 36},
    "snare":      {38, 40},
    "side_stick": {37},
    "closed_hat": {42, 44, 22},
    "open_hat":   {46, 26},
    "ride":       {51, 53, 59},
    "crash":      {49, 52, 55, 57},
    "clap":       {39},
    "tom":        {41, 43, 45, 47, 48, 50, 58},
}
VOICES = list(_VOICE_PITCHES)
_PITCH_TO_VOICE = {p: v for v, ps in _VOICE_PITCHES.items() for p in ps}

# The 8th-note offbeats ("&" of each beat) — used to estimate swing from the
# microtiming of a real performance.
_OFFBEAT_STEPS = {2, 6, 10, 14}


def empty_groove(genre: str) -> dict:
    return {
        "genre": genre,
        "songs": 0,
        "bars": 0.0,
        "hits": {v: [0.0] * _STEPS for v in VOICES},      # hit count per step
        "vel_sum": {v: [0.0] * _STEPS for v in VOICES},   # velocity sum per step
        "swing_delay_sum": 0.0,                            # Σ offbeat delay (beats)
        "swing_n": 0,
    }


def analyze_drum_song(song: MidiSong, groove: dict) -> bool:
    """Fold one drum performance into `groove`. Returns False if unusable."""
    notes = [n for n in song.notes if n.channel == _DRUM_CHANNEL]
    if len(notes) < 16:
        return False

    last_beat = max(n.start + n.duration for n in notes)
    n_bars = max(1, int(math.ceil(last_beat / 4.0)))

    for n in notes:
        voice = _PITCH_TO_VOICE.get(n.pitch)
        if voice is None:
            continue
        bar = int(n.start // 4)
        beat_in_bar = n.start - bar * 4
        step = int(round(beat_in_bar / _STEP)) % _STEPS
        groove["hits"][voice][step] += 1.0
        groove["vel_sum"][voice][step] += n.velocity
        # Swing: measure how late the offbeat hits land vs the exact grid.
        if step in _OFFBEAT_STEPS:
            grid = bar * 4 + step * _STEP
            delay = n.start - grid
            if -0.12 < delay < 0.2:        # ignore gross outliers / fills
                groove["swing_delay_sum"] += delay
                groove["swing_n"] += 1

    groove["bars"] += n_bars
    groove["songs"] += 1
    return True


def finalize_groove(groove: dict) -> dict:
    """Convert accumulated counts into probabilities, velocities, swing, and the
    derived generator fields. Returns a JSON-serialisable groove prior."""
    bars = max(1.0, groove["bars"])
    prob = {v: [round(min(1.0, groove["hits"][v][s] / bars), 4) for s in range(_STEPS)]
            for v in VOICES}
    vel = {v: [round(groove["vel_sum"][v][s] / groove["hits"][v][s], 1)
               if groove["hits"][v][s] > 0 else 0.0 for s in range(_STEPS)]
           for v in VOICES}
    swing = 0.0
    if groove["swing_n"] > 0:
        mean_delay = groove["swing_delay_sum"] / groove["swing_n"]   # beats
        # A full triplet swing places the "&" at 2/3 of the beat → delay ≈ 1/6 beat.
        # Map that to swing≈0.6 (a strong shuffle); clamp to [0, 0.75].
        swing = max(0.0, min(0.75, mean_delay / (1.0 / 6.0) * 0.6))

    return {
        "genre": groove["genre"],
        "songs": groove["songs"],
        "bars": round(bars, 1),
        "voices_prob": prob,
        "voices_vel": vel,
        "swing_est": round(swing, 3),
        "derived": derive_drum_fields(prob, swing),
    }


def derive_drum_fields(prob: dict, swing: float) -> dict:
    """Turn per-voice step probabilities into the style-JSON drum fields the
    generator consumes."""
    kick = prob["kick"]
    kick_pattern = [1 if kick[s] >= 0.35 else 0 for s in range(_STEPS)]
    kick_pattern[0] = 1                          # always anchor the downbeat

    # Backbeat: which of beats 1-4 the snare/clap lands on
    snare = [prob["snare"][s] + prob["clap"][s] for s in range(_STEPS)]
    snare_beats = [b for b in (1, 2, 3, 4) if snare[(b - 1) * 4] >= 0.3]
    if not snare_beats:
        snare_beats = [2, 4]

    # Hat density = fraction of 16th slots that carry a closed hat (or ride)
    hat = [max(prob["closed_hat"][s], prob["ride"][s]) for s in range(_STEPS)]
    hat_density = round(sum(1 for h in hat if h >= 0.25) / _STEPS, 3)

    use_ride = sum(prob["ride"]) > sum(prob["closed_hat"])

    return {
        "kick_pattern": kick_pattern,
        "snare_standard_beats": snare_beats,
        "hat_density": max(0.2, hat_density),
        "swing": round(swing, 3),
        "use_ride": use_ride,
    }
