import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.chords import roman_to_chord
from app.theory.scales import build_scale
from app.services.variation import should_trigger
from app.services.humanize import micro_jitter
from app.theory.rhythm import apply_swing


def _on_kick(beat: float, kick_times: list[float] | None) -> bool:
    """True if a kick drum falls within ~1/32nd note of this beat."""
    return bool(kick_times) and any(abs(k - beat) < 0.06 for k in kick_times)


def _snap_to_kick(beat: float, kick_times: list[float] | None) -> float:
    """Snap to exact kick time if one falls within ~1/32nd note. Otherwise return beat unchanged."""
    if kick_times:
        for k in kick_times:
            if abs(k - beat) < 0.06:
                return k
    return beat


def _approach(current_root: int, next_root: int, steps_away: int) -> int:
    """Chromatic approach note `steps_away` half-steps before next_root."""
    diff = next_root - current_root
    if diff == 0:
        return current_root
    direction = 1 if diff > 0 else -1
    return max(24, min(60, next_root - direction * steps_away))


def _generate_walking_bass(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
    progression: list,
    kick_times: list[float] | None = None,
) -> List[NoteEvent]:
    """Jazz-style 4-to-the-floor walking bass with chord-tone navigation and chromatic approach."""
    events: List[NoteEvent] = []
    prog_len = len(progression)
    beats_per_bar = 4
    swing_amount = style.get("drums", {}).get("swing", 0.0)
    ticks_per_beat = 480

    def _swing(beat: float) -> float:
        if swing_amount < 0.01:
            return beat
        tick = int(beat * ticks_per_beat)
        return apply_swing(tick, swing_amount, ticks_per_beat) / ticks_per_beat

    # Build scale note set for diatonic passing notes
    scale_pcs = set(n % 12 for n in build_scale(key, scale, octave_start=2, num_octaves=4))

    pair_direction: int = 1  # +1 = ascending arc, -1 = descending; refreshed every 2 bars

    for bar in range(bars):
        roman = progression[bar % prog_len]
        next_roman = progression[(bar + 1) % prog_len]
        pitches = roman_to_chord(roman, key, scale, octave=2)
        next_pitches = roman_to_chord(next_roman, key, scale, octave=2)

        root = max(28, min(50, pitches[0]))
        third_int = (pitches[1] - pitches[0]) if len(pitches) > 1 else 4
        fifth = max(28, min(52, root + 7))
        third = max(28, min(52, root + third_int))
        next_root = max(28, min(50, next_pitches[0]))

        bar_start = float(bar * beats_per_bar)

        # Re-roll net direction every 2-bar pair for phrase-level shape
        if bar % 2 == 0:
            pair_direction = random.choice([-1, 1])

        # Beat 1: root — anchor
        kb = 8 if _on_kick(bar_start, kick_times) else 0
        vel = min(127, 100 + kb + random.randint(-5, 5))
        events.append(NoteEvent(pitch=root, start=_swing(_snap_to_kick(bar_start, kick_times)), duration=0.88, velocity=vel, channel=1))

        # Beat 2: 3rd or 5th
        beat2 = bar_start + 1.0
        kb2 = 6 if _on_kick(beat2, kick_times) else 0
        if should_trigger(0.15) and bar % 2 == 1:
            # Occasional octave displacement on bar 2
            p2 = max(28, min(52, root - 12 if root >= 40 else root + 12))
        elif pair_direction == 1:
            # Ascending arc: start mid-low (3rd) so there's room to rise
            p2 = third if should_trigger(0.62) else fifth
        else:
            # Descending arc: start mid-high (5th) so there's room to fall
            p2 = fifth if should_trigger(0.62) else third
        events.append(NoteEvent(pitch=p2, start=_swing(beat2), duration=0.88,
                                velocity=min(127, 86 + kb2 + random.randint(-8, 8)), channel=1))

        # Beat 3: 5th or scalar passing note
        beat3 = bar_start + 2.0
        kb3 = 6 if _on_kick(beat3, kick_times) else 0
        if should_trigger(0.35) and complexity > 0.4:
            # Scalar passing note between beat-2 pitch and beat-4 approach
            mid = (p2 + next_root) // 2
            # Snap to nearest scale or chromatic step
            candidates = [mid, mid + 1, mid - 1]
            p3 = max(28, min(52, min(candidates, key=lambda n: abs(n - mid) + (0 if n % 12 in scale_pcs else 1))))
        elif pair_direction == 1:
            # Ascending arc: reach upward from p2 toward the 5th
            p3 = max(p2, fifth) if should_trigger(0.55) else fifth
            p3 = max(28, min(52, p3))
        else:
            # Descending arc: come down from p2 toward the 3rd
            p3 = min(p2, third) if should_trigger(0.55) else third
            p3 = max(28, min(52, p3))
        events.append(NoteEvent(pitch=p3, start=_swing(beat3), duration=0.88,
                                velocity=min(127, 84 + kb3 + random.randint(-8, 8)), channel=1))

        # Beat 4: chromatic or scale-step approach to next bar root
        beat4 = bar_start + 3.0
        kb4 = 6 if _on_kick(beat4, kick_times) else 0
        # Alternate between below-approach (most common) and above-approach (encircle feel)
        if should_trigger(0.35):
            approach = max(28, min(52, next_root + 1))  # half-step from above
        else:
            approach = _approach(root, next_root, 1)    # half-step from below
        # Occasionally use a two-step approach for larger intervals
        if abs(next_root - root) > 4 and complexity > 0.5 and should_trigger(0.45):
            approach = _approach(root, next_root, 2)
        # Sometimes diatonic (scale-step) instead of chromatic
        nr2_down_ok = (next_root - 2) % 12 in scale_pcs
        nr2_up_ok   = (next_root + 2) % 12 in scale_pcs
        if should_trigger(variation * 0.3) and (nr2_down_ok or nr2_up_ok):
            approach = (next_root - 2) if nr2_down_ok else (next_root + 2)
        approach = max(28, min(52, approach))
        events.append(NoteEvent(pitch=approach, start=_swing(beat4), duration=0.88,
                                velocity=min(127, 88 + kb4 + random.randint(-8, 8)), channel=1))

    return [NoteEvent(e.pitch, max(0.0, e.start + micro_jitter()), e.duration, e.velocity, e.channel) for e in events]


