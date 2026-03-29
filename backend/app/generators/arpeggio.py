import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.chords import roman_to_chord
from app.services.variation import should_trigger
from app.services.humanize import velocity_arc
from app.theory.rhythm import apply_swing


def generate_arpeggio(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
    progression: list | None = None,
    octave: int = 5,
) -> List[NoteEvent]:
    events: List[NoteEvent] = []
    if progression is None:
        templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
        progression = random.choice(templates)

    arp_cfg = style.get("arpeggio", {})
    pattern = arp_cfg.get("pattern", "up")          # up | down | up_down
    speed = arp_cfg.get("speed", 0.25)              # beats per note (0.25=16th, 0.5=8th)
    include_octave = arp_cfg.get("include_octave", False)
    allow_7th = arp_cfg.get("allow_7th", False)
    swing_amount = style.get("drums", {}).get("swing", 0.0)

    beats_per_bar = 4
    prog_len = len(progression)
    ticks_per_beat = 480

    for chord_idx in range(bars):
        roman = progression[chord_idx % prog_len]
        pitches = sorted(roman_to_chord(roman, key, scale, octave=octave, allow_7th=allow_7th))

        if include_octave:
            pitches = pitches + [pitches[0] + 12]

        if pattern == "up":
            seq = pitches
        elif pattern == "down":
            seq = list(reversed(pitches))
        elif pattern == "random":
            seq = random.sample(pitches, len(pitches))
        else:  # up_down
            seq = pitches + list(reversed(pitches[1:-1])) if len(pitches) > 2 else pitches

        bar_start = chord_idx * beats_per_bar
        pos = 0.0
        seq_idx = 0

        if pattern == "chord_burst":
            for j, pitch in enumerate(pitches):
                t = bar_start + j * 0.125
                base_vel = velocity_arc(chord_idx, bars, 74)
                vel = min(127, base_vel + (8 if j == 0 else 0) + random.randint(-4, 4))
                events.append(NoteEvent(
                    pitch=min(127, max(0, pitch)),
                    start=t,
                    duration=beats_per_bar * 0.9,
                    velocity=vel,
                    channel=3,
                ))
            continue  # skip the regular while loop for this bar

        while pos <= beats_per_bar - speed * 0.5:
            # Occasional rest for variation
            if seq_idx > 0 and should_trigger(variation * 0.3 + 0.05):
                pos += speed
                seq_idx += 1
                continue

            pitch = seq[seq_idx % len(seq)]
            is_root = (seq_idx % len(seq) == 0)
            beat_in_bar = pos % beats_per_bar
            is_strong = beat_in_bar < 0.01 or abs(beat_in_bar - 2.0) < 0.01
            is_medium = abs(beat_in_bar - 1.0) < 0.01 or abs(beat_in_bar - 3.0) < 0.01
            base_vel = velocity_arc(chord_idx, bars, 74)
            accent = 12 if is_root else (6 if is_strong else (3 if is_medium else 0))
            vel = min(127, base_vel + accent + random.randint(-6, 6))

            t_tick = int((bar_start + pos) * ticks_per_beat)
            t_tick = apply_swing(t_tick, swing_amount, ticks_per_beat)

            events.append(NoteEvent(
                pitch=min(127, max(0, pitch)),
                start=t_tick / ticks_per_beat,
                duration=speed * 0.8,
                velocity=vel,
                channel=3,
            ))

            pos += speed
            seq_idx += 1

    return events
