# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.

"""Generation core — one seeded, quality-scored attempt and its helpers.

Extracted from routes_generate.py so the /generate endpoints AND the Song
Builder both depend on a service module instead of importing generation logic
out of a route file. Holds `_run_attempt` (build every part for one seed),
progression choice, style blending / groove overlay, and the voice-leading and
quality helpers. Imports only services / generators / core — never routes."""
import logging
import random

from app.services.style_loader import load_style
from app.services.midi_writer import NoteEvent, ControlEvent, PitchBendEvent
from app.generators.chords import generate_chords, resolve_progression
from app.theory.scales import build_scale, scale_mode as _scale_mode
from app.generators.bass import generate_bass
from app.generators.melody import generate_melody
from app.generators.drums import generate_drums
from app.generators.arpeggio import generate_arpeggio
from app.generators.pads import generate_pads
from app.generators.counter_melody import generate_counter_melody
from app.generators.answer import melody_cell
from app.core.constants import DRUM_MAP
from app.services.humanize import (
    apply_groove_pocket, apply_feel, apply_compound_swing, COMPOUND_SWING_DEFAULT,
)
from app.services.quality import score_generation, extract_rhythm_patterns
from app.services.priors import load_prior, sample_progression, melody_prior_for, groove_fields_for
from app.core.arrangement import (
    _part_seed, scaled_profile,
    _apply_section_ramp, _plan_sections, _auto_arc_section_type, _section_end_bars,
)
from app.core.meter import parse_meter
from app.services.mixdown import (
    _PART_CHANNELS, _VELOCITY_SCALE, _generate_part_cc, _generate_melody_expression_cc, _generate_bass_expression_cc,
    _generate_808_pitch_bends, _shift,
    _apply_groove_push, _apply_dynamic,
)

logger = logging.getLogger(__name__)

def _final_chord_voicing(chord_events: list[NoteEvent]) -> list[int] | None:
    """Extract the last sounded chord voicing from a chord part's events.

    Used to thread voice leading across song sections: the closing voicing of
    one section seeds `prev_voicing` for the next, so the comp doesn't jump
    back to root position at every section seam. Strums offset note starts by
    a few ms, so everything within half a beat of the final onset counts as
    one voicing.
    """
    if not chord_events:
        return None
    last_start = max(e.start for e in chord_events)
    voicing = sorted({e.pitch for e in chord_events if e.start >= last_start - 0.5})
    return voicing or None


