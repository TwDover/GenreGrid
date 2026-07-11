# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
import concurrent.futures
import shutil
import io
import logging
import random
import re
import secrets
import uuid
import json as _json_module
from fastapi import APIRouter, HTTPException, UploadFile, Form
from fastapi import File as FastAPIFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from app.models.schemas import GenerateRequest, RegeneratePartRequest, GenerateResponse, FileInfo, GenerateSummary, QualityScore, BatchGenerateRequest, BuildSongRequest, BuildSongResponse, SongSectionResult, RegenerateSongPartRequest, RegenerateSongSectionRequest, RestoreSongVersionRequest
from app.services.style_loader import load_style
from app.services.midi_writer import NoteEvent, ControlEvent, PitchBendEvent, write_midi, write_combined_midi, rebuild_combined_from_parts, concatenate_midi_files, read_note_starts, mido_key_signature
from app.generators.chords import generate_chords, resolve_progression
from app.theory.chords import roman_to_chord
from app.theory.scales import build_scale, scale_mode as _scale_mode
from app.generators.bass import generate_bass
from app.generators.melody import generate_melody
from app.generators.drums import generate_drums
from app.generators.arpeggio import generate_arpeggio
from app.generators.pads import generate_pads
from app.generators.counter_melody import generate_counter_melody
from app.core.config import EXPORTS_DIR
from app.core.constants import DRUM_MAP
from app.services.quality import score_generation, extract_rhythm_patterns
from app.services.priors import load_prior, sample_progression, melody_prior_for, groove_fields_for
from app.services.library import save_generation as lib_save, is_saved, build_scoring_style
from app.core.arrangement import (
    SECTION_PROFILES, _SONG_TEMPLATES, _part_seed, _transpose_key,
    _apply_section_ramp, _plan_sections, _auto_arc_section_type, _section_end_bars,
    _song_tempo_map,
)
from app.services.mixdown import (
    _DEFAULT_PROGRAMS, _STYLE_PROGRAMS, _PART_CHANNELS, _VELOCITY_SCALE,
    _generate_part_cc, _generate_melody_expression_cc, _generate_bass_expression_cc,
    _generate_808_pitch_bends, _drop_quiet, _scale_velocity, _shift,
    _apply_groove_push, _apply_dynamic,
)