# Each pattern is a list of (beat_offset, velocity_scale) tuples.
# Duration is auto-computed to fill to the next hit (or end of bar).
# Patterns are chosen once per generation so regeneration always sounds different.
_808_PATTERNS: list[list[tuple[float, float]]] = [
    [(0.0, 1.00)],                                # minimal — single long root
    [(0.0, 1.00), (2.0, 0.88)],                   # two-hit halves
    [(0.0, 1.00), (2.5, 0.82)],                   # syncopated pocket
    [(0.0, 1.00), (1.75, 0.74), (3.0, 0.90)],    # three-hit trap
    [(0.5, 0.96)],                                # laid-back / late entry
    [(0.0, 1.00), (3.75, 0.84)],                  # tail accent
    [(0.0, 1.00), (1.5, 0.78), (3.0, 0.90)],     # dotted-feel
    [(0.0, 1.00), (2.0, 0.86), (3.5, 0.80)],     # three even-ish hits
]
_808_SIMPLE = [p for p in _808_PATTERNS if len(p) == 1]
_808_MULTI  = [p for p in _808_PATTERNS if len(p) > 1]


def _generate_808_bass(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
    progression: list,
    kick_times: list[float] | None = None,
) -> List[NoteEvent]:
    """Long-sustain 808-style bass with a randomly selected rhythmic pattern per generation."""
    events: List[NoteEvent] = []
    prog_len = len(progression)
    beats_per_bar = 4

    # Pick a rhythmic pattern for this entire generation — this is the key source
    # of variation between regenerations. Low complexity favours simpler patterns.
    if complexity < 0.35:
        pattern = random.choice(_808_SIMPLE)
    elif complexity > 0.65:
        pattern = random.choice(_808_MULTI)
    else:
        pattern = random.choice(_808_PATTERNS)

    for bar in range(bars):
        roman = progression[bar % prog_len]
        pitches = roman_to_chord(roman, key, scale, octave=2)
        root = max(24, min(48, pitches[0]))
        bar_start = float(bar * beats_per_bar)

        # Two-bar variation: second bar of each pair may drop or add one hit
        bar_pattern = pattern
        if bar % 2 == 1:
            if len(bar_pattern) > 1 and should_trigger(0.35):
                bar_pattern = bar_pattern[:-1]          # drop last hit
            elif len(bar_pattern) == 1 and should_trigger(0.25):
                bar_pattern = bar_pattern + [(2.0, 0.84)]  # add simple mid-bar hit

        for i, (beat_offset, vel_scale) in enumerate(bar_pattern):
            t = _snap_to_kick(bar_start + beat_offset, kick_times)
            # Duration fills to next hit (or bar end) with a small gap
            if i + 1 < len(bar_pattern):
                next_t = bar_start + bar_pattern[i + 1][0]
            else:
                next_t = bar_start + beats_per_bar
            tail_factor = style.get("bass", {}).get("808_tail", 0.92)
            duration = (next_t - t) * tail_factor

            kick_boost = 8 if _on_kick(t, kick_times) else 0
            base_vel = 108 if i == 0 else 94
            vel = min(127, int(base_vel * vel_scale) + kick_boost + random.randint(-6, 6))
            events.append(NoteEvent(pitch=root, start=t, duration=duration, velocity=vel, channel=1))

    return [NoteEvent(e.pitch, max(0.0, e.start + micro_jitter()), e.duration, e.velocity, e.channel) for e in events]