def _chord_tones_by_bar(chord_notes, bars: int) -> list | None:
    """Per-bar sorted pitch-class lists from chord notes.

    ``chord_notes`` is an iterable of (start_beat, pitch) pairs (from generated
    events or a read-back .mid). Lets the arpeggio arpeggiate the chords' *actual*
    voiced harmony (including the 7ths/9ths and borrowed color the chord generator
    chose) instead of a re-derived plain triad. Empty bars (chord rests) inherit
    the nearest neighbouring bar's harmony so the arp never lands on a single stray
    note. Returns None when no chord notes exist (caller falls back to roman voicing).
    """
    tones: list[set[int]] = [set() for _ in range(bars)]
    for start, pitch in chord_notes:
        b = int(start // 4)
        if 0 <= b < bars:
            tones[b].add(pitch % 12)
    if not any(tones):
        return None
    last: set[int] | None = None
    for i in range(bars):
        if tones[i]:
            last = tones[i]
        elif last is not None:
            tones[i] = set(last)
    nxt: set[int] | None = None
    for i in range(bars - 1, -1, -1):
        if tones[i]:
            nxt = tones[i]
        elif nxt is not None:
            tones[i] = set(nxt)
    return [sorted(t) for t in tones]


def _prevent_parallel_motion(
    melody_events: list[NoteEvent],
    bass_events: list[NoteEvent],
    section_scales: list[tuple[float, float, set[int]]] | None = None,
) -> list[NoteEvent]:
    """Nudge melody notes that form parallel octaves or fifths with the bass.

    Only fixes the worst offender (direct parallel motion into an octave or fifth).
    Preserves all timing and velocity. Parallel motion into a unison (octave) is
    most objectionable; fifths are secondary.

    ``section_scales`` — (start_beat, end_beat, scale_pcs) per section, so the
    replacement pitch is the nearest non-parallel SCALE tone for the key that
    section actually sounds in. Without it the nudge is a raw +1/+2 semitones,
    which planted flat-out out-of-key notes (D+2 in C minor = E natural) in the
    melody — trading a subtle voice-leading blemish for an audible wrong note.
    """
    if not bass_events or not melody_events:
        return melody_events

    # Build a quick lookup: for each beat position, what bass pitch is sounding?
    bass_sorted = sorted(bass_events, key=lambda e: e.start)

    def _bass_pitch_at(beat: float) -> int | None:
        # Find the last bass note that started at or before `beat`
        result = None
        for e in bass_sorted:
            if e.start <= beat + 0.05:
                result = e.pitch
            else:
                break
        return result

    def _scale_pcs_at(beat: float) -> set[int] | None:
        if not section_scales:
            return None
        for s_start, s_end, pcs in section_scales:
            if s_start <= beat < s_end:
                return pcs
        return section_scales[-1][2]

    _PARALLEL_INTERVALS = {0, 7}   # unison/octave (mod 12) and fifth

    def _nudged(pitch: int, bass_pitch: int, beat: float) -> int:
        pcs = _scale_pcs_at(beat)
        # Climb to the nearest higher pitch that breaks the parallel interval
        # AND stays in the section's scale (when known).
        for cand in range(pitch + 1, pitch + 13):
            if (cand - bass_pitch) % 12 in _PARALLEL_INTERVALS:
                continue
            if pcs is None or cand % 12 in pcs:
                return max(48, min(96, cand))
        return pitch

    fixed = []
    for i, mel in enumerate(melody_events):
        b_pitch = _bass_pitch_at(mel.start)
        if b_pitch is None:
            fixed.append(mel)
            continue

        # Check current interval
        interval = (mel.pitch - b_pitch) % 12
        if interval not in _PARALLEL_INTERVALS:
            fixed.append(mel)
            continue

        # Check if the previous mel note also made the same interval with prev bass
        # (that's what makes it "parallel" — motion into the same interval type)
        if i > 0:
            prev_mel = melody_events[i - 1]
            prev_bass = _bass_pitch_at(prev_mel.start)
            if prev_bass is not None:
                prev_interval = (prev_mel.pitch - prev_bass) % 12
                if prev_interval in _PARALLEL_INTERVALS:
                    # Parallel motion confirmed — nudge to a scale-safe pitch
                    fixed.append(NoteEvent(
                        pitch=_nudged(mel.pitch, b_pitch, mel.start), start=mel.start,
                        duration=mel.duration, velocity=mel.velocity, channel=mel.channel,
                    ))
                    continue

        fixed.append(mel)

    return fixed


def _resolve_avoid_notes(
    melody_events: list[NoteEvent],
    harmony_events: list[NoteEvent],
    section_scales: list[tuple[float, float, set[int]]] | None = None,
    min_duration: float = 0.45,
) -> list[NoteEvent]:
    """Nudge SUSTAINED melody notes off harsh clashes with the sounding harmony.

    An "avoid note" here is a melody note that (a) is not doubling any pitch
    class the harmony is sounding, and (b) sits at an ACTUAL distance of a
    minor 2nd (1 semitone) or minor 9th (13) from a simultaneously sounding
    chord/pad tone. Held for half a beat or more, that reads as a wrong note —
    the melody generator can't see the voicings the chords/pads actually chose
    (registers, extensions, strums), so this runs where the real events exist.
    Short notes are exempt: passing dissonance on 16ths is normal melodic
    motion. Wider mod-12 relatives (maj7, compound maj7) are consonant color
    and never touched.

    The replacement is the nearest in-scale pitch (per section, via
    ``section_scales``) that clears every overlapping harmony note; if none
    exists within a major 3rd, the note is left alone rather than mangled.
    """
    if not melody_events or not harmony_events:
        return melody_events

    harmony_sorted = sorted(harmony_events, key=lambda e: e.start)
    _HARSH = (1, 13)

    def _scale_pcs_at(beat: float) -> set[int] | None:
        if not section_scales:
            return None
        for s_start, s_end, pcs in section_scales:
            if s_start <= beat < s_end:
                return pcs
        return section_scales[-1][2]

    def _sounding(mel: NoteEvent) -> list[int]:
        out = []
        m_end = mel.start + mel.duration
        for h in harmony_sorted:
            if h.start >= m_end:
                break
            overlap = min(m_end, h.start + h.duration) - max(mel.start, h.start)
            if overlap > 0.1:
                out.append(h.pitch)
        return out

    fixed: list[NoteEvent] = []
    for mel in melody_events:
        if mel.duration < min_duration:
            fixed.append(mel)
            continue
        sounding = _sounding(mel)
        if not sounding or mel.pitch % 12 in {h % 12 for h in sounding}:
            fixed.append(mel)
            continue
        if not any(abs(mel.pitch - h) in _HARSH for h in sounding):
            fixed.append(mel)
            continue
        pcs = _scale_pcs_at(mel.start)
        new_pitch = mel.pitch
        for delta in (-1, 1, -2, 2, -3, 3, -4, 4):
            cand = mel.pitch + delta
            if not (0 <= cand <= 127):
                continue
            if pcs is not None and cand % 12 not in pcs:
                continue
            if any(abs(cand - h) in _HARSH for h in sounding):
                continue
            new_pitch = cand
            break
        fixed.append(NoteEvent(pitch=new_pitch, start=mel.start, duration=mel.duration,
                               velocity=mel.velocity, channel=mel.channel)
                     if new_pitch != mel.pitch else mel)
    return fixed


_MAX_QUALITY_ATTEMPTS = 5
_GREEN_THRESHOLD = 0.82
_GENERATION_TIMEOUT_S = 30
_QUALITY_DIMS = ("harmonic", "separation", "rhythm", "density", "mix")


def _all_green(quality_raw: dict) -> bool:
    return all(quality_raw.get(d, 0.0) >= _GREEN_THRESHOLD for d in _QUALITY_DIMS)


def _blend_styles(style: dict, blend_style_id: str | None, blend_amount: float) -> dict:
    """Numerically blend a second style into `style` (shared by /generate and
    the Song Builder). Groove/density/swing fields interpolate; progression
    template pools merge. Returns `style` unchanged when no blend applies."""
    if not blend_style_id or blend_style_id == style.get("id"):
        return style
    try:
        b_style = load_style(blend_style_id)
    except ValueError:
        logger.warning("Blend style %r not found — ignoring blend", blend_style_id)
        return style
    w = blend_amount
    _NUMERIC_BLEND = ("hat_density", "kick_density", "snare_density",
                      "swing", "syncopation_prob", "groove_push")
    blended = {**style}
    for key in _NUMERIC_BLEND:
        if key in style and key in b_style:
            blended[key] = (1 - w) * style[key] + w * b_style[key]
    a_progs = style.get("progression_templates", [])
    b_progs = b_style.get("progression_templates", [])
    if a_progs and b_progs:
        blended["progression_templates"] = a_progs + b_progs
    if "drums" in style and "drums" in b_style:
        d_a, d_b = style["drums"], b_style["drums"]
        drum_blend = {**d_a}
        for k in ("hat_density", "kick_density", "snare_density", "swing",
                  "triplet_probability", "ghost_probability"):
            if k in d_a and k in d_b:
                drum_blend[k] = (1 - w) * d_a[k] + w * d_b[k]
        blended["drums"] = drum_blend
    return blended


def _prior_name(style: dict) -> str:
    """Which mined prior a style draws from: explicit `prior` field, else its id."""
    return style.get("prior") or style.get("id", "")


def _overlay_groove(style: dict, use_priors: bool) -> dict:
    """Overlay a style with drum fields learned from a groove corpus, if one exists.

    The learned kick_pattern / snare backbeat / hat density / swing replace the
    style's hand-authored values so drums play a real, mined groove. Returns the
    style unchanged when no groove prior applies.
    """
    fields = groove_fields_for(style, use_priors)
    if not fields:
        return style
    return {**style, "drums": {**style.get("drums", {}), **fields}}


# Chord-type suffixes a template token may carry (mirrors roman_to_chord's list;
# longest first so e.g. 'ivsus2' strips to 'iv', not 'ivsus').
_ROMAN_SUFFIXES = ("m7b5", "mM7", "dim7", "maj7", "9sus4", "7sus4", "sus2", "sus4",
                   "add11", "add9", "aug", "dim", "m6", "m9", "6", "9")


def _template_tonic_mode(template: list[str]) -> str | None:
    """'minor' if the template's tonic chord is bare i, 'major' if bare I,
    'mixed' if it somehow contains both (a data bug), None if it never states
    an explicit tonic (e.g. a ii-V vamp) and so fits either mode."""
    has_min = has_maj = False
    for token in template:
        s = token.lstrip("b#")
        for suffix in _ROMAN_SUFFIXES:
            if s.lower().endswith(suffix):
                s = s[: -len(suffix)]
                break
        if s == "i":
            has_min = True
        elif s == "I":
            has_maj = True
    if has_min and has_maj:
        return "mixed"
    if has_min:
        return "minor"
    if has_maj:
        return "major"
    return None


def _choose_progression(style: dict, use_priors: bool, seed: int, scale: str = "minor") -> list[str]:
    """Pick a progression: a mined corpus prior when available+enabled, else a template.

    The template RNG draw happens regardless so seeds stay stable with the legacy
    path; the prior only replaces the resulting progression when one exists. The
    prior is queried by mode so a major-key request gets a major progression.

    Templates are filtered to those whose tonic quality matches the requested
    scale's mode: a bare-'i' (minor tonic) template under a major-scale melody
    puts the whole harmony in the parallel minor while the melody stays major —
    every E-natural grinds against the chords' Eb (and vice versa for 'I'
    templates under a minor scale). Style JSONs may legitimately carry both
    major and minor templates; the request's scale decides which set applies.
    """
    templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
    mode = _scale_mode(scale)
    compatible = [t for t in templates if _template_tonic_mode(t) in (mode, None)]
    random.seed(seed)
    progression = random.choice(compatible or templates)
    if use_priors:
        prior = load_prior(_prior_name(style))
        if prior:
            sampled = sample_progression(prior, length=len(progression), seed=seed, mode=scale)
            if sampled:
                progression = sampled
    hrb = style.get("harmonic_rhythm_bars", 1)
    if hrb > 1:
        progression = [chord for chord in progression for _ in range(hrb)]
    # Chromatic color: season the diatonic progression with borrowed chords and
    # secondary dominants (roadmap-2 item 4). Gated by the style's chromatic_color
    # (default 0 = byte-identical). Applied once here so every section and the
    # scorer share the identical colored progression.
    _color = style.get("chromatic_color", 0.0)
    if _color:
        from app.generators.chords import apply_chromatic_color
        progression = apply_chromatic_color(progression, scale, _color,
                                            random.Random(seed ^ 0x00C010A))
    return progression


def _run_attempt(
    req,
    style: dict,
    seed: int,
    is_loop: bool,
    groove_push: float,
    secondary_dominants: bool,
    tritone_sub: bool,
    scoring_style: dict | None = None,
    regen_part: str | None = None,
    regen_salt: int = 0,
    fixed_progression: list[str] | None = None,
    chords_prev_voicing: list[int] | None = None,
    melody_seed_motif: list[int] | None = None,
    rhythm_cell: list[float] | None = None,
    arp_contour: list[int] | None = None,
) -> tuple[dict, dict, dict, list, dict | None, dict, list]:
    """Run one generation attempt for a given seed.

    Returns (all_events, cc_parts, pb_parts, progression, quality_raw, patterns).
    quality_raw is None if scoring raised an exception.
    scoring_style overrides the style dict used for quality scoring only,
    so learned patterns can improve scorer accuracy without touching generation.

    regen_part/regen_salt re-roll a single part in place: only that part's seed is
    salted, so harmony and every other part come out byte-identical — used to
    regenerate one stem of a song without disturbing the rest.

    fixed_progression — when given, skips the per-call progression draw and uses this
    progression instead. Used by the song builder so every section of a song shares
    one harmonic identity instead of each section type independently rolling its own
    progression; per-section chord substitutions (resolve_progression, seeded per
    section) still vary, giving related-but-not-identical harmony across sections.

    chords_prev_voicing — the previous song section's final chord voicing, threaded
    into generate_chords so voice leading continues across section seams.
    melody_seed_motif — scale-step motif intervals from an earlier section (the
    verse theme), passed to generate_melody so choruses develop the verse's idea.
    """
    def _pseed(sec_i: int, part: str) -> int:
        s = (seed + regen_salt) if (regen_part and part == regen_part) else seed
        return _part_seed(s, sec_i, part)

    _use_priors = getattr(req, "use_priors", True) and not getattr(req, "custom_progression", None)
    style = _overlay_groove(style, getattr(req, "use_priors", True))
    progression = fixed_progression if fixed_progression is not None else _choose_progression(style, _use_priors, seed, req.scale)
    _melody_model = melody_prior_for(_prior_name(style), getattr(req, "use_priors", True))

    # Resolve section profile for loop-mode shaping (contrast spread scaled by
    # the dynamics macro — 0.5 reproduces SECTION_PROFILES exactly)
    _dynamics = getattr(req, "dynamics", 0.5)
    _sec_profile = scaled_profile(req.section_type, _dynamics) if is_loop else {}
    _sec_cplx = min(1.0, req.complexity * _sec_profile.get("complexity_scale", 1.0))
    _sec_var  = min(1.0, req.variation  * _sec_profile.get("variation_scale",  1.0))
    _sec_dyn  = _sec_profile.get("velocity_scale", 1.0)

    # Time signature: bar length in quarter-beats (4/4 → 4.0, so 4/4 is unchanged).
    meter = parse_meter(getattr(req, "time_signature", None))

    if is_loop:
        sections = [{"bars": req.bars, "complexity": _sec_cplx, "parts": req.parts,
                     "offset": 0, "key": req.key, "dynamic": _sec_dyn}]
    else:
        key_shift = style.get("chorus_key_shift", 0)
        sections = _plan_sections(req.bars, req.complexity, req.parts, req.key, key_shift, meter=meter)

    all_events: dict[str, list[NoteEvent]] = {part: [] for part in req.parts}
    _chords_prev = list(chords_prev_voicing) if chords_prev_voicing else None
    chorus_spans: list[tuple[float, float]] = []   # (start_beat, end_beat) per chorus, for the hook scorer

    for section_i, section in enumerate(sections):
        s_bars  = section["bars"]
        s_cplx  = section["complexity"]
        s_parts = set(section["parts"])
        s_off   = section["offset"]
        s_key   = section.get("key", req.key)

        random.seed(_part_seed(seed, section_i, "harmony"))
        s_resolved = resolve_progression(progression, req.scale, s_cplx, secondary_dominants, tritone_sub)

        s_dyn = section.get("dynamic", 1.0)

        # Section context for the drums: explicit in song-builder loop mode,
        # derived from the auto-arc's shape otherwise.
        if is_loop:
            s_sec_type  = req.section_type
            s_next_type = getattr(req, "next_section_type", None)
        else:
            s_sec_type  = _auto_arc_section_type(sections, section_i)
            s_next_type = (_auto_arc_section_type(sections, section_i + 1)
                           if section_i + 1 < len(sections) else None)

        if s_sec_type == "chorus":
            chorus_spans.append((float(s_off), float(s_off) + s_bars * meter.bar_beats))

        # A section only gets the "final cadence" static-root bass treatment if
        # it's genuinely the song's last section. In loop mode (song builder)
        # every template section — verse, chorus, etc. — runs through its own
        # single-section call here, so `sections` always has exactly one entry
        # and section_i is always 0; checking "is this the last entry in
        # `sections`" degenerates to "yes, always", mislabelling every
        # low-complexity section (typically verses) as an outro and freezing
        # their bass on the tonic for the whole section regardless of the
        # chord progression moving underneath it. Loop mode instead checks the
        # section's actual declared type.
        is_last_section = (s_sec_type in ("outro", "ending") if is_loop
                            else section_i == len(sections) - 1)
        is_outro = (is_last_section and s_cplx < 0.5 and s_bars >= 2)
        bass_prog = (["I"] * len(progression)) if is_outro else progression

        # Per-part complexity / variation overrides from section profile (loop mode only)
        eff_var      = _sec_var if is_loop else req.variation
        mel_cplx     = min(1.0, s_cplx * _sec_profile.get("melody_complexity_scale",  1.0))
        backing_cplx = min(1.0, s_cplx * _sec_profile.get("backing_complexity_scale", 1.0))

        # Harmonic rhythm: choruses/pre-choruses change chords faster. The boost
        # feeds one shared value into chords, bass, and melody so their grids agree.
        _harm_boost = scaled_profile(s_sec_type, _dynamics).get("harmonic_boost", 0.0)
        harmony_cplx = min(1.0, backing_cplx + _harm_boost)

        # Ensemble pushes: which chord changes anticipate ("and of 4" early) is
        # decided ONCE here, seeded, and observed by BOTH the comp and the
        # bass — a lone early comp against an on-grid bass reads as a mistake;
        # the band pushing together reads as an arrangement.
        random.seed(_pseed(section_i, "pushes"))
        _push_prob = style.get("chord_anticipation_prob", 0.15)
        _cpb = 2 if harmony_cplx > 0.6 else 1
        push_windows = {w for w in range(1, s_bars * _cpb) if random.random() < _push_prob}

        kick_times: list[float] = []
        if "drums" in req.parts and "drums" in s_parts:
            random.seed(_pseed(section_i, "drums"))
            drum_evts = generate_drums(style, s_bars, s_cplx, eff_var,
                                       section_end_bars=_section_end_bars(sections, s_off, meter),
                                       is_loop=is_loop,
                                       section_type=s_sec_type,
                                       next_section_type=s_next_type,
                                       dynamics=_dynamics, meter=meter)
            drum_evts = _apply_dynamic(drum_evts, s_dyn)
            all_events["drums"].extend(_shift(drum_evts, s_off))
            kick_times = [e.start for e in drum_evts if e.pitch == DRUM_MAP["kick"]]

        has_melody = "melody" in s_parts
        mel_range = style.get("melody", {}).get("range", [60, 79])
        # Always cap chord voicings below the melody's lowest note when melody is active.
        # Without this, default chord_register [48,72] lets chord tops reach into the
        # melody range [60,79], causing the two parts to fight for the same register.
        #
        # The cap is decided by whether the SONG carries a melody, not this section:
        # song-builder intros/outros/endings often drop the melody (hook tease,
        # sparse part modes), and deciding per-section made their chords float a
        # full octave above every melody-bearing section — a jarring register jump
        # into the first verse and again at the ending.
        _song_parts = getattr(req, "song_parts", None) or req.parts
        melody_ceiling = mel_range[0] if (has_melody or "melody" in _song_parts) else None

        # Riff mode: the sung melody stands down in riff verses (the riff IS the
        # part) and returns for choruses, bridges, and lead/solo sections.
        from app.generators.riff import riff_section_comp
        _melody_tacet = (
            riff_section_comp(style, s_sec_type)
            and s_sec_type not in ("chorus", "post_chorus", "pre_chorus",
                                    "bridge", "instrumental_solo")
        )

        mel_rests: list = []
        mel_evts: list = []
        if has_melody and "melody" in req.parts and not _melody_tacet:
            random.seed(_pseed(section_i, "melody"))
            mel_evts = generate_melody(style, s_key, req.scale, s_bars, mel_cplx,
                                       eff_var, s_resolved, is_loop=is_loop,
                                       melody_model=_melody_model,
                                       harmony_complexity=harmony_cplx,
                                       seed_motif=melody_seed_motif,
                                       section_type=s_sec_type, meter=meter)
            mel_evts = _apply_dynamic(mel_evts, s_dyn)
            all_events["melody"].extend(_shift(mel_evts, s_off))
            if mel_evts:
                sorted_mel = sorted(mel_evts, key=lambda e: e.start)
                for _i in range(1, len(sorted_mel)):
                    gap_s = sorted_mel[_i - 1].start + sorted_mel[_i - 1].duration
                    gap_e = sorted_mel[_i].start
                    if gap_e - gap_s >= 1.5:
                        mel_rests.append((round(gap_s, 3), round(gap_e, 3)))

        # Call-response answers trace the song's melodic cell. Before that cell
        # exists (the first verse — its theme is captured only after its backing
        # is built) fall back to THIS section's own opening contour, so verse 1
        # (where the space is greatest) can still answer thematically.
        _answer_cell = arp_contour or melody_cell(mel_evts, s_key, req.scale)

        # Counter-melody: harmony under the hook (choruses) or a thematic ANSWER
        # in the melody's holes (verse/intro/outro — see generate_counter_melody).
        # When it's answering, the bass floor-fill stands down for this section
        # (below) so the two don't both crowd into the same gap.
        _cm_answering = ("counter_melody" in req.parts and "counter_melody" in s_parts
                         and bool(mel_evts)
                         and s_sec_type not in (None, "chorus", "post_chorus"))
        if mel_evts and "counter_melody" in req.parts and "counter_melody" in s_parts:
            random.seed(_pseed(section_i, "counter_melody"))
            cm_evts = generate_counter_melody(mel_evts, s_key, req.scale, s_bars,
                                              s_resolved, style,
                                              melody_rests=mel_rests, cell=_answer_cell,
                                              section_type=s_sec_type, meter=meter)
            cm_evts = _apply_dynamic(cm_evts, s_dyn)
            all_events["counter_melody"].extend(_shift(cm_evts, s_off))

        # Fixed order so chords are generated before the arpeggio, letting the arp
        # arpeggiate the chords' real voiced harmony (chord_tones below).
        section_chord_tones: list | None = None
        for part in ("chords", "pads", "bass", "arpeggio"):
            if part not in req.parts or part not in s_parts:
                continue
            random.seed(_pseed(section_i, part))
            if part == "chords":
                evts = generate_chords(style, s_key, req.scale, s_bars, backing_cplx,
                                       eff_var, progression, s_resolved,
                                       melody_ceiling=melody_ceiling,
                                       kick_times=kick_times,
                                       melody_rests=mel_rests if has_melody else None,
                                       harmony_complexity=harmony_cplx,
                                       prev_voicing=_chords_prev,
                                       push_windows=push_windows,
                                       section_type=s_sec_type, meter=meter)
                section_chord_tones = _chord_tones_by_bar(
                    [(e.start, e.pitch) for e in evts], s_bars)
                _chords_prev = _final_chord_voicing(evts)
            elif part == "pads":
                evts = generate_pads(style, s_key, req.scale, s_bars, backing_cplx,
                                     eff_var, s_resolved,
                                     harmony_complexity=harmony_cplx,
                                     melody_top=(mel_range[1] if melody_ceiling is not None else None),
                                     meter=meter)
            elif part == "bass":
                evts = generate_bass(style, s_key, req.scale, s_bars, backing_cplx,
                                     eff_var, bass_prog, kick_times,
                                     melody_rests=(None if _cm_answering else mel_rests),
                                     harmony_complexity=harmony_cplx,
                                     push_windows=push_windows,
                                     rhythm_cell=rhythm_cell,
                                     cell_contour=_answer_cell,
                                     section_type=s_sec_type, meter=meter)
            elif part == "arpeggio":
                arp_octave = 6 if has_melody else 5
                # When melody is active, pull arpeggio back so it supports rather than competes.
                # mel_rests lets arpeggio fill the space when melody is silent (call-and-response).
                arp_cplx = backing_cplx * (0.68 if has_melody and "melody" in s_parts else 1.0)
                evts = generate_arpeggio(style, s_key, req.scale, s_bars, arp_cplx,
                                         eff_var, s_resolved, arp_octave,
                                         melody_rests=mel_rests if has_melody else None,
                                         chord_tones=section_chord_tones,
                                         seed_contour=arp_contour, meter=meter)
            evts = _apply_dynamic(evts, s_dyn)
            all_events[part].extend(_shift(evts, s_off))

    # Smooth dynamic steps at section transitions (verse→chorus lift, etc.)
    if not is_loop and len(sections) > 1:
        _apply_section_ramp(all_events, sections, meter=meter)

    if groove_push:
        for gp_part in ("melody", "chords", "arpeggio", "bass", "pads", "counter_melody"):
            if gp_part in all_events and all_events[gp_part]:
                all_events[gp_part] = _apply_groove_push(all_events[gp_part], groove_push)

    # Systematic feel first (styles with a feel profile): drums get per-class
    # microtiming + velocity contour, bass sits behind the kick. Those parts are
    # then excluded from the generic pocket so the two don't stack. Styles with
    # no feel profile skip this entirely and fall through unchanged.
    _feel_parts = apply_feel(all_events, style, meter=meter)

    # Shared groove pocket: every remaining part shifts onto the same per-16th-slot
    # micro-offsets (style-seeded, deterministic) so the band plays TOGETHER —
    # independent per-note jitter alone made the composite subtly smear.
    apply_groove_pocket(all_events, style, skip=_feel_parts, meter=meter)

    # Compound meters (6/8, 9/8, 12/8) get their triplet lilt on top: a
    # per-dotted-quarter velocity contour + a middle-eighth swing. No-op for
    # every other meter (4/4/simple/odd stay byte-identical).
    apply_compound_swing(all_events, meter, style.get("compound_swing", COMPOUND_SWING_DEFAULT))

    if all_events.get("melody"):
        # Per-section scale pcs (sections can sit in shifted keys — chorus lift)
        # so both melody clean-up passes nudge to in-key pitches, never chromatic ones.
        _mel_scale_name = style.get("melody_scale", req.scale)
        _section_scales = [
            (float(s["offset"]), float(s["offset"] + s["bars"] * 4),
             {p % 12 for p in build_scale(s.get("key", req.key), _mel_scale_name,
                                          octave_start=4, num_octaves=1)})
            for s in sections
        ]
        if all_events.get("bass"):
            all_events["melody"] = _prevent_parallel_motion(
                all_events["melody"], all_events["bass"], _section_scales
            )
        # Avoid-note pass: sustained melody notes a real m2/m9 from the
        # chords'/pads' ACTUAL voicing move to a safe scale tone (the melody
        # generator can't see voicings; this runs on the finished events).
        _harmony_evts = (all_events.get("chords") or []) + (all_events.get("pads") or [])
        if _harmony_evts:
            all_events["melody"] = _resolve_avoid_notes(
                all_events["melody"], _harmony_evts, _section_scales
            )

    cc_parts: dict[str, list[ControlEvent]] = {}
    for part in req.parts:
        if part == "drums" or part not in all_events or not all_events[part]:
            continue
        channel = _PART_CHANNELS.get(part, 0)
        cc_parts[part] = _generate_part_cc(part, req.bars, channel, style=style)

    if "melody" in all_events and all_events["melody"]:
        ch = _PART_CHANNELS.get("melody", 2)
        melody_cc11 = _generate_melody_expression_cc(all_events["melody"], ch)
        cc_parts.setdefault("melody", []).extend(melody_cc11)

    bass_style_type = style.get("bass", {}).get("bass_style", "standard")
    if bass_style_type != "808" and "bass" in all_events and all_events["bass"]:
        ch = _PART_CHANNELS.get("bass", 1)
        cc_parts.setdefault("bass", []).extend(
            _generate_bass_expression_cc(all_events["bass"], ch)
        )

    pb_parts: dict[str, list[PitchBendEvent]] = {}
    if "bass" in all_events and all_events["bass"]:
        bass_cfg = style.get("bass", {})
        if bass_cfg.get("bass_style") == "808":
            ch = _PART_CHANNELS.get("bass", 1)
            pb_parts["bass"] = _generate_808_pitch_bends(all_events["bass"], ch)

    patterns = extract_rhythm_patterns(all_events, req.bars)

    # Pre-apply the same velocity scaling used for MIDI output so the mix scorer
    # evaluates what the listener will actually hear, not the raw generator values.
    _scored_events = {
        part: [
            NoteEvent(e.pitch, e.start, e.duration,
                      max(1, min(127, int(e.velocity * _VELOCITY_SCALE.get(part, 1.0)))),
                      e.channel)
            for e in evts
        ]
        for part, evts in all_events.items()
    }

    try:
        quality_raw = score_generation(
            _scored_events, scoring_style or style,
            req.key, req.scale, req.bars, progression, req.complexity,
            chorus_spans=chorus_spans,
        )
    except Exception as exc:
        logger.error("Quality scoring failed (seed=%s): %s", seed, exc, exc_info=True)
        quality_raw = None

    return all_events, cc_parts, pb_parts, progression, quality_raw, patterns, sections
