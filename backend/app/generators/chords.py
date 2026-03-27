import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.chords import roman_to_chord
from app.services.variation import should_trigger
from app.services.humanize import timing_jitter, velocity_arc, phrase_breath_factor
from app.theory.rhythm import apply_swing


def _apply_inversion(pitches: list[int], inversion: int) -> list[int]:
    result = sorted(pitches)
    for _ in range(inversion % max(1, len(result))):
        result = sorted(result[1:] + [result[0] + 12])
    return result


def _movement_score(pitches: list[int], prev_pitches: list[int]) -> float:
    """Sum of each new pitch's distance to its nearest previous pitch."""
    return sum(min(abs(p - q) for q in prev_pitches) for p in pitches)


def _voice_lead(pitches: list[int], prev_pitches: list[int]) -> list[int]:
    """Return the inversion of pitches that minimizes total movement from prev_pitches.

    Uses a 2-key score: (total_movement, -shared_pitch_classes). When two voicings
    cost equal movement, the one retaining more common tones (guide tones) wins.
    """
    if not prev_pitches:
        return sorted(pitches)

    prev_pcs = {q % 12 for q in prev_pitches}

    def _score(candidate: list[int]) -> tuple[float, int]:
        move_cost = _movement_score(candidate, prev_pitches)
        common = sum(1 for p in candidate if p % 12 in prev_pcs)
        return (move_cost, -common)  # minimize movement, maximize common pitch classes

    best = sorted(pitches)
    best_score = _score(best)

    for inv in range(len(pitches)):
        candidate = _apply_inversion(pitches, inv)
        for top_shift in (0, 12, -12):
            variant = candidate[:-1] + [candidate[-1] + top_shift]
            s = _score(variant)
            if s < best_score:
                best = variant
                best_score = s

    return best


def _clamp_register(pitches: list[int], low: int = 55, high: int = 84) -> list[int]:
    """Shift the entire voicing by octaves until it fits within [low, high]."""
    s = sorted(pitches)
    while s[0] < low and s[-1] + 12 <= 127:
        s = [p + 12 for p in s]
    while s[-1] > high and s[0] - 12 >= 0:
        s = [p - 12 for p in s]
    return s


def _drop_2(pitches: list[int]) -> list[int]:
    """Drop the second-highest note an octave for a more open jazz voicing."""
    if len(pitches) < 4:
        return pitches
    s = sorted(pitches)
    s[-2] -= 12
    return sorted(s)


def _apply_substitution(roman: str, scale: str, complexity: float, secondary_dominants: bool = False, tritone_sub: bool = False) -> str:
    """Probabilistic harmonic color substitutions at higher complexity."""
    if complexity < 0.4 or not should_trigger(0.25):
        return roman
    # Borrow iv from parallel minor when in a major-family scale (darker color)
    if roman == 'IV' and scale in ('major', 'mixolydian', 'lydian', 'pentatonic_major'):
        return 'iv'
    # Raise v to V in minor context: secondary dominant with leading-tone pull
    if roman == 'v' and scale in ('minor', 'dorian', 'phrygian', 'pentatonic_minor'):
        return 'V'
    if secondary_dominants and complexity > 0.45:
        if roman == 'ii' and scale in ('major', 'mixolydian') and should_trigger(0.40):
            return 'II'   # ii → V/V
        if roman == 'vi' and scale in ('major', 'mixolydian') and should_trigger(0.30):
            return 'VI'   # vi → V/ii
        if roman == 'iii' and scale in ('major',) and should_trigger(0.20):
            return 'III'  # iii → V/vi
    # Tritone substitution: V → bII (descends by half-step into I, rich chromatic bass motion)
    if tritone_sub and roman == 'V' and complexity > 0.5 and should_trigger(0.25):
        return 'bII'
    return roman


def resolve_progression(progression: list, scale: str, complexity: float, secondary_dominants: bool = False, tritone_sub: bool = False) -> list:
    """Pre-apply substitutions once so chords and melody share identical harmony.

    Call this in the route before generating chords/melody, then pass the result as
    ``resolved_progression`` to ``generate_chords`` and as ``progression`` to
    ``generate_melody``.  Both generators will then target the same chord tones.
    """
    return [_apply_substitution(roman, scale, complexity, secondary_dominants, tritone_sub) for roman in progression]


