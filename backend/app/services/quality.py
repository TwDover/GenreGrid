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
from app.core.meter import Meter, DEFAULT_METER, backbeat_beats

_BEATS_PER_BAR = 4    # 4/4 fallback for callers that don't know their meter
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
    meter: Meter = DEFAULT_METER,
) -> list[tuple[float, float, set[int]]]:
    """Return (start_beat, end_beat, pitch_class_set) for every chord slot."""
    chords_per_bar = 2 if complexity > 0.6 else 1
    bpc = meter.bar_beats / chords_per_bar      # beats per chord
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


def _build_chord_map_from_sections(
    sections: list[dict], key: str, scale: str,
) -> list[tuple[float, float, set[int]]]:
    """Chord map built from the harmony each section actually played.

    `_build_chord_map` tiles the *raw* progression across the whole generation at
    one global chord rate. That is not what sounds: `resolve_progression` swaps in
    7ths/9ths, secondary dominants, and tritone subs per section; a chorus can sit
    in a lifted key; and choruses raise the chord rate to two per bar. Scoring a
    melody built on those chords against the pre-substitution template penalised
    exactly the attempts that used the harmony features, so the search preferred
    the blandest option available.

    Each section supplies `offset`, `bars`, `key`, `bar_beats`, `chords_per_bar`,
    and its resolved `romans` (see services.generation._run_attempt).
    """
    result: list[tuple[float, float, set[int]]] = []
    for sec in sections:
        romans = sec.get("romans") or []
        if not romans:
            continue
        cpb       = max(1, int(sec.get("chords_per_bar", 1)))
        bar_beats = float(sec.get("bar_beats", _BEATS_PER_BAR))
        offset    = float(sec.get("offset", 0.0))
        sec_key   = sec.get("key") or key       # chorus-lift sections resolve in a shifted key
        bpc       = bar_beats / cpb
        for i in range(int(sec.get("bars", 0)) * cpb):
            roman = romans[i % len(romans)]
            start = offset + i * bpc
            try:
                pitches = roman_to_chord(roman, sec_key, scale, octave=4,
                                         allow_7th=True, allow_9th=True)
                pcs = {p % 12 for p in pitches}
            except Exception:
                pcs = set()
            result.append((start, start + bpc, pcs))
    result.sort(key=lambda slot: slot[0])
    return result


def _chord_pcs_at(beat: float, chord_map: list) -> set[int]:
    for start, end, pcs in chord_map:
        if start <= beat < end:
            return pcs
    return chord_map[-1][2] if chord_map else set()


def _extract_steps(
    events: list[NoteEvent],
    pitch_filter: int | set[int] | None,
    bars: int,
    channel_filter: int | None = None,
    meter: Meter = DEFAULT_METER,
) -> list[float]:
    """Normalised 16th-step hit-density vector averaged over all bars.

    The vector is one bar long *in this meter* — 16 steps in 4/4, 12 in 3/4 and
    6/8, 14 in 7/8. Folding events onto a fixed 16-step grid smeared every
    non-4/4 bar across the wrong slots (bar 2 of a 3/4 groove started at beat 3,
    which the 4/4 grid called step 12 of bar 0), which is what collapsed the
    rhythm dimension to noise in every meter but 4/4.

    ``pitch_filter`` may be a single pitch, a set of pitches (any match), or None.
    """
    n_steps = meter.steps_per_bar
    counts = [0.0] * n_steps
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
        bar = int(e.start / meter.bar_beats)
        if bar >= bars:
            continue
        beat_in_bar = e.start - bar * meter.bar_beats
        step_i = round(beat_in_bar / _STEP)
        if 0 <= step_i < n_steps:
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


def _fit_reference(ref: list, n_steps: int, wrap: bool) -> list[float]:
    """Refit a 16-step 4/4 reference pattern onto an ``n_steps`` bar.

    ``kick_pattern`` and ``chord_rhythm`` are hand-authored 16-step 4/4 vectors,
    but the generators don't refuse to play them in another meter — they reindex
    them, and the scorer has to expect what was actually played. The drum
    generator keeps pattern entries whose position falls inside the bar and adds
    nothing past the pattern's end (``i * step < beats_per_bar``), so its
    reference truncates and zero-pads. The chord generator indexes modulo the
    pattern length, so its reference tiles. Both are identity at 16 steps, which
    is why 4/4 scores are untouched.
    """
    if wrap:
        return [float(ref[i % len(ref)]) for i in range(n_steps)]
    return [float(ref[i]) if i < len(ref) else 0.0 for i in range(n_steps)]


