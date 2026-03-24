"""Rhythm utilities — beat/subdivision helpers."""


def subdivisions_per_bar(time_sig_num: int = 4, subdivision: int = 16) -> int:
    """Number of subdivisions in one bar."""
    return time_sig_num * (subdivision // 4)


def beats_to_ticks(beats: float, ticks_per_beat: int = 480) -> int:
    return int(beats * ticks_per_beat)


def sixteenth_to_ticks(sixteenths: float, ticks_per_beat: int = 480) -> int:
    return int(sixteenths * ticks_per_beat / 4)


def apply_swing(tick: int, swing: float, ticks_per_beat: int = 480) -> int:
    """Push every odd 8th-note subdivision forward by swing amount (0=straight, 1=full triplet)."""
    eighth = ticks_per_beat // 2
    beat_pos = tick % ticks_per_beat
    eighth_pos = beat_pos // eighth
    pos_in_eighth = beat_pos % eighth
    if eighth_pos % 2 == 1:
        shift = int(swing * eighth / 3)
        return tick + shift
    return tick
