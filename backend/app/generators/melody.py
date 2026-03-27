import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.scales import build_scale
from app.theory.chords import roman_to_chord
from app.theory.notes import note_name_to_midi
from app.services.variation import should_trigger
from app.services.humanize import beat_velocity, timing_jitter, velocity_arc
from app.theory.rhythm import apply_swing


def _chord_tone_indices(roman: str, key: str, scale: str, scale_notes: list) -> list:
    """Return indices into scale_notes whose pitch class matches a chord tone."""
    chord_pitches = {p % 12 for p in roman_to_chord(roman, key, scale, octave=4)}
    return [i for i, n in enumerate(scale_notes) if n % 12 in chord_pitches]


def _phrase_vel_arc(beat_in_phrase: float, phrase_beats: float, base: int) -> int:
    """Per-phrase velocity arc: soft start, peak at ~65%, resolve softer at tail."""
    pos = beat_in_phrase / max(1, phrase_beats)
    if pos < 0.12:
        factor = 0.80
    elif pos < 0.65:
        factor = 0.80 + 0.20 * (pos / 0.65)
    elif pos < 0.85:
        factor = 1.00
    else:
        factor = 1.00 - 0.15 * ((pos - 0.85) / 0.15)
    return max(1, min(127, int(base * factor)))


def _blue_note(pitch: int, key_root_pc: int, probability: float) -> int:
    """Occasionally bend a scale tone to a blue note (b3, b5, b7)."""
    if not should_trigger(probability):
        return pitch
    pc = (pitch - key_root_pc) % 12
    if pc == 4:    # major 3rd → flat 3rd (blues classic)
        return pitch - 1
    if pc == 7 and should_trigger(0.4):    # 5th → flat 5th (tritone passing)
        return pitch - 1
    if pc == 11 and should_trigger(0.3):   # major 7th → flat 7th
        return pitch - 1
    return pitch


