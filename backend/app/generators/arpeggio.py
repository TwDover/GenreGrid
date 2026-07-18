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
from app.services.humanize import (
    velocity_arc, timing_jitter, phrase_breath_factor,
    style_jitter, style_velocity_variation,
)
from app.theory.rhythm import apply_swing


def _voice_pitch_classes(pcs: list[int], octave: int) -> list[int]:
    """Voice a set of pitch classes into a single ascending octave from `octave`.

    Used when the caller supplies the chord generator's actual pitch classes so
    the arpeggio arpeggiates the *real* harmony (including 7ths/9ths and any
    borrowed color) rather than a re-derived plain triad.
    """
    base = 12 * (octave + 1)          # MIDI: C_octave (octave=5 → C5 = 72)
    voiced = sorted({base + ((pc - base) % 12) for pc in pcs})
    return voiced or [base]


def generate_arpeggio(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
    progression: list | None = None,
    octave: int = 5,
    melody_rests: list | None = None,
    chord_tones: list | None = None,
    seed_contour: list[int] | None = None,
) -> List[NoteEvent]:
    """Generate an arpeggio part.

    ``chord_tones`` — optional list of per-bar pitch-class lists taken from the
    chord generator's actual voicings. When provided, the arpeggio uses the same
    harmonic content as the chords (matching extensions/color); otherwise it
    falls back to deriving a triad from the roman numeral.
    """
    events: List[NoteEvent] = []
    if progression is None:
        templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
        progression = random.choice(templates)

    arp_cfg = style.get("arpeggio", {})
    pattern = arp_cfg.get("pattern", "up")          # up | down | up_down
    speed = arp_cfg.get("speed", 0.25)              # beats per note (0.25=16th, 0.5=8th)
    include_octave = arp_cfg.get("include_octave", False)
    allow_7th = arp_cfg.get("allow_7th", False)
    swing_amount = style.get("drums", {}).get("swing", 0.0)

    beats_per_bar = 4
    prog_len = len(progression)
    ticks_per_beat = 480

    # Pre-compute per-style jitter budget (arp sits between chords and melody in looseness)
    arp_jitter = style_jitter(style) * 0.75

    def _rest_boost(t: float) -> float:
        """Return a velocity scale-up when arp lands during a melody rest.

        When melody is silent, arpeggio steps into the foreground to fill the
        space (call-and-response). When melody is playing, the 68% complexity
        reduction already thins the arp; keeping boost=1.0 here means it stays
        in the background without fighting the melody.
        """
        if not melody_rests:
            return 1.0
        return 1.18 if any(rs <= t < re for rs, re in melody_rests) else 1.0

    for chord_idx in range(bars):
        if chord_tones:
            pcs = chord_tones[chord_idx % len(chord_tones)]
            pitches = _voice_pitch_classes(pcs, octave)
        else:
            roman = progression[chord_idx % prog_len]
            pitches = sorted(roman_to_chord(roman, key, scale, octave=octave, allow_7th=allow_7th))

        if include_octave:
            pitches = pitches + [pitches[0] + 12]

        # 2-bar variation: second bar of each pair may invert the direction for contrast
        effective_pattern = pattern
        if chord_idx % 2 == 1 and pattern in ("up", "down") and should_trigger(variation * 0.55):
            effective_pattern = "down" if pattern == "up" else "up"

        # Thematic unification: each 4-bar phrase OPENS with the gesture of
        # the song theme's melodic cell — the arp outlines the same shape the
        # hook sings (rising cell → rising arp, arched cell → up_down).
        if seed_contour and chord_idx % 4 == 0:
            _ups = sum(1 for iv in seed_contour if iv > 0)
            _downs = sum(1 for iv in seed_contour if iv < 0)
            if _ups and _downs:
                effective_pattern = "up_down"
            elif _downs:
                effective_pattern = "down"
            elif _ups:
                effective_pattern = "up"

        if effective_pattern == "up":
            seq = pitches
        elif effective_pattern == "down":
            seq = list(reversed(pitches))
        elif pattern == "random":
            seq = random.sample(pitches, len(pitches))
        else:  # up_down
            seq = pitches + list(reversed(pitches[1:-1])) if len(pitches) > 2 else pitches

        bar_start = chord_idx * beats_per_bar
        pos = 0.0
        seq_idx = 0

        # Phrase-level dynamics: 4-bar breath shape + slight bar-2 de-emphasis
        breath = phrase_breath_factor(chord_idx)
        pair_dyn = 0.94 if chord_idx % 2 == 1 else 1.0
        vel_var = style_velocity_variation(style)

        if pattern == "chord_burst":
            for j, pitch in enumerate(pitches):
                t = max(0.0, bar_start + j * 0.125 + timing_jitter(arp_jitter * 0.4))
                base_vel = int(velocity_arc(chord_idx, bars, 74) * breath * pair_dyn * _rest_boost(t))
                vel = min(127, base_vel + (8 if j == 0 else 0) + random.randint(-vel_var, vel_var))
                events.append(NoteEvent(
                    pitch=min(127, max(0, pitch)),
                    start=t,
                    duration=beats_per_bar * 0.9,
                    velocity=vel,
                    channel=3,
                ))
            continue  # skip the regular while loop for this bar

        while pos <= beats_per_bar - speed * 0.5:
            # Occasional rest for variation — rests land more often on weak 16th positions
            beat_in_bar = pos % beats_per_bar
            is_strong = beat_in_bar < 0.01 or abs(beat_in_bar - 2.0) < 0.01
            rest_prob = (variation * 0.15 + 0.02) if is_strong else (variation * 0.35 + 0.05)
            if seq_idx > 0 and should_trigger(rest_prob):
                pos += speed
                seq_idx += 1
                continue

            pitch = seq[seq_idx % len(seq)]
            is_root = (seq_idx % len(seq) == 0)
            is_medium = abs(beat_in_bar - 1.0) < 0.01 or abs(beat_in_bar - 3.0) < 0.01
            t_tick = int((bar_start + pos) * ticks_per_beat)
            t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)
            t_start = max(0.0, t_tick / ticks_per_beat + timing_jitter(arp_jitter))

            base_vel = int(velocity_arc(chord_idx, bars, 74) * breath * pair_dyn * _rest_boost(t_start))
            accent = 12 if is_root else (6 if is_strong else (3 if is_medium else 0))
            vel = min(127, base_vel + accent + random.randint(-vel_var, vel_var))

            events.append(NoteEvent(
                pitch=min(127, max(0, pitch)),
                start=t_start,
                duration=speed * 0.8,
                velocity=vel,
                channel=3,
            ))

            pos += speed
            seq_idx += 1

    return events
