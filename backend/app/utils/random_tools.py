import random
from typing import TypeVar, List

T = TypeVar("T")


def weighted_choice(options: List[T], weights: List[float]) -> T:
    return random.choices(options, weights=weights, k=1)[0]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def random_seed(seed: int | None = None) -> None:
    if seed is not None:
        random.seed(seed)