def _add_grace_note(
    events: List[NoteEvent],
    pitch: int,
    beat: float,
    velocity: int,
    channel: int,
) -> None:
    """Insert a 32nd-note grace note just before the target pitch."""
    grace_start = max(0.0, beat - 0.0625)
    events.append(NoteEvent(
        pitch=max(0, pitch - 1),   # chromatic approach from below
        start=grace_start,
        duration=0.055,
        velocity=max(1, velocity - 28),
        channel=channel,
    ))


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

    swing_amount = style.get("drums", {}).get("swing", 0.0)
    ticks_per_beat = 480
    blue_notes = style.get("blue_notes", False)
    grace_notes = style.get("grace_notes", False)

    # Key root pitch class for blue note calculations
    key_root_pc = note_name_to_midi(key, 4) % 12

    def _swing(beat: float) -> float:
        if swing_amount < 0.01:
            return beat
        tick = int(beat * ticks_per_beat)
        return apply_swing(tick, swing_amount, ticks_per_beat) / ticks_per_beat

    mel_scale = style.get("melody_scale", scale)
    vel_arc_start = style.get("vel_arc_start", 0.75)
    velocity_base = style.get("velocity_base", 82)

    def _styled_arc(bar: int, total: int, base: int, start: float) -> int:
        t = bar / max(1, total - 1)
        return max(1, min(127, int(base * (start + (1.0 - start) * t))))

    density = mel_cfg.get("density", 0.5) * (0.8 + 0.4 * complexity)
    density = min(0.92, max(0.2, density))
    stepwise = mel_cfg.get("stepwise_motion", 0.7)
    leap_prob = mel_cfg.get("leap_probability", 0.15)
    note_range = mel_cfg.get("range", [60, 79])

    scale_notes = [n for n in build_scale(key, mel_scale, octave_start=4, num_octaves=2)
                   if note_range[0] <= n <= note_range[1]]
    if not scale_notes:
        scale_notes = build_scale(key, mel_scale, octave_start=4, num_octaves=2)

    beats_per_bar = 4
    step = 0.25  # 16th notes
    chords_per_bar = 2 if complexity > 0.6 else 1
    beats_per_chord = beats_per_bar / chords_per_bar
    prog_len = len(progression)
    total_beats = bars * beats_per_bar
    phrase_beats = beats_per_bar * 4  # 4-bar phrases
    question_beats = phrase_beats / 2  # first half = question

    current_note_idx = len(scale_notes) // 2
    _prev_pitch: int | None = None     # anti-repetition tracking
    _rep_count: int = 0

    # Generate raw notes for all bars
    raw: List[NoteEvent] = []
    beat = 0.0
    while beat < total_beats - step:
        bar_num = int(beat / beats_per_bar)
        beat_in_phrase = beat % phrase_beats
        is_phrase_start = beat > 0.5 and beat_in_phrase < step
        is_cadence_bar = beat_in_phrase >= phrase_beats - beats_per_bar  # last bar of phrase
        is_phrase_tail = beat_in_phrase >= phrase_beats - 1.0  # last beat of phrase
        # Call/response: question = first half of phrase, response = second half
        is_question = beat_in_phrase < question_beats
        is_response_tail = beat_in_phrase >= phrase_beats - beats_per_bar * 1.5

        # Phrase start: short breath between phrases
        if is_phrase_start and should_trigger(0.30):
            beat += step * random.choice([1, 2])
            continue

        chord_idx = int(beat / beats_per_chord)
        current_roman = progression[chord_idx % prog_len]
        beat_in_chord = beat - chord_idx * beats_per_chord

        # Phrase tail: hold on a long cadential note then rest
        if is_phrase_tail:
            ct = _chord_tone_indices(current_roman, key, mel_scale, scale_notes)
            if ct:
                current_note_idx = ct[0]  # resolve to root-ish tone
            pitch = scale_notes[current_note_idx]
            remaining = phrase_beats - beat_in_phrase
            dur = max(step, remaining * 0.85)
            base_vel = _styled_arc(bar_num, bars, velocity_base, vel_arc_start)
            base_vel = _phrase_vel_arc(beat_in_phrase, phrase_beats, base_vel)
            vel = beat_velocity(beat, base_vel)
            raw.append(NoteEvent(
                pitch=pitch,
                start=max(0.0, _swing(beat) + timing_jitter()),
                duration=min(dur, total_beats - beat),
                velocity=vel,
                channel=2,
            ))
            # Skip to start of next phrase
            beat = (int(beat / phrase_beats) + 1) * phrase_beats
            continue

        # Cadence bar: reduce density for breathing room, strong chord-tone bias
        effective_density = density * 0.72 if is_cadence_bar else density
        if not should_trigger(effective_density):
            beat += step
            continue

        is_chord_downbeat = beat_in_chord < step
        is_strong_beat = (beat % 1.0) < step
        chord_tone_prob = 0.85 if is_cadence_bar else (0.65 if is_chord_downbeat else 0.35)

        # Call/response: response half resolves strongly to chord tones, root bias
        if is_response_tail:
            chord_tone_prob = min(0.92, chord_tone_prob + 0.25)

        if (is_chord_downbeat or is_cadence_bar) and should_trigger(chord_tone_prob):
            ct = _chord_tone_indices(current_roman, key, mel_scale, scale_notes)
            if ct:
                # In response half, prefer lower (root-ish) chord tones for resolution
                if is_response_tail and len(ct) > 1:
                    current_note_idx = ct[0]
                else:
                    current_note_idx = min(ct, key=lambda i: abs(i - current_note_idx))
        elif is_strong_beat and should_trigger(0.35):
            ct = _chord_tone_indices(current_roman, key, mel_scale, scale_notes)
            if ct:
                current_note_idx = min(ct, key=lambda i: abs(i - current_note_idx))
        else:
            if should_trigger(stepwise) and len(scale_notes) > 2:
                range_frac  = current_note_idx / max(1, len(scale_notes) - 1)
                phrase_pos  = beat_in_phrase / phrase_beats  # 0.0 → 1.0 through the phrase

                # Range extremes override everything to pull back toward center
                if range_frac > 0.8:
                    d_weights = [0.85, 0.15]
                elif range_frac < 0.2:
                    d_weights = [0.15, 0.85]
                else:
                    # Call/response arch contour:
                    # Question (0→0.5): build upward tension
                    # Response (0.5→1.0): resolve downward
                    if phrase_pos < 0.45:
                        d_weights = [0.32, 0.68]   # upward — building question
                    elif phrase_pos > 0.75:
                        d_weights = [0.72, 0.28]   # downward — resolving response
                    else:
                        d_weights = [0.5, 0.5]

                direction = random.choices([-1, 1], weights=d_weights)[0]
                current_note_idx = max(0, min(len(scale_notes) - 1, current_note_idx + direction))
            elif should_trigger(leap_prob) and len(scale_notes) > 4:
                # Leaps in question half go upward; in response half go downward
                if is_question:
                    leap = random.choice([2, 3])
                else:
                    leap = random.choice([-3, -2])
                current_note_idx = max(0, min(len(scale_notes) - 1, current_note_idx + leap))

        pitch = scale_notes[current_note_idx]

        # Anti-repetition: no more than 2 consecutive identical pitches
        if pitch == _prev_pitch:
            _rep_count += 1
            if _rep_count >= 2:
                step_dir = 1 if current_note_idx < len(scale_notes) // 2 else -1
                current_note_idx = max(0, min(len(scale_notes) - 1, current_note_idx + step_dir))
                pitch = scale_notes[current_note_idx]
                _rep_count = 0
        else:
            _rep_count = 0
        _prev_pitch = pitch

        # Blue notes: occasional chromatic inflection (b3, b5, b7)
        if blue_notes and should_trigger(0.18):
            pitch = _blue_note(pitch, key_root_pc, 1.0)
            pitch = max(note_range[0], min(note_range[1], pitch))

        # Sparse styles mix short and medium notes; dense styles favor quick notes
        if density < 0.45:
            dur_steps = random.choices([1, 2, 3, 4], weights=[0.35, 0.38, 0.18, 0.09])[0]
        else:
            dur_steps = random.choices([1, 2, 3, 4], weights=[0.48, 0.35, 0.13, 0.04])[0]
        # Articulation: longer notes get higher legato factor so they don't sound clipped
        legato = 0.88 if dur_steps <= 2 else 0.94
        duration = min(dur_steps * step * legato, total_beats - beat)
        base_vel = _styled_arc(bar_num, bars, velocity_base, vel_arc_start)
        base_vel = _phrase_vel_arc(beat_in_phrase, phrase_beats, base_vel)
        vel = beat_velocity(beat, base_vel)
        jitter = timing_jitter()

        # Grace note: add before chord-tone arrivals on downbeats in expressive styles
        if grace_notes and is_chord_downbeat and is_strong_beat and should_trigger(0.22):
            ct = _chord_tone_indices(current_roman, key, mel_scale, scale_notes)
            if current_note_idx in ct:
                _add_grace_note(raw, pitch, max(0.0, _swing(beat) + jitter), vel, channel=2)

        raw.append(NoteEvent(
            pitch=pitch,
            start=max(0.0, _swing(beat) + jitter),
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
        if roll < 0.30:
            # Exact repeat with velocity shift
            vel_shift = random.randint(-8, 8)
            for n in motif:
                t = b_start + (n.start % block_beats)
                if t < total_beats:
                    final.append(NoteEvent(n.pitch, t, min(n.duration, total_beats - t),
                                           max(1, min(127, n.velocity + vel_shift)), n.channel))
        elif roll < 0.52:
            # Pitch-shifted repeat
            shift = random.choice([-5, -4, -3, -2, 2, 3, 4, 5])
            for n in motif:
                shifted = n.pitch + shift
                if note_range[0] <= shifted <= note_range[1] and scale_notes:
                    new_p = min(scale_notes, key=lambda s: abs(s - shifted))
                    t = b_start + (n.start % block_beats)
                    if t < total_beats:
                        final.append(NoteEvent(new_p, t, min(n.duration, total_beats - t),
                                               n.velocity, n.channel))
        elif roll < 0.68:
            # Fragmentation: only first half of motif
            half = block_beats / 2
            frag = [n for n in motif if n.start % block_beats < half]
            vel_shift = random.randint(-5, 5)
            for n in frag:
                t = b_start + (n.start % block_beats)
                if t < total_beats:
                    final.append(NoteEvent(n.pitch, t, min(n.duration, total_beats - t),
                                           max(1, min(127, n.velocity + vel_shift)), n.channel))
        elif roll < 0.84:
            # Melodic inversion: flip intervals relative to first motif note
            if motif and scale_notes:
                anchor = motif[0].pitch
                for n in motif:
                    interval = n.pitch - anchor
                    inverted_p = anchor - interval
                    # Snap to nearest scale tone in range
                    candidates = [s for s in scale_notes if note_range[0] <= s <= note_range[1]]
                    if candidates:
                        new_p = min(candidates, key=lambda s: abs(s - inverted_p))
                        t = b_start + (n.start % block_beats)
                        if t < total_beats:
                            final.append(NoteEvent(new_p, t, min(n.duration, total_beats - t),
                                                   n.velocity, n.channel))
        else:
            final.extend(existing)

    # Post-process: enforce max-2-consecutive-same-pitch across full output
    # (motif copies at block boundaries can create longer runs)
    out: List[NoteEvent] = []
    _pp_prev: int | None = None
    _pp_count: int = 0
    for note in sorted(final, key=lambda n: n.start):
        if note.pitch == _pp_prev:
            _pp_count += 1
            if _pp_count >= 2:
                new_p = note.pitch + (1 if note.pitch < note_range[1] else -1)
                out.append(NoteEvent(new_p, note.start, note.duration, note.velocity, note.channel))
                _pp_prev = new_p
                _pp_count = 0
                continue
        else:
            _pp_count = 0
        out.append(note)
        _pp_prev = note.pitch
    return out
