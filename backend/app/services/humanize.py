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


def timing_jitter(max_beats: float = 0.025) -> float:
    """Return a small random beat offset (±max_beats) for timing humanization."""
    return random.uniform(-max_beats, max_beats)


def velocity_arc(bar: int, total_bars: int, base: int) -> int:
    """Scale velocity from 75% at bar 0 up to 100% at the last bar."""
    t = bar / max(1, total_bars - 1)
    factor = 0.75 + 0.25 * t
    return max(1, min(127, int(base * factor)))
