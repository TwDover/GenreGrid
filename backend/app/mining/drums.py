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

from app.mining.midi_io import MidiSong

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

# For fills we keep the tom hi/mid/lo distinction (a fill's identity is its tom
# cascade), mapping pitches straight to the drum generator's DRUM_MAP keys.
_FILL_PITCH_TO_KEY: dict[int, str] = {
    35: "kick", 36: "kick",
    37: "snare", 38: "snare", 40: "snare",
    39: "clap",
    42: "closed_hat", 44: "closed_hat", 22: "closed_hat",
    46: "open_hat", 26: "open_hat",
    49: "crash", 52: "crash", 55: "crash", 57: "crash",
    51: "ride", 53: "ride", 59: "ride",
    48: "tom_hi", 50: "tom_hi",
    45: "tom_mid", 47: "tom_mid",
    41: "tom_lo", 43: "tom_lo", 58: "tom_lo",
}


# Drum voices grouped into the four feel classes the humanizer applies. Mirrors
# app.core.feel.drum_class, but expressed over this module's mined voice names.
_FEEL_CLASS_VOICES = {
    "kick":  ["kick"],
    "snare": ["snare", "clap", "side_stick"],
    "hat":   ["closed_hat", "open_hat", "ride"],
    "other": ["crash", "tom"],
}


def empty_groove(genre: str) -> dict:
    return {
        "genre": genre,
        "songs": 0,
        "bars": 0.0,
        "hits": {v: [0.0] * _STEPS for v in VOICES},      # hit count per step
        "vel_sum": {v: [0.0] * _STEPS for v in VOICES},   # velocity sum per step
        # Feel: per-voice, per-step Σ of the hit's signed offset from its grid
        # line (beats) — the systematic microtiming a real drummer plays.
        "time_off_sum": {v: [0.0] * _STEPS for v in VOICES},
        "time_off_n": {v: [0.0] * _STEPS for v in VOICES},
        "swing_delay_sum": 0.0,                            # Σ offbeat delay (beats)
        "swing_n": 0,
        "fills": [],                                       # list of mined fill patterns
    }


def analyze_fill_song(song: MidiSong, groove: dict, max_fills: int = 16) -> bool:
    """Extract one drum-fill pattern from a fill performance and append it.

    A fill is stored as a list of [step (0-15), voice, velocity] over the single
    busiest bar (the fill's climax). The drum generator plays these at section
    transitions instead of the hand-authored variants.
    """
    if len(groove["fills"]) >= max_fills:
        return False
    notes = [n for n in song.notes if n.channel == _DRUM_CHANNEL]
    if len(notes) < 4:
        return False
    # Busiest bar = the fill's peak
    from collections import Counter
    bar_counts = Counter(int(n.start // 4) for n in notes)
    if not bar_counts:
        return False
    best_bar = bar_counts.most_common(1)[0][0]
    b0 = best_bar * 4
    fill: list = []
    for n in notes:
        if b0 <= n.start < b0 + 4:
            key = _FILL_PITCH_TO_KEY.get(n.pitch)
            if key is None:
                continue
            step = int(round((n.start - b0) / _STEP))
            if 0 <= step < _STEPS:
                fill.append([step, key, int(n.velocity)])
    if len(fill) >= 3:
        groove["fills"].append(sorted(fill))
        return True
    return False


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
        # Feel: signed offset of this hit from its own grid line (ignore fill
        # slop beyond a 32nd either side, which would poison the median).
        grid = bar * 4 + step * _STEP
        delay = n.start - grid
        if -0.125 < delay < 0.125:
            groove["time_off_sum"][voice][step] += delay
            groove["time_off_n"][voice][step] += 1.0
        # Swing: measure how late the offbeat hits land vs the exact grid.
        if step in _OFFBEAT_STEPS and -0.12 < delay < 0.2:   # ignore gross outliers / fills
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
        "fills": groove.get("fills", []),
        "derived": derive_drum_fields(prob, vel, swing),
        "feel": derive_feel(groove),
    }


def derive_drum_fields(prob: dict, vel: dict, swing: float) -> dict:
    """Turn per-voice step probabilities/velocities into the style-JSON drum
    fields the generator consumes."""
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

    # Per-step hat placement probability + velocity accent (the human hat feel).
    hat_prob = [round(prob["closed_hat"][s], 3) for s in range(_STEPS)]
    hv = vel.get("closed_hat", [0.0] * _STEPS)
    peak = max(hv) or 1.0
    hat_vel = [round(hv[s] / peak, 3) if hv[s] > 0 else 0.6 for s in range(_STEPS)]

    return {
        "kick_pattern": kick_pattern,
        "snare_standard_beats": snare_beats,
        "hat_density": max(0.2, hat_density),
        "hat_pattern": hat_prob,
        "hat_vel": hat_vel,
        "swing": round(swing, 3),
        "use_ride": use_ride,
    }


def derive_feel(groove: dict) -> dict:
    """Turn the accumulated per-voice microtiming and velocity into the style
    ``feel`` block the humanizer applies (app.core.feel): per instrument class, a
    16-slot timing offset (median-ish signed offset from the grid, beats) and a
    16-slot velocity factor (each step's mean velocity / the class's peak).

    Only slots with enough support carry an offset; sparse slots stay 0.0 so a
    thin corpus doesn't invent feel it never observed."""
    hits = groove["hits"]
    vel_sum = groove["vel_sum"]
    toff_sum = groove["time_off_sum"]
    toff_n = groove["time_off_n"]

    feel: dict = {}
    for cls, voices in _FEEL_CLASS_VOICES.items():
        timing = [0.0] * _STEPS
        vel_step = [0.0] * _STEPS
        for s in range(_STEPS):
            n_off = sum(toff_n[v][s] for v in voices)
            if n_off >= 3:                       # need a few observations to trust it
                timing[s] = round(sum(toff_sum[v][s] for v in voices) / n_off, 5)
            n_hit = sum(hits[v][s] for v in voices)
            if n_hit > 0:
                vel_step[s] = sum(vel_sum[v][s] for v in voices) / n_hit
        peak = max(vel_step) or 1.0
        velocity = [round(vel_step[s] / peak, 3) if vel_step[s] > 0 else 1.0
                    for s in range(_STEPS)]
        feel[cls] = {"timing": timing, "velocity": velocity}
    return feel
