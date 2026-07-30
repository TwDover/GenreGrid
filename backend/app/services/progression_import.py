# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Seed a song from a user-typed chord progression.

Accepts either roman numerals ("i VI III VII") or absolute chord names
("Am F C G") and returns a validated roman-numeral list that plugs straight into
the existing ``progression_override`` seam on BuildSongRequest — so a typed
progression bypasses the style's pool exactly the way the melody-import path's
derived progression does.

Roman numerals are emitted relative to the *major* scale (with flats/sharps for
chromatic degrees, e.g. a natural-minor tonic loop reads ``i bIII iv bVII``).
That is deliberate: ``roman_to_chord`` resolves an *altered* numeral against the
major scale regardless of the key's mode, so this notation round-trips to the
same absolute chord in any key — the inverse of what the generator consumes.
"""
import re

from app.core.constants import NOTE_NAMES

# Validation shape for a single roman token: optional accidental, I–VII in either
# case, optional chord-quality suffix. Shared with routes_song so the /build-song
# and /rebuild-song-progression paths validate identically.
ROMAN_TOKEN_RE = re.compile(
    r'^[b#]?(VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)'
    r'(maj7|m7b5|dim7|dim|aug|sus[24]|add\d+|m?6|m?7|m?9|\+)?$')

# Absolute note letter (+ optional accidental) → pitch class. Flats fold onto the
# sharp spellings NOTE_NAMES uses; the theoretical Cb/Fb/E#/B# are accepted too.
_ENHARMONIC = {
    "Cb": 11, "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4,
    "Fb": 4, "E#": 5, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8,
    "A": 9, "A#": 10, "Bb": 10, "B": 11, "B#": 0,
}

# Chord-root pitch-class offset above the key root → roman numeral (major-scale
# reference; chromatic degrees carry an accidental). Case is applied by quality.
_INTERVAL_TO_ROMAN = {
    0: "I", 1: "bII", 2: "II", 3: "bIII", 4: "III", 5: "IV",
    6: "#IV", 7: "V", 8: "bVI", 9: "VI", 10: "bVII", 11: "VII",
}

_CHORD_ROOT_RE = re.compile(r'^([A-G][b#]?)(.*)$')


def _quality_to_roman_suffix(quality: str) -> tuple[bool, str]:
    """Map a chord-name quality tail → (is_minor, roman_suffix).

    ``is_minor`` chooses the numeral's case; the suffix is one recognised by
    ROMAN_TOKEN_RE / roman_to_chord. Unknown tails fall back to a plain triad.
    """
    q = quality.strip()
    ql = q.lower()
    # Order matters: match longer / more specific qualities first.
    if ql in ("maj7", "major7", "M7", "Δ", "Δ7") or q in ("maj7", "M7"):
        return False, "maj7"
    if ql in ("m7b5", "min7b5", "ø", "ø7", "halfdim", "half-dim"):
        return True, "m7b5"
    if ql in ("dim7", "°7", "o7"):
        return True, "dim7"
    if ql in ("dim", "°", "o"):
        return True, "dim"
    if ql in ("aug", "+", "+5", "#5"):
        return False, "aug"
    if ql in ("sus2",):
        return False, "sus2"
    if ql in ("sus4", "sus"):
        return False, "sus4"
    if ql in ("m6", "min6", "-6"):
        return True, "m6"
    if ql in ("6",):
        return False, "6"
    if ql in ("m9", "min9", "-9"):
        return True, "m9"
    if ql in ("9",):
        return False, "9"
    if ql in ("add9",):
        return False, "add9"
    if ql in ("add11",):
        return False, "add11"
    # Bare dominant / minor sevenths: roman_to_chord has no "7"/"m7" resolver
    # (sevenths are added by the generator's style flags, not the roman token),
    # so keep the correct root + triad quality and drop the unresolvable tail.
    if ql in ("m7", "min7", "-7"):
        return True, ""
    if ql in ("7", "dom7"):
        return False, ""
    if ql in ("m", "min", "-", "mi"):
        return True, ""
    if ql in ("", "maj", "major", "M"):
        return False, ""
    # Unrecognised tail (e.g. an exotic extension) — keep the triad, drop the tail.
    if q and q[0] in ("m", "-") and not q.lower().startswith("maj"):
        return True, ""
    return False, ""


def chord_name_to_roman(name: str, key: str, scale: str = "minor") -> str:
    """Convert an absolute chord name (e.g. "Am", "F", "Cmaj7", "F#m7") to a
    roman numeral relative to `key`. `scale` is accepted for symmetry but does
    not change the result — chromatic degrees are spelled against the major
    scale so the token round-trips through roman_to_chord in any mode.

    Raises ValueError if `name` has no parseable A–G root.
    """
    m = _CHORD_ROOT_RE.match(name.strip())
    if not m:
        raise ValueError(f"'{name}' isn't a chord name")
    root_str, quality = m.group(1), m.group(2)
    root_pc = _ENHARMONIC.get(root_str)
    if root_pc is None:
        raise ValueError(f"'{name}' has an unknown root note")

    if key not in NOTE_NAMES:
        raise ValueError(f"unknown key '{key}'")
    key_pc = NOTE_NAMES.index(key)
    interval = (root_pc - key_pc) % 12

    numeral = _INTERVAL_TO_ROMAN[interval]           # e.g. "bVI" (upper by default)
    is_minor, suffix = _quality_to_roman_suffix(quality)

    # Split any accidental prefix so we case only the numeral letters.
    prefix = ""
    body = numeral
    if body and body[0] in ("b", "#"):
        prefix, body = body[0], body[1:]
    if is_minor:
        body = body.lower()
    return f"{prefix}{body}{suffix}"


def _looks_like_roman(token: str) -> bool:
    return bool(ROMAN_TOKEN_RE.match(token))


def parse_progression(text: str, key: str, scale: str = "minor") -> list[str]:
    """Parse a free-typed progression into a validated roman-numeral list.

    Accepts space / comma / ``|`` / ``→`` / ``->`` separators and a mix of roman
    numerals and absolute chord names per token. Raises ValueError with a
    specific message on the first token that is neither.
    """
    raw = re.split(r'[\s,|]+|->|→', text.strip())
    tokens = [t for t in (tok.strip() for tok in raw) if t]
    if len(tokens) < 2:
        raise ValueError("A progression needs at least two chords")

    out: list[str] = []
    for tok in tokens:
        if _looks_like_roman(tok):
            out.append(tok)
            continue
        # Not a bare roman — try to read it as an absolute chord name.
        try:
            roman = chord_name_to_roman(tok, key, scale)
        except ValueError:
            raise ValueError(f"'{tok}' isn't a valid chord or roman numeral")
        if not ROMAN_TOKEN_RE.match(roman):
            raise ValueError(f"'{tok}' isn't a valid chord or roman numeral")
        out.append(roman)
    return out
