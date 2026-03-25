import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.chords import roman_to_chord
from app.services.variation import should_trigger
from app.theory.rhythm import apply_swing


def _approach(current_root: int, next_root: int, steps_away: int) -> int:
    """Chromatic approach note `steps_away` half-steps before next_root."""
    diff = next_root - current_root
    if diff == 0:
        return current_root
    direction = 1 if diff > 0 else -1
    return max(24, min(60, next_root - direction * steps_away))


def _generate_808_bass(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
    progression: list,
) -> List[NoteEvent]:
    """Long-sustain 808-style bass: one deep root note per bar, occasional mid-bar hit."""
    events: List[NoteEvent] = []
    bass_cfg = style.get("bass", {})
    prog_len = len(progression)
    beats_per_bar = 4

    for bar in range(bars):
        roman = progression[bar % prog_len]
        pitches = roman_to_chord(roman, key, scale, octave=2)
        root = max(24, min(48, pitches[0]))

        bar_start = float(bar * beats_per_bar)

        # Main hit: beat 1, sustain almost the whole bar
        sustain = beats_per_bar * 0.92
        events.append(NoteEvent(
            pitch=root,
            start=bar_start,
            duration=sustain,
            velocity=100 + random.randint(-6, 6),
            channel=1,
        ))

        # Optional mid-bar second hit at higher complexity
        if complexity > 0.4 and should_trigger(0.35 + complexity * 0.2):
            second_beat = random.choice([2.0, 2.5, 3.0])
            remaining = beats_per_bar - second_beat
            events.append(NoteEvent(
                pitch=root,
                start=bar_start + second_beat,
                duration=remaining * 0.85,
                velocity=88 + random.randint(-8, 8),
                channel=1,
            ))

    return events


def generate_bass(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
    progression: list | None = None,
) -> List[NoteEvent]:
    if progression is None:
        templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
        progression = random.choice(templates)

    bass_cfg = style.get("bass", {})

    if bass_cfg.get("bass_style") == "808":
        return _generate_808_bass(style, key, scale, bars, complexity, variation, progression)

    events: List[NoteEvent] = []
    density = bass_cfg.get("pattern_density", 0.5)
    sustain_bias = bass_cfg.get("sustain_bias", 0.6)
    octave_jump_prob = bass_cfg.get("octave_jumps", 0.15)
    swing_amount = style.get("drums", {}).get("swing", 0.0)

    ticks_per_beat = 480

    def _swing(beat: float) -> float:
        if swing_amount < 0.01:
            return beat
        tick = int(beat * ticks_per_beat)
        return apply_swing(tick, swing_amount, ticks_per_beat) / ticks_per_beat

    beats_per_bar = 4
    step_size = 0.5          # 8th note grid
    subdivisions = int(beats_per_bar / step_size)
    prog_len = len(progression)

    for chord_idx in range(bars):
        roman = progression[chord_idx % prog_len]
        next_roman = progression[(chord_idx + 1) % prog_len]

        chord_pitches = roman_to_chord(roman, key, scale, octave=3)
        next_pitches = roman_to_chord(next_roman, key, scale, octave=3)

        root = chord_pitches[0]
        if should_trigger(octave_jump_prob):
            root -= 12
        root = max(24, min(52, root))

        interval_third = chord_pitches[1] - chord_pitches[0] if len(chord_pitches) > 1 else 4
        third = max(24, min(60, root + interval_third))
        fifth = max(24, min(60, root + 7))

        next_root = max(24, min(52, next_pitches[0]))
        bar_start = chord_idx * beats_per_bar

        for step in range(subdivisions):
            beat = bar_start + step * step_size
            steps_to_next = subdivisions - 1 - step

            if step == 0:
                dur = step_size * (3 if should_trigger(sustain_bias) else 1)
                events.append(NoteEvent(
                    pitch=root, start=_swing(beat), duration=dur * 0.9,
                    velocity=92 + random.randint(-4, 4), channel=1,
                ))

            elif steps_to_next == 0 and should_trigger(0.7):
                pitch = _approach(root, next_root, 1)
                events.append(NoteEvent(
                    pitch=pitch, start=_swing(beat), duration=step_size * 0.8,
                    velocity=72 + random.randint(-6, 6), channel=1,
                ))

            elif steps_to_next == 1 and complexity > 0.5 and should_trigger(0.5):
                pitch = _approach(root, next_root, 2)
                events.append(NoteEvent(
                    pitch=pitch, start=_swing(beat), duration=step_size * 0.8,
                    velocity=70 + random.randint(-6, 6), channel=1,
                ))

            elif step == 4 and should_trigger(density):
                pitch = fifth if should_trigger(0.6) else root
                dur = step_size * (2 if should_trigger(sustain_bias * 0.4) else 1)
                events.append(NoteEvent(
                    pitch=pitch, start=_swing(beat), duration=dur * 0.9,
                    velocity=80 + random.randint(-8, 8), channel=1,
                ))

            elif step in (2, 6) and complexity > 0.5 and should_trigger(density * 0.65):
                pitch = random.choice([root, fifth, third])
                events.append(NoteEvent(
                    pitch=pitch, start=_swing(beat), duration=step_size * 0.85,
                    velocity=74 + random.randint(-8, 8), channel=1,
                ))

            elif step not in (0, 4) and should_trigger(density * (0.4 + complexity * 0.3)):
                if should_trigger(sustain_bias * 0.5):
                    continue
                pitch = fifth if should_trigger(0.3) else root
                events.append(NoteEvent(
                    pitch=pitch, start=_swing(beat), duration=step_size * 0.75,
                    velocity=66 + random.randint(-8, 8), channel=1,
                ))

    return events
