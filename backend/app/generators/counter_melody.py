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
from app.theory.scales import build_scale
from app.theory.chords import roman_to_chord
from app.services.variation import should_trigger
from app.generators.answer import build_answer_phrase


def generate_counter_melody(
    melody_events: List[NoteEvent],
    key: str,
    scale: str,
    bars: int,
    progression: list | None = None,
    style: dict | None = None,
    melody_rests: list | None = None,
    cell: list[int] | None = None,
    section_type: str | None = None,
) -> List[NoteEvent]:
    """The melody's second voice — dual mode depending on the section.

    HARMONY mode (choruses, and the default when no ``section_type`` is given):
    a diatonic 3rd/6th below the lead's structural notes, snapping to chord tones
    on downbeats — thickens the hook without doubling every ornament.

    ANSWER mode (verse/intro/outro, where the melody leaves space): instead of
    shadowing the lead it ANSWERS it — dropping a short thematic lick (shaped by
    the song's melodic ``cell``) into each ``melody_rests`` hole, so the two
    voices trade phrases the way a horn answers a vocal. Needs ``melody_rests``
    and ``cell``; without them it stays silent (the lead simply owns the space).

    Either way it's softer than the lead so it reads as a response, not a
    competing second lead.
    """
    if not melody_events:
        return []

    style = style or {}
    cm_cfg = style.get("counter_melody", {})
    vel_scale = cm_cfg.get("velocity_scale", 0.72)
    floor = cm_cfg.get("floor", 55)   # don't harmonize below this — muddiness guard

    beats_per_bar = 4
    prog_len = len(progression) if progression else 0

    # ── Answer mode ───────────────────────────────────────────────────────────
    if section_type not in (None, "chorus", "post_chorus"):
        if not (melody_rests and cell and progression):
            return []
        mel_sorted = sorted(melody_events, key=lambda e: e.start)
        answers: List[NoteEvent] = []
        for rest_start, rest_end in melody_rests:
            if rest_end - rest_start < 2.0 or not should_trigger(0.6):
                continue
            # Reply at or just below the call's last pitch — a connected response.
            before = [e for e in mel_sorted if e.start + e.duration <= rest_start + 0.1]
            call_pitch = before[-1].pitch if before else 67
            call_vel   = before[-1].velocity if before else 80
            hi = min(78, call_pitch)
            lo = max(53, hi - 12)
            roman = progression[int(rest_start / beats_per_bar) % prog_len]
            answers.extend(build_answer_phrase(
                cell, key, scale, roman, rest_start, rest_end,
                lo=lo, hi=hi, channel=5, base_vel=max(1, int(call_vel * 0.82)),
                rng=random, invert=True))
        return answers

    # Scale lattice spanning below the melody register for stepping down 3rds/6ths
    scale_notes = build_scale(key, scale, octave_start=3, num_octaves=4)

    def _chord_pcs_at(beat: float) -> set[int]:
        if not progression:
            return set()
        chord_idx = int(beat / beats_per_bar) % prog_len
        return {p % 12 for p in roman_to_chord(progression[chord_idx], key, scale, octave=4)}

    def _select(min_dur: float, strong_only: bool) -> list:
        picked, last = [], -1.0
        for note in sorted(melody_events, key=lambda e: e.start):
            beat_in_bar = note.start % beats_per_bar
            is_strong = (beat_in_bar % 1.0) < 0.13
            if note.duration < min_dur or (strong_only and not is_strong):
                continue
            if note.start - last < 0.5:   # at most one harmony note per half-beat
                continue
            picked.append(note)
            last = note.start
        return picked

    # Prefer long notes on strong beats; if the melody is busy (few long notes),
    # relax so the harmony line always exists when a melody does.
    selected = _select(0.45, strong_only=True) or _select(0.25, strong_only=False)

    events: List[NoteEvent] = []
    for note in selected:
        beat_in_bar = note.start % beats_per_bar

        # Nearest scale index at or below the melody pitch
        below = [i for i, n in enumerate(scale_notes) if n <= note.pitch]
        if not below:
            continue
        idx = below[-1]
        # Diatonic 3rd below (2 scale steps); occasionally a 6th for variety
        steps = 5 if should_trigger(0.22) else 2
        h_idx = max(0, idx - steps)
        pitch = scale_notes[h_idx]

        # On bar downbeats, prefer a chord tone: walk down until the pitch class
        # belongs to the sounding chord (bounded walk keeps us near the 3rd/6th).
        if beat_in_bar < 0.13:
            chord_pcs = _chord_pcs_at(note.start)
            walk = h_idx
            while chord_pcs and walk > 0 and scale_notes[walk] % 12 not in chord_pcs and h_idx - walk < 3:
                walk -= 1
            if chord_pcs and scale_notes[walk] % 12 in chord_pcs:
                pitch = scale_notes[walk]

        if pitch < floor or pitch >= note.pitch:
            continue

        events.append(NoteEvent(
            pitch=pitch,
            start=note.start + 0.012,   # a hair behind the lead — reads as backing
            duration=note.duration * 0.96,
            velocity=max(1, min(127, int(note.velocity * vel_scale))),
            channel=5,
        ))

    return events