router = APIRouter()
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

    # Resolve section profile for loop-mode shaping
    _sec_profile = SECTION_PROFILES.get(req.section_type or "", {}) if is_loop else {}
    _sec_cplx = min(1.0, req.complexity * _sec_profile.get("complexity_scale", 1.0))
    _sec_var  = min(1.0, req.variation  * _sec_profile.get("variation_scale",  1.0))
    _sec_dyn  = _sec_profile.get("velocity_scale", 1.0)

    if is_loop:
        sections = [{"bars": req.bars, "complexity": _sec_cplx, "parts": req.parts,
                     "offset": 0, "key": req.key, "dynamic": _sec_dyn}]
    else:
        key_shift = style.get("chorus_key_shift", 0)
        sections = _plan_sections(req.bars, req.complexity, req.parts, req.key, key_shift)

    all_events: dict[str, list[NoteEvent]] = {part: [] for part in req.parts}
    _chords_prev = list(chords_prev_voicing) if chords_prev_voicing else None

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
        _harm_boost = SECTION_PROFILES.get(s_sec_type or "", {}).get("harmonic_boost", 0.0)
        harmony_cplx = min(1.0, backing_cplx + _harm_boost)

        kick_times: list[float] = []
        if "drums" in req.parts and "drums" in s_parts:
            random.seed(_pseed(section_i, "drums"))
            drum_evts = generate_drums(style, s_bars, s_cplx, eff_var,
                                       section_end_bars=_section_end_bars(sections, s_off),
                                       is_loop=is_loop,
                                       section_type=s_sec_type,
                                       next_section_type=s_next_type)
            drum_evts = _apply_dynamic(drum_evts, s_dyn)
            all_events["drums"].extend(_shift(drum_evts, s_off))
            kick_times = [e.start for e in drum_evts if e.pitch == DRUM_MAP["kick"]]

        has_melody = "melody" in s_parts
        mel_range = style.get("melody", {}).get("range", [60, 79])
        # Always cap chord voicings below the melody's lowest note when melody is active.
        # Without this, default chord_register [48,72] lets chord tops reach into the
        # melody range [60,79], causing the two parts to fight for the same register.
        melody_ceiling = mel_range[0] if has_melody else None

        mel_rests: list = []
        mel_evts: list = []
        if has_melody and "melody" in req.parts:
            random.seed(_pseed(section_i, "melody"))
            mel_evts = generate_melody(style, s_key, req.scale, s_bars, mel_cplx,
                                       eff_var, s_resolved, is_loop=is_loop,
                                       melody_model=_melody_model,
                                       harmony_complexity=harmony_cplx,
                                       seed_motif=melody_seed_motif)
            mel_evts = _apply_dynamic(mel_evts, s_dyn)
            all_events["melody"].extend(_shift(mel_evts, s_off))
            if mel_evts:
                sorted_mel = sorted(mel_evts, key=lambda e: e.start)
                for _i in range(1, len(sorted_mel)):
                    gap_s = sorted_mel[_i - 1].start + sorted_mel[_i - 1].duration
                    gap_e = sorted_mel[_i].start
                    if gap_e - gap_s >= 1.5:
                        mel_rests.append((round(gap_s, 3), round(gap_e, 3)))

        # Counter-melody: harmony line derived from the melody's structural notes
        if mel_evts and "counter_melody" in req.parts and "counter_melody" in s_parts:
            random.seed(_pseed(section_i, "counter_melody"))
            cm_evts = generate_counter_melody(mel_evts, s_key, req.scale, s_bars,
                                              s_resolved, style)
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
                                       prev_voicing=_chords_prev)
                section_chord_tones = _chord_tones_by_bar(
                    [(e.start, e.pitch) for e in evts], s_bars)
                _chords_prev = _final_chord_voicing(evts)
            elif part == "pads":
                evts = generate_pads(style, s_key, req.scale, s_bars, backing_cplx,
                                     eff_var, s_resolved)
            elif part == "bass":
                evts = generate_bass(style, s_key, req.scale, s_bars, backing_cplx,
                                     eff_var, bass_prog, kick_times,
                                     melody_rests=mel_rests,
                                     harmony_complexity=harmony_cplx)
            elif part == "arpeggio":
                arp_octave = 6 if has_melody else 5
                # When melody is active, pull arpeggio back so it supports rather than competes.
                # mel_rests lets arpeggio fill the space when melody is silent (call-and-response).
                arp_cplx = backing_cplx * (0.68 if has_melody and "melody" in s_parts else 1.0)
                evts = generate_arpeggio(style, s_key, req.scale, s_bars, arp_cplx,
                                         eff_var, s_resolved, arp_octave,
                                         melody_rests=mel_rests if has_melody else None,
                                         chord_tones=section_chord_tones)
            evts = _apply_dynamic(evts, s_dyn)
            all_events[part].extend(_shift(evts, s_off))

    # Smooth dynamic steps at section transitions (verse→chorus lift, etc.)
    if not is_loop and len(sections) > 1:
        _apply_section_ramp(all_events, sections)

    if groove_push:
        for gp_part in ("melody", "chords", "arpeggio", "bass", "pads", "counter_melody"):
            if gp_part in all_events and all_events[gp_part]:
                all_events[gp_part] = _apply_groove_push(all_events[gp_part], groove_push)

    if "melody" in all_events and "bass" in all_events:
        # Per-section scale pcs (sections can sit in shifted keys — chorus lift)
        # so the parallel-motion fix nudges to in-key pitches, never chromatic ones.
        _mel_scale_name = style.get("melody_scale", req.scale)
        _section_scales = [
            (float(s["offset"]), float(s["offset"] + s["bars"] * 4),
             {p % 12 for p in build_scale(s.get("key", req.key), _mel_scale_name,
                                          octave_start=4, num_octaves=1)})
            for s in sections
        ]
        all_events["melody"] = _prevent_parallel_motion(
            all_events["melody"], all_events["bass"], _section_scales
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
            req.key, req.scale, req.bars, progression, req.complexity
        )
    except Exception as exc:
        logger.error("Quality scoring failed (seed=%s): %s", seed, exc, exc_info=True)
        quality_raw = None

    return all_events, cc_parts, pb_parts, progression, quality_raw, patterns, sections


