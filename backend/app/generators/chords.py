import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.chords import roman_to_chord
from app.services.variation import should_trigger


def generate_chords(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
    progression: list | None = None,
) -> List[NoteEvent]:
    events: List[NoteEvent] = []
    if progression is None:
        templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
        progression = random.choice(templates)
    ext = style.get("chord_extensions", {})
    allow_7th_prob = ext.get("allow_7th", 0.3)
    allow_9th_prob = ext.get("allow_9th", 0.1)

    beats_per_bar = 4
    chords_per_bar = 2 if complexity > 0.6 else 1
    beats_per_chord = beats_per_bar / chords_per_bar

    total_chords = bars * chords_per_bar
    prog_len = len(progression)

    for i in range(total_chords):
        roman = progression[i % prog_len]
        allow_7th = should_trigger(allow_7th_prob)
        allow_9th = should_trigger(allow_9th_prob) if allow_7th else False
        pitches = roman_to_chord(roman, key, scale, octave=4, allow_7th=allow_7th, allow_9th=allow_9th)

        start_beat = i * beats_per_chord
        duration = beats_per_chord * 0.95  # slight gap

        vel_base = 75
        vel = vel_base + random.randint(-8, 8)

        for pitch in pitches:
            events.append(NoteEvent(
                pitch=min(127, max(0, pitch)),
                start=start_beat,
                duration=duration,
                velocity=vel,
                channel=0,
            ))

    return events
