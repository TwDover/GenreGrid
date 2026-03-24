import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.chords import roman_to_chord
from app.services.variation import should_trigger
from app.services.humanize import timing_jitter, velocity_arc


def _apply_inversion(pitches: list[int], inversion: int) -> list[int]:
    result = sorted(pitches)
    for _ in range(inversion % max(1, len(result))):
        result = sorted(result[1:] + [result[0] + 12])
    return result


def _voice_lead(pitches: list[int], prev_top: int) -> list[int]:
    """Return the inversion of pitches whose top note is closest to prev_top."""
    best = sorted(pitches)
    best_dist = abs(best[-1] - prev_top)
    for inv in range(1, len(pitches)):
        candidate = _apply_inversion(pitches, inv)
        dist = abs(candidate[-1] - prev_top)
        if dist < best_dist:
            best = candidate
            best_dist = dist
    return best


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
    chord_rhythm = style.get("chord_rhythm")  # optional 16th-note grid list

    beats_per_bar = 4
    chords_per_bar = 2 if complexity > 0.6 else 1
    beats_per_chord = beats_per_bar / chords_per_bar
    total_chords = bars * chords_per_bar
    prog_len = len(progression)
    step = 0.25  # 16th note

    prev_top = 72  # initial reference for voice leading

    for i in range(total_chords):
        roman = progression[i % prog_len]
        allow_7th = should_trigger(allow_7th_prob)
        allow_9th = should_trigger(allow_9th_prob) if allow_7th else False
        pitches = roman_to_chord(roman, key, scale, octave=4, allow_7th=allow_7th, allow_9th=allow_9th)

        if complexity > 0.25 and should_trigger(0.75):
            pitches = _voice_lead(pitches, prev_top)
        else:
            pitches = sorted(pitches)

        prev_top = pitches[-1]

        start_beat = i * beats_per_chord
        bar_num = int(start_beat / beats_per_bar)
        is_downbeat = (start_beat % beats_per_bar) < 0.01
        base_vel = velocity_arc(bar_num, bars, 74)
        vel = (base_vel + 6 if is_downbeat else base_vel) + random.randint(-5, 5)

        if chord_rhythm:
            # Fire chord hits on every pattern grid position = 1
            num_steps = int(beats_per_chord / step)
            bar_offset = start_beat % beats_per_bar
            for s in range(num_steps):
                beat_in_bar = bar_offset + s * step
                pattern_idx = int(beat_in_bar / step) % len(chord_rhythm)
                if chord_rhythm[pattern_idx]:
                    hit_start = start_beat + s * step + timing_jitter(0.015)
                    hit_vel = vel - random.randint(0, 10)
                    for pitch in pitches:
                        events.append(NoteEvent(
                            pitch=min(127, max(0, pitch)),
                            start=max(0.0, hit_start),
                            duration=step * 0.8,
                            velocity=max(1, hit_vel),
                            channel=0,
                        ))
        else:
            duration = beats_per_chord * 0.95
            jitter = timing_jitter(0.015)
            for pitch in pitches:
                events.append(NoteEvent(
                    pitch=min(127, max(0, pitch)),
                    start=max(0.0, start_beat + jitter),
                    duration=duration,
                    velocity=vel,
                    channel=0,
                ))

    return events