def _rhythm_fit(
    drums:  list[NoteEvent],
    chords: list[NoteEvent],
    style:  dict,
    bars:   int,
    meter:  Meter = DEFAULT_METER,
) -> tuple[float, list[str]]:
    """Cosine similarity between generated and style-canonical rhythm patterns.

    Every reference is refit to this meter's bar before comparison — the step
    patterns through ``_fit_reference`` (the generators' own reindexing rule) and
    the backbeat through ``backbeat_beats`` (the drum generator's own felt-pulse
    placement). Comparing a 3/4 bar against an unmodified 16-step 4/4 vector was
    what pinned the rhythm dimension at 0.51 in every meter but 4/4.
    """
    drum_cfg = style.get("drums", {})
    flags    = []
    scores   = []
    n_steps  = meter.steps_per_bar

    # Kick pattern
    ref_kick = drum_cfg.get("kick_pattern")
    if ref_kick and drums:
        ref_kick = _fit_reference(ref_kick, n_steps, wrap=False)
        gen_kick = _extract_steps(drums, _KICK_PITCH, bars, DRUM_CHANNEL, meter)
        s = _cosine(gen_kick, ref_kick)
        scores.append(s)
        if s < 0.45:
            flags.append("Kick pattern diverges from style signature")

    # Snare/clap backbeat — build a reference from the style's snare_standard_beats
    # (1-indexed beats, e.g. [2, 4]) and compare where the generated backbeat lands.
    ref_beats = drum_cfg.get("snare_standard_beats")
    if ref_beats and drums:
        ref_snare = [0.0] * n_steps
        for b in backbeat_beats(meter, ref_beats):
            idx = int(round((b - 1) * 4))
            if 0 <= idx < n_steps:
                ref_snare[idx] = 1.0
        if any(ref_snare):
            gen_snare = _extract_steps(drums, _SNARE_PITCHES, bars, DRUM_CHANNEL, meter)
            s = _cosine(gen_snare, ref_snare)
            scores.append(s)
            if s < 0.45:
                flags.append("Snare backbeat doesn't sit where the style expects")

    # Chord comping rhythm
    ref_chord = style.get("chord_rhythm")
    if ref_chord and chords:
        ref_chord = _fit_reference(ref_chord, n_steps, wrap=True)
        gen_chord = _extract_steps(chords, None, bars, channel_filter=0, meter=meter)
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
    meter:      Meter = DEFAULT_METER,
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
    total_beats = bars * meter.bar_beats
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


