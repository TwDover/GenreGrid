# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.chords import roman_to_chord
from app.services.variation import should_trigger
from app.services.humanize import timing_jitter
from app.generators.chords import _voice_lead, _clamp_register


def generate_pads(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
    progression: list | None = None,
) -> List[NoteEvent]:
    """Sustained atmospheric chord layer above the comp chords.

    One held voicing per chord change, voiced open in a high register with soft
    velocities — the "glue" that fills the space between comp chords and melody
    in choruses/bridges without competing with either. Voice-led between chords
    so the layer moves as little as possible (pads should feel stationary).
    """
    events: List[NoteEvent] = []
    if progression is None:
        templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
        progression = random.choice(templates)

    pad_cfg = style.get("pads", {})
    # High register above the comp chords' default [48, 72] ceiling.
    reg_low, reg_high = pad_cfg.get("register", style.get("pad_register", [64, 86]))
    velocity_base = pad_cfg.get("velocity", 54)
    # 9th color adds shimmer at higher complexity
    color_9th_prob = pad_cfg.get("color_9th_prob", 0.35 if complexity > 0.5 else 0.0)

    beats_per_bar = 4
    # Pads hold longer than the comp: one chord per bar regardless of the comp's
    # harmonic rhythm, indexing the same resolved progression grid as the chords
    # (chords_per_bar = 2 windows both map into the same bar's slot pair, so the
    # bar-level pad harmony always contains the sounding chord's bar).
    chords_per_bar = 2 if complexity > 0.6 else 1
    prog_len = len(progression)

    prev_pitches: list[int] = []
    for bar in range(bars):
        chord_idx = bar * chords_per_bar
        roman = progression[chord_idx % prog_len]

        pitches = roman_to_chord(roman, key, scale, octave=5)
        if color_9th_prob > 0 and should_trigger(color_9th_prob):
            pitches = pitches + [pitches[0] + 14]

        # Open the voicing: drop the middle voice down an octave for air
        if len(pitches) >= 3:
            s = sorted(pitches)
            pitches = [s[0]] + [p + 12 for p in s[1:2]] + s[2:]

        if prev_pitches:
            pitches = _voice_lead(pitches, prev_pitches)
        pitches = _clamp_register(sorted(set(pitches)), low=reg_low, high=reg_high)
        prev_pitches = sorted(pitches)

        start = float(bar * beats_per_bar)
        # Slight overlap into the next bar for a legato wash
        duration = beats_per_bar * 1.04 if bar < bars - 1 else float(beats_per_bar)
        vel = velocity_base + random.randint(-4, 4)
        for note_i, p in enumerate(sorted(pitches)):
            events.append(NoteEvent(
                pitch=min(127, max(0, p)),
                start=max(0.0, start + timing_jitter(0.012) + note_i * 0.02),
                duration=min(duration, bars * beats_per_bar - start),
                velocity=max(1, min(127, vel - note_i * 2)),
                channel=4,
            ))

    return events
