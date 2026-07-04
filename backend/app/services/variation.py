# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Variation helpers — introduce controlled randomness based on variation parameter."""
import random


def should_trigger(probability: float) -> bool:
    return random.random() < probability


def vary(value: float, variation: float, low: float = 0.0, high: float = 1.0) -> float:
    delta = (random.random() * 2 - 1) * variation
    return max(low, min(high, value + delta))


def pick_weighted(options: list, weights: list):
    return random.choices(options, weights=weights, k=1)[0]
