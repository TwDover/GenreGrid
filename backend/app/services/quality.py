# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""
Generation quality scorer.

Each style's JSON encodes its canonical structure (kick_pattern, chord_rhythm,
melody density/range, bass density). We treat these as the "known-good reference"
and compare generated events against them across five dimensions.

Weights reflect musical priority:
  harmonic coherence  30 %  — do parts play compatible pitches?
  rhythm fit          23 %  — do rhythms match the style signature?
  register separation 16 %  — are parts in distinct frequency bands?
  melodic contour     10 %  — does the melody have shape and variety?
  density fit         11 %  — are note densities right for the style?
  mix balance         10 %  — are velocity levels proportionate?
"""
import math

from app.services.midi_writer import NoteEvent
from app.theory.chords import roman_to_chord
from app.theory.notes import note_name_to_midi
from app.core.constants import DRUM_MAP, DRUM_CHANNEL, SCALE_INTERVALS

_BEATS_PER_BAR = 4
_STEP = 0.25          # 16th note in beats
_KICK_PITCH = DRUM_MAP["kick"]   # 36
# Snare/clap land on the backbeat — the second-strongest groove signature after
# the kick. Match any of them so clap-driven styles score too.
_SNARE_PITCHES = {DRUM_MAP["snare"], DRUM_MAP["clap"], 40}


# ── helpers ──────────────────────────────────────────────────────────────────

def _scale_pcs(key: str, scale: str) -> set[int]:
    intervals = SCALE_INTERVALS.get(scale, SCALE_INTERVALS["minor"])
    root_pc = note_name_to_midi(key, 4) % 12
    return {(root_pc + iv) % 12 for iv in intervals}


def _build_chord_map(
    progression: list, key: str, scale: str, bars: int, complexity: float,
) -> list[tuple[float, float, set[int]]]:
    """Return (start_beat, end_beat, pitch_class_set) for every chord slot."""
    chords_per_bar = 2 if complexity > 0.6 else 1
    bpc = _BEATS_PER_BAR / chords_per_bar       # beats per chord
    total = bars * chords_per_bar
    prog_len = len(progression)
    result = []
    for i in range(total):
        roman = progression[i % prog_len]
        start = i * bpc
        end   = start + bpc
        try:
            pitches = roman_to_chord(roman, key, scale, octave=4,
                                     allow_7th=True, allow_9th=True)
            pcs = {p % 12 for p in pitches}
        except Exception:
            pcs = set()
        result.append((start, end, pcs))
    return result


def _chord_pcs_at(beat: float, chord_map: list) -> set[int]:
    for start, end, pcs in chord_map:
        if start <= beat < end:
            return pcs
    return chord_map[-1][2] if chord_map else set()


def _extract_16step(
    events: list[NoteEvent],
    pitch_filter: int | set[int] | None,
    bars: int,
    channel_filter: int | None = None,
) -> list[float]:
    """Normalised 16-step hit-density vector averaged over all bars.

    ``pitch_filter`` may be a single pitch, a set of pitches (any match), or None.
    """
    counts = [0.0] * 16
    is_set = isinstance(pitch_filter, set)
    for e in events:
        if channel_filter is not None and e.channel != channel_filter:
            continue
        if pitch_filter is not None:
            if is_set:
                if e.pitch not in pitch_filter:
                    continue
            elif e.pitch != pitch_filter:
                continue
        bar = int(e.start / _BEATS_PER_BAR)
        if bar >= bars:
            continue
        beat_in_bar = e.start - bar * _BEATS_PER_BAR
        step_i = round(beat_in_bar / _STEP)
        if 0 <= step_i < 16:
            counts[step_i] += 1.0

    total = sum(counts)
    if total == 0:
        return counts
    return [v / total for v in counts]


def _cosine(a: list[float], b: list[int | float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if len(a) != len(b):
        return 0.5
    dot  = sum(x * y for x, y in zip(a, b))
    ma   = math.sqrt(sum(x * x for x in a))
    mb   = math.sqrt(sum(y * y for y in b))
    if ma < 1e-9 or mb < 1e-9:
        return 0.5
    return dot / (ma * mb)


def _avg_pitch(events: list[NoteEvent]) -> float | None:
    if not events:
        return None
    return sum(e.pitch for e in events) / len(events)


def _avg_vel(events: list[NoteEvent]) -> float | None:
    if not events:
        return None
    return sum(e.velocity for e in events) / len(events)


# ── dimension scorers ─────────────────────────────────────────────────────────

def _harmonic_coherence(
    melody: list[NoteEvent],
    key: str, scale: str,
    chord_map: list,
) -> tuple[float, list[str]]:
    """Duration-weighted ratio of melody notes that are chord/scale tones."""
    if not melody:
        return 0.65, []          # no melody — mild neutral

    spcs = _scale_pcs(key, scale)
    w_total = w_consonant = 0.0

    for n in melody:
        pc   = n.pitch % 12
        cpcs = _chord_pcs_at(n.start, chord_map)
        w    = min(n.duration, 2.0)          # weight by duration, capped at 2 beats
        w_total += w

        if pc in cpcs:
            w_consonant += w * 1.00          # chord tone — best
        elif pc in spcs:
            w_consonant += w * 0.86          # in-key scale tone — good (passing notes are normal)
        else:
            w_consonant += w * 0.50          # chromatic / outside — blue notes and passing tones are musically intentional

    score = w_consonant / w_total if w_total else 0.65
    flags = []
    if score < 0.52:
        flags.append("Melody clashes heavily with chords — many non-scale tones")
    elif score < 0.68:
        flags.append("Melody has notable dissonance against chord tones")
    return min(1.0, score), flags


def _melodic_contour(melody: list[NoteEvent]) -> tuple[float, list[str]]:
    """Reward melodies with genuine shape — a line can be perfectly consonant
    yet lifeless (one repeated note, or a monotonic ramp). Harmonic coherence
    can't catch that, so contour scores interval/direction/pitch variety.
    """
    if len(melody) < 4:
        return 0.70, []          # too short to judge — mild neutral

    notes    = sorted(melody, key=lambda e: e.start)
    pitches  = [n.pitch for n in notes]
    intervals = [pitches[i + 1] - pitches[i] for i in range(len(pitches) - 1)]
    n = len(intervals)

    repeats = sum(1 for iv in intervals if iv == 0) / n            # same note again
    leaps   = sum(1 for iv in intervals if abs(iv) > 7) / n        # wider than a 5th

    dirs = [1 if iv > 0 else -1 for iv in intervals if iv != 0]
    changes = sum(1 for i in range(1, len(dirs)) if dirs[i] != dirs[i - 1])
    change_ratio = changes / max(1, len(dirs) - 1)                 # contour undulation

    variety = len(set(pitches)) / len(pitches)                    # distinct-pitch ratio
    span    = max(pitches) - min(pitches)                         # semitone spread

    # Sub-scores with musical sweet spots
    s_rep  = 1.0 - min(1.0, max(0.0, repeats - 0.15) / 0.50)      # fine ≤15% repeats
    s_leap = 1.0 - min(1.0, max(0.0, leaps - 0.20) / 0.45)        # fine ≤20% big leaps
    if change_ratio < 0.15:
        s_dir = 0.40                                              # monotonic ramp
    elif change_ratio > 0.80:
        s_dir = 0.55                                              # zig-zag / noisy
    else:
        s_dir = 1.0
    s_var  = min(1.0, variety / 0.60)                            # 60%+ distinct = full
    s_span = min(1.0, span / 12.0)                               # an octave of range = full

    score = s_rep * 0.28 + s_leap * 0.18 + s_dir * 0.24 + s_var * 0.18 + s_span * 0.12

    flags = []
    if repeats > 0.50:
        flags.append("Melody repeats the same note too often — static contour")
    if change_ratio < 0.15:
        flags.append("Melody moves in one direction with little shape")
    if variety < 0.30:
        flags.append("Melody uses very few distinct pitches")
    return min(1.0, score), flags


def _register_separation(
    melody: list[NoteEvent],
    chords: list[NoteEvent],
    bass:   list[NoteEvent],
) -> tuple[float, list[str]]:
    """Parts should occupy distinct registers: melody > chords > bass."""
    flags  = []
    scores = []

    m_avg = _avg_pitch(melody)
    c_avg = _avg_pitch(chords)
    b_avg = _avg_pitch(bass)

    if m_avg is not None and c_avg is not None:
        gap = m_avg - c_avg       # semitones melody above chords
        # Score 1.0 at gap ≥ 12, green (0.82) at gap ≥ 7, fades to 0 below 0.
        s = max(0.0, min(1.0, 0.2 + gap * 0.07))
        scores.append(s)
        if gap < 0:
            flags.append("Melody sits below chord voicings — register overlap")
        elif gap < 3:
            flags.append("Melody and chords are too close in register")

    if c_avg is not None and b_avg is not None:
        gap = c_avg - b_avg       # semitones chords above bass
        # Score 1.0 at gap ≥ 15, green (0.82) at gap ≥ 10, fades to 0 below −5.
        # Cinematic/orchestral styles naturally have a gap of 10–12 semitones.
        s = max(0.0, min(1.0, (gap + 5) / 20.0))
        scores.append(s)
        if gap < 4:
            flags.append("Chords and bass are in the same register")

    return (sum(scores) / len(scores) if scores else 0.65), flags


def _rhythm_fit(
    drums:  list[NoteEvent],
    chords: list[NoteEvent],
    style:  dict,
    bars:   int,
) -> tuple[float, list[str]]:
    """Cosine similarity between generated and style-canonical rhythm patterns."""
    drum_cfg = style.get("drums", {})
    flags    = []
    scores   = []

    # Kick pattern
    ref_kick = drum_cfg.get("kick_pattern")
    if ref_kick and drums:
        gen_kick = _extract_16step(drums, _KICK_PITCH, bars, DRUM_CHANNEL)
        s = _cosine(gen_kick, ref_kick)
        scores.append(s)
        if s < 0.45:
            flags.append("Kick pattern diverges from style signature")

    # Snare/clap backbeat — build a reference from the style's snare_standard_beats
    # (1-indexed beats, e.g. [2, 4]) and compare where the generated backbeat lands.
    ref_beats = drum_cfg.get("snare_standard_beats")
    if ref_beats and drums:
        ref_snare = [0.0] * 16
        for b in ref_beats:
            idx = int(round((b - 1) * 4))
            if 0 <= idx < 16:
                ref_snare[idx] = 1.0
        if any(ref_snare):
            gen_snare = _extract_16step(drums, _SNARE_PITCHES, bars, DRUM_CHANNEL)
            s = _cosine(gen_snare, ref_snare)
            scores.append(s)
            if s < 0.45:
                flags.append("Snare backbeat doesn't sit where the style expects")

    # Chord comping rhythm
    ref_chord = style.get("chord_rhythm")
    if ref_chord and chords:
        gen_chord = _extract_16step(chords, None, bars, channel_filter=0)
        s = _cosine(gen_chord, ref_chord)
        scores.append(s)
        if s < 0.38:
            flags.append("Chord rhythm doesn't match style comping pattern")

    if not scores:
        return 0.85, []           # no reference patterns — can't penalise
    return sum(scores) / len(scores), flags


def _density_fit(
    melody:     list[NoteEvent],
    bass:       list[NoteEvent],
    style:      dict,
    bars:       int,
    complexity: float = 0.5,
) -> tuple[float, list[str]]:
    """Compare notes-per-beat against style-expected density targets.

    The style JSON ``density`` field is a probability-per-16th-note-step (0–1).
    ``actual`` is measured in notes-per-beat, so the target must be converted:
      target_notes_per_beat ≈ density × complexity_scale × steps_per_beat / avg_dur_steps

    steps_per_beat = 4 (16th notes); avg_dur_steps ≈ 1.65 (weighted average of
    the generator's duration distribution); combined factor ≈ 2.4 → use 2.5 for
    a slight upward bias that matches empirical generator output.

    Bass generators always place a root note (and usually an approach note)
    regardless of pattern_density, so the effective bass rate has a fixed
    baseline added on top of the density-driven hits.
    """
    total_beats = bars * _BEATS_PER_BAR
    if total_beats == 0:
        return 0.65, []

    mel_cfg  = style.get("melody", {})
    bass_cfg = style.get("bass",   {})
    flags    = []
    scores   = []

    complexity_scale = 0.8 + 0.4 * complexity

    # Melody — density is probability/step; convert to notes/beat
    # Under-density uses a softer 0.40 coefficient because 8-bar arrangements have a
    # 2-bar drums-only intro, so melody only plays in 6/8 bars (actual/target ≈ 0.75).
    if melody:
        actual = len(melody) / total_beats
        target = mel_cfg.get("density", 0.5) * complexity_scale * 2.5
        target = max(0.05, target)
        ratio  = actual / target
        if ratio < 1.0:
            s = max(0.0, 1.0 - (1.0 - ratio) * 0.40)
        else:
            s = max(0.0, 1.0 - (ratio - 1.0) * 0.60)
        scores.append(s)
        if ratio < 0.25:
            flags.append("Melody is much sparser than expected for this style")
        elif ratio > 3.0:
            flags.append("Melody is much denser than expected for this style")

    # Bass — always-placed notes (root + approach) create a baseline above pattern_density
    if bass:
        actual = len(bass) / total_beats
        target = 0.35 + bass_cfg.get("pattern_density", 0.5) * 0.70
        target = max(0.05, target)
        ratio  = actual / target
        # Asymmetric penalty: under-density is a real concern (0.35), but over-density is
        # often caused by call-response fills and pattern variation which are musically good.
        # Over-density uses a softer 0.20 coefficient so fill-heavy generations don't fail.
        if ratio < 1.0:
            s = max(0.0, 1.0 - (1.0 - ratio) * 0.35)
        else:
            s = max(0.0, 1.0 - (ratio - 1.0) * 0.20)
        scores.append(s)
        if ratio < 0.20:
            flags.append("Bass is much sparser than expected")
        elif ratio > 4.0:
            flags.append("Bass is much denser than expected")

    return (sum(scores) / len(scores) if scores else 0.65), flags


def _mix_balance(
    melody: list[NoteEvent],
    chords: list[NoteEvent],
    bass:   list[NoteEvent],
) -> tuple[float, list[str]]:
    """Check velocity ratios match a natural mix hierarchy."""
    m_vel = _avg_vel(melody)
    c_vel = _avg_vel(chords)
    b_vel = _avg_vel(bass)
    flags  = []
    scores = []

    if m_vel is not None and c_vel is not None and c_vel > 0:
        r = m_vel / c_vel
        # beat_velocity applies 0.62–0.78× reduction to off-beat melody notes while
        # chords don't use beat_velocity — so the melody/chord ratio naturally sits
        # at 0.40–0.65 even in a perfectly balanced mix, especially for styles with
        # vel_arc_start (orchestral, cinematic) or heavy syncopation.
        # Threshold 0.30: below that, melody is genuinely inaudible vs chords.
        # Formula scores green (0.82) at r ≈ 0.43; caps at 1.0 for r ≥ 0.58.
        if r < 0.30:
            flags.append("Chords overpower melody — mix sounds cluttered")
            scores.append(0.35)
        elif r > 2.0:
            flags.append("Melody velocity is too dominant")
            scores.append(0.55)
        else:
            scores.append(min(1.0, 0.30 + r * 1.20))

    if b_vel is not None and c_vel is not None and c_vel > 0:
        r = b_vel / c_vel
        # Ideal: bass 0.9–1.5× chords; allow up to 2.5× for styles that build
        # gradually (vel_arc_start) or use 808/sub-bass which is naturally louder.
        if r < 0.55:
            flags.append("Bass is very quiet relative to chords")
            scores.append(0.40)
        elif r > 2.5:
            flags.append("Bass overpowers the mid-range")
            scores.append(0.45)
        else:
            scores.append(0.88)

    return (sum(scores) / len(scores) if scores else 0.70), flags


# ── pattern extraction (also used by the library) ────────────────────────────

def extract_rhythm_patterns(all_events: dict, bars: int) -> dict:
    """Extract normalised 16-step kick and chord patterns from generated events.

    Returns a dict with ``kick_pattern`` and ``chord_pattern`` lists (length 16,
    each value 0–1), suitable for storing in the generation library and for
    blending into future scoring references.
    """
    drums  = all_events.get("drums",  [])
    chords = all_events.get("chords", [])
    return {
        "kick_pattern":  _extract_16step(drums,  _KICK_PITCH, bars, DRUM_CHANNEL),
        "chord_pattern": _extract_16step(chords, None,        bars, channel_filter=0),
    }


# ── public API ────────────────────────────────────────────────────────────────

def score_generation(
    all_events:  dict[str, list[NoteEvent]],
    style:       dict,
    key:         str,
    scale:       str,
    bars:        int,
    progression: list,
    complexity:  float,
) -> dict:
    """
    Score a generation across five musical dimensions.

    Returns:
        total     — weighted composite (0–1)
        harmonic  — chord-tone alignment
        register  — register separation between parts
        rhythm    — match to style's canonical kick/chord patterns
        contour   — melodic shape / interval & pitch variety
        density   — notes-per-beat vs style targets
        mix       — velocity balance
        label     — "Excellent" | "Good" | "Fair" | "Weak"
        flags     — list of human-readable issue descriptions
    """
    melody = all_events.get("melody", [])
    chords = all_events.get("chords", [])
    bass   = all_events.get("bass",   [])
    drums  = all_events.get("drums",  [])

    chord_map = _build_chord_map(progression, key, scale, bars, complexity)

    s_harm,   f_harm   = _harmonic_coherence(melody, key, scale, chord_map)
    s_reg,    f_reg    = _register_separation(melody, chords, bass)
    s_rhythm, f_rhythm = _rhythm_fit(drums, chords, style, bars)
    s_cont,   f_cont   = _melodic_contour(melody)
    s_dens,   f_dens   = _density_fit(melody, bass, style, bars, complexity)
    s_mix,    f_mix    = _mix_balance(melody, chords, bass)

    total = (
        s_harm   * 0.30 +
        s_reg    * 0.16 +
        s_rhythm * 0.23 +
        s_cont   * 0.10 +
        s_dens   * 0.11 +
        s_mix    * 0.10
    )

    if total >= 0.82:
        label = "Excellent"
    elif total >= 0.68:
        label = "Good"
    elif total >= 0.52:
        label = "Fair"
    else:
        label = "Weak"

    return {
        "total":    round(total,    3),
        "harmonic": round(s_harm,   3),
        "register": round(s_reg,    3),
        "rhythm":   round(s_rhythm, 3),
        "contour":  round(s_cont,   3),
        "density":  round(s_dens,   3),
        "mix":      round(s_mix,    3),
        "label":    label,
        "flags":    f_harm + f_reg + f_rhythm + f_cont + f_dens + f_mix,
    }
