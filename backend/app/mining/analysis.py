# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Key detection, chord recognition, and roman-token conversion.

The roman tokens produced here use the same vocabulary the generators consume
(``roman_to_chord`` in app.theory.chords), so a mined progression can be fed
straight back into ``generate_chords``.
"""
import math

from app.core.constants import NOTE_NAMES, SCALE_INTERVALS
from app.mining.midi_io import MidiSong, Note

_BEATS_PER_BAR = 4

# Krumhansl–Kessler key profiles
_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

# Chord templates as pitch-class offsets from the root.
_CHORD_TEMPLATES: dict[str, tuple[int, ...]] = {
    "maj":  (0, 4, 7),
    "min":  (0, 3, 7),
    "dim":  (0, 3, 6),
    "aug":  (0, 4, 8),
    "maj7": (0, 4, 7, 11),
    "min7": (0, 3, 7, 10),
    "dom7": (0, 4, 7, 10),
    "sus4": (0, 5, 7),
}

# Chromatic semitone-from-tonic → base roman numeral (accidentals reference the
# major scale, matching roman_to_chord's borrowed-chord handling).
_SEMITONE_TO_ROMAN = {
    0: "I", 1: "bII", 2: "II", 3: "bIII", 4: "III", 5: "IV",
    6: "#IV", 7: "V", 8: "bVI", 9: "VI", 10: "bVII", 11: "VII",
}


def _pc_histogram(notes: list[Note]) -> list[float]:
    """Duration-weighted pitch-class histogram (length 12)."""
    hist = [0.0] * 12
    for n in notes:
        hist[n.pitch % 12] += max(0.05, n.duration)
    return hist


def _correlate(hist: list[float], profile: list[float]) -> float:
    n = len(hist)
    mh = sum(hist) / n
    mp = sum(profile) / n
    num = sum((hist[i] - mh) * (profile[i] - mp) for i in range(n))
    denh = math.sqrt(sum((hist[i] - mh) ** 2 for i in range(n)))
    denp = math.sqrt(sum((profile[i] - mp) ** 2 for i in range(n)))
    if denh < 1e-9 or denp < 1e-9:
        return 0.0
    return num / (denh * denp)


def _boundary_bass_pc(notes: list[Note], at_start: bool) -> int | None:
    """Pitch class of the lowest note at the song's first onset / final chord.

    Songs overwhelmingly begin (and usually end) on the tonic, which
    disambiguates the relative major/minor pair that raw profile correlation
    cannot tell apart (A-minor and C-major share every pitch class). We read the
    bass register (lowest note) since that carries the chord root."""
    if not notes:
        return None
    if at_start:
        anchor = min(n.start for n in notes)
        group = [n for n in notes if abs(n.start - anchor) < 0.25]
    else:
        anchor = max(n.start + n.duration for n in notes)
        group = [n for n in notes if abs((n.start + n.duration) - anchor) < 0.5]
    if not group:
        return None
    return min(n.pitch for n in group) % 12


def detect_key(song: MidiSong) -> tuple[str, str]:
    """Return (key_name, mode) via Krumhansl–Schmuckler with tonic disambiguation."""
    pitched = song.pitched_notes()
    hist = _pc_histogram(pitched)
    total = sum(hist)
    if total < 1e-6:
        return "C", "major"

    first_pc = _boundary_bass_pc(pitched, at_start=True)
    last_pc = _boundary_bass_pc(pitched, at_start=False)
    norm = [h / total for h in hist]

    best_score = -1e9
    best = (0, "major")
    for tonic in range(12):
        rotated = hist[tonic:] + hist[:tonic]
        for mode, profile in (("major", _MAJOR_PROFILE), ("minor", _MINOR_PROFILE)):
            score = _correlate(rotated, profile)
            # Tonic-salience + starts/ends-on-tonic bonuses break relative-key ties.
            # The first chord is the strongest cue (a loop starting on the vi of the
            # relative major is heard as the minor tonic), so weight it highest.
            score += 0.15 * norm[tonic]
            if first_pc == tonic:
                score += 0.45
            if last_pc == tonic:
                score += 0.20
            if score > best_score:
                best_score = score
                best = (tonic, mode)
    return NOTE_NAMES[best[0]], best[1]


def _best_chord(hist: list[float]) -> tuple[int, str] | None:
    """Best (root_pc, quality) for a bar's pitch-class histogram, or None."""
    total = sum(hist)
    if total < 1e-6:
        return None
    best_score = -1e9
    best: tuple[int, str] | None = None
    for root in range(12):
        for quality, template in _CHORD_TEMPLATES.items():
            tset = {(root + iv) % 12 for iv in template}
            inside = sum(hist[pc] for pc in tset)
            outside = total - inside
            # Reward energy on chord tones, penalise energy outside, and slightly
            # prefer simpler triads so a plain major isn't always beaten by a 7th.
            score = inside - 0.55 * outside - 0.04 * len(template)
            # Root emphasis: the bass/root pitch class should carry weight.
            score += 0.25 * hist[root]
            if score > best_score:
                best_score = score
                best = (root, quality)
    return best


_DEGREE_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII"]


def _roman_token(root_pc: int, quality: str, tonic_pc: int, mode: str) -> str:
    """Roman token in the generator's vocabulary.

    Diatonic chord roots use the plain scale-degree roman (matching how
    roman_to_chord reads unaccented numerals against the mode's scale); chromatic
    roots fall back to accidental notation referencing the major scale.
    """
    semitone = (root_pc - tonic_pc) % 12
    intervals = SCALE_INTERVALS.get(mode, SCALE_INTERVALS["minor"])
    if semitone in intervals:
        roman = _DEGREE_ROMAN[intervals.index(semitone)]
    else:
        roman = _SEMITONE_TO_ROMAN[semitone]
    is_minor_quality = quality in ("min", "min7", "dim")
    token = roman.lower() if is_minor_quality else roman
    if quality == "dim":
        token += "dim"
    return token


def bar_chords(
    song: MidiSong, tonic_pc: int, harmonic_notes: list[Note], mode: str = "minor",
) -> list[str]:
    """Per-bar roman tokens for the given harmonic notes (chords + bass)."""
    if not harmonic_notes:
        return []
    last_beat = max(n.start + n.duration for n in harmonic_notes)
    n_bars = max(1, math.ceil(last_beat / _BEATS_PER_BAR))
    tokens: list[str] = []
    for bar in range(n_bars):
        b0 = bar * _BEATS_PER_BAR
        b1 = b0 + _BEATS_PER_BAR
        hist = [0.0] * 12
        for note in harmonic_notes:
            # overlap of the note with this bar, weighted by duration in-bar
            ov = min(note.start + note.duration, b1) - max(note.start, b0)
            if ov > 0:
                hist[note.pitch % 12] += ov
        chord = _best_chord(hist)
        if chord is not None:
            tokens.append(_roman_token(chord[0], chord[1], tonic_pc, mode))
    return tokens


def in_scale_degree(pitch: int, tonic_pc: int, mode: str) -> int | None:
    """Scale-degree index (0-6) of a pitch in the key, or None if chromatic."""
    intervals = SCALE_INTERVALS.get(mode, SCALE_INTERVALS["minor"])
    semitone = (pitch - tonic_pc) % 12
    return intervals.index(semitone) if semitone in intervals else None
