"""Stub for future section-based arrangement generation."""
from typing import List
from app.services.midi_writer import NoteEvent


def generate_arrangement(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
) -> dict[str, List[NoteEvent]]:
    """Placeholder — returns empty parts until Milestone 6."""
    return {}
