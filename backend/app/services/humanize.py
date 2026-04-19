"""Apply subtle timing and velocity humanization to note events."""
import random


def humanize_velocity(velocity: int, amount: float = 0.1) -> int:
    spread = int(velocity * amount)
    return max(1, min(127, velocity + random.randint(-spread, spread)))


def humanize_timing(tick: int, amount_ticks: int = 10) -> int:
    return max(0, tick + random.randint(-amount_ticks, amount_ticks))


def beat_velocity(beat: float, base: int, beats_per_bar: int = 4) -> int:
    """Scale velocity by beat position. Beat 1 loudest, upbeats softest."""
    pos = beat % beats_per_bar
    if pos < 0.01:                          # beat 1
        factor = 1.0
    elif abs(pos - 2.0) < 0.01:            # beat 3
        factor = 0.88
    elif abs(pos - 1.0) < 0.01 or abs(pos - 3.0) < 0.01:   # beats 2 & 4
        factor = 0.78
    else:                                   # upbeats / 16th subdivisions
        factor = 0.62 + random.random() * 0.15
    return max(1, min(127, int(base * factor) + random.randint(-4, 4)))


# 4-bar phrase breathing: the classic swell-and-resolve shape shared by all parts.
# Bar 0 = gentle start, bar 1 = building, bar 2 = peak, bar 3 = slight breath before repeat.
_PHRASE_BREATH = [0.95, 1.00, 1.04, 0.96]


def phrase_breath_factor(bar_num: int) -> float:
    """Return a velocity scale factor for bar_num's position in a 4-bar phrase.

    Applying this consistently across melody, chords, and bass makes all parts
    breathe together, which is the core of a convincing groove.
    """
    return _PHRASE_BREATH[bar_num % 4]


def timing_jitter(max_beats: float = 0.025) -> float:
    """Return a small random beat offset (±max_beats) for timing humanization."""
    return random.uniform(-max_beats, max_beats)


def velocity_arc(bar: int, total_bars: int, base: int) -> int:
    """Scale velocity from 75% at bar 0 up to 100% at the last bar."""
    t = bar / max(1, total_bars - 1)
    factor = 0.75 + 0.25 * t
    return max(1, min(127, int(base * factor)))


def micro_jitter(ticks_per_beat: int = 480, max_ticks: int = 3) -> float:
    """Tiny ±1–3 tick timing offset that removes the quantized feel without audible slop."""
    return random.randint(-max_ticks, max_ticks) / ticks_per_beat


def _humanize_scale(style: dict) -> float:
    """Return the user-requested humanize multiplier (0=tight, 1=loose), defaulting to 0.5."""
    return float(style.get("_humanize_scale", 0.5))


def style_jitter(style: dict) -> float:
    """Return a timing jitter amount scaled to the style's feel.

    Tight styles (techno, drill, house): ±0.008 beats
    Medium styles (rnb, funk, boom_bap): ±0.018 beats
    Loose styles (jazz, lofi, bossa_nova): ±0.032 beats
    """
    jitter_map = {
        # tight
        "techno": 0.008, "drill": 0.008, "house": 0.010, "drum_and_bass": 0.008,
        "jersey_club": 0.008, "future_bass": 0.010,
        # medium
        "rnb": 0.018, "funk": 0.018, "boom_bap": 0.020, "dark_trap": 0.015,
        "trap_soul": 0.015, "cloud_rap": 0.015, "reggaeton": 0.015,
        "dancehall": 0.018, "cumbia": 0.018, "afrobeats": 0.020,
        # loose
        "jazz": 0.032, "lofi": 0.030, "bossa_nova": 0.028, "latin_jazz": 0.028,
        "soul": 0.025, "ambient": 0.035, "dark_ambient": 0.035,
        "cinematic": 0.025, "epic_orchestral": 0.022, "synthwave": 0.012,
    }
    style_id = style.get("id", "")
    base = jitter_map.get(style_id, 0.018)
    # Scale: at humanize=0 → 25% of base; at humanize=1 → 175% of base
    scale = 0.25 + _humanize_scale(style) * 1.5
    return base * scale


def style_velocity_variation(style: dict) -> int:
    """Return max velocity variation (±N) for this style.

    Tight electronic styles: ±4 (very consistent)
    Medium styles: ±8
    Loose/expressive styles: ±12 (more human feel)
    """
    variation_map = {
        # tight
        "techno": 4, "drill": 4, "house": 5, "drum_and_bass": 4,
        "jersey_club": 4, "future_bass": 5,
        # medium
        "rnb": 8, "funk": 9, "boom_bap": 9, "dark_trap": 6,
        "trap_soul": 6, "cloud_rap": 6, "reggaeton": 7,
        "dancehall": 8, "cumbia": 8, "afrobeats": 9, "synthwave": 5,
        # loose / expressive
        "jazz": 12, "lofi": 11, "bossa_nova": 11, "latin_jazz": 11,
        "soul": 10, "ambient": 8, "dark_ambient": 8,
        "cinematic": 7, "epic_orchestral": 7,
    }
    style_id = style.get("id", "")
    base = variation_map.get(style_id, 8)
    scale = 0.25 + _humanize_scale(style) * 1.5
    return max(1, int(base * scale))
