import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.scales import build_scale
from app.services.variation import should_trigger


def generate_melody(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
) -> List[NoteEvent]:
    events: List[NoteEvent] = []
    mel_cfg = style.get("melody", {})

    density = mel_cfg.get("density", 0.35) * (0.5 + complexity)
    stepwise = mel_cfg.get("stepwise_motion", 0.7)
    leap_prob = mel_cfg.get("leap_probability", 0.15)
    rest_prob = mel_cfg.get("rest_probability", 0.3)
    note_range = mel_cfg.get("range", [60, 79])

    scale_notes = [n for n in build_scale(key, scale, octave_start=4, num_octaves=2)
                   if note_range[0] <= n <= note_range[1]]
    if not scale_notes:
        scale_notes = build_scale(key, scale, octave_start=4, num_octaves=2)

    beats_per_bar = 4
    step = 0.25  # 16th notes
    steps_per_bar = int(beats_per_bar / step)
    current_note_idx = len(scale_notes) // 2

    beat = 0.0
    while beat < bars * beats_per_bar - step:
        if should_trigger(rest_prob):
            beat += step * random.choice([1, 2])
            continue
        if not should_trigger(density):
            beat += step
            continue

        # Choose note
        if should_trigger(stepwise) and len(scale_notes) > 2:
            direction = random.choice([-1, 1])
            current_note_idx = max(0, min(len(scale_notes) - 1, current_note_idx + direction))
        elif should_trigger(leap_prob) and len(scale_notes) > 4:
            leap = random.choice([-3, -2, 2, 3])
            current_note_idx = max(0, min(len(scale_notes) - 1, current_note_idx + leap))

        pitch = scale_notes[current_note_idx]
        dur_steps = random.choices([1, 2, 4], weights=[0.5, 0.35, 0.15])[0]
        duration = dur_steps * step * 0.9
        vel = 80 + random.randint(-12, 12)

        events.append(NoteEvent(pitch=pitch, start=beat, duration=duration, velocity=vel, channel=2))
        beat += dur_steps * step

    return events
