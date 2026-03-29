NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

SCALE_INTERVALS = {
    "major":       [0, 2, 4, 5, 7, 9, 11],
    "minor":       [0, 2, 3, 5, 7, 8, 10],
    "dorian":      [0, 2, 3, 5, 7, 9, 10],
    "phrygian":    [0, 1, 3, 5, 7, 8, 10],
    "lydian":      [0, 2, 4, 6, 7, 9, 11],
    "mixolydian":  [0, 2, 4, 5, 7, 9, 10],
    "locrian":     [0, 1, 3, 5, 6, 8, 10],
    "pentatonic_minor": [0, 3, 5, 7, 10],
    "pentatonic_major": [0, 2, 4, 7, 9],
    "blues":            [0, 3, 5, 6, 7, 10],
    "harmonic_minor":   [0, 2, 3, 5, 7, 8, 11],
    "phrygian_dominant": [0, 1, 4, 5, 7, 8, 10],
    "whole_tone":       [0, 2, 4, 6, 8, 10],
}

ROMAN_TO_DEGREE = {
    "I": 0, "II": 1, "III": 2, "IV": 3,
    "V": 4, "VI": 5, "VII": 6,
    "i": 0, "ii": 1, "iii": 2, "iv": 3,
    "v": 4, "vi": 5, "vii": 6,
}

DRUM_MAP = {
    "kick":       36,
    "snare":      38,
    "clap":       39,
    "closed_hat": 42,
    "open_hat":   46,
    "ride":       51,
    "crash":      49,
    "tom_hi":     50,
    "tom_mid":    47,
    "tom_lo":     43,
    "perc1":      60,
    "perc2":      61,
}

TICKS_PER_BEAT = 480
DRUM_CHANNEL = 9