@router.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    try:
        style = load_style(req.style_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, req.bpm))

    gen_id = str(uuid.uuid4())[:8]
    output_dir = EXPORTS_DIR / gen_id
    output_dir.mkdir(parents=True, exist_ok=True)

    programs: dict[str, int] = {**_DEFAULT_PROGRAMS, **_STYLE_PROGRAMS.get(req.style_id, {})}

    secondary_dominants = style.get("secondary_dominants", False)
    tritone_sub = style.get("tritone_substitution", False)
    is_loop = (req.mode == "loop")
    groove_push = style.get("groove_push", 0.0)

    style = _blend_styles(style, req.blend_style_id, req.blend_amount)

    # Inject humanize scale so generators can read it without API changes
    style = {**style, "_humanize_scale": req.humanize}

    # Use custom progression if provided (validate roman numerals loosely)
    if req.custom_progression:
        style = {**style, "progression_templates": [req.custom_progression]}

    # Use library-learned patterns to sharpen the scorer's rhythm references
    scoring_style = build_scoring_style(style, req.style_id)

    # Start with the requested seed (or a fresh random one)
    base_seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)

    def _run_best_attempt():
        _best_events = _best_cc = _best_pb = _best_progression = _best_quality_raw = _best_patterns = None
        _best_seed = base_seed
        for attempt in range(_MAX_QUALITY_ATTEMPTS):
            # Deterministic retry seeds: a given base seed always reproduces the
            # same attempt sequence (global-RNG retries made seeded generations
            # unreproducible whenever the quality gate triggered a retry).
            attempt_seed = base_seed if attempt == 0 else _part_seed(base_seed, attempt, "retry")
            _evts, _cc, _pb, _prog, _qraw, _pats, _secs = _run_attempt(
                req, style, attempt_seed, is_loop, groove_push, secondary_dominants, tritone_sub,
                scoring_style=scoring_style,
            )
            if _best_quality_raw is None or (
                _qraw is not None and _qraw.get("total", 0) > _best_quality_raw.get("total", 0)
            ):
                _best_events, _best_cc, _best_pb = _evts, _cc, _pb
                _best_progression, _best_quality_raw = _prog, _qraw
                _best_patterns, _best_sections = _pats, _secs
                _best_seed = attempt_seed
            if _qraw is not None and _all_green(_qraw):
                _best_seed = attempt_seed
                break
        return _best_events, _best_cc, _best_pb, _best_progression, _best_quality_raw, _best_patterns, _best_sections, _best_seed

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
            _fut = _pool.submit(_run_best_attempt)
            (best_events, best_cc, best_pb, best_progression,
             best_quality_raw, best_patterns, best_sections, best_seed) = _fut.result(timeout=_GENERATION_TIMEOUT_S)
    except concurrent.futures.TimeoutError:
        raise HTTPException(status_code=504, detail=f"Generation timed out after {_GENERATION_TIMEOUT_S}s")

    all_events  = best_events
    cc_parts    = best_cc
    pb_parts    = best_pb
    progression = best_progression
    quality_raw = best_quality_raw
    patterns    = best_patterns
    seed        = best_seed

    quality = QualityScore(**quality_raw) if quality_raw else None

    import json as _json

    # Write patterns.json so the frontend's manual-save can retrieve them later
    (output_dir / "patterns.json").write_text(_json.dumps(patterns or {}))

    # Auto-save to library when all dimensions are green
    if quality_raw and _all_green(quality_raw):
        try:
            lib_save(
                gen_id=gen_id,
                style_id=req.style_id,
                key=req.key,
                scale=req.scale,
                bpm=bpm,
                bars=req.bars,
                seed=seed,
                quality_raw=quality_raw,
                patterns=patterns or {},
            )
        except Exception as exc:
            logger.warning("Library auto-save failed for gen_id=%s: %s", gen_id, exc)

    _sid = style.get("id", "")
    files = []
    for part, events in all_events.items():
        if not events:
            continue
        events = _scale_velocity(events, part, _sid)
        events = _drop_quiet(events)
        filename = f"{part}.mid"
        out_path = output_dir / filename
        write_midi(events, out_path, bpm=bpm, program=programs.get(part),
                   cc_events=cc_parts.get(part), pb_events=pb_parts.get(part))
        files.append(FileInfo(part=part, filename=filename, url=f"/exports/{gen_id}/{filename}"))

    if len(all_events) > 1:
        combined_path = output_dir / "combined.mid"
        clean_events = {p: _drop_quiet(_scale_velocity(e, p, _sid)) for p, e in all_events.items()}
        write_combined_midi(clean_events, combined_path, bpm=bpm, programs=programs,
                           cc_parts=cc_parts, pb_parts=pb_parts)
        files.append(FileInfo(part="combined", filename="combined.mid", url=f"/exports/{gen_id}/combined.mid"))

    # In arrangement mode, also write per-section MIDI files
    if not is_loop and best_sections:
        sec_dir = output_dir / "sections"
        sec_dir.mkdir(exist_ok=True)
        import json as _js
        section_meta = []
        for sec_i, sec in enumerate(best_sections):
            sec_start = float(sec["offset"])
            sec_end = sec_start + sec["bars"] * 4.0
            sec_name = sec.get("section_type", f"section_{sec_i + 1}")
            sec_evts: dict[str, list] = {}
            for part, evts in all_events.items():
                clipped = [
                    NoteEvent(e.pitch, e.start - sec_start, e.duration, e.velocity, e.channel)
                    for e in evts
                    if sec_start <= e.start < sec_end
                ]
                if clipped:
                    sec_evts[part] = _drop_quiet(_scale_velocity(clipped, part, _sid))
            if sec_evts:
                sec_combined = sec_dir / f"{sec_i + 1:02d}_{sec_name}_combined.mid"
                write_combined_midi(sec_evts, sec_combined, bpm=bpm, programs=programs)
                section_meta.append({
                    "index": sec_i + 1, "name": sec_name,
                    "bars": sec["bars"], "bpm": bpm,
                    "file": sec_combined.name,
                })
        (sec_dir / "sections.json").write_text(_js.dumps(section_meta, indent=2))

    return GenerateResponse(
        generation_id=gen_id,
        style=req.style_id,
        files=files,
        summary=GenerateSummary(
            key=f"{req.key} {req.scale}",
            key_root=req.key,
            scale=req.scale,
            bpm=bpm,
            bars=req.bars,
            complexity=req.complexity,
            variation=req.variation,
            mode=req.mode,
            section_type=req.section_type,
        ),
        seed=seed,
        quality=quality,
        auto_saved=bool(quality_raw and _all_green(quality_raw)),
        progression=progression,
    )


