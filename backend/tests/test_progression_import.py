# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Seed-from-a-progression parser: roman passthrough, chord-name → roman across
keys/qualities, and the round-trip guarantee that a parsed token resolves back to
the absolute chord the user typed (roadmap-2 5.4)."""
import pytest

from app.services.progression_import import (chord_name_to_roman, parse_progression,
                                             ROMAN_TOKEN_RE)
from app.theory.chords import roman_to_chord


def _pcs_from_chord(name: str) -> set[int]:
    """Pitch classes of a plain chord name, parsed independently of the module
    under test (a tiny reference so the round-trip check isn't circular)."""
    roots = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
             "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
    import re
    m = re.match(r"^([A-G][b#]?)(.*)$", name)
    root = roots[m.group(1)]
    q = m.group(2).lower()
    if q.startswith(("m", "-")) and not q.startswith("maj"):
        third = 3
    elif q.startswith("dim") or q == "°":
        third = 3
    else:
        third = 4
    fifth = 6 if (q.startswith("dim") or q == "°") else (8 if q.startswith("aug") or q == "+" else 7)
    return {root % 12, (root + third) % 12, (root + fifth) % 12}


def test_roman_passthrough_is_untouched():
    assert parse_progression("i VI III VII", "A", "minor") == ["i", "VI", "III", "VII"]
    assert parse_progression("I  IV | V  vi", "C", "major") == ["I", "IV", "V", "vi"]


def test_chord_names_round_trip_to_the_typed_chord():
    for prog, key, scale in [
        ("Am F C G", "A", "minor"),
        ("C G Am F", "C", "major"),
        ("F#m D A E", "A", "major"),
        ("Dm Bb F C", "F", "major"),
    ]:
        romans = parse_progression(prog, key, scale)
        for typed, roman in zip(prog.split(), romans):
            got = {p % 12 for p in roman_to_chord(roman, key, scale, octave=4)}
            assert got == _pcs_from_chord(typed), f"{typed} → {roman} gave {got}"


def test_quality_case_and_suffix_mapping():
    # Major triad → uppercase; minor → lowercase; maj7 preserved; dim/aug suffixes.
    assert chord_name_to_roman("C", "C", "major") == "I"
    assert chord_name_to_roman("Am", "C", "major") == "vi"
    assert chord_name_to_roman("Cmaj7", "C", "major") == "Imaj7"
    assert chord_name_to_roman("Bdim", "C", "major") == "viidim"
    # Bare 7ths keep the correct triad quality but drop the unresolvable "7" tail.
    assert chord_name_to_roman("G7", "C", "major") == "V"
    assert chord_name_to_roman("Am7", "C", "major") == "vi"


def test_accidental_degrees_spell_with_flats_or_sharps():
    # Natural-minor tonic loop, written against the major scale.
    assert parse_progression("Am C F G", "A", "minor") == ["i", "bIII", "bVI", "bVII"]


def test_mixed_roman_and_chord_tokens():
    assert parse_progression("i F C bVII", "A", "minor") == ["i", "bVI", "bIII", "bVII"]


def test_every_emitted_token_is_valid():
    for tok in parse_progression("Cmaj7 Am Dm G Bdim F#m", "C", "major"):
        assert ROMAN_TOKEN_RE.match(tok), tok


def test_bad_token_raises_valueerror():
    with pytest.raises(ValueError):
        parse_progression("Am Xyz C G", "A", "minor")
    with pytest.raises(ValueError):
        parse_progression("Am", "A", "minor")   # needs at least two chords


def test_key_is_relative_not_absolute():
    # The same chord name maps to different romans depending on the key.
    assert chord_name_to_roman("G", "C", "major") == "V"
    assert chord_name_to_roman("G", "G", "major") == "I"
    assert chord_name_to_roman("G", "A", "minor") == "bVII"
