# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
import random
from typing import List

from app.services.midi_writer import NoteEvent
from app.theory.scales import build_scale, scale_mode
from app.theory.chords import roman_to_chord
from app.theory.notes import note_name_to_midi
from app.services.variation import should_trigger
from app.services.humanize import beat_velocity, timing_jitter, velocity_arc, micro_jitter, phrase_breath_factor, style_jitter, style_velocity_variation
from app.theory.rhythm import apply_swing
from app.theory.phrase_plan import plan_phrases


def _trill_events(note: NoteEvent, trill_pitch: int, vel_variation: int = 4) -> List[NoteEvent]:
    """Expand a long note into a trill (rapid alternation between note.pitch and trill_pitch)."""
    step = 0.125   # 32nd note
    n_steps = max(4, int(note.duration / step))
    result = []
    for k in range(n_steps):
        p = trill_pitch if k % 2 == 1 else note.pitch
        t = note.start + k * step
        remaining = note.duration - k * step
        if remaining < 0.02:
            break
        dur = min(step * 0.88, remaining)
        vel = note.velocity if k == 0 else max(1, min(127, note.velocity - 12 + random.randint(-vel_variation, vel_variation)))
        result.append(NoteEvent(p, t, dur, vel, note.channel))
    return result


def _chord_tone_indices(roman: str, key: str, scale: str, scale_notes: list) -> list:
    """Return indices into scale_notes whose pitch class matches a chord tone."""
    chord_pitches = {p % 12 for p in roman_to_chord(roman, key, scale, octave=4)}
    return [i for i, n in enumerate(scale_notes) if n % 12 in chord_pitches]