def _hook_score(chorus_melody: list[NoteEvent],
                meter: Meter = DEFAULT_METER) -> tuple[float | None, list[str]]:
    """How *memorable* the chorus melody is. Correctness scorers (coherence,
    contour, …) can pass a chorus that's valid but forgettable. A hook is
    catchy because it's *compressible*: a rhythmic figure that repeats across
    bars, a small pitch vocabulary, and a melodic motif that recurs.

    Returns ``(None, [])`` when there's no chorus melody to judge (too few
    notes) so styles/sections without a chorus aren't scored on this dimension.

    Sub-scores:
      (a) onset self-similarity — mean pairwise cosine of the per-bar 16-step
          onset vectors. High = the bars share a rhythmic figure (the hook).
      (b) pitch-class economy — distinct pitch-class count, best in a 3–6
          sweet spot; fewer is monotonous, more resists memorisation.
      (c) motif repetition — share of notes covered by a repeated interval
          trigram (the tune restates a shape rather than wandering).
    """
    if len(chorus_melody) < 8:
        return None, []

    from collections import Counter

    notes   = sorted(chorus_melody, key=lambda e: e.start)
    pitches = [n.pitch for n in notes]

    # (a) per-bar onset self-similarity — bars are this meter's bars, so a 6/8
    # hook is compared bar-to-bar rather than every-4-quarter-beats.
    n_steps = meter.steps_per_bar
    bar_vecs: dict[int, list[float]] = {}
    for n in notes:
        b   = int(n.start // meter.bar_beats)
        vec = bar_vecs.setdefault(b, [0.0] * n_steps)
        step = round((n.start - b * meter.bar_beats) / _STEP)
        if 0 <= step < n_steps:
            vec[step] += 1.0
    active = [v for v in bar_vecs.values() if sum(v) > 0]
    if len(active) >= 2:
        sims = [_cosine(active[i], active[j])
                for i in range(len(active)) for j in range(i + 1, len(active))]
        s_selfsim = sum(sims) / len(sims)
    else:
        s_selfsim = 0.5                       # single-bar chorus — can't judge repetition

    # (b) pitch-class economy — sweet spot 3–6 distinct classes
    n_pcs = len({p % 12 for p in pitches})
    if 3 <= n_pcs <= 6:
        s_pcs = 1.0
    elif n_pcs < 3:
        s_pcs = 0.55                          # one or two notes — droning, not a tune
    else:
        s_pcs = max(0.0, 1.0 - (n_pcs - 6) * 0.12)

    # (c) motif repetition — notes covered by a repeated interval trigram
    intervals = [pitches[i + 1] - pitches[i] for i in range(len(pitches) - 1)]
    N = 3
    grams  = [tuple(intervals[i:i + N]) for i in range(len(intervals) - N + 1)]
    counts = Counter(grams)
    covered: set[int] = set()
    for i, g in enumerate(grams):
        if counts[g] >= 2:
            covered.update(range(i, i + N + 1))   # trigram spans N+1 pitches
    motif_ratio = len(covered) / len(pitches)
    s_motif = min(1.0, motif_ratio / 0.5)     # 50% coverage = full marks

    score = s_selfsim * 0.40 + s_pcs * 0.25 + s_motif * 0.35

    flags = []
    if s_selfsim < 0.35:
        flags.append("Chorus bars don't share a rhythmic figure — no hook")
    if n_pcs > 8:
        flags.append("Chorus melody uses too many pitches to be catchy")
    return min(1.0, score), flags


# ── pattern extraction (also used by the library) ────────────────────────────

def extract_rhythm_patterns(all_events: dict, bars: int,
                            meter: Meter = DEFAULT_METER) -> dict:
    """Extract normalised per-bar kick and chord patterns from generated events.

    Returns a dict with ``kick_pattern`` and ``chord_pattern`` lists (one bar of
    16th steps in this meter — 16 entries in 4/4, each value 0–1), suitable for
    storing in the generation library and for blending into future scoring
    references. The library only blends length-16 patterns back in, since the
    style JSON references it blends *with* are 4/4 (see library._get_learned_patterns).
    """
    drums  = all_events.get("drums",  [])
    chords = all_events.get("chords", [])
    return {
        "kick_pattern":  _extract_steps(drums,  _KICK_PITCH, bars, DRUM_CHANNEL, meter),
        "chord_pattern": _extract_steps(chords, None, bars, channel_filter=0, meter=meter),
    }


def _style_match(progression: list, melody: list[NoteEvent], style: dict) -> tuple[float | None, list[str]]:
    """How closely the generation matches the genre's *mined* distribution.

    Only applies when a corpus prior exists for the style: rewards chord
    transitions the genre actually uses and a melodic-interval profile close to
    the genre's. Returns (None, []) when there's no prior, so styles without one
    aren't scored on this dimension.
    """
    from app.services.priors import load_prior
    name = style.get("prior") or style.get("id", "")
    prior = load_prior(name)
    if not prior:
        return None, []

    scores: list[float] = []

    # Harmony: fraction of chord transitions present in the genre's bigram model.
    harmony = prior.get("harmony", {})
    bigram = harmony.get("bigram", {})
    if progression and len(progression) > 1 and bigram:
        total = hits = 0
        for a, b in zip(progression, progression[1:]):
            total += 1
            if float(bigram.get(a, {}).get(b, 0)) > 0:
                hits += 1
        if total:
            scores.append(hits / total)

    # Melody: cosine similarity of the interval histogram to the genre's.
    ints = (prior.get("melody", {}) or {}).get("intervals", {})
    if melody and len(melody) > 2 and ints:
        sm = sorted(melody, key=lambda e: e.start)
        gen = [0.0] * 25   # intervals -12..12
        for i in range(1, len(sm)):
            iv = max(-12, min(12, sm[i].pitch - sm[i - 1].pitch))
            gen[iv + 12] += 1.0
        pri = [float(ints.get(str(k), ints.get(k, 0))) for k in range(-12, 13)]
        scores.append(_cosine(gen, pri))

    if not scores:
        return None, []
    s = sum(scores) / len(scores)
    flags = ["Drifts from the genre's learned style"] if s < 0.4 else []
    return min(1.0, s), flags


# ── public API ────────────────────────────────────────────────────────────────

def score_generation(
    all_events:  dict[str, list[NoteEvent]],
    style:       dict,
    key:         str,
    scale:       str,
    bars:        int,
    progression: list,
    complexity:  float,
    chorus_spans: list[tuple[float, float]] | None = None,
    resolved_sections: list[dict] | None = None,
    meter:       Meter = DEFAULT_METER,
) -> dict:
    """
    Score a generation across five musical dimensions.

    ``chorus_spans`` (start_beat, end_beat) pairs mark the song's chorus
    sections; when supplied, the melody inside them is scored for hook
    memorability as an extra dimension. Omit it (loops without a chorus,
    callers that don't track sections) and the hook dimension is skipped.

    ``resolved_sections`` carries the post-substitution harmony each section
    actually played; when supplied it replaces ``progression`` as the source of
    the chord map (see ``_build_chord_map_from_sections``). ``progression`` is
    still used for ``_style_match``, which compares against corpus bigrams mined
    from *template*-level romans, not substituted ones.

    ``meter`` is the time signature the events were generated in. Every bar-
    relative measurement (rhythm step vectors, hook self-similarity bars,
    notes-per-beat density, the legacy chord map) is computed on that bar length;
    the 4/4 default makes every formula collapse to the previous arithmetic.

    Returns:
        total     — weighted composite (0–1)
        harmonic  — chord-tone alignment
        register  — register separation between parts
        rhythm    — match to style's canonical kick/chord patterns
        contour   — melodic shape / interval & pitch variety
        density   — notes-per-beat vs style targets
        mix       — velocity balance
        hook      — chorus memorability (0 when no chorus melody to judge)
        label     — "Excellent" | "Good" | "Fair" | "Weak"
        flags     — list of human-readable issue descriptions
    """
    melody = all_events.get("melody", [])
    chords = all_events.get("chords", [])
    bass   = all_events.get("bass",   [])
    drums  = all_events.get("drums",  [])

    chord_map = (
        _build_chord_map_from_sections(resolved_sections, key, scale)
        if resolved_sections
        else _build_chord_map(progression, key, scale, bars, complexity, meter)
    )

    s_harm,   f_harm   = _harmonic_coherence(melody, key, scale, chord_map)
    s_reg,    f_reg    = _register_separation(melody, chords, bass)
    s_rhythm, f_rhythm = _rhythm_fit(drums, chords, style, bars, meter)
    s_cont,   f_cont   = _melodic_contour(melody)
    s_dens,   f_dens   = _density_fit(melody, bass, style, bars, complexity, meter)
    s_mix,    f_mix    = _mix_balance(melody, chords, bass)
    s_style,  f_style  = _style_match(progression, melody, style)

    # Hook memorability — chorus melody only. Slice the melody to the chorus
    # spans; when a chorus is present the search starts hunting *catchy*
    # choruses, not merely valid ones.
    s_hook, f_hook = None, []
    if chorus_spans and melody:
        chorus_mel = [
            n for n in melody
            if any(start <= n.start < end for start, end in chorus_spans)
        ]
        s_hook, f_hook = _hook_score(chorus_mel, meter)

    # Weighted, normalised over the applicable dimensions (style-match only counts
    # when a corpus prior exists, and hook only when there's a chorus melody, so
    # styles/sections without them aren't diluted).
    weighted = [
        (s_harm, 0.30), (s_reg, 0.16), (s_rhythm, 0.23),
        (s_cont, 0.10), (s_dens, 0.11), (s_mix, 0.10),
    ]
    if s_style is not None:
        weighted.append((s_style, 0.14))
    if s_hook is not None:
        weighted.append((s_hook, 0.12))
    total = sum(v * w for v, w in weighted) / sum(w for _, w in weighted)

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
        "separation": round(s_reg,  3),
        "rhythm":   round(s_rhythm, 3),
        "contour":  round(s_cont,   3),
        "density":  round(s_dens,   3),
        "mix":      round(s_mix,    3),
        "style_match": round(s_style, 3) if s_style is not None else 0.0,
        "hook":     round(s_hook, 3) if s_hook is not None else 0.0,
        "label":    label,
        "flags":    f_harm + f_reg + f_rhythm + f_cont + f_dens + f_mix + f_style + f_hook,
    }