@router.post("/generate-stream")
def generate_stream(req: GenerateRequest):
    """SSE endpoint: streams attempt progress then the final GenerateResponse."""
    def event_stream():
        try:
            style = load_style(req.style_id)
        except ValueError as e:
            yield f"data: {_json_module.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        bpm_min, bpm_max = style.get("bpm_range", [40, 240])
        bpm = max(bpm_min, min(bpm_max, req.bpm))
        gen_id = str(uuid.uuid4())[:8]
        output_dir = EXPORTS_DIR / gen_id
        output_dir.mkdir(parents=True, exist_ok=True)

        programs = {**_DEFAULT_PROGRAMS, **_STYLE_PROGRAMS.get(req.style_id, {})}
        secondary_dominants = style.get("secondary_dominants", False)
        tritone_sub = style.get("tritone_substitution", False)
        is_loop = (req.mode == "loop")
        groove_push = style.get("groove_push", 0.0)
        style = {**style, "_humanize_scale": req.humanize}
        if req.custom_progression:
            style = {**style, "progression_templates": [req.custom_progression]}
        scoring_style = build_scoring_style(style, req.style_id)
        base_seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)

        best_events = best_cc = best_pb = best_progression = best_quality_raw = best_patterns = None
        best_seed = base_seed

        for attempt in range(_MAX_QUALITY_ATTEMPTS):
            # Deterministic retry seeds: a given base seed always reproduces the
            # same attempt sequence (global-RNG retries made seeded generations
            # unreproducible whenever the quality gate triggered a retry).
            attempt_seed = base_seed if attempt == 0 else _part_seed(base_seed, attempt, "retry")
            yield f"data: {_json_module.dumps({'type': 'progress', 'attempt': attempt + 1, 'total': _MAX_QUALITY_ATTEMPTS})}\n\n"
            try:
                evts, cc, pb, prog, qraw, pats, secs = _run_attempt(
                    req, style, attempt_seed, is_loop, groove_push,
                    secondary_dominants, tritone_sub, scoring_style=scoring_style,
                )
            except Exception as exc:
                logger.error("Attempt %d failed: %s", attempt + 1, exc, exc_info=True)
                continue
            if best_quality_raw is None or (qraw and qraw.get("total", 0) > best_quality_raw.get("total", 0)):
                best_events, best_cc, best_pb = evts, cc, pb
                best_progression, best_quality_raw, best_patterns = prog, qraw, pats
                best_seed = attempt_seed
            if qraw and _all_green(qraw):
                best_seed = attempt_seed
                break

        quality = QualityScore(**best_quality_raw) if best_quality_raw else None
        if best_quality_raw and _all_green(best_quality_raw):
            try:
                lib_save(gen_id=gen_id, style_id=req.style_id, key=req.key, scale=req.scale,
                         bpm=bpm, bars=req.bars, seed=best_seed,
                         quality_raw=best_quality_raw, patterns=best_patterns or {})
            except Exception as exc:
                logger.warning("Library auto-save failed: %s", exc)
        (output_dir / "patterns.json").write_text(_json_module.dumps(best_patterns or {}))

        _sid = style.get("id", "")
        files = []
        for part, events in (best_events or {}).items():
            if not events:
                continue
            events = _scale_velocity(events, part, _sid)
            events = _drop_quiet(events)
            filename = f"{part}.mid"
            write_midi(events, output_dir / filename, bpm=bpm,
                       program=programs.get(part),
                       cc_events=(best_cc or {}).get(part),
                       pb_events=(best_pb or {}).get(part))
            files.append(FileInfo(part=part, filename=filename, url=f"/exports/{gen_id}/{filename}"))

        if best_events and len(best_events) > 1:
            combined_path = output_dir / "combined.mid"
            clean = {p: _drop_quiet(_scale_velocity(e, p, _sid)) for p, e in best_events.items()}
            write_combined_midi(clean, combined_path, bpm=bpm, programs=programs,
                               cc_parts=best_cc or {}, pb_parts=best_pb or {})
            files.append(FileInfo(part="combined", filename="combined.mid",
                                  url=f"/exports/{gen_id}/combined.mid"))

        response = GenerateResponse(
            generation_id=gen_id, style=req.style_id, files=files,
            summary=GenerateSummary(key=f"{req.key} {req.scale}", key_root=req.key,
                                    scale=req.scale, bpm=bpm, bars=req.bars,
                                    complexity=req.complexity, variation=req.variation,
                                    mode=req.mode, section_type=req.section_type),
            seed=best_seed, quality=quality,
            auto_saved=bool(best_quality_raw and _all_green(best_quality_raw)),
            progression=best_progression or [],
        )
        yield f"data: {_json_module.dumps({'type': 'done', 'result': response.model_dump()})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/batch-generate", response_model=list[GenerateResponse])
