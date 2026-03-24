import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.chords import roman_to_chord
from app.services.variation import should_trigger


def generate_bass(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
) -> List[NoteEvent]:
    events: List[NoteEvent] = []
    templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
    progression = random.choice(templates)
    bass_cfg = style.get("bass", {})

    density = bass_cfg.get("pattern_density", 0.5)
    sustain_bias = bass_cfg.get("sustain_bias", 0.6)
    octave_jump_prob = bass_cfg.get("octave_jumps", 0.15)

    beats_per_bar = 4
    subdivisions = beats_per_bar * 2  # 8th notes
    chords_per_bar = 1
    chords_total = bars * chords_per_bar
    prog_len = len(progression)

    for chord_idx in range(chords_total):
        roman = progression[chord_idx % prog_len]
        root_pitches = roman_to_chord(roman, key, scale, octave=3)
        root = root_pitches[0]  # lowest note

        # Optionally drop an octave
        if should_trigger(octave_jump_prob):
            root -= 12
        root = max(24, min(60, root))

        bar_start = chord_idx * beats_per_bar

        # Build rhythmic pattern for this bar
        step_size = 0.5  # 8th notes
        for step in range(subdivisions):
            beat = bar_start + step * step_size
            if step == 0:
                # Always hit root on beat 1
                dur = step_size * (3 if should_trigger(sustain_bias) else 1)
                events.append(NoteEvent(pitch=root, start=beat, duration=dur * 0.9, velocity=90 + random.randint(-5, 5), channel=1))
            elif should_trigger(density * (1 + complexity * 0.5)):
                dur = step_size * (2 if should_trigger(sustain_bias) else 1)
                vel = 75 + random.randint(-10, 10)
                events.append(NoteEvent(pitch=root, start=beat, duration=dur * 0.9, velocity=vel, channel=1))

    return events
