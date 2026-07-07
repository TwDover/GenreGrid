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


def _vary_repeat(events: list[NoteEvent], part: str) -> list[NoteEvent]:
    """Light variation applied when a cached section theme repeats.

    Keeps the theme recognizable (same pitches, same rhythm skeleton) while
    removing the photocopy feel: velocities re-humanize, and ~18% of the
    melody's long notes gain an upper-neighbor turn ornament. Caller seeds the
    RNG so repeats are deterministic per section occurrence.
    """
    out: list[NoteEvent] = []
    for e in events:
        vel = max(1, min(127, e.velocity + random.randint(-6, 6)))
        if part == "melody" and e.duration >= 1.0 and random.random() < 0.18:
            d1, d2 = e.duration * 0.5, e.duration * 0.22
            d3 = e.duration - d1 - d2
            out.append(NoteEvent(e.pitch, e.start, d1 * 0.95, vel, e.channel))
            out.append(NoteEvent(min(127, e.pitch + 2), e.start + d1, d2 * 0.9,
                                 max(1, vel - 10), e.channel))
            out.append(NoteEvent(e.pitch, e.start + d1 + d2, d3 * 0.95,
                                 max(1, vel - 4), e.channel))
        else:
            out.append(NoteEvent(e.pitch, e.start, e.duration, vel, e.channel))
    return out


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