def batch_generate(req: BatchGenerateRequest):
    """Run `count` independent generations and return all results sorted best-first."""
    results = []
    for _ in range(req.count):
        seed_req = GenerateRequest(**{**req.base.model_dump(), "seed": None})
        results.append(generate(seed_req))
    results.sort(key=lambda r: r.quality.total if r.quality else 0.0, reverse=True)
    return results


@router.post("/regenerate-part", response_model=FileInfo)
def regenerate_part(req: RegeneratePartRequest):
    output_dir = EXPORTS_DIR / req.generation_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail="Generation not found")

    try:
        style = load_style(req.style_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    style = _overlay_groove(style, getattr(req, "use_priors", True))
    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, req.bpm))

    # Replay the original seed so we pick the same progression and substitutions —
    # keeps harmony consistent with the other parts generated from that seed.
    progression = _choose_progression(style, getattr(req, "use_priors", True), req.seed, req.scale)

    secondary_dominants = style.get("secondary_dominants", False)
    tritone_sub = style.get("tritone_substitution", False)

    # New independent seed for just this part — use OS entropy so it's different
    # every call regardless of what req.seed was.
    new_seed = secrets.randbelow(2**31)
    random.seed(new_seed)

    programs: dict[str, int] = {**_DEFAULT_PROGRAMS, **_STYLE_PROGRAMS.get(req.style_id, {})}
    if req.mode == "loop":
        sections = [{"bars": req.bars, "complexity": req.complexity, "parts": [req.part], "offset": 0, "key": req.key}]
    else:
        key_shift = style.get("chorus_key_shift", 0)
        sections = _plan_sections(req.bars, req.complexity, [req.part], req.key, key_shift)
    events: list[NoteEvent] = []

    # Detect if melody.mid already exists alongside the regenerated part so
    # arpeggio can be pushed to a higher octave to avoid register conflict.
    melody_exists = (output_dir / "melody.mid").exists()

    # When regenerating the arpeggio, read the already-saved chords so the new arp
    # arpeggiates the real voiced harmony (matching extensions) rather than a plain
    # triad. Built once as an absolute per-bar map, sliced per section below.
    global_chord_tones: list | None = None
    if req.part == "arpeggio":
        chords_path = output_dir / "chords.mid"
        if chords_path.exists():
            try:
                global_chord_tones = _chord_tones_by_bar(read_note_starts(chords_path), req.bars)
            except Exception:
                global_chord_tones = None

    for section_i, section in enumerate(sections):
        s_bars  = section["bars"]
        s_cplx  = section["complexity"]
        s_parts = set(section["parts"])
        s_off   = section["offset"]
        s_key   = section.get("key", req.key)
        if req.part not in s_parts:
            continue

        # Re-resolve substitutions with this section's complexity so the
        # regenerated part stays harmonically aligned with the original session.
        # Resolved on the same deterministic "harmony" seed _run_attempt used when the
        # sibling parts were first generated (isolated via save/restore so it doesn't
        # perturb the independent content randomness this regenerated part should get).
        saved_content_state = random.getstate()
        random.seed(_part_seed(req.seed, section_i, "harmony"))
        s_resolved = resolve_progression(progression, req.scale, s_cplx, secondary_dominants, tritone_sub)
        random.setstate(saved_content_state)

        kick_times: list[float] = []
        if req.part in ("bass", "chords"):
            saved_state = random.getstate()
            random.seed(_part_seed(req.seed, section_i, "drums"))
            drum_evts_tmp = generate_drums(style, s_bars, s_cplx, req.variation,
                                           section_end_bars=_section_end_bars(sections, s_off))
            kick_times = [e.start for e in drum_evts_tmp if e.pitch == DRUM_MAP["kick"]]
            random.setstate(saved_state)

        s_dyn = section.get("dynamic", 1.0)

        if req.part == "chords":
            evts = generate_chords(style, s_key, req.scale, s_bars, s_cplx,
                                   req.variation, progression, s_resolved,
                                   kick_times=kick_times)
        elif req.part == "bass":
            evts = generate_bass(style, s_key, req.scale, s_bars, s_cplx,
                                 req.variation, progression, kick_times)
        elif req.part == "melody":
            evts = generate_melody(style, s_key, req.scale, s_bars, s_cplx,
                                   req.variation, s_resolved,
                                   melody_model=melody_prior_for(_prior_name(style),
                                                                 getattr(req, "use_priors", True)))
        elif req.part == "pads":
            evts = generate_pads(style, s_key, req.scale, s_bars, s_cplx,
                                 req.variation, s_resolved)
        elif req.part == "counter_melody":
            # Rebuild the sibling melody deterministically (same part-seed the
            # original generation used) so the re-rolled harmony line tracks the
            # melody that's actually on disk.
            saved_cm_state = random.getstate()
            random.seed(_part_seed(req.seed, section_i, "melody"))
            sib_mel = generate_melody(style, s_key, req.scale, s_bars, s_cplx,
                                      req.variation, s_resolved,
                                      melody_model=melody_prior_for(_prior_name(style),
                                                                    getattr(req, "use_priors", True)))
            random.setstate(saved_cm_state)
            evts = generate_counter_melody(sib_mel, s_key, req.scale, s_bars,
                                           s_resolved, style)
        elif req.part == "drums":
            evts = generate_drums(style, s_bars, s_cplx, req.variation,
                                  section_end_bars=_section_end_bars(sections, s_off))
        elif req.part == "arpeggio":
            arp_octave = 6 if melody_exists else 5
            sec_tones = None
            if global_chord_tones:
                start_bar = int(s_off // 4)
                sec_tones = global_chord_tones[start_bar:start_bar + s_bars] or None
            evts = generate_arpeggio(style, s_key, req.scale, s_bars, s_cplx,
                                     req.variation, s_resolved, arp_octave,
                                     chord_tones=sec_tones)
        else:
            continue
        evts = _apply_dynamic(evts, s_dyn)
        events.extend(_shift(evts, s_off))

    groove_push = style.get("groove_push", 0.0)
    if groove_push and req.part in ("melody", "chords", "arpeggio", "bass"):
        events = _apply_groove_push(events, groove_push)

    events = _scale_velocity(events, req.part, style.get("id", ""))
    events = _drop_quiet(events)

    channel = _PART_CHANNELS.get(req.part, 0)
    part_cc = _generate_part_cc(req.part, req.bars, channel, style=style) if req.part != "drums" else None

    if req.part == "melody" and events:
        cc11 = _generate_melody_expression_cc(events, channel)
        part_cc = (part_cc or []) + cc11

    pb_events = None
    if req.part == "bass":
        bass_cfg = style.get("bass", {})
        if bass_cfg.get("bass_style") == "808":
            pb_events = _generate_808_pitch_bends(events, channel)
        elif events:
            bass_cc11 = _generate_bass_expression_cc(events, channel)
            part_cc = (part_cc or []) + bass_cc11

    filename = f"{req.part}.mid"
    out_path = output_dir / filename
    write_midi(events, out_path, bpm=bpm, program=programs.get(req.part),
               cc_events=part_cc, pb_events=pb_events)

    # Rebuild combined.mid so it reflects the newly regenerated part
    rebuild_combined_from_parts(output_dir, bpm)

    return FileInfo(part=req.part, filename=filename, url=f"/exports/{req.generation_id}/{filename}")


@router.get("/exports/{gen_id}/bundle.zip")
def download_bundle(gen_id: str):
    import zipfile, io
    output_dir = EXPORTS_DIR / gen_id
    if not output_dir.exists():
        raise HTTPException(status_code=404, detail="Generation not found")
    mid_files = list(output_dir.glob("*.mid"))
    if not mid_files:
        raise HTTPException(status_code=404, detail="No MIDI files found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(mid_files):
            zf.write(f, f.name)
    buf.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=genregrid_{gen_id}.zip"},
    )


@router.get("/exports/{gen_id}/sections.zip")
def download_sections(gen_id: str):
    import zipfile, io
    sec_dir = EXPORTS_DIR / gen_id / "sections"
    if not sec_dir.exists():
        raise HTTPException(status_code=404, detail="No section stems found — generate in Arrangement mode first")
    mid_files = list(sec_dir.glob("*.mid"))
    if not mid_files:
        raise HTTPException(status_code=404, detail="No section MIDI files found")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(mid_files):
            zf.write(f, f"sections/{f.name}")
        meta = sec_dir / "sections.json"
        if meta.exists():
            zf.write(meta, "sections/sections.json")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=genregrid_{gen_id}_sections.zip"},
    )


