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
    return [root, root + 4, root + 7]


def _seventh(root: int, quality: str, chord_quality: str) -> list[int]:
    base = _triad(root, chord_quality)
    if quality == "major7":
        return base + [root + 11]
    elif quality == "minor7":
        return base + [root + 10]
    elif quality == "dom7":
        return base + [root + 10]
    return base


def roman_to_chord(
    roman: str,
    key: str,
    scale: str,
    octave: int = 4,
    allow_7th: bool = False,
    allow_9th: bool = False,
) -> list[int]:
    """Convert roman numeral to list of MIDI pitches."""
    intervals = SCALE_INTERVALS.get(scale, SCALE_INTERVALS["minor"])
    root_midi = note_name_to_midi(key, octave)

    # Determine degree
    numeral = roman.replace("b", "").replace("#", "")
    degree = ROMAN_TO_DEGREE.get(numeral, 0)
    is_minor = roman == roman.lower()

    semitone = intervals[degree % len(intervals)]
    chord_root = root_midi + semitone
    quality = "minor" if is_minor else "major"

    if allow_9th:
        notes = _seventh(chord_root, "minor7" if is_minor else "dom7", quality)
        ninth = chord_root + 14
        return notes + [ninth]
    if allow_7th:
        return _seventh(chord_root, "minor7" if is_minor else "dom7", quality)
    return _triad(chord_root, quality)