def _melody_motif_intervals(mel_events: list[NoteEvent], key: str, scale: str) -> list[int] | None:
    """Scale-step intervals of a melody's opening motif (up to 4 intervals).

    Extracted from the first verse of a built song and handed to chorus
    generation so the chorus melody develops the verse's theme instead of
    inventing an unrelated one. Pitches are snapped to the scale lattice and
    expressed as index deltas, so the motif transposes cleanly to any register.
    """
    if not mel_events:
        return None
    from app.theory.scales import build_scale
    lattice = build_scale(key, scale, octave_start=2, num_octaves=6)
    pitches = [e.pitch for e in sorted(mel_events, key=lambda e: e.start)[:5]]
    if len(pitches) < 2:
        return None
    idxs = [min(range(len(lattice)), key=lambda i: abs(lattice[i] - p)) for p in pitches]
    intervals = [idxs[k + 1] - idxs[k] for k in range(len(idxs) - 1)]
    # An all-zero motif (repeated note) carries no shape worth reusing
    return intervals if any(intervals) else None


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
    scale_notes: list[int] | None = None,
) -> list[NoteEvent]:
    """Nudge melody notes that form parallel octaves or fifths with the bass.

    Only fixes the worst offender (direct parallel motion into an octave or fifth)
    by raising or lowering by 1 semitone. Preserves all timing and velocity.
    Parallel motion into a unison (octave) is most objectionable; fifths are secondary.
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

    _PARALLEL_INTERVALS = {0, 7}   # unison/octave (mod 12) and fifth

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
                    # Parallel motion confirmed — nudge melody ±1 semitone
                    new_pitch = mel.pitch + (1 if interval == 7 else 2)
                    new_pitch = max(48, min(96, new_pitch))
                    fixed.append(NoteEvent(
                        pitch=new_pitch, start=mel.start,
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


def _choose_progression(style: dict, use_priors: bool, seed: int, scale: str = "minor") -> list[str]:
    """Pick a progression: a mined corpus prior when available+enabled, else a template.

    The template RNG draw happens regardless so seeds stay stable with the legacy
    path; the prior only replaces the resulting progression when one exists. The
    prior is queried by mode so a major-key request gets a major progression.
    """
    templates = style.get("progression_templates", [["i", "VI", "III", "VII"]])
    random.seed(seed)
    progression = random.choice(templates)
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
        is_outro = (section_i == len(sections) - 1 and s_cplx < 0.5 and s_bars >= 2)
        bass_prog = (["I"] * len(progression)) if is_outro else progression

        # Per-part complexity / variation overrides from section profile (loop mode only)
        eff_var      = _sec_var if is_loop else req.variation
        mel_cplx     = min(1.0, s_cplx * _sec_profile.get("melody_complexity_scale",  1.0))
        backing_cplx = min(1.0, s_cplx * _sec_profile.get("backing_complexity_scale", 1.0))

        # Section context for the drums: explicit in song-builder loop mode,
        # derived from the auto-arc's shape otherwise.
        if is_loop:
            s_sec_type  = req.section_type
            s_next_type = getattr(req, "next_section_type", None)
        else:
            s_sec_type  = _auto_arc_section_type(sections, section_i)
            s_next_type = (_auto_arc_section_type(sections, section_i + 1)
                           if section_i + 1 < len(sections) else None)

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
        all_events["melody"] = _prevent_parallel_motion(
            all_events["melody"], all_events["bass"]
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


def _generate_song_sections(req, style, bpm, base_seed, chorus_key_shift,
                            secondary_dominants, tritone_sub, groove_push,
                            regen_part=None, regen_salt=0, bridge_key_shift=0,
                            fixed_section_seeds=None, final_chorus_lift=0,
                            custom_template=None, user_progression=None,
                            hook_melody=None):
    """Run a song template's section loop → (song_events, section_results, total_bars, section_seeds).

    Shared by build_song and regenerate_song_part. regen_part/regen_salt re-roll one
    part in place while harmony and every other part stay identical.

    Each section runs the same quality-scored, multi-attempt search plain /generate
    uses (`_MAX_QUALITY_ATTEMPTS`, best-of scoring) instead of a single unscreened
    attempt — sections used to ship whatever the first random roll produced.

    `fixed_section_seeds` — when given (regenerate_song_part), replays the exact
    winning attempt seed chosen for each section by the original build_song call
    instead of re-deriving and re-searching, so non-regenerated parts come out
    byte-identical to what's already on disk.

    `final_chorus_lift` — extra semitones added to the LAST chorus's key (the
    classic gear-change); the cached chorus theme is transposed to match.
    `custom_template` — list of section dicts overriding the named template.
    `user_progression` / `hook_melody` — melody-import mode: the derived
    progression replaces the style draw, and the user's melody becomes the
    chorus hook (cached as the chorus theme, so repeats/tease/counter-melody
    all build on it).
    """
    if custom_template:
        template = [dict(sd) for sd in custom_template]
    else:
        template = _SONG_TEMPLATES.get(req.template, _SONG_TEMPLATES["verse_chorus"])
    full_parts   = list(req.parts)
    no_arp       = [p for p in req.parts if p != "arpeggio"]
    foundation   = [p for p in req.parts if p in ("drums", "bass")]
    sparse_parts = [p for p in req.parts if p in ("drums", "bass", "chords")]
    melodic      = [p for p in req.parts if p in ("chords", "melody")]
    no_drums     = [p for p in req.parts if p != "drums"]
    chords_only  = [p for p in req.parts if p == "chords"]
    parts_modes = {
        "full": full_parts, "no_arp": no_arp, "foundation": foundation,
        "sparse": sparse_parts, "melodic": melodic or chords_only,
        "no_drums": no_drums, "chords_only": chords_only or foundation,
    }

    scoring_style = build_scoring_style(style, req.style_id)

    # Per-section style overrides (custom templates): a section can generate in a
    # different style while the whole song keeps one progression/key, so a lofi
    # verse can drop into a house chorus without losing harmonic identity.
    _sec_style_cache: dict[str, tuple[dict, dict]] = {}

    def _style_for(style_id: str | None) -> tuple[dict, dict]:
        if not style_id or style_id == style.get("id"):
            return style, scoring_style
        if style_id not in _sec_style_cache:
            try:
                s = {**load_style(style_id), "_humanize_scale": style.get("_humanize_scale", 0.5)}
                _sec_style_cache[style_id] = (s, build_scoring_style(s, style_id))
            except ValueError:
                logger.warning("Section style %r not found — using the song style", style_id)
                _sec_style_cache[style_id] = (style, scoring_style)
        return _sec_style_cache[style_id]

    # One progression for the whole song so every section shares a harmonic identity.
    # Per-section chord substitutions (inside _run_attempt, seeded per section) still
    # vary each section's exact chords, so chorus/bridge relate to the verse instead
    # of each section type independently rolling an unrelated progression.
    song_progression = (list(user_progression) if user_progression
                        else _choose_progression(style, req.use_priors, base_seed, req.scale))

    song_events: dict[str, list] = {p: [] for p in req.parts}
    section_results: list[dict] = []
    section_seeds: list[int] = []
    ramp_sections: list[dict] = []
    beat_offset = 0.0
    total_bars = 0
    type_seed: dict[str, int] = {}
    type_occurrence: dict[str, int] = {}
    # First occurrence of each section type caches its melodic/harmonic parts so
    # later sections of the same type reuse the theme (the verse tune returns).
    type_theme: dict[str, dict] = {}

    # The counter-melody is reserved for the climactic last chorus so the final
    # chorus sounds bigger than the ones before it.
    last_chorus_i = max((i for i, s in enumerate(template)
                         if s["section_type"] == "chorus"), default=-1)

    # Threaded across sections: the closing chord voicing (voice-leading
    # continuity at seams) and the verse's opening motif (chorus develops it).
    prev_voicing: list[int] | None = None
    verse_motif: list[int] | None = None
    _hook_motif = (_melody_motif_intervals(hook_melody, req.key, req.scale)
                   if hook_melody else None)
    # Intro hook tease: when the intro would carry a melody, hold it back and
    # overlay a thinned copy of the chorus melody after the loop instead.
    tease_intro: dict | None = None
    chorus_theme_shift = 0   # key shift the cached chorus theme was generated in

    for sec_i, sec_def in enumerate(template):
        sec_type   = sec_def["section_type"]
        sec_bars   = sec_def.get("bars", 8)
        sec_name   = sec_def.get("name") or sec_type
        parts_mode = sec_def.get("parts_mode", "full")
        sec_parts  = list(parts_modes.get(parts_mode, full_parts) or full_parts)

        # Arrangement colors: pads fill out only the big sections; the
        # counter-melody appears only on the final chorus.
        if "pads" in sec_parts and sec_type not in ("chorus", "bridge"):
            sec_parts = [p for p in sec_parts if p != "pads"]
        if "counter_melody" in sec_parts and sec_i != last_chorus_i:
            sec_parts = [p for p in sec_parts if p != "counter_melody"]

        # Intro tease: strip the intro's own melody — the chorus hook (thinned)
        # takes its place once the chorus theme exists.
        if sec_i == 0 and sec_type == "intro" and "melody" in sec_parts and last_chorus_i > 0:
            sec_parts = [p for p in sec_parts if p != "melody"]
            tease_intro = {"bars": sec_bars}

        key_shift = (
            chorus_key_shift if sec_def.get("chorus_key")
            else bridge_key_shift if sec_def.get("bridge_key")
            else 0
        )
        # Gear change: the last chorus lifts above the earlier ones.
        if sec_i == last_chorus_i:
            key_shift += final_chorus_lift
        sec_key = _transpose_key(req.key, key_shift) if key_shift else req.key

        occ = type_occurrence.get(sec_type, 0)
        if sec_type not in type_seed:
            type_seed[sec_type] = _part_seed(base_seed, sec_i, "type")
        type_occurrence[sec_type] = occ + 1
        sec_seed = (type_seed[sec_type] + occ * 73_856) % (2 ** 31)

        next_sec_type = template[sec_i + 1]["section_type"] if sec_i + 1 < len(template) else None
        sec_style, sec_scoring = _style_for(sec_def.get("style_id"))

        sec_req = GenerateRequest.model_construct(
            style_id=req.style_id, key=sec_key, scale=req.scale, bpm=bpm,
            bars=sec_bars, complexity=req.complexity, variation=req.variation,
            parts=sec_parts, mode="loop", seed=sec_seed, section_type=sec_type,
            next_section_type=next_sec_type,
            humanize=req.humanize, custom_progression=None, blend_style_id=None,
            blend_amount=0.5, use_priors=req.use_priors,
        )

        # Choruses develop the verse's motif; other section types keep their own
        # ideas. In melody-import mode every melodic section develops the HOOK's
        # motif instead, so the whole song grows out of the user's idea.
        if hook_melody:
            sec_motif = _hook_motif if sec_type in ("verse", "chorus", "bridge") else None
        else:
            sec_motif = verse_motif if sec_type == "chorus" else None

        if fixed_section_seeds is not None:
            # Replay: reuse the exact seed the original build_song call landed on
            # for this section — no re-search, so untouched parts stay identical.
            winning_seed = fixed_section_seeds[sec_i] if sec_i < len(fixed_section_seeds) else sec_seed
            _qraw = None
            try:
                evts, _cc, _pb, _prog, _qraw, _patterns, _secs = _run_attempt(
                    sec_req, sec_style, winning_seed, True, groove_push, secondary_dominants, tritone_sub,
                    scoring_style=sec_scoring, regen_part=regen_part, regen_salt=regen_salt,
                    fixed_progression=song_progression,
                    chords_prev_voicing=prev_voicing, melody_seed_motif=sec_motif,
                )
            except Exception as exc:
                logger.error("build_song section %r failed: %s", sec_name, exc, exc_info=True)
                evts = {}
        else:
            # Quality-gated multi-attempt search, mirroring plain /generate's
            # _run_best_attempt — song sections previously ran once with no
            # quality check at all.
            best_evts, best_total, winning_seed = None, -1.0, sec_seed
            for attempt in range(_MAX_QUALITY_ATTEMPTS):
                attempt_seed = sec_seed if attempt == 0 else _part_seed(sec_seed, attempt, "retry")
                try:
                    evts, _cc, _pb, _prog, qraw, _patterns, _secs = _run_attempt(
                        sec_req, sec_style, attempt_seed, True, groove_push, secondary_dominants, tritone_sub,
                        scoring_style=sec_scoring, regen_part=regen_part, regen_salt=regen_salt,
                        fixed_progression=song_progression,
                        chords_prev_voicing=prev_voicing, melody_seed_motif=sec_motif,
                    )
                except Exception as exc:
                    logger.error("build_song section %r attempt %d failed: %s", sec_name, attempt, exc, exc_info=True)
                    continue
                total = qraw.get("total", 0.0) if qraw is not None else 0.0
                if best_evts is None or total > best_total:
                    best_evts, best_total, winning_seed = evts, total, attempt_seed
                if qraw is not None and _all_green(qraw):
                    break
            evts = best_evts or {}

        section_seeds.append(winning_seed)

        # Melody-import: the user's melody IS the chorus. Swap it in before the
        # theme cache locks, so every chorus repeat, the intro tease, and the
        # counter-melody derive from the real hook. Transposed to the chorus key.
        if hook_melody and sec_type == "chorus" and "chorus" not in type_theme and evts.get("melody") is not None:
            from app.services.melody_import import fit_melody_to_bars
            fitted = fit_melody_to_bars(hook_melody, sec_bars)
            if key_shift:
                fitted = [NoteEvent(min(127, max(0, e.pitch + key_shift)), e.start,
                                    e.duration, e.velocity, e.channel) for e in fitted]
            evts["melody"] = fitted

        sec_quality = best_total if (fixed_section_seeds is None and best_total >= 0) else (
            _qraw.get("total") if fixed_section_seeds is not None and _qraw else None)

        # Cross-section motif reuse: the first section of each type sets the theme
        # (melody + harmony); later sections of that type reuse it, keeping fresh
        # drums so the groove still evolves. Same-type sections share a key, so the
        # reused parts need no transposition.
        if sec_type not in type_theme:
            type_theme[sec_type] = {p: list(e) for p, e in evts.items() if p != "drums"}
            if sec_type == "chorus":
                chorus_theme_shift = key_shift   # key the cached chorus theme sounds in
        else:
            for p, cached in type_theme[sec_type].items():
                if p in evts:
                    evts[p] = list(cached)
            # Gear change: the cached chorus theme sounds in the earlier chorus
            # key — transpose it up to this section's lifted key.
            if sec_i == last_chorus_i and final_chorus_lift:
                for p in type_theme[sec_type]:
                    if evts.get(p):
                        evts[p] = [NoteEvent(min(127, max(0, e.pitch + final_chorus_lift)),
                                             e.start, e.duration, e.velocity, e.channel)
                                   for e in evts[p]]
            # Light variation so the repeat isn't a photocopy of the first pass.
            random.seed(_part_seed(winning_seed, 0, "repeat_var"))
            for p in type_theme[sec_type]:
                if evts.get(p):
                    evts[p] = _vary_repeat(evts[p], p)
            # The theme swap replaced this section's melody with the cached one, so
            # any counter-melody derived from the discarded fresh melody would be
            # harmonizing a line that no longer sounds — re-derive it from the
            # melody that will actually play.
            if "counter_melody" in evts and evts.get("melody"):
                random.seed(_part_seed(winning_seed, 0, "counter_melody"))
                evts["counter_melody"] = generate_counter_melody(
                    evts["melody"], sec_key, req.scale, sec_bars,
                    song_progression, sec_style)

        # Thread voice-leading and the verse theme into the next section: the
        # post-theme-swap events are what actually sound, so extract from those.
        if evts.get("chords"):
            prev_voicing = _final_chord_voicing(evts["chords"])
        if verse_motif is None and sec_type == "verse" and evts.get("melody"):
            verse_motif = _melody_motif_intervals(evts["melody"], req.key, req.scale)

        for part, part_evts in evts.items():
            if part in song_events and part_evts:
                song_events[part].extend(_shift(part_evts, beat_offset))

        section_results.append({
            "name": sec_name, "section_type": sec_type,
            "bars": sec_bars, "start_bar": total_bars, "key": sec_key,
            "quality": round(sec_quality, 3) if sec_quality is not None else None,
        })
        ramp_sections.append({
            "offset": beat_offset, "bars": sec_bars,
            "dynamic": SECTION_PROFILES.get(sec_type, {}).get("velocity_scale", 1.0),
        })
        beat_offset += sec_bars * 4
        total_bars  += sec_bars

    # Smooth velocity jumps at section boundaries (verse→chorus lift, etc.). This
    # previously only ran inside a single _run_attempt's own internal auto-arc
    # sections and never across the song builder's independently-generated
    # sections, so every Verse→Chorus/Chorus→Bridge transition was a hard jump.
    if len(ramp_sections) > 1:
        _apply_section_ramp(song_events, ramp_sections)

    # ── Intro hook tease ─────────────────────────────────────────────────────
    # The intro previews the chorus melody: thinned to its structural notes,
    # softer, and transposed back to the home key if the chorus modulates.
    # Deterministic — derived entirely from the cached chorus theme.
    if tease_intro and "melody" in song_events:
        chorus_mel = type_theme.get("chorus", {}).get("melody") or []
        if chorus_mel:
            limit = tease_intro["bars"] * 4
            in_window = [e for e in chorus_mel if e.start < limit - 0.05]
            # Prefer the hook's structural notes; if the chorus opens busy (no
            # long/strong-beat notes in the intro window), tease the full line
            # instead so the intro never ends up silent.
            thin = [e for e in in_window
                    if (e.start % 1.0) < 0.13 or e.duration >= 0.75] or in_window
            song_events["melody"].extend(
                NoteEvent(min(127, max(0, e.pitch - chorus_theme_shift)), e.start,
                          min(e.duration, limit - e.start),
                          max(1, int(e.velocity * 0.72)), e.channel)
                for e in thin
            )

    # ── Ending bar ────────────────────────────────────────────────────────────
    # A real cadence instead of just stopping: the tonic chord, bass root, and a
    # kick+crash land on one extra bar and ring out (the tempo map's ritardando
    # covers this bar). Deterministic from base_seed so every regeneration flow
    # reproduces identical ending events for untouched parts.
    random.seed(_part_seed(base_seed, len(template), "ending"))
    ending_start = float(total_bars * 4)
    tonic_roman = "i" if req.scale in ("minor", "dorian", "phrygian", "harmonic_minor",
                                       "pentatonic_minor", "blues", "locrian") else "I"
    tonic = roman_to_chord(tonic_roman, req.key, req.scale, octave=4)
    ring = 4.0
    if "chords" in song_events:
        base = sorted(tonic)
        for ni, p in enumerate(base):
            song_events["chords"].append(NoteEvent(
                pitch=p, start=ending_start + ni * 0.012, duration=ring,
                velocity=max(1, 84 - ni * 4), channel=0))
    if "pads" in song_events and song_events.get("pads"):
        for ni, p in enumerate(sorted(tonic)):
            song_events["pads"].append(NoteEvent(
                pitch=min(127, p + 12), start=ending_start, duration=ring,
                velocity=56 - ni * 2, channel=4))
    if "bass" in song_events:
        song_events["bass"].append(NoteEvent(
            pitch=max(0, tonic[0] - 24), start=ending_start, duration=ring,
            velocity=92, channel=1))
    if "melody" in song_events and song_events.get("melody"):
        mel_range = style.get("melody", {}).get("range", [60, 79])
        root_pc = tonic[0] % 12
        candidates = [p for p in range(mel_range[0], mel_range[1] + 1) if p % 12 == root_pc]
        if candidates:
            song_events["melody"].append(NoteEvent(
                pitch=candidates[len(candidates) // 2], start=ending_start,
                duration=ring, velocity=78, channel=2))
    if "drums" in song_events:
        song_events["drums"].append(NoteEvent(DRUM_MAP["kick"], ending_start, 0.1, 116, 9))
        song_events["drums"].append(NoteEvent(DRUM_MAP["crash"], ending_start, ring, 104, 9))
    section_results.append({
        "name": "End", "section_type": "ending",
        "bars": 1, "start_bar": total_bars, "key": req.key,
    })
    total_bars += 1

    return song_events, section_results, total_bars, section_seeds


def _section_markers(section_results: list[dict], home_key: str) -> list[tuple[float, str]]:
    """MIDI section markers for the DAW timeline; sections that modulate away
    from the home key carry the key in the label (e.g. "Final Chorus (B)")."""
    return [
        (float(s["start_bar"] * 4),
         s["name"] if s.get("key", home_key) == home_key else f"{s['name']} ({s['key']})")
        for s in section_results
    ]


def _write_song_output(song_events: dict, output_dir, gen_id: str, bpm: int, style: dict,
                       programs: dict, parts: list[str], total_bars: int,
                       section_results: list[dict], key: str = "C",
                       scale: str = "minor") -> list[FileInfo]:
    """Write every stem + song.mid for a built song (CC, pitch bends, tempo map).

    Shared by build_song and regenerate_song_section so both produce identical
    file layouts. The tempo map (chorus push + ending ritardando) is written
    into every stem so they stay sample-locked in any DAW; section markers and
    the key signature go into song.mid so DAW timelines mirror the app's.
    """
    song_cc: dict[str, list] = {}
    for part in parts:
        if part == "drums" or not song_events.get(part):
            continue
        channel = _PART_CHANNELS.get(part, 0)
        song_cc[part] = _generate_part_cc(part, total_bars, channel, style=style)

    if song_events.get("melody"):
        ch = _PART_CHANNELS.get("melody", 2)
        song_cc.setdefault("melody", []).extend(
            _generate_melody_expression_cc(song_events["melody"], ch)
        )

    song_pb: dict[str, list] = {}
    if song_events.get("bass") and style.get("bass", {}).get("bass_style") == "808":
        ch = _PART_CHANNELS.get("bass", 1)
        song_pb["bass"] = _generate_808_pitch_bends(song_events["bass"], ch)

    tempo_map = _song_tempo_map(section_results, bpm, ending_bars=1)

    files: list[FileInfo] = []
    _sid = style.get("id", "")
    for part, evts in song_events.items():
        if not evts:
            continue
        clean = _drop_quiet(_scale_velocity(evts, part, _sid))
        if not clean:
            continue
        fname = f"{part}.mid"
        write_midi(clean, output_dir / fname, bpm=bpm, program=programs.get(part),
                   cc_events=song_cc.get(part), pb_events=song_pb.get(part),
                   tempo_events=tempo_map)
        files.append(FileInfo(part=part, filename=fname, url=f"/exports/{gen_id}/{fname}"))

    if len([p for p, e in song_events.items() if e]) > 1:
        clean_all = {p: _drop_quiet(_scale_velocity(e, p, _sid)) for p, e in song_events.items() if e}
        write_combined_midi(clean_all, output_dir / "song.mid", bpm=bpm, programs=programs,
                            cc_parts=song_cc, pb_parts=song_pb, tempo_events=tempo_map,
                            markers=_section_markers(section_results, key),
                            key_signature=mido_key_signature(key, scale))
        files.append(FileInfo(part="song", filename="song.mid", url=f"/exports/{gen_id}/song.mid"))
    return files


@router.post("/build-song", response_model=BuildSongResponse)
def build_song(req: BuildSongRequest):
    """Generate a full song by stitching independently-generated sections."""
    return _do_build_song(req)


def _do_build_song(req: BuildSongRequest, user_progression: list[str] | None = None,
                   hook_melody: list[NoteEvent] | None = None) -> BuildSongResponse:
    """Shared song-build core. `user_progression`/`hook_melody` come from the
    melody-import endpoint: the song is built around the user's uploaded idea."""
    try:
        style = load_style(req.style_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, req.bpm))

    gen_id = str(uuid.uuid4())[:8]
    output_dir = EXPORTS_DIR / gen_id
    output_dir.mkdir(parents=True, exist_ok=True)

    programs = {**_DEFAULT_PROGRAMS, **_STYLE_PROGRAMS.get(req.style_id, {})}
    secondary_dominants = style.get("secondary_dominants", False)
    tritone_sub = style.get("tritone_substitution", False)
    groove_push = style.get("groove_push", 0.0)
    # User-controlled chorus modulation overrides the style default when provided.
    chorus_key_shift = req.chorus_key_shift if req.chorus_key_shift is not None else style.get("chorus_key_shift", 0)
    # Bridges default to a lift to the subdominant (a common bridge-modulation target)
    # unless the style or request overrides it — unlike chorus_key_shift, which
    # defaults to no shift, bridges benefit from contrast out of the box.
    bridge_key_shift = req.bridge_key_shift if req.bridge_key_shift is not None else style.get("bridge_key_shift", 5)
    # Gear change on the LAST chorus only — classic pop move, on by default (+1).
    final_chorus_lift = req.final_chorus_lift if req.final_chorus_lift is not None else style.get("final_chorus_lift", 1)
    custom_template = ([sd.model_dump() for sd in req.custom_template]
                       if req.custom_template else None)
    style = _blend_styles(style, getattr(req, "blend_style_id", None), getattr(req, "blend_amount", 0.5))
    style = {**style, "_humanize_scale": req.humanize}

    base_seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)

    song_events, section_results, total_bars, section_seeds = _generate_song_sections(
        req, style, bpm, base_seed, chorus_key_shift,
        secondary_dominants, tritone_sub, groove_push,
        bridge_key_shift=bridge_key_shift,
        final_chorus_lift=final_chorus_lift,
        custom_template=custom_template,
        user_progression=user_progression,
        hook_melody=hook_melody,
    )

    # Persist the params needed to regenerate a single part later.
    import json as _jmeta
    (output_dir / "song_meta.json").write_text(_jmeta.dumps({
        "style_id": req.style_id, "key": req.key, "scale": req.scale,
        "bpm": bpm, "complexity": req.complexity, "variation": req.variation,
        "humanize": req.humanize, "parts": list(req.parts), "template": req.template,
        "use_priors": req.use_priors, "chorus_key_shift": chorus_key_shift,
        "bridge_key_shift": bridge_key_shift, "base_seed": base_seed,
        "final_chorus_lift": final_chorus_lift, "custom_template": custom_template,
        "blend_style_id": getattr(req, "blend_style_id", None),
        "blend_amount": getattr(req, "blend_amount", 0.5),
        "user_progression": user_progression,
        "hook_melody": ([[e.pitch, round(e.start, 4), round(e.duration, 4), e.velocity, e.channel]
                         for e in hook_melody] if hook_melody else None),
        "section_seeds": section_seeds,
    }))

    files = _write_song_output(song_events, output_dir, gen_id, bpm, style, programs,
                               list(req.parts), total_bars, section_results,
                               key=req.key, scale=req.scale)

    import json as _jsong
    (output_dir / "song_structure.json").write_text(_jsong.dumps(section_results, indent=2))

    return BuildSongResponse(
        generation_id=gen_id,
        style=req.style_id,
        files=files,
        seed=base_seed,
        template=req.template,
        total_bars=total_bars,
        sections=[SongSectionResult(**s) for s in section_results],
        bpm=bpm,
        key=f"{req.key} {req.scale}",
    )


