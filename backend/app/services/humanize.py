"""Apply subtle timing and velocity humanization to note events."""
import random
from dataclasses import dataclass


def humanize_velocity(velocity: int, amount: float = 0.1) -> int:
    spread = int(velocity * amount)
    return max(1, min(127, velocity + random.randint(-spread, spread)))


def humanize_timing(tick: int, amount_ticks: int = 10) -> int:
    return max(0, tick + random.randint(-amount_ticks, amount_ticks))
