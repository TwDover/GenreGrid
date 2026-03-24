import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.scales import build_scale
from app.theory.chords import roman_to_chord
from app.services.variation import should_trigger
from app.services.humanize import beat_velocity, timing_jitter, velocity_arc


def _chord_tone_indices(roman: str, key: str, scale: str, scale_notes: list) -> list:
    """Return indices into scale_notes whose pitch class matches a chord tone."""
    chord_pitches = {p % 12 for p in roman_to_chord(roman, key, scale, octave=4)}
    return [i for i, n in enumerate(scale_notes) if n % 12 in chord_pitches]


def generate_melody(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
    progression: list | None = None,
) -> List[NoteEvent]:
    events: List[NoteEvent] = []
    mel_cfg = style.get("melody", {})

    if progression is None:
        templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
        progression = random.choice(templates)

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
    chords_per_bar = 2 if complexity > 0.6 else 1
    beats_per_chord = beats_per_bar / chords_per_bar
    prog_len = len(progression)
    total_beats = bars * beats_per_bar

    current_note_idx = len(scale_notes) // 2

    # Generate raw notes for all bars
    raw: List[NoteEvent] = []
    beat = 0.0
    while beat < total_beats - step:
        bar_num = int(beat / beats_per_bar)
        if should_trigger(rest_prob):
            beat += step * random.choice([1, 2])
            continue
        if not should_trigger(density):
            beat += step
            continue

        chord_idx = int(beat / beats_per_chord)
        current_roman = progression[chord_idx % prog_len]
        beat_in_chord = beat - chord_idx * beats_per_chord

        is_chord_downbeat = beat_in_chord < step
        is_strong_beat = (beat % 1.0) < step

        if is_chord_downbeat and should_trigger(0.65):
            ct = _chord_tone_indices(current_roman, key, scale, scale_notes)
            if ct:
                current_note_idx = min(ct, key=lambda i: abs(i - current_note_idx))
        elif is_strong_beat and should_trigger(0.35):
            ct = _chord_tone_indices(current_roman, key, scale, scale_notes)
            if ct:
                current_note_idx = min(ct, key=lambda i: abs(i - current_note_idx))
        else:
            if should_trigger(stepwise) and len(scale_notes) > 2:
                direction = random.choice([-1, 1])
                current_note_idx = max(0, min(len(scale_notes) - 1, current_note_idx + direction))
            elif should_trigger(leap_prob) and len(scale_notes) > 4:
                leap = random.choice([-3, -2, 2, 3])
                current_note_idx = max(0, min(len(scale_notes) - 1, current_note_idx + leap))

        pitch = scale_notes[current_note_idx]
        dur_steps = random.choices([1, 2, 4], weights=[0.5, 0.35, 0.15])[0]
        duration = dur_steps * step * 0.9
        base_vel = velocity_arc(bar_num, bars, 82)
        vel = beat_velocity(beat, base_vel)
        jitter = timing_jitter()

        raw.append(NoteEvent(
            pitch=pitch,
            start=max(0.0, beat + jitter),
            duration=duration,
            velocity=vel,
            channel=2,
        ))
        beat += dur_steps * step

    # Motif repetition: use first 2 bars as motif, replicate/vary subsequent blocks
    block_beats = beats_per_bar * 2  # 8 beats = 2 bars
    motif = [n for n in raw if n.start < block_beats]

    if not motif or bars <= 2:
        return raw

    # Keep first block; rebuild subsequent blocks
    final: List[NoteEvent] = list(motif)
    num_blocks = (bars + 1) // 2

    for block in range(1, num_blocks):
        b_start = block * block_beats
        b_end = b_start + block_beats
        existing = [n for n in raw if b_start <= n.start < b_end]

        roll = random.random()
        if roll < 0.45:
            # Exact repeat — shift motif time to this block
            for n in motif:
                t = b_start + (n.start % block_beats)
                if t < total_beats:
                    final.append(NoteEvent(
                        pitch=n.pitch,
                        start=t,
                        duration=n.duration,
                        velocity=n.velocity,
                        channel=n.channel,
                    ))
        elif roll < 0.80:
            # Pitch-shifted repeat — transpose by ±2–5 semitones staying in range
            shift = random.choice([-5, -4, -3, -2, 2, 3, 4, 5])
            for n in motif:
                new_p = n.pitch + shift
                if note_range[0] <= new_p <= note_range[1]:
                    t = b_start + (n.start % block_beats)
                    if t < total_beats:
                        final.append(NoteEvent(
                            pitch=new_p,
                            start=t,
                            duration=n.duration,
                            velocity=n.velocity,
                            channel=n.channel,
                        ))
        else:
            # New material from raw generation
            final.extend(existing)

    return sorted(final, key=lambda n: n.start)
