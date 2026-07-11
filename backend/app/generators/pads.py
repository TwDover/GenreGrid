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

    One held voicing per chord change, voiced in a high register with soft
    velocities — the "glue" that fills the space between comp chords and melody
    in choruses/bridges without competing with either.

    Stationarity is the defining property of a pad, so each chord tone is
    placed individually at the in-register pitch NEAREST the previous bar's
    voicing. (The earlier pipeline voice-led a fresh octave-5 voicing and then
    octave-shifted the WHOLE result to fit the register — which undid the
    voice leading whenever the led voicing poked past a register bound, making
    the pad layer leap an octave up and back between adjacent bars.)
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

    center = (reg_low + reg_high) // 2

    prev_pitches: list[int] = []
    for bar in range(bars):
        chord_idx = bar * chords_per_bar
        roman = progression[chord_idx % prog_len]

        chord = roman_to_chord(roman, key, scale, octave=5)
        pcs = sorted({p % 12 for p in chord})
        if color_9th_prob > 0 and should_trigger(color_9th_prob):
            pcs = sorted(set(pcs) | {(chord[0] + 14) % 12})

        # Place each chord tone at the register position nearest the previous
        # bar's voicing (nearest the register center on the first bar). Every
        # voice moves at most a tritone bar-to-bar, so the layer sits still
        # while the harmony changes under it.
        voiced: list[int] = []
        for pc in pcs:
            candidates = [p for p in range(reg_low, reg_high + 1) if p % 12 == pc]
            if not candidates:
                continue
            if prev_pitches:
                pick = min(candidates, key=lambda p: min(abs(p - q) for q in prev_pitches))
            else:
                pick = min(candidates, key=lambda p: abs(p - center))
            voiced.append(pick)
        pitches = sorted(set(voiced))
        if not pitches:
            continue
        prev_pitches = pitches

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