_ALL_SONG_PARTS = frozenset({"chords", "bass", "melody", "drums", "arpeggio", "pads", "counter_melody"})


@router.post("/regenerate-song-part", response_model=FileInfo)
def regenerate_song_part(req: RegenerateSongPartRequest):
    """Re-roll a single part of a built song — or add a part that wasn't built.

    Reruns the song's section loop with only the target part's seed salted, so
    harmony and every other part stay identical; writes the new stem and rebuilds
    song.mid from the on-disk stems. When the requested part wasn't in the
    original build (e.g. the user forgot to tick pads), it is generated fresh
    against the song's persisted seeds and added to the song's part list.
    """
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found or too old to regenerate")
    meta = _json_module.loads(meta_path.read_text())
    is_new_part = req.part not in meta.get("parts", [])
    if is_new_part:
        if req.part not in _ALL_SONG_PARTS:
            raise HTTPException(status_code=400, detail=f"Unknown part '{req.part}'")
        if req.part == "counter_melody" and "melody" not in meta.get("parts", []):
            raise HTTPException(status_code=400,
                                detail="counter_melody needs the melody part in the song")

    try:
        style = load_style(meta["style_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, meta["bpm"]))
    secondary_dominants = style.get("secondary_dominants", False)
    tritone_sub = style.get("tritone_substitution", False)
    groove_push = style.get("groove_push", 0.0)
    style = _blend_styles(style, meta.get("blend_style_id"), meta.get("blend_amount", 0.5))
    style = {**style, "_humanize_scale": meta["humanize"]}
    programs = {**_DEFAULT_PROGRAMS, **_STYLE_PROGRAMS.get(meta["style_id"], {})}

    _snapshot_song(output_dir)   # version history: state before this mutation

    gen_parts = list(meta["parts"]) + ([req.part] if is_new_part else [])
    song_req = BuildSongRequest.model_construct(
        style_id=meta["style_id"], key=meta["key"], scale=meta["scale"], bpm=meta["bpm"],
        complexity=meta["complexity"], variation=meta["variation"], humanize=meta["humanize"],
        parts=gen_parts, template=meta["template"], use_priors=meta["use_priors"],
        seed=meta["base_seed"], chorus_key_shift=meta["chorus_key_shift"],
    )

    salt = secrets.randbelow(2 ** 31) or 1   # non-zero so the part actually changes
    song_events, _sections, total_bars, _seeds = _generate_song_sections(
        song_req, style, bpm, meta["base_seed"], meta["chorus_key_shift"],
        secondary_dominants, tritone_sub, groove_push,
        regen_part=req.part, regen_salt=salt,
        bridge_key_shift=meta.get("bridge_key_shift", 0),
        fixed_section_seeds=meta.get("section_seeds"),
        final_chorus_lift=meta.get("final_chorus_lift", 0),
        custom_template=meta.get("custom_template"),
        user_progression=meta.get("user_progression"),
        hook_melody=_hook_from_meta(meta),
    )

    evts = song_events.get(req.part) or []
    if not evts:
        hint = ""
        if req.part == "counter_melody":
            hint = " — the counter-melody plays only in the final chorus, and this template has no chorus"
        elif req.part == "pads":
            hint = " — pads play only in chorus and bridge sections, and this template has neither"
        raise HTTPException(status_code=400 if is_new_part else 500,
                            detail=f"No events generated for {req.part}{hint}")

    _sid = style.get("id", "")
    part_cc = None
    if req.part != "drums":
        channel = _PART_CHANNELS.get(req.part, 0)
        part_cc = _generate_part_cc(req.part, total_bars, channel, style=style)
        if req.part == "melody":
            part_cc = part_cc + _generate_melody_expression_cc(evts, channel)
    part_pb = None
    if req.part == "bass" and style.get("bass", {}).get("bass_style") == "808":
        part_pb = _generate_808_pitch_bends(evts, _PART_CHANNELS.get("bass", 1))

    tempo_map = _song_tempo_map(_sections, bpm, ending_bars=1)
    scaled = _drop_quiet(_scale_velocity(evts, req.part, _sid))
    fname = f"{req.part}.mid"
    part_path = output_dir / fname
    # Back up the current stem (one level of undo). The ".prev" name has no .mid
    # extension so rebuild_combined_from_parts won't fold it into the song.
    if part_path.exists():
        shutil.copy(part_path, output_dir / f"{req.part}.prev")
    write_midi(scaled, part_path, bpm=bpm, program=programs.get(req.part),
               cc_events=part_cc, pb_events=part_pb, tempo_events=tempo_map)

    # Rebuild song.mid from all stems on disk (new part + untouched others).
    rebuild_combined_from_parts(output_dir, bpm, combined_name="song.mid", tempo_events=tempo_map,
                                markers=_section_markers(_sections, meta.get("key", "C")),
                                key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")))

    # An added part becomes a first-class member of the song so later
    # regenerations and undos treat it like any originally-built stem.
    if is_new_part:
        meta["parts"] = gen_parts
        meta_path.write_text(_json_module.dumps(meta))

    return FileInfo(part=req.part, filename=fname, url=f"/exports/{req.generation_id}/{fname}")


def _template_section_results(template_name: str, key: str = "C",
                              custom: list[dict] | None = None) -> list[dict]:
    """Section layout (start_bar/bars/type) for a template, including the ending
    bar — enough to rebuild the tempo map without regenerating any music."""
    template = custom or _SONG_TEMPLATES.get(template_name, _SONG_TEMPLATES["verse_chorus"])
    out, sb = [], 0
    for sd in template:
        bars = sd.get("bars", 8)
        out.append({"name": sd.get("name") or sd["section_type"], "section_type": sd["section_type"],
                    "bars": bars, "start_bar": sb, "key": key})
        sb += bars
    out.append({"name": "End", "section_type": "ending", "bars": 1, "start_bar": sb, "key": key})
    return out


def _hook_from_meta(meta: dict) -> list[NoteEvent] | None:
    """Rebuild the imported hook melody persisted in song_meta.json."""
    raw = meta.get("hook_melody")
    if not raw:
        return None
    return [NoteEvent(int(p), float(s), float(d), int(v), int(ch)) for p, s, d, v, ch in raw]


@router.post("/build-song-from-melody", response_model=BuildSongResponse)
async def build_song_from_melody(
    file: UploadFile = FastAPIFile(...),
    style_id: str = Form(...),
    template: str = Form("verse_chorus"),
    parts: str = Form("chords,bass,melody,drums,pads"),
    complexity: float = Form(0.6),
    variation: float = Form(0.4),
    humanize: float = Form(0.5),
    use_priors: bool = Form(False),
    chorus_key_shift: int = Form(0),
    final_chorus_lift: int = Form(1),
    seed: int | None = Form(None),
):
    """Build a full song around an uploaded melody.

    The melody's key is detected (Krumhansl-Schmuckler), a supporting chord
    progression is derived bar by bar, and the melody becomes the song's chorus
    hook — repeats, the intro tease, the counter-melody, and every section's
    motif development all grow out of the user's idea.
    """
    from app.services.melody_import import parse_melody_midi, detect_key, derive_progression

    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(status_code=400, detail="MIDI file too large (5 MB max)")
    try:
        melody, file_bpm = parse_melody_midi(data)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse that file as MIDI")
    if len(melody) < 4:
        raise HTTPException(status_code=400, detail="No usable melody found in the file (need at least 4 notes)")

    key, scale = detect_key(melody)
    progression = derive_progression(melody, key, scale)

    try:
        style = load_style(style_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = int(max(bpm_min, min(bpm_max, file_bpm or 120)))

    req = BuildSongRequest(
        style_id=style_id, key=key, scale=scale, bpm=bpm,
        complexity=complexity, variation=variation, humanize=humanize,
        parts=[p.strip() for p in parts.split(",") if p.strip()],
        template=template, seed=seed, use_priors=use_priors,
        chorus_key_shift=chorus_key_shift, final_chorus_lift=final_chorus_lift,
    )
    return _do_build_song(req, user_progression=progression, hook_melody=melody)


_MAX_SONG_VERSIONS = 5
_VERSION_ID = re.compile(r"^\d{10,16}$")


def _snapshot_song(output_dir) -> None:
    """Snapshot every stem + metadata into versions/<ms> before a mutation.

    Keeps the last _MAX_SONG_VERSIONS so any re-roll / added part / restore can
    be stepped back from the History picker (deeper than the one-level .prev).
    """
    import time as _time
    versions_dir = output_dir / "versions"
    versions_dir.mkdir(exist_ok=True)
    snap = versions_dir / str(int(_time.time() * 1000))
    snap.mkdir(exist_ok=True)
    for f in output_dir.iterdir():
        if f.is_file() and (f.suffix == ".mid" or f.name in ("song_meta.json", "song_structure.json")):
            shutil.copy(f, snap / f.name)
    snaps = sorted((d for d in versions_dir.iterdir() if d.is_dir()), key=lambda d: d.name)
    for old_snap in snaps[:-_MAX_SONG_VERSIONS]:
        shutil.rmtree(old_snap, ignore_errors=True)


@router.get("/song-versions/{generation_id}")
def list_song_versions(generation_id: str):
    """Versions saved before each mutation, newest first."""
    from datetime import datetime
    if not _SAFE_PATH.match(generation_id):
        raise HTTPException(status_code=400, detail="Invalid generation id")
    versions_dir = EXPORTS_DIR / generation_id / "versions"
    if not versions_dir.exists():
        return []
    out = []
    for d in sorted((d for d in versions_dir.iterdir() if d.is_dir()),
                    key=lambda d: d.name, reverse=True):
        try:
            saved_at = datetime.fromtimestamp(int(d.name) / 1000).isoformat(timespec="seconds")
        except (ValueError, OSError):
            continue
        out.append({"id": d.name, "saved_at": saved_at})
    return out


@router.post("/restore-song-version", response_model=list[FileInfo])
def restore_song_version(req: RestoreSongVersionRequest):
    """Restore a snapshot. The current state is snapshotted first, so a restore
    is itself restorable."""
    if not _SAFE_PATH.match(req.generation_id) or not _VERSION_ID.match(req.version_id):
        raise HTTPException(status_code=400, detail="Invalid id")
    output_dir = EXPORTS_DIR / req.generation_id
    snap = output_dir / "versions" / req.version_id
    if not snap.exists():
        raise HTTPException(status_code=404, detail="Version not found")

    _snapshot_song(output_dir)
    snap_names = {f.name for f in snap.iterdir() if f.is_file()}
    for f in snap.iterdir():
        if f.is_file():
            shutil.copy(f, output_dir / f.name)
    # Stems created after this snapshot (e.g. a later-added part) must go too
    for f in output_dir.glob("*.mid"):
        if f.name not in snap_names:
            f.unlink()
    return [FileInfo(part=f.stem, filename=f.name,
                     url=f"/exports/{req.generation_id}/{f.name}")
            for f in sorted(output_dir.glob("*.mid"))]


@router.post("/undo-song-part", response_model=FileInfo)
def undo_song_part(req: RegenerateSongPartRequest):
    """Restore the previous version of a song stem (one level of undo)."""
    output_dir = EXPORTS_DIR / req.generation_id
    prev = output_dir / f"{req.part}.prev"
    if not prev.exists():
        raise HTTPException(status_code=404, detail="Nothing to undo for this part")
    meta_path = output_dir / "song_meta.json"
    meta = _json_module.loads(meta_path.read_text()) if meta_path.exists() else {}
    bpm = meta.get("bpm", 120)
    _layout = _template_section_results(meta.get("template", "verse_chorus"), meta.get("key", "C"),
                                        custom=meta.get("custom_template"))
    tempo_map = _song_tempo_map(_layout, bpm, ending_bars=1)

    shutil.copy(prev, output_dir / f"{req.part}.mid")
    prev.unlink()   # one level of undo only
    rebuild_combined_from_parts(output_dir, bpm, combined_name="song.mid", tempo_events=tempo_map,
                                markers=_section_markers(_layout, meta.get("key", "C")),
                                key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")))
    return FileInfo(part=req.part, filename=f"{req.part}.mid",
                    url=f"/exports/{req.generation_id}/{req.part}.mid")


@router.post("/regenerate-song-section", response_model=list[FileInfo])
def regenerate_song_section(req: RegenerateSongSectionRequest):
    """Re-roll one section of a built song, keeping every other section identical.

    Replaces the stored winning seed for that section and replays the song's
    section loop, so all parts of the target section get fresh music while the
    rest of the song reproduces byte-for-byte from the persisted seeds. Note the
    ripple rules: re-rolling the first occurrence of a section type also updates
    later sections of that type (they reuse its theme), and re-rolling a verse
    can reshape choruses (they develop the verse's motif) — musically intended.
    """
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found or too old to regenerate")
    meta = _json_module.loads(meta_path.read_text())
    section_seeds = list(meta.get("section_seeds") or [])
    template = meta.get("custom_template") or _SONG_TEMPLATES.get(meta.get("template", ""), _SONG_TEMPLATES["verse_chorus"])
    if not section_seeds:
        raise HTTPException(status_code=400, detail="This song predates section re-roll — rebuild it once to enable")
    if not (0 <= req.section_index < len(template)):
        raise HTTPException(status_code=400, detail=f"section_index must be 0..{len(template) - 1}")

    try:
        style = load_style(meta["style_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, meta["bpm"]))
    secondary_dominants = style.get("secondary_dominants", False)
    tritone_sub = style.get("tritone_substitution", False)
    groove_push = style.get("groove_push", 0.0)
    style = _blend_styles(style, meta.get("blend_style_id"), meta.get("blend_amount", 0.5))
    style = {**style, "_humanize_scale": meta["humanize"]}
    programs = {**_DEFAULT_PROGRAMS, **_STYLE_PROGRAMS.get(meta["style_id"], {})}

    _snapshot_song(output_dir)   # version history: state before this mutation

    section_seeds[req.section_index] = secrets.randbelow(2 ** 31)

    song_req = BuildSongRequest.model_construct(
        style_id=meta["style_id"], key=meta["key"], scale=meta["scale"], bpm=meta["bpm"],
        complexity=meta["complexity"], variation=meta["variation"], humanize=meta["humanize"],
        parts=meta["parts"], template=meta["template"], use_priors=meta["use_priors"],
        seed=meta["base_seed"], chorus_key_shift=meta["chorus_key_shift"],
    )
    song_events, section_results, total_bars, _seeds = _generate_song_sections(
        song_req, style, bpm, meta["base_seed"], meta["chorus_key_shift"],
        secondary_dominants, tritone_sub, groove_push,
        bridge_key_shift=meta.get("bridge_key_shift", 0),
        fixed_section_seeds=section_seeds,
        final_chorus_lift=meta.get("final_chorus_lift", 0),
        custom_template=meta.get("custom_template"),
        user_progression=meta.get("user_progression"),
        hook_melody=_hook_from_meta(meta),
    )

    # Back up all stems (one level of undo per part via /undo-song-part)
    for part in meta["parts"]:
        p = output_dir / f"{part}.mid"
        if p.exists():
            shutil.copy(p, output_dir / f"{part}.prev")

    files = _write_song_output(song_events, output_dir, req.generation_id, bpm, style,
                               programs, list(meta["parts"]), total_bars, section_results,
                               key=meta.get("key", "C"), scale=meta.get("scale", "minor"))

    meta["section_seeds"] = section_seeds
    meta_path.write_text(_json_module.dumps(meta))
    (output_dir / "song_structure.json").write_text(_json_module.dumps(section_results, indent=2))
    return files


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
