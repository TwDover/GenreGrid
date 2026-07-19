# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Riff-first architecture for guitar genres (metal / rock / doom).

Those genres aren't comped chords with a melody on top — their identity is a
1–2 bar low-register figure the guitar and bass play in *unison*: palm-muted
pedal-tone chugs on the chord root, power-chord stabs on the figure's accents,
a chromatic/scale approach note walking into the next chord.

`build_riff` is the single source of truth for that figure. It's a song-level
object: deterministic from the style id, section type, and progression, so every
section of a song and every regeneration reproduces the identical riff — and the
guitar and the bass, rendering the *same* RiffNote list an octave apart, are
guaranteed to lock in unison. The chord generator renders it with power-chord
stabs; the bass renders the roots an octave down.
"""
import zlib
from dataclasses import dataclass

from app.theory.chords import roman_to_chord

_STEP = 0.25          # 16th note in beats
_STEPS = 16


@dataclass
class RiffNote:
    start: float      # beats from section start
    pitch: int        # pedal-register root (or approach note)
    duration: float   # beats
    accent: bool      # True → power-chord stab; False → single-note chug
    approach: bool = False   # True → chromatic/scale walk into the next chord


# Per-figure rhythmic cells, chosen by section role. Steps are 16th-note slots of
# a bar; accents mark the slots that get a power-chord stab rather than a chug.
_RIFF_CELLS = {
    # Verse/default: the metal gallop — 8th + two 16ths on every beat, stabs on 1 & 3.
    "drive": {"steps": [0, 2, 3, 4, 6, 7, 8, 10, 11, 12, 14, 15],
              "accents": {0, 8}, "dur": 0.22},
    # Chorus: opened-up power-chord stabs on the quarter notes, ringing.
    "open":  {"steps": [0, 4, 8, 12], "accents": {0, 4, 8, 12}, "dur": 0.90},
    # Intro/outro/breakdown (doom): half-time crush — hit on 1 and the & of 3, long ring.
    "crush": {"steps": [0, 10], "accents": {0, 10}, "dur": 2.20},
}


def _cell_for(section_type: str | None) -> str:
    if section_type in ("chorus", "post_chorus"):
        return "open"
    if section_type in ("intro", "outro", "ending", "breakdown"):
        return "crush"
    return "drive"


def _fit(pitch: int, low: int, high: int) -> int:
    while pitch < low:
        pitch += 12
    while pitch > high:
        pitch -= 12
    return pitch


def build_riff(
    style: dict,
    key: str,
    scale: str,
    progression: list,
    bars: int,
    section_type: str | None = None,
    pedal_low: int = 40,
) -> list[RiffNote]:
    """The section's riff as pedal-register RiffNotes (root octave ≈ `pedal_low`).

    One chord per bar (riffs pedal slowly); the bar's chord root is the pedal.
    The last 16th before a chord change becomes a chromatic approach toward the
    next root. Deterministic: no RNG state, seeded only by style/section/prog."""
    if not progression:
        return []
    cell = _RIFF_CELLS[_cell_for(section_type)]
    steps, accents, base_dur = cell["steps"], cell["accents"], cell["dur"]
    prog_len = len(progression)
    pedal_high = pedal_low + 11

    # A stable per-style toggle: some styles double-time the last bar's tail. Kept
    # deterministic (crc32 of the style id) so it never breaks regeneration.
    _ = zlib.crc32(f"riff:{style.get('id','')}:{section_type}".encode())

    out: list[RiffNote] = []
    for bar in range(bars):
        roman = progression[bar % prog_len]
        next_roman = progression[(bar + 1) % prog_len]
        root = _fit(roman_to_chord(roman, key, scale, octave=2)[0], pedal_low, pedal_high)
        next_root = _fit(roman_to_chord(next_roman, key, scale, octave=2)[0], pedal_low, pedal_high)

        for step in steps:
            start = bar * 4.0 + step * _STEP
            accent = step in accents
            dur = base_dur
            # Last 16th of the bar, heading into a new chord → chromatic approach.
            if step == steps[-1] and step >= 14 and next_root != root:
                direction = 1 if next_root > root else -1
                out.append(RiffNote(start, next_root - direction, min(dur, 0.22),
                                    accent=False, approach=True))
            else:
                out.append(RiffNote(start, root, dur, accent=accent))
    return out


def is_riff_style(style: dict) -> bool:
    """True when the style opts into riff mode anywhere (base comp or a section
    variant). Used to gate bass doubling and melody stand-down."""
    if style.get("comp_style") == "riff":
        return True
    variants = style.get("comp_section_variants") or {}
    return "riff" in variants.values()


def riff_section_comp(style: dict, section_type: str | None) -> bool:
    """True when THIS section renders as a riff (after applying section variants)."""
    variants = style.get("comp_section_variants") or {}
    if section_type and section_type in variants:
        return variants[section_type] == "riff"
    return style.get("comp_style") == "riff"
