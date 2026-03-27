from app.core.constants import SCALE_INTERVALS, ROMAN_TO_DEGREE
from app.theory.notes import note_name_to_midi


def _triad(root: int, quality: str) -> list[int]:
    if quality == "major":
        return [root, root + 4, root + 7]
    elif quality == "minor":
        return [root, root + 3, root + 7]
    elif quality == "diminished":
        return [root, root + 3, root + 6]
    elif quality == "augmented":
        return [root, root + 4, root + 8]
    elif quality == "sus2":
        return [root, root + 2, root + 7]
    elif quality == "sus4":
        return [root, root + 5, root + 7]
    return [root, root + 4, root + 7]


def _seventh(root: int, quality: str, chord_quality: str) -> list[int]:
    base = _triad(root, chord_quality)
    if quality == "major7":
        return base + [root + 11]
    elif quality in ("minor7", "dom7"):
        return base + [root + 10]
    elif quality == "dim7":
        return [root, root + 3, root + 6, root + 9]
    elif quality == "hdim7":
        return [root, root + 3, root + 6, root + 10]
    return base


def roman_to_chord(
    roman: str,
    key: str,
    scale: str,
    octave: int = 4,
    allow_7th: bool = False,
    allow_9th: bool = False,
) -> list[int]:
    """Convert roman numeral to list of MIDI pitches.

    Supports:
    - Flat/sharp prefix: bVII, #IV, bvi
    - Uppercase/lowercase for major/minor quality
    - Suffix types: sus2, sus4, add9, add11, aug, dim, dim7, m7b5, maj7
    """
    intervals = SCALE_INTERVALS.get(scale, SCALE_INTERVALS["minor"])
    root_midi = note_name_to_midi(key, octave)

    # Parse flat/sharp prefix — only treat leading 'b' as flat when followed by a Roman numeral letter
    alteration = 0
    s = roman
    if len(s) > 1 and s[0] == "b" and s[1].upper() in "IVX":
        alteration = -1
        s = s[1:]
    elif s.startswith("#"):
        alteration = 1
        s = s[1:]

    # Parse chord-type suffix (longer strings first to prevent partial matches)
    chord_type = None
    for suffix in ("m7b5", "mM7", "dim7", "maj7", "9sus4", "7sus4", "sus2", "sus4", "add11", "add9", "aug", "dim", "m6", "m9", "6", "9"):
        if s.lower().endswith(suffix):
            chord_type = suffix
            s = s[: -len(suffix)]
            break

    # Uppercase numeral for degree lookup; preserve original case for quality
    is_minor = s == s.lower()
    degree = ROMAN_TO_DEGREE.get(s.upper(), 0)

    if alteration != 0:
        # b/# modifiers are borrowed-chord notation — always reference major scale degrees
        # so that bVII = whole step below tonic regardless of whether the key is major or minor
        major_intervals = SCALE_INTERVALS["major"]
        semitone = major_intervals[degree % len(major_intervals)]
    else:
        semitone = intervals[degree % len(intervals)]
    chord_root = root_midi + semitone + alteration

    # Explicit chord type suffix overrides allow_7th / allow_9th style parameters
    if chord_type == "sus2":
        return [chord_root, chord_root + 2, chord_root + 7]
    if chord_type == "sus4":
        return [chord_root, chord_root + 5, chord_root + 7]
    if chord_type == "aug":
        return [chord_root, chord_root + 4, chord_root + 8]
    if chord_type == "dim":
        return [chord_root, chord_root + 3, chord_root + 6]
    if chord_type == "dim7":
        return [chord_root, chord_root + 3, chord_root + 6, chord_root + 9]
    if chord_type == "m7b5":
        return [chord_root, chord_root + 3, chord_root + 6, chord_root + 10]
    if chord_type == "maj7":
        quality = "minor" if is_minor else "major"
        return _seventh(chord_root, "major7", quality)
    if chord_type == "add9":
        quality = "minor" if is_minor else "major"
        return _triad(chord_root, quality) + [chord_root + 14]
    if chord_type == "add11":
        quality = "minor" if is_minor else "major"
        return _triad(chord_root, quality) + [chord_root + 17]
    if chord_type == "6":
        return [chord_root, chord_root + 4, chord_root + 7, chord_root + 9]
    if chord_type == "m6":
        return [chord_root, chord_root + 3, chord_root + 7, chord_root + 9]
    if chord_type == "m9":
        return [chord_root, chord_root + 3, chord_root + 7, chord_root + 10, chord_root + 14]
    if chord_type == "9":
        quality = "minor" if is_minor else "major"
        seventh_q = "minor7" if is_minor else "dom7"
        return _seventh(chord_root, seventh_q, quality) + [chord_root + 14]
    if chord_type == "mM7":
        # Minor-major 7th: minor triad + major 7th — distinctive jazz/film chord
        return [chord_root, chord_root + 3, chord_root + 7, chord_root + 11]
    if chord_type == "7sus4":
        return [chord_root, chord_root + 5, chord_root + 7, chord_root + 10]
    if chord_type == "9sus4":
        return [chord_root, chord_root + 5, chord_root + 7, chord_root + 10, chord_root + 14]

    # Default triad — optionally extended by style config
    quality = "minor" if is_minor else "major"
    # V chord (degree 4) uses dominant 7th for harmonic tension toward I;
    # all other major chords use major 7th.
    seventh_quality = "minor7" if is_minor else ("dom7" if degree == 4 else "major7")
    if allow_9th:
        notes = _seventh(chord_root, seventh_quality, quality)
        return notes + [chord_root + 14]
    if allow_7th:
        return _seventh(chord_root, seventh_quality, quality)
    return _triad(chord_root, quality)
