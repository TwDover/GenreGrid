# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
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