def generate_bass(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
    progression: list | None = None,
    kick_times: list[float] | None = None,
    melody_rests: list | None = None,   # NEW: list of (start_beat, end_beat) tuples
) -> List[NoteEvent]:
    if progression is None:
        templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
        progression = random.choice(templates)

    bass_cfg = style.get("bass", {})

    if bass_cfg.get("bass_style") == "808":
        return _generate_808_bass(style, key, scale, bars, complexity, variation, progression, kick_times)

    if bass_cfg.get("bass_style") == "walking":
        return _generate_walking_bass(style, key, scale, bars, complexity, variation, progression, kick_times)

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
    # Match the chord generator's chord density: 2 chords/bar at high complexity
    chords_per_bar = 2 if complexity > 0.6 else 1
    beats_per_chord = beats_per_bar / chords_per_bar
    step_size = 0.5          # 8th note grid
    subdivisions = int(beats_per_chord / step_size)
    total_chords = bars * chords_per_bar
    prog_len = len(progression)

    for chord_idx in range(total_chords):
        roman = progression[chord_idx % prog_len]
        next_roman = progression[(chord_idx + 1) % prog_len]

        chord_pitches = roman_to_chord(roman, key, scale, octave=2)
        next_pitches = roman_to_chord(next_roman, key, scale, octave=2)

        root = chord_pitches[0]
        if should_trigger(octave_jump_prob):
            root += 12   # jump UP an octave for variety (was: down, which went below useful range)
        root = max(24, min(48, root))

        interval_third = chord_pitches[1] - chord_pitches[0] if len(chord_pitches) > 1 else 4
        third = max(24, min(52, root + interval_third))
        fifth = max(24, min(52, root + 7))

        next_root = max(24, min(48, next_pitches[0]))
        chord_start = chord_idx * beats_per_chord
        # two-bar pattern variation: second bar of each 2-bar phrase
        bar_in_pair = int(chord_start / beats_per_bar) % 2

        for step in range(subdivisions):
            beat = chord_start + step * step_size
            steps_to_next = subdivisions - 1 - step
            kick_boost = 10 if _on_kick(beat, kick_times) else 0

            if step == 0:
                # Always anchor on chord root at the start of each chord window
                dur = step_size * (3 if should_trigger(sustain_bias) else 1)
                # Don't sustain past the chord window
                dur = min(dur, beats_per_chord * 0.9)
                events.append(NoteEvent(
                    pitch=root, start=_swing(_snap_to_kick(beat, kick_times)), duration=dur * 0.9,
                    velocity=min(127, 92 + kick_boost + random.randint(-4, 4)), channel=1,
                ))

            elif steps_to_next == 0 and should_trigger(0.7):
                # Approach note into next chord root
                pitch = next_root if should_trigger(0.5) else _approach(root, next_root, 1)
                events.append(NoteEvent(
                    pitch=pitch, start=_swing(beat), duration=step_size * 0.8,
                    velocity=min(127, 76 + kick_boost + random.randint(-6, 6)), channel=1,
                ))

            elif steps_to_next == 1 and complexity > 0.5 and should_trigger(0.5):
                pitch = _approach(root, next_root, 2)
                events.append(NoteEvent(
                    pitch=pitch, start=_swing(beat), duration=step_size * 0.8,
                    velocity=min(127, 70 + kick_boost + random.randint(-6, 6)), channel=1,
                ))

            elif step == subdivisions // 2 and should_trigger(density):
                # Mid-chord hit: root, 3rd, or 5th — 3rd adds harmonic clarity (R&B/funk arch)
                pitch = random.choices([fifth, third, root], weights=[0.45, 0.35, 0.20])[0]
                dur = step_size * (2 if should_trigger(sustain_bias * 0.4) else 1)
                dur = min(dur, beats_per_chord * 0.5)
                events.append(NoteEvent(
                    pitch=pitch, start=_swing(beat), duration=dur * 0.9,
                    velocity=min(127, 80 + kick_boost + random.randint(-8, 8)), channel=1,
                ))

            elif step in (subdivisions // 4, subdivisions * 3 // 4) and complexity > 0.5 and should_trigger(density * 0.65):
                pitch = random.choice([root, fifth, third])
                events.append(NoteEvent(
                    pitch=pitch, start=_swing(beat), duration=step_size * 0.85,
                    velocity=min(127, 74 + kick_boost + random.randint(-8, 8)), channel=1,
                ))

            elif step not in (0, subdivisions // 2) and should_trigger(density * (0.4 + complexity * 0.3)):
                if should_trigger(sustain_bias * 0.5):
                    continue
                pitch = fifth if should_trigger(0.3) else root
                events.append(NoteEvent(
                    pitch=pitch, start=_swing(beat), duration=step_size * 0.75,
                    velocity=min(127, 66 + kick_boost + random.randint(-8, 8)), channel=1,
                ))

    # ── Call-response fills during melody rests ───────────────────────────────
    # When melody has a meaningful rest (>= 1.5 beats), bass answers with a
    # brief 2-note ascending figure (root → 5th) to fill the silence.
    if melody_rests:
        fill_events: List[NoteEvent] = []
        total_beats_inner = bars * beats_per_bar
        for rest_start, rest_end in melody_rests:
            rest_dur = rest_end - rest_start
            if rest_dur < 1.5 or rest_start >= total_beats_inner:
                continue
            if not should_trigger(0.48):
                continue
            c_idx = int(rest_start / beats_per_chord)
            fill_roman = progression[c_idx % prog_len]
            try:
                fill_pitches = roman_to_chord(fill_roman, key, scale, octave=3)
            except Exception:
                continue
            fill_root  = max(28, min(48, fill_pitches[0]))
            fill_fifth = max(28, min(52, fill_root + 7))
            for k, pitch in enumerate([fill_root, fill_fifth]):
                ft = rest_start + k * 0.5
                if ft + 0.35 <= rest_end and ft < total_beats_inner:
                    fill_events.append(NoteEvent(
                        pitch=pitch,
                        start=_swing(ft),
                        duration=0.36,
                        velocity=min(127, 74 + random.randint(-8, 8)),
                        channel=1,
                    ))
        events.extend(fill_events)

    return [NoteEvent(e.pitch, max(0.0, e.start + micro_jitter()), e.duration, e.velocity, e.channel) for e in events]