def _is_dominant(roman: str) -> bool:
    """Return True if roman is a dominant V or a raised secondary dominant (II, III, VI)."""
    s = roman.lstrip("b#")
    for suffix in ("m7b5", "mM7", "dim7", "maj7", "9sus4", "7sus4", "sus2", "sus4", "add11", "add9", "aug", "dim", "m6", "m9", "6", "9"):
        if s.lower().endswith(suffix):
            s = s[: -len(suffix)]
            break
    return s in ("V", "II", "III", "VI")


def generate_chords(
    style: dict,
    key: str,
    scale: str,
    bars: int,
    complexity: float,
    variation: float,
    progression: list | None = None,
    resolved_progression: list | None = None,
    melody_ceiling: int | None = None,
) -> List[NoteEvent]:
    events: List[NoteEvent] = []
    if progression is None:
        templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
        progression = random.choice(templates)

    # Use pre-resolved progression when provided so chords and melody stay in sync.
    # Otherwise apply substitutions per-chord internally (legacy / standalone behaviour).
    prog_source = resolved_progression if resolved_progression is not None else None
    prog_len = len(resolved_progression if resolved_progression is not None else progression)

    ext = style.get("chord_extensions", {})
    allow_7th_prob = ext.get("allow_7th", 0.3)
    allow_9th_prob = ext.get("allow_9th", 0.1)
    swing_amount = style.get("drums", {}).get("swing", 0.0)

    altered_dominant_prob = style.get("altered_dominant_prob", 0.0)
    # Strum timing: seconds per string. Slow styles (lofi/soul) ~20ms, tight styles (funk/jazz) ~5-8ms.
    # Stored as beats; converts to real time at runtime based on BPM (handled by sequencer/DAW).
    strum_speed = style.get("strum_speed", 0.010)

    # Staccato factor: shorten note durations for styles that want sharp articulation.
    # Only applies when duration is computed from chord_rhythm steps (not comp_duration_override).
    staccato_factor = style.get("staccato_factor", 1.0)

    # Register: lower by default to leave headroom for melody above.
    # Styles that use high-register pads can override via "chord_register".
    ch_low, ch_high = style.get("chord_register", [48, 72])

    # Keep chord voicings below the melody's range so they don't fight for the same register
    if melody_ceiling is not None:
        ch_high = min(ch_high, melody_ceiling - 1)
        ch_low  = min(ch_low, ch_high - 12)  # ensure at least an octave of range

    # comp_style overrides chord_rhythm with a curated comping pattern
    comp_style = style.get("comp_style")
    # fmt: off
    _COMP_RHYTHMS = {
        # Jazz: sparse syncopated — "and of 1", beat 2, "and of 3", beat 4
        "jazz_comp":   [0,0,0,1,0,1,0,0,0,0,0,1,0,1,0,0],
        # Bossa nova: 1, "and of 2", "and of 3", beat 4 — classic Brazilian comp
        "bossa_comp":  [1,0,0,0,0,1,0,0,0,0,1,0,0,0,1,0],
        # Funk: tight stabs with anticipations
        "funk_stab":   [1,0,1,0,0,1,0,1,0,1,0,0,1,0,0,1],
        # Lofi: lazy strum on 1 and late upbeat
        "lofi_strum":  [1,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0],
        # Pad: hold — single hit per bar
        "pad_hold":    [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
        # House: offbeat 8th-note stabs
        "house_stab":  [0,0,1,0,0,0,1,0,0,0,1,0,0,0,1,0],
        # Synthwave: quarter-note gated stabs
        "synth_gate":  [1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0],
    }
    # fmt: on
    chord_rhythm = _COMP_RHYTHMS.get(comp_style) if comp_style else style.get("chord_rhythm")

    # Comp style also affects note duration
    _COMP_DURATIONS = {
        "jazz_comp":   0.38,   # punchy jazz comping
        "bossa_comp":  0.48,   # slightly rounder bossa feel
        "funk_stab":   0.38,   # tight staccato
        "lofi_strum":  None,   # auto (fill to next hit)
        "pad_hold":    3.80,   # long sustain
        "house_stab":  0.42,   # offbeat 8th-note stabs
        "synth_gate":  0.20,   # very short = gated synth
    }
    comp_duration_override = _COMP_DURATIONS.get(comp_style) if comp_style else None

    # Open voicing: jazz/soul/lofi occasionally drop an inner voice for a sparser sound
    open_voicing_prob = style.get("open_voicing_prob", 0.0)
    drop_2_prob = style.get("drop_2_prob", 0.0)
    passing_chord_prob = style.get("passing_chord_prob", 0.0)
    turnaround_prob = style.get("turnaround_prob", 0.0)

    vel_arc_start = style.get("vel_arc_start", 0.75)
    velocity_base = style.get("velocity_base", 74)

    def _styled_arc(bar: int, total: int, base: int, start: float) -> int:
        t = bar / max(1, total - 1)
        return max(1, min(127, int(base * (start + (1.0 - start) * t))))

    beats_per_bar = 4
    phrase_beats = beats_per_bar * 4  # 4-bar phrase = 16 beats
    chords_per_bar = 2 if complexity > 0.6 else 1
    beats_per_chord = beats_per_bar / chords_per_bar
    total_chords = bars * chords_per_bar
    step = 0.25  # 16th note
    ticks_per_beat = 480

    def _swing(beat: float) -> float:
        if swing_amount < 0.01:
            return beat
        tick = int(beat * ticks_per_beat)
        return apply_swing(tick, swing_amount, ticks_per_beat) / ticks_per_beat

    prev_pitches: list[int] = []  # tracks the sounded voicing for voice leading

    for i in range(total_chords):
        if prog_source is not None:
            roman = prog_source[i % prog_len]
        else:
            roman = _apply_substitution(progression[i % prog_len], scale, complexity)
        allow_7th = should_trigger(allow_7th_prob)
        allow_9th = should_trigger(allow_9th_prob) if allow_7th else False
        pitches = roman_to_chord(roman, key, scale, octave=4, allow_7th=allow_7th, allow_9th=allow_9th)

        # Altered dominant: on V / secondary dominant chords, substitute a b9, #9, or b13
        if altered_dominant_prob > 0 and _is_dominant(roman) and allow_7th and should_trigger(altered_dominant_prob):
            chord_root = pitches[0]
            alt_interval = random.choice([13, 15, 20])  # b9, #9, b13
            # Remove natural 9th if present, then add the alteration
            pitches = [p for p in pitches if p != chord_root + 14]
            pitches.append(chord_root + alt_interval)

        if prev_pitches:
            pitches = _voice_lead(pitches, prev_pitches)
        else:
            pitches = sorted(pitches)

        pitches = _clamp_register(pitches, low=ch_low, high=ch_high)

        # Open voicing: drop an inner voice occasionally for an airy jazz/acoustic feel
        sounded = sorted(pitches)
        if open_voicing_prob > 0 and len(sounded) >= 4 and should_trigger(open_voicing_prob):
            # Remove one middle voice (index 1 or 2), keep root and top
            drop_idx = random.randint(1, len(sounded) - 2)
            sounded = sounded[:drop_idx] + sounded[drop_idx + 1:]
        pitches = sounded

        # Drop-2 voicing: drop second-highest note an octave (jazz open voicing)
        if drop_2_prob > 0 and len(pitches) >= 4 and should_trigger(drop_2_prob):
            pitches = _drop_2(pitches)
            pitches = _clamp_register(pitches, low=ch_low, high=ch_high)

        prev_pitches = sorted(pitches)  # record the clamped (sounded) voicing

        start_beat = i * beats_per_chord
        bar_num = int(start_beat / beats_per_bar)
        is_downbeat = (start_beat % beats_per_bar) < 0.01
        base_vel = _styled_arc(bar_num, bars, velocity_base, vel_arc_start)
        base_vel = int(base_vel * phrase_breath_factor(bar_num))
        vel = (base_vel + 6 if is_downbeat else base_vel) + random.randint(-5, 5)

        # Chromatic passing chord: brief half-step approach to this chord root, fired 0.25 beats before downbeat
        if i > 0 and passing_chord_prob > 0 and (start_beat % beats_per_bar) < 0.01 and should_trigger(passing_chord_prob):
            approach_start = start_beat - 0.25
            if approach_start >= 0:
                chord_root_midi = roman_to_chord(roman, key, scale, octave=4)[0]
                approach_root = chord_root_midi - 1   # half-step below
                for p in [approach_root, approach_root + 7]:   # root + fifth dyad
                    # Clamp passing chord notes to the same register ceiling as regular chords
                    clamped_p = p
                    while clamped_p > ch_high and clamped_p - 12 >= 0:
                        clamped_p -= 12
                    events.append(NoteEvent(
                        pitch=min(127, max(0, clamped_p)),
                        start=max(0.0, _swing(approach_start) + timing_jitter(0.010)),
                        duration=0.18,
                        velocity=max(1, min(127, vel - 28)),
                        channel=0,
                    ))

        # Turnaround: detect last-chord slot of a 4-bar phrase and replace with ii-V
        phrase_pos = start_beat % phrase_beats if phrase_beats > 0 else 0
        is_last_phrase_chord = (
            turnaround_prob > 0
            and phrase_beats > 0
            and (phrase_pos + beats_per_chord >= phrase_beats)
            and start_beat > 0
            and should_trigger(turnaround_prob)
        )

        if is_last_phrase_chord:
            ta_scale_is_minor = scale in ("minor", "phrygian", "locrian", "pentatonic_minor")
            ta_chords = ["iim7b5", "V"] if ta_scale_is_minor else ["ii", "V"]
            ta_dur = beats_per_chord / 2.0
            for ta_i, ta_roman in enumerate(ta_chords):
                ta_start = start_beat + ta_i * ta_dur
                ta_pitches = roman_to_chord(ta_roman, key, scale, octave=4, allow_7th=True)
                if prev_pitches:
                    ta_pitches = _voice_lead(ta_pitches, prev_pitches)
                else:
                    ta_pitches = sorted(ta_pitches)
                ta_pitches = _clamp_register(ta_pitches, low=ch_low, high=ch_high)
                prev_pitches = sorted(ta_pitches)
                ta_vel = vel - random.randint(2, 8)
                for note_idx, pitch in enumerate(sorted(ta_pitches)):
                    events.append(NoteEvent(
                        pitch=min(127, max(0, pitch)),
                        start=max(0.0, _swing(ta_start) + timing_jitter(0.012) + note_idx * strum_speed),
                        duration=min(ta_dur * 0.75, 1.5),
                        velocity=max(1, min(127, ta_vel)),
                        channel=0,
                    ))
        else:
            if chord_rhythm:
                num_steps = int(beats_per_chord / step)
                bar_offset = start_beat % beats_per_bar
                base_idx = int(bar_offset / step)

                # Pre-compute which steps have hits so we can calculate sustain to next hit
                hit_steps = [
                    s for s in range(num_steps)
                    if chord_rhythm[(base_idx + s) % len(chord_rhythm)]
                ]

                # Guarantee a hit on the downbeat of each bar (step 0 when bar_offset < step)
                # so the chord always sounds at the bar start even in sparse comp rhythms
                if bar_offset < step and 0 not in hit_steps:
                    hit_steps = [0] + hit_steps

                sorted_pitches = sorted(pitches)
                n = len(sorted_pitches)

                for hi, s in enumerate(hit_steps):
                    # Hold until the next hit (or end of the chord window), then leave a small gap
                    steps_to_next = (hit_steps[hi + 1] - s) if hi + 1 < len(hit_steps) else (num_steps - s)
                    if comp_duration_override is not None:
                        duration = comp_duration_override
                    else:
                        duration = max(step * 0.8, steps_to_next * step * 0.92)
                        if staccato_factor < 1.0:
                            duration = max(step * 0.5, duration * staccato_factor)

                    hit_start = _swing(start_beat + s * step) + timing_jitter(0.015)
                    hit_vel = vel - random.randint(0, 10)
                    sorted_pitches_hit = sorted(pitches)
                    n_hit = len(sorted_pitches_hit)
                    for note_idx, pitch in enumerate(sorted_pitches_hit):
                        # Lower notes slightly louder, upper notes softer — natural strum taper
                        strum_vel_offset = int((n_hit - 1 - note_idx) * 5)
                        # Strum timing: each note arrives slightly after the previous (simulates strum)
                        strum_time = note_idx * strum_speed
                        events.append(NoteEvent(
                            pitch=min(127, max(0, pitch)),
                            start=max(0.0, hit_start + strum_time),
                            duration=duration,
                            velocity=max(1, min(127, hit_vel + strum_vel_offset)),
                            channel=0,
                        ))
            else:
                duration = comp_duration_override if comp_duration_override is not None else beats_per_chord * 0.95
                if comp_duration_override is None and staccato_factor < 1.0:
                    duration = max(step * 0.5, duration * staccato_factor)
                jitter = timing_jitter(0.015)
                sorted_pitches = sorted(pitches)
                n = len(sorted_pitches)
                for note_idx, pitch in enumerate(sorted_pitches):
                    strum_vel_off = int((n - 1 - note_idx) * 5)
                    strum_time = note_idx * 0.010
                    events.append(NoteEvent(
                        pitch=min(127, max(0, pitch)),
                        start=max(0.0, _swing(start_beat) + jitter + strum_time),
                        duration=duration,
                        velocity=max(1, min(127, vel + strum_vel_off)),
                        channel=0,
                    ))

    return events
