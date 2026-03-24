"""Variation helpers — introduce controlled randomness based on variation parameter."""
import random


def should_trigger(probability: float) -> bool:
    return random.random() < probability


def vary(value: float, variation: float, low: float = 0.0, high: float = 1.0) -> float:
    delta = (random.random() * 2 - 1) * variation
    return max(low, min(high, value + delta))


def pick_weighted(options: list, weights: list):
    return random.choices(options, weights=weights, k=1)[0]