def _secondary_dominant_color(roman: str, key: str, active_scale: list[int],
                              scale: str = "major") -> list[int]:
    """Return active_scale extended with the raised 3rd of any secondary dominant chord.

    In MAJOR keys, uppercase II, III, and VI are non-diatonic secondary dominants
    (V/V, V/vi, V/ii) whose chromatically raised 3rd acts as a leading tone into
    the target chord — adding that pitch class gives the melody the option to use
    the characteristic color note. In MINOR keys the same numerals are the
    ordinary diatonic III/VI/VII-family chords (i–VI–III–VII progressions live on
    them), so treating them as secondary dominants injected wrong chromatic
    notes (C# and G# in a C-minor melody) — minor-family scales return unchanged.
    For all other chord types, returns active_scale unchanged.
    """
    if scale_mode(scale) != "major":
        return active_scale
    s = roman.lstrip("b#")
    for suffix in ("mM7", "m7b5", "dim7", "maj7", "9sus4", "7sus4",
                   "sus2", "sus4", "add11", "add9", "aug", "dim", "m6", "m9", "6", "9", "7"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    if s not in ("II", "III", "VI"):
        return active_scale
    try:
        pitches = roman_to_chord(roman, key, "major", octave=4)
        color_pc = pitches[1] % 12 if len(pitches) > 1 else None
    except Exception:
        return active_scale
    if color_pc is None:
        return active_scale
    lo, hi = active_scale[0], active_scale[-1]
    extras = [n for n in range(lo - 12, hi + 13) if n % 12 == color_pc and lo <= n <= hi]
    if not extras:
        return active_scale
    return sorted(set(active_scale) | set(extras))


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
    is_loop: bool = False,
    melody_model: dict | None = None,
    harmony_complexity: float | None = None,
    seed_motif: list[int] | None = None,
) -> List[NoteEvent]:
    """`melody_model` — optional mined melody prior (interval/phrase-bigram stats).

    When supplied, the free-motion connecting notes follow the corpus's real
    interval contour instead of the hand-coded stepwise/leap heuristic; chord-tone
    placement on downbeats and cadences is untouched, so harmony stays intact.

    `harmony_complexity` — the complexity value used by `generate_chords`/`generate_bass`
    for this same section. The chords-per-bar grid is derived from it (falling back to
    `complexity` when omitted) so melody's chord-change timing can't drift out of sync
    with the actual sounding harmony when a section profile scales melody and backing
    complexity differently.

    `seed_motif` — scale-step intervals of a motif from an earlier section (e.g. the
    verse's opening phrase). When provided, this melody develops that motif instead of
    inventing an unrelated one, so a song's chorus feels like it grew out of its verse.
    """
    events: List[NoteEvent] = []
    _mined_prev_iv: int | None = None
    if melody_model is not None:
        from app.services.priors import (
            sample_melody_interval as _sample_mel_iv,
            sample_melody_duration as _sample_mel_dur,
        )
    mel_cfg = style.get("melody", {})
    trill_prob = mel_cfg.get("trill_prob", 0.0)
    run_prob   = mel_cfg.get("run_prob", 0.0)
    bebop_run_prob = mel_cfg.get("bebop_run_prob", 0.0)

    if progression is None:
        templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
        progression = random.choice(templates)

    swing_amount = style.get("drums", {}).get("swing", 0.0)
    syncopation_prob = style.get("syncopation_prob", mel_cfg.get("syncopation_prob", 0.0))
    phrase_anticipation_prob = mel_cfg.get("phrase_anticipation_prob", style.get("phrase_anticipation_prob", 0.0))
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

    # Extended scale for climactic phrases: up one octave higher
    phrase_climax_prob = mel_cfg.get("phrase_climax_prob", 0.0)
    note_range_hi = [note_range[0], min(96, note_range[1] + 12)]
    scale_notes_hi = [n for n in build_scale(key, mel_scale, octave_start=4, num_octaves=3)
                      if note_range_hi[0] <= n <= note_range_hi[1]]
    if not scale_notes_hi:
        scale_notes_hi = scale_notes

    # Active scale and phrase register tracking
    active_scale = scale_notes
    use_hi_register = False
    current_phrase_idx = -1

    beats_per_bar = 4
    step = 0.25  # 16th notes
    _harmony_cplx = complexity if harmony_complexity is None else harmony_complexity
    chords_per_bar = 2 if _harmony_cplx > 0.6 else 1
    beats_per_chord = beats_per_bar / chords_per_bar
    prog_len = len(progression)
    total_beats = bars * beats_per_bar
    phrase_beats = beats_per_bar * 4  # 4-bar phrases

    # Phrase architecture: every phrase gets a role (statement/contrast/climax/...)
    # from a form grammar BEFORE any notes exist. The plan decides each phrase's
    # contour peak, register target, density, cadence, and motif restatement --
    # the note-level logic below fills the phrases in.
    _num_phrases = max(1, int((total_beats + phrase_beats - 1) // phrase_beats))
    _plans = plan_phrases(_num_phrases)

    current_note_idx = len(scale_notes) // 2  # always start in the normal (low) register
    _prev_pitch: int | None = None     # anti-repetition tracking
    _rep_count: int = 0
    _last_interval: int = 0            # signed interval in scale steps for post-leap enforcement

    # Motif development: seed motif intervals extracted from the first phrase —
    # or handed in from an earlier section so the melody develops the song's theme.
    _motif_seeded = bool(seed_motif)
    _motif_intervals: list[int] = list(seed_motif) if seed_motif else []
    _motif_locked = _motif_seeded       # True once the seed phrase is complete

    # Generate raw notes for all bars
    raw: List[NoteEvent] = []
    beat = 0.0
    while beat < total_beats - step:
        bar_num = int(beat / beats_per_bar)
        beat_in_phrase = beat % phrase_beats
        is_phrase_start = beat > 0.5 and beat_in_phrase < step

        # Switch registers at phrase boundaries: the PLANNED climax phrase gets
        # the high octave (styles opt in via phrase_climax_prob); every phrase
        # glides toward its planned register target so the section has shape.
        phrase_idx = int(beat / phrase_beats)
        plan = _plans[min(phrase_idx, len(_plans) - 1)]
        if phrase_idx != current_phrase_idx:
            current_phrase_idx = phrase_idx
            use_hi_register = plan.climax and phrase_climax_prob > 0
            new_scale = scale_notes_hi if use_hi_register else scale_notes
            if new_scale is not active_scale:
                # Re-anchor index to the nearest pitch in the new scale
                cur_pitch = active_scale[current_note_idx] if active_scale else 60
                active_scale = new_scale
                current_note_idx = min(range(len(active_scale)), key=lambda i: abs(active_scale[i] - cur_pitch))
            # Glide halfway toward the phrase's register target
            _reg_target = int(plan.register * (len(active_scale) - 1))
            current_note_idx = (current_note_idx + _reg_target) // 2
        is_cadence_bar = beat_in_phrase >= phrase_beats - beats_per_bar  # last bar of phrase
        is_phrase_tail = beat_in_phrase >= phrase_beats - 1.0  # last beat of phrase
        # Call/response: "question" = before the phrase's planned contour peak
        is_question = (beat_in_phrase / phrase_beats) < plan.contour_peak
        is_response_tail = beat_in_phrase >= phrase_beats - beats_per_bar * 1.5

        # Motif development: lock seed motif after first phrase, replay at subsequent phrase starts
        if is_phrase_start and phrase_idx > 0:
            # Lock the motif after the first phrase
            if not _motif_locked and phrase_idx == 1 and len(raw) >= 3:
                pitches = [e.pitch for e in raw if e.start < phrase_beats]
                if len(pitches) >= 2:
                    _motif_intervals = []
                    for k in range(min(4, len(pitches) - 1)):
                        p_cur = pitches[k]
                        p_nxt = pitches[k + 1]
                        try:
                            i_cur = active_scale.index(min(active_scale, key=lambda n: abs(n - p_cur)))
                            i_nxt = active_scale.index(min(active_scale, key=lambda n: abs(n - p_nxt)))
                            _motif_intervals.append(i_nxt - i_cur)
                        except Exception:
                            pass
                _motif_locked = True

            # Replay the motif when this phrase's ROLE calls for restatement
            # (a seeded song-level theme replays at least that often).
            _replay_p = max(plan.replay_motif, 0.55 if _motif_seeded else 0.0)
            if _motif_locked and _motif_intervals and _replay_p > 0:
                if should_trigger(_replay_p):
                    for interval in _motif_intervals:
                        new_idx = max(0, min(len(active_scale) - 1, current_note_idx + interval))
                        current_note_idx = new_idx

        # Phrase start: anticipate by an 8th note ("and of 4") or take a breath
        phrase_anticipation = 0.0
        if is_phrase_start:
            if phrase_anticipation_prob > 0 and should_trigger(phrase_anticipation_prob):
                phrase_anticipation = -0.5   # push first note to "and of beat 4"
            elif should_trigger(0.30):
                beat += step * random.choice([1, 2])
                continue

        chord_idx = int(beat / beats_per_chord)
        current_roman = progression[chord_idx % prog_len]
        beat_in_chord = beat - chord_idx * beats_per_chord

        # Chord-scale pool: extend active_scale with secondary-dominant color notes
        # (major keys only — see _secondary_dominant_color). The pool is used
        # transiently for stepwise motion; current_note_idx always indexes
        # active_scale, and _color_pitch carries a pool-only color tone for
        # this iteration's sounded note when motion passes through one.
        chord_pool = _secondary_dominant_color(current_roman, key, active_scale, scale)
        _color_pitch: int | None = None

        # Phrase tail: hold on a long cadential note then rest
        if is_phrase_tail:
            ct = _chord_tone_indices(current_roman, key, scale, active_scale)
            # The PLAN decides open (half cadence: sd2/sd5) vs closed (tonic).
            # In loop mode the very last phrase always resolves so the loop-back
            # sounds clean (the planner also forces the section's last phrase closed).
            is_last_phrase = (beat + phrase_beats - beat_in_phrase >= total_beats)
            is_antecedent = plan.cadence_open and not (is_loop and is_last_phrase)
            if is_antecedent:
                # Open cadence: scale degree 2 (maj 2nd above root) or scale degree 5 (perf 5th)
                open_pcs = {(key_root_pc + 2) % 12, (key_root_pc + 7) % 12}
                open_candidates = [i for i, n in enumerate(active_scale) if n % 12 in open_pcs]
                if open_candidates:
                    current_note_idx = min(open_candidates, key=lambda i: abs(i - current_note_idx))
                elif ct:
                    current_note_idx = ct[-1]  # fallback: highest chord tone = open feel
            else:
                # Closed cadence: tonic (sd1)
                tonic_candidates = [i for i, n in enumerate(active_scale) if n % 12 == key_root_pc]
                if tonic_candidates:
                    current_note_idx = min(tonic_candidates, key=lambda i: abs(i - current_note_idx))
                elif ct:
                    current_note_idx = ct[0]  # fallback: root-ish chord tone
            pitch = active_scale[current_note_idx]
            remaining = phrase_beats - beat_in_phrase
            dur = max(step, remaining * 0.85)
            base_vel = _styled_arc(bar_num, bars, velocity_base, vel_arc_start)
            base_vel = _phrase_vel_arc(beat_in_phrase, phrase_beats, base_vel)
            base_vel = int(base_vel * phrase_breath_factor(bar_num))
            vel = beat_velocity(beat, base_vel)
            raw.append(NoteEvent(
                pitch=pitch,
                start=max(0.0, _swing(beat) + timing_jitter(style_jitter(style))),
                duration=min(dur, total_beats - beat),
                velocity=vel,
                channel=2,
            ))
            # Skip to start of next phrase
            beat = (int(beat / phrase_beats) + 1) * phrase_beats
            continue

        # Cadence bar: reduce density for breathing room, strong chord-tone bias.
        # The phrase's planned density multiplier shapes the section (sparser
        # contrast phrases, busier climax).
        effective_density = density * plan.density_mult * (0.72 if is_cadence_bar else 1.0)
        if not should_trigger(effective_density):
            beat += step
            continue

        is_chord_downbeat = beat_in_chord < step
        is_strong_beat = (beat % 1.0) < step

        # Syncopation: anticipate strong beats by an 8th or 16th note (lands early = ahead of beat)
        sync_offset = 0.0
        if syncopation_prob > 0 and is_strong_beat and beat > 0.5 and should_trigger(syncopation_prob):
            sync_offset = -random.choice([0.25, 0.5])
        chord_tone_prob = 0.85 if is_cadence_bar else (0.65 if is_chord_downbeat else 0.35)

        # Call/response: response half resolves strongly to chord tones, root bias
        if is_response_tail:
            chord_tone_prob = min(0.92, chord_tone_prob + 0.25)

        if (is_chord_downbeat or is_cadence_bar) and should_trigger(chord_tone_prob):
            ct = _chord_tone_indices(current_roman, key, scale, active_scale)
            if ct:
                # In response half, prefer lower (root-ish) chord tones for resolution
                if is_response_tail and len(ct) > 1:
                    current_note_idx = ct[0]
                    _last_interval = 0
                else:
                    current_note_idx = min(ct, key=lambda i: abs(i - current_note_idx))
                    _last_interval = 0
        elif is_strong_beat and should_trigger(0.35):
            ct = _chord_tone_indices(current_roman, key, scale, active_scale)
            if ct:
                current_note_idx = min(ct, key=lambda i: abs(i - current_note_idx))
                _last_interval = 0
        elif melody_model is not None and len(active_scale) > 2:
            # Data-driven contour: sample a semitone interval from the mined model
            # and snap to the nearest scale tone (harmony stays chord-locked above).
            iv = _sample_mel_iv(melody_model, _mined_prev_iv, random)
            if iv is not None:
                target = active_scale[min(current_note_idx, len(active_scale) - 1)] + iv
                current_note_idx = min(range(len(active_scale)),
                                       key=lambda i: abs(active_scale[i] - target))
                _mined_prev_iv = iv
                _last_interval = 0
        else:
            if should_trigger(stepwise) and len(chord_pool) > 2:
                range_frac  = current_note_idx / max(1, len(active_scale) - 1)
                phrase_pos  = beat_in_phrase / phrase_beats  # 0.0 → 1.0 through the phrase

                # Range extremes override everything to pull back toward center
                # (the climax phrase is allowed to sit near the top)
                if range_frac > (0.94 if plan.climax else 0.8):
                    d_weights = [0.85, 0.15]
                elif range_frac < 0.2:
                    d_weights = [0.15, 0.85]
                else:
                    # Arch contour around the phrase's PLANNED peak: rise into
                    # it, hover near it, resolve downward after.
                    _peak = plan.contour_peak
                    if phrase_pos < _peak - 0.08:
                        d_weights = [0.32, 0.68]   # rising toward the peak
                    elif phrase_pos > _peak + 0.12:
                        d_weights = [0.72, 0.28]   # resolving after the peak
                    else:
                        d_weights = [0.5, 0.5]     # hovering at the peak

                direction = random.choices([-1, 1], weights=d_weights)[0]
                # Post-leap rule: after a leap larger than a 4th (>2 scale steps),
                # force the next motion in the opposite direction
                if abs(_last_interval) >= 3 and direction == (1 if _last_interval > 0 else -1):
                    direction = -direction
                # Walk in chord-pool space so motion can pass THROUGH a
                # secondary-dominant color tone, but re-anchor current_note_idx
                # to active_scale afterwards: the two lists have different
                # lengths when color extras exist, and reading a scale index
                # straight out of the pool shifted every note above an inserted
                # extra by one slot — chord-tone targeting would aim at Eb and
                # sound D.
                _cur_pitch = active_scale[min(current_note_idx, len(active_scale) - 1)]
                _pool_idx = min(range(len(chord_pool)), key=lambda i: abs(chord_pool[i] - _cur_pitch))
                next_idx = max(0, min(len(chord_pool) - 1, _pool_idx + direction))
                # Avoid augmented 2nds (3 semitones between adjacent scale steps) —
                # common in harmonic minor / phrygian. Skip the problematic step.
                if (next_idx != _pool_idx and
                        abs(chord_pool[next_idx] - chord_pool[_pool_idx]) == 3):
                    next_idx = max(0, min(len(chord_pool) - 1, next_idx + direction))
                _stepped = chord_pool[next_idx]
                current_note_idx = min(range(len(active_scale)),
                                       key=lambda i: abs(active_scale[i] - _stepped))
                if _stepped != active_scale[current_note_idx]:
                    _color_pitch = _stepped   # sound the color tone this note only
                _last_interval = direction
            elif should_trigger(leap_prob) and len(chord_pool) > 4:
                # Leaps in question half go upward; in response half go downward
                if is_question:
                    leap = random.choice([2, 3])
                else:
                    leap = random.choice([-3, -2])
                current_note_idx = max(0, min(len(active_scale) - 1, current_note_idx + leap))
                _last_interval = leap

        # Reserve the top of the range for the climax phrase: everything else
        # gets a soft ceiling, so the section's high point lands where planned.
        if not plan.climax:
            _ceiling = int((len(active_scale) - 1) * 0.82)
            if current_note_idx > _ceiling:
                current_note_idx = _ceiling
                _color_pitch = None

        pitch = (_color_pitch if _color_pitch is not None
                 else active_scale[min(current_note_idx, len(active_scale) - 1)])

        # Anti-repetition: no more than 2 consecutive identical pitches
        if pitch == _prev_pitch:
            _rep_count += 1
            if _rep_count >= 2:
                step_dir = 1 if current_note_idx < len(active_scale) // 2 else -1
                current_note_idx = max(0, min(len(active_scale) - 1, current_note_idx + step_dir))
                pitch = active_scale[min(current_note_idx, len(active_scale) - 1)]
                _rep_count = 0
        else:
            _rep_count = 0
        _prev_pitch = pitch

        # Blue notes: occasional chromatic inflection (b3, b5, b7)
        if blue_notes and should_trigger(0.18):
            pitch = _blue_note(pitch, key_root_pc, 1.0)
            active_range = note_range_hi if use_hi_register else note_range
            pitch = max(active_range[0], min(active_range[1], pitch))

        # Chord tones landing on chord downbeats get longer values — structural arrivals ring out
        _chord_pcs = {p % 12 for p in roman_to_chord(current_roman, key, scale, octave=4)}
        _is_structural = is_chord_downbeat and (pitch % 12) in _chord_pcs
        # Data-driven note rhythm: sample the duration from the corpus's real
        # duration distribution when a melody prior is present.
        _md = _sample_mel_dur(melody_model, random) if melody_model is not None else None
        if _md is not None:
            dur_steps = _md
        elif _is_structural:
            dur_steps = random.choices([1, 2, 3, 4], weights=[0.15, 0.38, 0.32, 0.15])[0]
        elif density < 0.45:
            dur_steps = random.choices([1, 2, 3, 4], weights=[0.35, 0.38, 0.18, 0.09])[0]
        else:
            dur_steps = random.choices([1, 2, 3, 4], weights=[0.48, 0.35, 0.13, 0.04])[0]
        # Articulation: longer notes get higher legato factor so they don't sound clipped
        legato = 0.88 if dur_steps <= 2 else 0.94
        duration = min(dur_steps * step * legato, total_beats - beat)
        base_vel = _styled_arc(bar_num, bars, velocity_base, vel_arc_start)
        base_vel = _phrase_vel_arc(beat_in_phrase, phrase_beats, base_vel)
        base_vel = int(base_vel * phrase_breath_factor(bar_num))
        vel = beat_velocity(beat, base_vel)
        jitter = timing_jitter(style_jitter(style))

        # Grace note: add before chord-tone arrivals on downbeats in expressive styles
        if grace_notes and is_chord_downbeat and is_strong_beat and should_trigger(0.22):
            ct = _chord_tone_indices(current_roman, key, scale, active_scale)
            if current_note_idx in ct:
                _add_grace_note(raw, pitch, max(0.0, _swing(beat) + jitter), vel, channel=2)

        raw.append(NoteEvent(
            pitch=pitch,
            start=max(0.0, _swing(beat) + jitter + sync_offset + phrase_anticipation),
            duration=duration,
            velocity=vel,
            channel=2,
        ))
        beat += dur_steps * step

    # ── Trill expansion ──────────────────────────────────────────────────────
    if trill_prob > 0:
        expanded: List[NoteEvent] = []
        for note in raw:
            if note.duration > 1.5 and should_trigger(trill_prob):
                # Trill up to the next scale tone
                idx = next((i for i, n in enumerate(scale_notes) if n == note.pitch), -1)
                if idx >= 0 and idx + 1 < len(scale_notes):
                    trill_pitch = scale_notes[idx + 1]
                    expanded.extend(_trill_events(note, trill_pitch, style_velocity_variation(style)))
                    continue
            expanded.append(note)
        raw = expanded

    # ── Descending bebop runs ─────────────────────────────────────────────────
    # Replace long notes on downbeats with 4-note descending scale runs.
    # Chord tones land on the downbeat (first note), passing tones on upbeats —
    # the characteristic bebop rhythm that makes jazz lines swing.
    if bebop_run_prob > 0:
        bebop_expanded: List[NoteEvent] = []
        for note in raw:
            beat_in_bar = round(note.start % 4, 3)
            is_strong = beat_in_bar < 0.06 or abs(beat_in_bar - 2.0) < 0.06
            if is_strong and note.duration >= 0.9 and should_trigger(bebop_run_prob):
                idx = next((i for i, n in enumerate(scale_notes) if n == note.pitch), -1)
                if idx >= 3:
                    run_dur = 0.25  # 16th notes
                    for k in range(4):
                        rp = scale_notes[idx - k]
                        rt = note.start + k * run_dur
                        if rt < note.start + note.duration and rt < total_beats:
                            rv = max(1, min(127, note.velocity - k * 5))
                            bebop_expanded.append(
                                NoteEvent(rp, rt, run_dur * 0.82, rv, note.channel)
                            )
                    continue
            bebop_expanded.append(note)
        raw = bebop_expanded

    # ── Approach runs ─────────────────────────────────────────────────────────
    if run_prob > 0:
        # Build a set of beat positions already occupied so we don't collide
        occupied: set[float] = {round(n.start, 3) for n in raw}
        run_notes: List[NoteEvent] = []
        beats_per_bar_inner = 4
        for note in raw:
            # Only add runs before chord-downbeat notes on strong beats
            beat_in_bar = round(note.start % beats_per_bar_inner, 3)
            if beat_in_bar > 0.05 and abs(beat_in_bar - 2.0) > 0.05:
                continue
            if not should_trigger(run_prob):
                continue
            # 3-note ascending scale run leading into this note
            idx = next((i for i, n in enumerate(scale_notes) if n == note.pitch), -1)
            if idx < 3:
                continue
            run_start = note.start - 0.75
            if run_start < 0:
                continue
            conflict = any(abs(t - (run_start + k * 0.25)) < 0.12 for k in range(3) for t in occupied)
            if conflict:
                continue
            for k in range(3):
                rp = scale_notes[idx - (3 - k)]
                rt = run_start + k * 0.25
                rv = max(1, min(127, note.velocity - 18 + k * 5))
                run_notes.append(NoteEvent(rp, rt, 0.20, rv, note.channel))
        raw = raw + run_notes

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

        # Recapitulation: the final block restates the opening motif (exact or
        # lightly pitch-shifted) so the phrase returns to its theme to close.
        is_last_block = block == num_blocks - 1

        # The phrase PLAN outranks block-level motif development: climax blocks
        # always keep their phrase-shaped content (that's the planned high point),
        # and elsewhere transforms apply only about half the time so motif unity
        # doesn't erase the planned contour. The final block's recapitulation is
        # exempt — restating the theme to close is part of the form.
        blk_plan = _plans[min((block * 2) // 4, len(_plans) - 1)]
        if not is_last_block and (blk_plan.climax or random.random() < 0.45):
            final.extend(existing)
            continue
        roll = random.uniform(0.0, 0.45) if (is_last_block and num_blocks > 2) else random.random()
        if roll < 0.27:
            # Exact repeat with velocity shift + per-note micro-jitter
            vel_shift = random.randint(-8, 8)
            for n in motif:
                t = b_start + (n.start % block_beats) + micro_jitter()
                if t < total_beats:
                    final.append(NoteEvent(n.pitch, max(0.0, t), min(n.duration, total_beats - t),
                                           max(1, min(127, n.velocity + vel_shift + random.randint(-3, 3))), n.channel))
        elif roll < 0.48:
            # Pitch-shifted repeat (capped below the climax's reserved top
            # unless this block IS the climax)
            _blk_top = scale_notes[-1] if blk_plan.climax else scale_notes[int(0.82 * (len(scale_notes) - 1))]
            shift = random.choice([-5, -4, -3, -2, 2, 3, 4, 5])
            for n in motif:
                shifted = min(n.pitch + shift, _blk_top)
                if note_range[0] <= shifted <= note_range[1] and scale_notes:
                    new_p = min(scale_notes, key=lambda s: abs(s - shifted))
                    t = b_start + (n.start % block_beats) + micro_jitter()
                    if t < total_beats:
                        final.append(NoteEvent(new_p, max(0.0, t), min(n.duration, total_beats - t),
                                               max(1, min(127, n.velocity + random.randint(-3, 3))), n.channel))
        elif roll < 0.62:
            # Fragmentation: only first half of motif
            half = block_beats / 2
            frag = [n for n in motif if n.start % block_beats < half]
            vel_shift = random.randint(-5, 5)
            for n in frag:
                t = b_start + (n.start % block_beats) + micro_jitter()
                if t < total_beats:
                    final.append(NoteEvent(n.pitch, max(0.0, t), min(n.duration, total_beats - t),
                                           max(1, min(127, n.velocity + vel_shift + random.randint(-3, 3))), n.channel))
        elif roll < 0.76:
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
                        t = b_start + (n.start % block_beats) + micro_jitter()
                        if t < total_beats:
                            final.append(NoteEvent(new_p, max(0.0, t), min(n.duration, total_beats - t),
                                                   max(1, min(127, n.velocity + random.randint(-3, 3))), n.channel))
        elif roll < 0.91:
            # Diatonic sequence: transpose motif by a diatonic 3rd or 5th,
            # snapping each note to the nearest scale tone. Most common real-world
            # compositional development technique.
            shift_steps = random.choice([-5, -3, -2, 2, 3, 5])  # scale steps
            _vel_var = style_velocity_variation(style)
            vel_shift = random.randint(-_vel_var, _vel_var)
            _blk_ceil = (len(scale_notes) - 1) if blk_plan.climax else int(0.82 * (len(scale_notes) - 1))
            for n in motif:
                idx = min(range(len(scale_notes)), key=lambda i: abs(scale_notes[i] - n.pitch))
                new_idx = max(0, min(_blk_ceil, idx + shift_steps))
                new_p = scale_notes[new_idx]
                if note_range[0] <= new_p <= note_range[1]:
                    t = b_start + (n.start % block_beats) + micro_jitter()
                    if t < total_beats:
                        final.append(NoteEvent(
                            new_p, max(0.0, t), min(n.duration, total_beats - t),
                            max(1, min(127, n.velocity + vel_shift + random.randint(-3, 3))),
                            n.channel,
                        ))
        else:
            final.extend(existing)

    # Post-process: enforce max-2-consecutive-same-pitch across full output
    # (motif copies at block boundaries can create longer runs). The variation
    # pitch moves to the NEIGHBOURING SCALE TONE — a raw ±1 semitone here
    # planted out-of-key notes (a third consecutive Eb in C minor became an
    # E natural grinding against the Eb in the chords).
    out: List[NoteEvent] = []
    _pp_prev: int | None = None
    _pp_count: int = 0
    for note in sorted(final, key=lambda n: n.start):
        if note.pitch == _pp_prev:
            _pp_count += 1
            if _pp_count >= 2:
                _sn_idx = min(range(len(scale_notes)), key=lambda i: abs(scale_notes[i] - note.pitch))
                if note.pitch < note_range[1] and _sn_idx + 1 < len(scale_notes):
                    new_p = scale_notes[_sn_idx + 1]
                elif _sn_idx > 0:
                    new_p = scale_notes[_sn_idx - 1]
                else:
                    new_p = note.pitch
                out.append(NoteEvent(new_p, note.start, note.duration, note.velocity, note.channel))
                _pp_prev = new_p
                _pp_count = 0
                continue
        else:
            _pp_count = 0
        out.append(note)
        _pp_prev = note.pitch
    return out