@router.get("/exports/{gen_id}/{filename}")
def download_export(gen_id: str, filename: str):
    file_path = EXPORTS_DIR / gen_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path), media_type="audio/midi", filename=filename)


_SAFE_PATH = re.compile(r'^[a-zA-Z0-9_\-]{1,80}$')


class ArrangeEntry(BaseModel):
    generation_id: str
    filename: str


class ArrangeRequest(BaseModel):
    entries: list[ArrangeEntry]


@router.post("/arrange")
def arrange(req: ArrangeRequest):
    """Concatenate multiple MIDI files sequentially into an arrangement."""
    if not req.entries:
        raise HTTPException(400, "No entries provided")

    paths = []
    for entry in req.entries:
        if not _SAFE_PATH.match(entry.generation_id):
            raise HTTPException(400, f"Invalid generation_id: {entry.generation_id!r}")
        safe_name = entry.filename.replace("/", "").replace("\\", "")
        path = EXPORTS_DIR / entry.generation_id / safe_name
        if not path.exists():
            raise HTTPException(404, f"File not found: {entry.generation_id}/{safe_name}")
        paths.append(path)

    try:
        out_mid = concatenate_midi_files(paths)
    except Exception as exc:
        logger.error("arrange failed: %s", exc)
        raise HTTPException(500, "Failed to build arrangement") from exc

    buf = io.BytesIO()
    out_mid.save(file=buf)
    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="audio/midi",
        headers={"Content-Disposition": "attachment; filename=arrangement.mid"},
    )
