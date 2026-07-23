# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.
"""Song Builder endpoints and orchestration: templates -> sections -> stems,
plus per-part/per-section regeneration, version history, and melody import.

Split out of routes_generate.py; the loop/arrangement generation core
(_run_attempt and friends) stays there and is imported here.
"""
import logging
import random
import re
import secrets
import shutil
import uuid
import json as _json_module

from fastapi import APIRouter, HTTPException, UploadFile, Form
from fastapi import File as FastAPIFile

from app.models.schemas import (GenerateRequest, FileInfo, BuildSongRequest, BuildSongResponse,
                                SongSectionResult, RegenerateSongPartRequest,
                                RegenerateSongSectionRequest, RestoreSongVersionRequest,
                                SetPartGainRequest, EditPartRequest, SongSectionDef,
                                RollSongPartRequest, SongPartCandidate, KeepSongPartCandidateRequest,
                                RebuildSongProgressionRequest)
from app.services.style_loader import load_style
from app.services.midi_writer import (NoteEvent, write_midi, write_combined_midi,
                                      rebuild_combined_from_parts, mido_key_signature)
from app.services.library import build_scoring_style
from app.generators.counter_melody import generate_counter_melody
from app.theory.chords import roman_to_chord
from app.core.config import EXPORTS_DIR
from app.core.constants import DRUM_MAP
from app.core.arrangement import (
    SECTION_PROFILES, _SONG_TEMPLATES, _part_seed, _transpose_key,
    _apply_section_ramp, _song_tempo_map, apply_arrangement_dynamics,
    apply_melodic_pickups,
)
from app.services.mixdown import (
    _PART_CHANNELS, part_midi_meta,
    _generate_part_cc, _generate_melody_expression_cc,
    _generate_808_pitch_bends, _drop_quiet, _scale_velocity, _shift,
    generate_build_sweeps, generate_section_crescendo,
)
from app.api.routes_generate import (
    _run_attempt, _choose_progression, _blend_styles, _all_green,
    _MAX_QUALITY_ATTEMPTS, _SAFE_PATH, _final_chord_voicing,
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
        template = [dict(sd) for sd in _SONG_TEMPLATES.get(req.template, _SONG_TEMPLATES["verse_chorus"])]

    # DJ edit: bookend the arrangement with an 8-bar beat-only (drums+bass)
    # section for mixing — steady, no fills, no melodic content, outside the arc.
    # Only meaningful when the song actually has a rhythm section.
    if getattr(req, "dj_edit", False) and {"drums", "bass"} & set(req.parts):
        template = (
            [{"name": "DJ Intro", "section_type": "dj_intro", "bars": 8, "parts_mode": "foundation"}]
            + template
            + [{"name": "DJ Outro", "section_type": "dj_outro", "bars": 8, "parts_mode": "foundation"}]
        )

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

    # Pre-choruses get a rising harmonic ramp instead of the song loop — the
    # classic build (predominant -> dominant) that makes the chorus drop land.
    _prechorus_prog = (["ii", "IV", "V", "V"] if req.scale == "major"
                       else ["iv", "v", "VI", "VII"])

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
    rhythm_cell: list[float] | None = None   # the song's rhythmic cell (onset offsets, from the first theme)
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

        # Arrangement colors: pads fill out only the big sections. The
        # counter-melody harmonizes the hook on the final chorus AND answers the
        # lead's holes in the sections with space (verse/intro/outro); it's kept
        # out of the dense middle sections so it never turns into a constant
        # second lead. See generate_counter_melody for the mode split.
        if "pads" in sec_parts and sec_type not in ("chorus", "bridge"):
            sec_parts = [p for p in sec_parts if p != "pads"]
        if "counter_melody" in sec_parts and not (
                sec_i == last_chorus_i or sec_type in ("verse", "intro", "outro")):
            sec_parts = [p for p in sec_parts if p != "counter_melody"]

        # Layer accumulation: every RETURN of a section type carries something
        # its first pass didn't, so repeats escalate instead of photocopying.
        # Verse 2+ gains the arpeggio its template mode withheld; repeated
        # choruses get busier hats (below, via the style overlay).
        _prior_occ = type_occurrence.get(sec_type, 0)
        if (sec_type == "verse" and _prior_occ >= 1
                and "arpeggio" in req.parts and "arpeggio" not in sec_parts):
            sec_parts = sec_parts + ["arpeggio"]

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
        if sec_type == "chorus" and _prior_occ >= 1:
            _drums_cfg = sec_style.get("drums", {})
            sec_style = {**sec_style, "drums": {
                **_drums_cfg, "hat_density": min(1.0, _drums_cfg.get("hat_density", 0.5) * 1.18)}}
        sec_progression = _prechorus_prog if sec_type == "pre_chorus" else song_progression
        # Bridge escape: a fresh progression that opens off the song's beaten path
        # and walks home on a dominant pedal. Seeded so ~half of songs keep today's
        # bridge; opt-in per style via bridge_escape_prob (default 0 = unchanged).
        if sec_type == "bridge":
            _besc = style.get("bridge_escape_prob", 0.0)
            if _besc and random.Random(base_seed ^ 0x8B12D6).random() < _besc:
                sec_progression, _ = _bridge_escape_progression(song_progression, req.scale)

        sec_req = GenerateRequest.model_construct(
            style_id=req.style_id, key=sec_key, scale=req.scale, bpm=bpm,
            bars=sec_bars, complexity=req.complexity, variation=req.variation,
            dynamics=req.dynamics,
            parts=sec_parts, mode="loop", seed=sec_seed, section_type=sec_type,
            next_section_type=next_sec_type,
            song_parts=list(req.parts),   # full song part list — keeps register decisions consistent in sections that drop parts
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
                    fixed_progression=sec_progression,
                    chords_prev_voicing=prev_voicing, melody_seed_motif=sec_motif,
                    rhythm_cell=rhythm_cell, arp_contour=verse_motif,
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
                        fixed_progression=sec_progression,
                        chords_prev_voicing=prev_voicing, melody_seed_motif=sec_motif,
                        rhythm_cell=rhythm_cell, arp_contour=verse_motif,
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
            # answering/harmonizing a line that no longer sounds — re-derive it
            # from the melody that will actually play (in the same mode the
            # section uses: harmony on the chorus, answer in verse/intro/outro).
            if "counter_melody" in evts and evts.get("melody"):
                random.seed(_part_seed(winning_seed, 0, "counter_melody"))
                _cm_mel = sorted(evts["melody"], key=lambda e: e.start)
                _cm_rests = [(round(_cm_mel[i - 1].start + _cm_mel[i - 1].duration, 3),
                              round(_cm_mel[i].start, 3))
                             for i in range(1, len(_cm_mel))
                             if _cm_mel[i].start - (_cm_mel[i - 1].start + _cm_mel[i - 1].duration) >= 1.5]
                _cm_cell = verse_motif or _melody_motif_intervals(evts["melody"], sec_key, req.scale)
                evts["counter_melody"] = generate_counter_melody(
                    evts["melody"], sec_key, req.scale, sec_bars,
                    song_progression, sec_style,
                    melody_rests=_cm_rests, cell=_cm_cell, section_type=sec_type)

        # Thread voice-leading and the verse theme into the next section: the
        # post-theme-swap events are what actually sound, so extract from those.
        if evts.get("chords"):
            prev_voicing = _final_chord_voicing(evts["chords"])
        if verse_motif is None and sec_type == "verse" and evts.get("melody"):
            verse_motif = _melody_motif_intervals(evts["melody"], req.key, req.scale)
        if rhythm_cell is None and evts.get("melody"):
            # The song's rhythmic cell: the first theme's opening onset
            # pattern (16th-quantized, within-bar offsets). Later sections'
            # bass echoes it and the arpeggio takes its contour — the "one
            # composer" glue between parts.
            _onsets = sorted(e.start for e in evts["melody"] if e.start < 8.0)
            rhythm_cell = []
            for _o in _onsets:
                _q = round((_o % 4) * 4) / 4
                if _q not in rhythm_cell:
                    rhythm_cell.append(_q)
                if len(rhythm_cell) >= 4:
                    break
            rhythm_cell = rhythm_cell or None

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
            # Prefer the hook's structural notes for a clean preview.
            thin = [e for e in in_window
                    if (e.start % 1.0) < 0.13 or e.duration >= 0.75]
            # Commit to a real phrase or stay silent: a lone note (or two) reads
            # as an accidental keypress, not a hook preview. Use the thinned hook
            # only if it's a phrase; else tease the fuller line; if even that is
            # just a note or two, leave the intro to the groove.
            _PHRASE = 3
            tease = (thin if len(thin) >= _PHRASE
                     else in_window if len(in_window) >= _PHRASE else [])
            song_events["melody"].extend(
                NoteEvent(min(127, max(0, e.pitch - chorus_theme_shift)), e.start,
                          min(e.duration, limit - e.start),
                          # Floor above the _drop_quiet threshold (20): a soft-
                          # style hook (lofi) scaled by 0.72 dips below it, and
                          # the mixdown would then cull the quiet notes back down
                          # to the lone stray this whole branch exists to avoid.
                          max(34, int(e.velocity * 0.72)), e.channel)
                for e in tease
            )

    # ── Arrangement dynamics ──────────────────────────────────────────────────
    # Dropouts and breakdowns (pre-chorus drop, bridge breakdown, thinned
    # verse 2) — applied before the ending bar so the final cadence survives.
    apply_arrangement_dynamics(song_events, section_results, base_seed,
                               dynamics=req.dynamics)
    # Pickups run AFTER dynamics so they lead into melody that survived the
    # dropouts (and can sing across a full-band stop).
    apply_melodic_pickups(song_events, section_results, base_seed, req.scale, style)

    # ── Ending variety ────────────────────────────────────────────────────────
    # Every song used to end with the identical ring-out formula. Three seeded
    # endings now: ring-out (the classic), cold stop (staccato final hit), and
    # the hook-echo outro — the outro's own melody is replaced by thinned
    # fragments of the chorus hook, fading, so the song looks BACK at its own
    # idea on the way out instead of introducing fresh material.
    _end_rng = random.Random(_part_seed(base_seed, 917, "ending"))
    _ending_style = _end_rng.choices(["ring", "cold", "hook_echo"], weights=[0.45, 0.2, 0.35])[0]
    _outro_sec = next((s for s in section_results if s.get("section_type") == "outro"), None)
    if _ending_style == "hook_echo":
        _hook = type_theme.get("chorus", {}).get("melody") or []
        if _outro_sec and _hook and "melody" in song_events:
            o_start = _outro_sec["start_bar"] * 4.0
            o_beats = _outro_sec["bars"] * 4.0
            frag = [e for e in sorted(_hook, key=lambda e: e.start) if e.start < 8.0]
            thin = [e for e in frag if (e.start % 1.0) < 0.13 or e.duration >= 0.75] or frag
            song_events["melody"] = [e for e in song_events["melody"]
                                     if not (o_start - 0.1 <= e.start < o_start + o_beats)]
            placements = [(o_start, 0.72)]
            if o_beats >= 12:
                placements.append((o_start + o_beats / 2, 0.5))
            for _base, _velf in placements:
                for e in thin:
                    t = _base + e.start
                    if t < o_start + o_beats - 0.25:
                        song_events["melody"].append(NoteEvent(
                            min(127, max(0, e.pitch - chorus_theme_shift)), t,
                            min(e.duration, o_start + o_beats - t),
                            max(1, int(e.velocity * _velf)), e.channel))
            song_events["melody"].sort(key=lambda e: e.start)
        else:
            _ending_style = "ring"   # nothing to echo — fall back gracefully

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
    # Cold stop: the band hits the final chord staccato and it's over — no ring.
    ring = 0.35 if _ending_style == "cold" else 4.0
    if "chords" in song_events:
        # Voice the final chord in the register the song's comp actually ended
        # in (prev_voicing = the outro's closing voicing). The hardcoded
        # octave-4 tonic sat a full octave above the melody-capped comp, so the
        # very last bar leapt upward out of the song's register.
        chord_tonic = sorted(tonic)
        if prev_voicing:
            _target = sum(prev_voicing) / len(prev_voicing)
            _mean = sum(chord_tonic) / len(chord_tonic)
            _oct_shift = min((-24, -12, 0, 12, 24), key=lambda o: abs(_mean + o - _target))
            chord_tonic = [max(0, min(127, p + _oct_shift)) for p in chord_tonic]
        for ni, p in enumerate(chord_tonic):
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
    # The melody deliberately does NOT restate a note on the ending bar: its
    # line already resolved in the outro, and a lone root popping up over the
    # final chord read as an accidental keypress. The cadence is the band's —
    # chord + bass + kick/crash ringing out.
    if "drums" in song_events:
        song_events["drums"].append(NoteEvent(DRUM_MAP["kick"], ending_start, 0.1, 116, 9))
        song_events["drums"].append(NoteEvent(DRUM_MAP["crash"], ending_start, ring, 104, 9))
    section_results.append({
        "name": "End", "section_type": "ending",
        "bars": 1, "start_bar": total_bars, "key": req.key,
    })
    total_bars += 1

    return song_events, section_results, total_bars, section_seeds, song_progression


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

    # Section-level automation: pre-chorus filter sweeps + crescendo into the chorus.
    for automation in (generate_build_sweeps(section_results, parts),
                       generate_section_crescendo(section_results, parts)):
        for part, evs in automation.items():
            if song_events.get(part):
                song_cc.setdefault(part, []).extend(evs)

    song_pb: dict[str, list] = {}
    if song_events.get("bass") and style.get("bass", {}).get("bass_style") == "808":
        ch = _PART_CHANNELS.get("bass", 1)
        song_pb["bass"] = _generate_808_pitch_bends(song_events["bass"], ch)

    tempo_map = _song_tempo_map(section_results, bpm, ending_bars=1)
    _, track_names = part_midi_meta(style)

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
                   tempo_events=tempo_map, track_name=track_names.get(part))
        files.append(FileInfo(part=part, filename=fname, url=f"/exports/{gen_id}/{fname}"))

    if len([p for p, e in song_events.items() if e]) > 1:
        clean_all = {p: _drop_quiet(_scale_velocity(e, p, _sid)) for p, e in song_events.items() if e}
        write_combined_midi(clean_all, output_dir / "song.mid", bpm=bpm, programs=programs,
                            cc_parts=song_cc, pb_parts=song_pb, tempo_events=tempo_map,
                            markers=_section_markers(section_results, key),
                            key_signature=mido_key_signature(key, scale),
                            track_names=track_names)
        files.append(FileInfo(part="song", filename="song.mid", url=f"/exports/{gen_id}/song.mid"))
    return files


_MAJOR_FAMILY_SCALES = ("major", "mixolydian", "lydian", "pentatonic_major")


def _bridge_escape_progression(song_progression: list, scale: str) -> tuple[list, str]:
    """A bridge grammar that starts somewhere the song hasn't been and walks home
    (roadmap-2 item 5). Opens on a diatonic chord absent from the verse/chorus
    loop (vi if the song is I-heavy, ♭VI as the deceptive option in minor), takes
    a bar of departure, then a dominant-pedal bar that pulls back into the return.

    Returns (progression, opening_chord). The caller decides (seeded) whether to
    use it, so half of songs keep today's bridge sound."""
    used = set(song_progression)
    if scale in _MAJOR_FAMILY_SCALES:
        openers, mid, dom = ["vi", "IV", "ii", "iii"], "ii", "V"
    else:
        openers, mid, dom = ["bVI", "iv", "bII", "bVII"], "iv", "V"
    opener = next((c for c in openers if c not in used), openers[0])
    if mid == opener:
        mid = dom
    return [opener, mid, dom, dom], opener


@router.post("/build-song", response_model=BuildSongResponse)
def build_song(req: BuildSongRequest):
    """Generate a full song by stitching independently-generated sections."""
    return _do_build_song(req)


_ROMAN_TOKEN_RE = re.compile(
    r'^[b#]?(VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)(maj7|m7b5|dim7|dim|aug|sus[24]|add\d+|m?6|m?7|m?9|\+)?$')


@router.post("/rebuild-song-progression", response_model=BuildSongResponse)
def rebuild_song_progression(req: RebuildSongProgressionRequest):
    """Rebuild a song with a user-edited progression (roadmap-2 item 6).

    Everything else — style, key, seed, template, section layout — is replayed
    from the original build, so only the harmony changes. Produces a new song
    (the original stays on disk); the edited progression is validated against the
    song's key before anything is regenerated."""
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found or too old to edit")
    meta = _json_module.loads(meta_path.read_text())

    key, scale = meta.get("key", "C"), meta.get("scale", "minor")
    prog = [r.strip() for r in req.progression if r.strip()]
    if len(prog) < 2:
        raise HTTPException(status_code=400, detail="A progression needs at least two chords")
    # Validate each token is a real roman numeral (optional accidental + I–VII in
    # either case + an optional chord-quality suffix) — roman_to_chord silently
    # defaults unknown tokens to the tonic, so a shape check is what actually rejects typos.
    for roman in prog:
        if not _ROMAN_TOKEN_RE.match(roman):
            raise HTTPException(status_code=400, detail=f"'{roman}' isn't a valid roman numeral")

    custom = meta.get("custom_template")
    song_req = BuildSongRequest(
        style_id=meta["style_id"], key=key, scale=scale, bpm=meta["bpm"],
        complexity=meta["complexity"], variation=meta["variation"],
        dynamics=meta.get("dynamics", 0.5), humanize=meta["humanize"],
        parts=meta["parts"], template=meta.get("template", "verse_chorus"),
        seed=meta["base_seed"], use_priors=meta["use_priors"],
        chorus_key_shift=meta.get("chorus_key_shift"),
        bridge_key_shift=meta.get("bridge_key_shift"),
        final_chorus_lift=meta.get("final_chorus_lift"),
        custom_template=[SongSectionDef(**sd) for sd in custom] if custom else None,
        blend_style_id=meta.get("blend_style_id"),
        blend_amount=meta.get("blend_amount", 0.5),
        dj_edit=meta.get("dj_edit", False),
        progression_override=prog,
    )
    # Preserve an imported hook melody (melody-import songs) while overriding harmony.
    return _do_build_song(song_req, hook_melody=_hook_from_meta(meta))


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

    programs, track_names = part_midi_meta(style)
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

    song_events, section_results, total_bars, section_seeds, song_progression = _generate_song_sections(
        req, style, bpm, base_seed, chorus_key_shift,
        secondary_dominants, tritone_sub, groove_push,
        bridge_key_shift=bridge_key_shift,
        final_chorus_lift=final_chorus_lift,
        custom_template=custom_template,
        user_progression=user_progression or getattr(req, "progression_override", None),
        hook_melody=hook_melody,
    )

    # Persist the params needed to regenerate a single part later.
    import json as _jmeta
    (output_dir / "song_meta.json").write_text(_jmeta.dumps({
        "style_id": req.style_id, "key": req.key, "scale": req.scale,
        "bpm": bpm, "complexity": req.complexity, "variation": req.variation,
        "dynamics": req.dynamics,
        "humanize": req.humanize, "parts": list(req.parts), "template": req.template,
        "use_priors": req.use_priors, "chorus_key_shift": chorus_key_shift,
        "bridge_key_shift": bridge_key_shift, "base_seed": base_seed,
        "final_chorus_lift": final_chorus_lift, "custom_template": custom_template,
        "blend_style_id": getattr(req, "blend_style_id", None),
        "blend_amount": getattr(req, "blend_amount", 0.5),
        "dj_edit": getattr(req, "dj_edit", False),
        "user_progression": user_progression,
        # The resolved song progression, pinned so section re-rolls reproduce it
        # and the UI can show/lock it (roadmap-2 item 6).
        "song_progression": song_progression,
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
        progression=song_progression,
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
    programs, track_names = part_midi_meta(style)

    _snapshot_song(output_dir)   # version history: state before this mutation

    gen_parts = list(meta["parts"]) + ([req.part] if is_new_part else [])
    song_req = BuildSongRequest.model_construct(
        style_id=meta["style_id"], key=meta["key"], scale=meta["scale"], bpm=meta["bpm"],
        complexity=meta["complexity"], variation=meta["variation"], humanize=meta["humanize"],
        dynamics=meta.get("dynamics", 0.5),
        parts=gen_parts, template=meta["template"], use_priors=meta["use_priors"],
        seed=meta["base_seed"], chorus_key_shift=meta["chorus_key_shift"],
        dj_edit=meta.get("dj_edit", False),   # keep the DJ bookends so section seeds still line up
    )

    salt = secrets.randbelow(2 ** 31) or 1   # non-zero so the part actually changes
    song_events, _sections, total_bars, _seeds, _prog = _generate_song_sections(
        song_req, style, bpm, meta["base_seed"], meta["chorus_key_shift"],
        secondary_dominants, tritone_sub, groove_push,
        regen_part=req.part, regen_salt=salt,
        bridge_key_shift=meta.get("bridge_key_shift", 0),
        fixed_section_seeds=meta.get("section_seeds"),
        final_chorus_lift=meta.get("final_chorus_lift", 0),
        custom_template=meta.get("custom_template"),
        # Pin the persisted progression so a part re-roll targets the same harmony.
        user_progression=meta.get("song_progression") or meta.get("user_progression"),
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
        # A re-rolled stem keeps its pre-chorus sweeps/crescendo (build_song adds
        # these in _write_song_output, which this single-stem path bypasses)
        for automation in (generate_build_sweeps(_sections, [req.part]),
                           generate_section_crescendo(_sections, [req.part])):
            part_cc = part_cc + automation.get(req.part, [])
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
               cc_events=part_cc, pb_events=part_pb, tempo_events=tempo_map,
               track_name=track_names.get(req.part))

    # Rebuild song.mid from all stems on disk (new part + untouched others).
    rebuild_combined_from_parts(output_dir, bpm, combined_name="song.mid", tempo_events=tempo_map,
                                markers=_section_markers(_sections, meta.get("key", "C")),
                                key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")),
                                track_names=track_names)

    # An added part becomes a first-class member of the song so later
    # regenerations and undos treat it like any originally-built stem.
    if is_new_part:
        meta["parts"] = gen_parts
        meta_path.write_text(_json_module.dumps(meta))

    return FileInfo(part=req.part, filename=fname, url=f"/exports/{req.generation_id}/{fname}")


def _render_song_part_stem(output_dir, meta: dict, style: dict, part: str, salt: int,
                           programs: dict, track_names: dict, bpm: int, out_name: str) -> bool:
    """Render one variation of a song part (salted) and write it to `out_name`,
    WITHOUT touching the live stem or song.mid. Used to roll compare-and-keep
    candidates. Returns False when the part produced no notes."""
    secondary_dominants = style.get("secondary_dominants", False)
    tritone_sub = style.get("tritone_substitution", False)
    groove_push = style.get("groove_push", 0.0)

    song_req = BuildSongRequest.model_construct(
        style_id=meta["style_id"], key=meta["key"], scale=meta["scale"], bpm=meta["bpm"],
        complexity=meta["complexity"], variation=meta["variation"], humanize=meta["humanize"],
        dynamics=meta.get("dynamics", 0.5),
        parts=meta["parts"], template=meta["template"], use_priors=meta["use_priors"],
        seed=meta["base_seed"], chorus_key_shift=meta["chorus_key_shift"],
        dj_edit=meta.get("dj_edit", False),
    )
    song_events, _sections, total_bars, _seeds, _prog = _generate_song_sections(
        song_req, style, bpm, meta["base_seed"], meta["chorus_key_shift"],
        secondary_dominants, tritone_sub, groove_push,
        regen_part=part, regen_salt=salt,
        bridge_key_shift=meta.get("bridge_key_shift", 0),
        fixed_section_seeds=meta.get("section_seeds"),
        final_chorus_lift=meta.get("final_chorus_lift", 0),
        custom_template=meta.get("custom_template"),
        user_progression=meta.get("song_progression") or meta.get("user_progression"),
        hook_melody=_hook_from_meta(meta),
    )
    evts = song_events.get(part) or []
    if not evts:
        return False

    _sid = style.get("id", "")
    part_cc = None
    if part != "drums":
        channel = _PART_CHANNELS.get(part, 0)
        part_cc = _generate_part_cc(part, total_bars, channel, style=style)
        if part == "melody":
            part_cc = part_cc + _generate_melody_expression_cc(evts, channel)
        for automation in (generate_build_sweeps(_sections, [part]),
                           generate_section_crescendo(_sections, [part])):
            part_cc = part_cc + automation.get(part, [])
    part_pb = None
    if part == "bass" and style.get("bass", {}).get("bass_style") == "808":
        part_pb = _generate_808_pitch_bends(evts, _PART_CHANNELS.get("bass", 1))

    tempo_map = _song_tempo_map(_sections, bpm, ending_bars=1)
    scaled = _drop_quiet(_scale_velocity(evts, part, _sid))
    write_midi(scaled, output_dir / out_name, bpm=bpm, program=programs.get(part),
               cc_events=part_cc, pb_events=part_pb, tempo_events=tempo_map,
               track_name=track_names.get(part))
    return True


def _clear_part_candidates(output_dir, part: str) -> None:
    for f in output_dir.glob(f"{part}.cand*.mid"):
        f.unlink(missing_ok=True)


@router.post("/roll-song-part-candidates", response_model=list[SongPartCandidate])
def roll_song_part_candidates(req: RollSongPartRequest):
    """Roll several candidate variations of one song part so the user can compare
    and keep the best (roadmap-2 item 7). Candidates are written to separate
    `{part}.candN.mid` files; the live stem and song.mid are left untouched until
    the user commits one via /keep-song-part-candidate."""
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found or too old to re-roll")
    meta = _json_module.loads(meta_path.read_text())
    if req.part not in meta.get("parts", []):
        raise HTTPException(status_code=400, detail=f"'{req.part}' is not a part of this song")

    try:
        style = load_style(meta["style_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, meta["bpm"]))
    style = _blend_styles(style, meta.get("blend_style_id"), meta.get("blend_amount", 0.5))
    style = {**style, "_humanize_scale": meta["humanize"]}
    programs, track_names = part_midi_meta(style)

    _clear_part_candidates(output_dir, req.part)
    candidates: list[SongPartCandidate] = []
    # Deterministic per-generation salts so the same song always rolls the same
    # candidate set (reproducible), while each candidate differs from the others.
    for i in range(req.count):
        salt = (secrets.randbelow(2 ** 31) or 1)
        out_name = f"{req.part}.cand{i}.mid"
        if _render_song_part_stem(output_dir, meta, style, req.part, salt,
                                  programs, track_names, bpm, out_name):
            candidates.append(SongPartCandidate(
                index=i, filename=out_name,
                url=f"/exports/{req.generation_id}/{out_name}"))
    if not candidates:
        raise HTTPException(status_code=500, detail=f"No candidates generated for {req.part}")
    return candidates


@router.post("/keep-song-part-candidate", response_model=FileInfo)
def keep_song_part_candidate(req: KeepSongPartCandidateRequest):
    """Commit a rolled candidate as the part's live stem: snapshot for history,
    promote the chosen candidate, rebuild song.mid, and clear the candidates."""
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found")
    meta = _json_module.loads(meta_path.read_text())
    cand_path = output_dir / f"{req.part}.cand{req.index}.mid"
    if not cand_path.exists():
        raise HTTPException(status_code=404, detail="That candidate is no longer available — re-roll to try again")

    try:
        style = load_style(meta["style_id"])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    bpm_min, bpm_max = style.get("bpm_range", [40, 240])
    bpm = max(bpm_min, min(bpm_max, meta["bpm"]))
    style = _blend_styles(style, meta.get("blend_style_id"), meta.get("blend_amount", 0.5))
    style = {**style, "_humanize_scale": meta["humanize"]}
    _, track_names = part_midi_meta(style)

    _snapshot_song(output_dir)   # version history: state before this mutation
    live = output_dir / f"{req.part}.mid"
    if live.exists():
        shutil.copy(live, output_dir / f"{req.part}.prev")   # one-level undo
    shutil.copy(cand_path, live)
    _clear_part_candidates(output_dir, req.part)

    layout = _template_section_results(
        meta.get("template", "verse_chorus"), meta.get("key", "C"),
        custom=meta.get("custom_template"))
    rebuild_combined_from_parts(
        output_dir, bpm, combined_name="song.mid",
        tempo_events=_song_tempo_map(layout, bpm, ending_bars=1),
        markers=_section_markers(layout, meta.get("key", "C")),
        key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")),
        track_names=track_names)
    return FileInfo(part=req.part, filename=f"{req.part}.mid",
                    url=f"/exports/{req.generation_id}/{req.part}.mid")


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


def _rescale_stem_velocities(path, factor: float) -> None:
    """Rewrite a stem .mid scaling note-on velocities by `factor` (clamped 1-127),
    preserving CC, pitch bends, tempo map, markers, and program changes."""
    import mido
    mid = mido.MidiFile(str(path))
    for track in mid.tracks:
        for msg in track:
            if msg.type == "note_on" and msg.velocity > 0:
                msg.velocity = max(1, min(127, round(msg.velocity * factor)))
    mid.save(str(path))


@router.post("/set-part-gain", response_model=FileInfo)
def set_part_gain(req: SetPartGainRequest):
    """In-app mixer: set a part's gain relative to how it was generated (1.0).

    The stem's velocities are rescaled on disk (so preview, drag-to-DAW, and
    exports all reflect it) and the setting persists in song_meta so it shows
    correctly after a reload. Gains are absolute, not cumulative — setting 1.0
    restores the generated balance exactly (modulo integer rounding).
    """
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found")
    part_path = output_dir / f"{req.part}.mid"
    if not part_path.exists():
        raise HTTPException(status_code=404, detail=f"No {req.part} stem in this song")

    meta = _json_module.loads(meta_path.read_text())
    mixer = meta.get("mixer") or {}
    old_gain = float(mixer.get(req.part, 1.0))
    factor = req.gain / old_gain if old_gain > 1e-6 else req.gain
    if abs(factor - 1.0) > 1e-6:
        _rescale_stem_velocities(part_path, factor)

    mixer[req.part] = req.gain
    meta["mixer"] = mixer
    meta_path.write_text(_json_module.dumps(meta))

    bpm = meta.get("bpm", 120)
    layout = _template_section_results(meta.get("template", "verse_chorus"), meta.get("key", "C"),
                                       custom=meta.get("custom_template"))
    try:
        _, _track_names = part_midi_meta(load_style(meta.get("style_id", "")))
    except Exception:
        _track_names = {}
    rebuild_combined_from_parts(output_dir, bpm, combined_name="song.mid",
                                tempo_events=_song_tempo_map(layout, bpm, ending_bars=1),
                                markers=_section_markers(layout, meta.get("key", "C")),
                                key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")),
                                track_names=_track_names)
    return FileInfo(part=req.part, filename=f"{req.part}.mid",
                    url=f"/exports/{req.generation_id}/{req.part}.mid")


@router.post("/edit-part", response_model=FileInfo)
def edit_part(req: EditPartRequest):
    """Light note editing: replace a song stem's notes with a hand-edited list.

    The stem is rewritten on disk (same tempo map, program, and part CC as the
    sibling endpoints) and song.mid is rebuilt from the stems, so preview,
    drag-to-DAW, and exports all reflect the edit. The pre-edit state is
    snapshotted first, so an edit is restorable from the History picker.
    """
    if not _SAFE_PATH.match(req.generation_id):
        raise HTTPException(status_code=400, detail="Invalid generation id")
    if req.part not in _ALL_SONG_PARTS:
        raise HTTPException(status_code=400, detail=f"Unknown part '{req.part}'")
    output_dir = EXPORTS_DIR / req.generation_id
    meta_path = output_dir / "song_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Song not found")
    part_path = output_dir / f"{req.part}.mid"
    if not part_path.exists():
        raise HTTPException(status_code=404, detail=f"No {req.part} stem in this song")

    meta = _json_module.loads(meta_path.read_text())
    _snapshot_song(output_dir)   # version history: state before this mutation

    bpm = meta.get("bpm", 120)
    layout = _template_section_results(meta.get("template", "verse_chorus"), meta.get("key", "C"),
                                       custom=meta.get("custom_template"))
    tempo_map = _song_tempo_map(layout, bpm, ending_bars=1)
    total_bars = sum(s["bars"] for s in layout)

    channel = 9 if req.part == "drums" else _PART_CHANNELS.get(req.part, 0)
    events = [NoteEvent(n.pitch, n.start, n.duration, n.velocity, channel) for n in req.notes]

    # Same CC treatment as regenerate_song_part — pan/reverb per part, plus
    # expression swells re-derived from the edited melody line.
    part_cc = None
    if req.part != "drums":
        try:
            style = load_style(meta["style_id"])
        except (ValueError, KeyError):
            style = None
        part_cc = _generate_part_cc(req.part, total_bars, channel, style=style)
        if req.part == "melody":
            part_cc = part_cc + _generate_melody_expression_cc(events, channel)
        # An edited stem keeps its pre-chorus sweeps/crescendo too
        for automation in (generate_build_sweeps(layout, [req.part]),
                           generate_section_crescendo(layout, [req.part])):
            part_cc = part_cc + automation.get(req.part, [])

    programs, track_names = part_midi_meta(style if style else {"id": meta.get("style_id", "")})
    write_midi(events, part_path, bpm=bpm, program=programs.get(req.part),
               cc_events=part_cc, tempo_events=tempo_map,
               track_name=track_names.get(req.part))

    rebuild_combined_from_parts(output_dir, bpm, combined_name="song.mid", tempo_events=tempo_map,
                                markers=_section_markers(layout, meta.get("key", "C")),
                                key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")),
                                track_names=track_names)
    return FileInfo(part=req.part, filename=f"{req.part}.mid",
                    url=f"/exports/{req.generation_id}/{req.part}.mid")


@router.get("/songs", response_model=list[BuildSongResponse])
def list_songs(limit: int = 20):
    """Previously built songs, newest first, rehydrated from disk.

    Lets the UI survive a reload: song stems, structure, and regeneration
    context all live in the export folder, so the frontend can re-open any
    recent song exactly as it was (including its version history).
    """
    entries: list[tuple[float, BuildSongResponse]] = []
    if not EXPORTS_DIR.exists():
        return []
    for d in EXPORTS_DIR.iterdir():
        meta_path = d / "song_meta.json"
        structure_path = d / "song_structure.json"
        if not (d.is_dir() and meta_path.exists() and structure_path.exists()):
            continue
        try:
            meta = _json_module.loads(meta_path.read_text())
            sections = _json_module.loads(structure_path.read_text())
            files = [FileInfo(part=f.stem, filename=f.name, url=f"/exports/{d.name}/{f.name}")
                     for f in sorted(d.glob("*.mid"))]
            if not files:
                continue
            total_bars = sum(s.get("bars", 0) for s in sections)
            entries.append((meta_path.stat().st_mtime, BuildSongResponse(
                generation_id=d.name,
                style=meta.get("style_id", ""),
                files=files,
                seed=meta.get("base_seed", 0),
                template=meta.get("template", "verse_chorus"),
                total_bars=total_bars,
                sections=[SongSectionResult(**s) for s in sections],
                bpm=meta.get("bpm", 120),
                key=f"{meta.get('key', 'C')} {meta.get('scale', 'minor')}",
                progression=meta.get("song_progression"),
                mixer=meta.get("mixer") or {},
            )))
        except Exception:
            continue   # a half-written or legacy folder never breaks the list
    entries.sort(key=lambda e: e[0], reverse=True)
    return [r for _, r in entries[:limit]]


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
    try:
        _, _track_names = part_midi_meta(load_style(meta.get("style_id", "")))
    except Exception:
        _track_names = {}
    rebuild_combined_from_parts(output_dir, bpm, combined_name="song.mid", tempo_events=tempo_map,
                                markers=_section_markers(_layout, meta.get("key", "C")),
                                key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")),
                                track_names=_track_names)
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
    programs, track_names = part_midi_meta(style)

    _snapshot_song(output_dir)   # version history: state before this mutation

    section_seeds[req.section_index] = secrets.randbelow(2 ** 31)

    song_req = BuildSongRequest.model_construct(
        style_id=meta["style_id"], key=meta["key"], scale=meta["scale"], bpm=meta["bpm"],
        complexity=meta["complexity"], variation=meta["variation"], humanize=meta["humanize"],
        dynamics=meta.get("dynamics", 0.5),
        parts=meta["parts"], template=meta["template"], use_priors=meta["use_priors"],
        seed=meta["base_seed"], chorus_key_shift=meta["chorus_key_shift"],
    )
    song_events, section_results, total_bars, _seeds, _prog = _generate_song_sections(
        song_req, style, bpm, meta["base_seed"], meta["chorus_key_shift"],
        secondary_dominants, tritone_sub, groove_push,
        bridge_key_shift=meta.get("bridge_key_shift", 0),
        fixed_section_seeds=section_seeds,
        final_chorus_lift=meta.get("final_chorus_lift", 0),
        custom_template=meta.get("custom_template"),
        # Pin the persisted progression so re-rolling a section keeps the song's harmony.
        user_progression=meta.get("song_progression") or meta.get("user_progression"),
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

    # Part locking: any locked stem is restored to its pre-reroll state (the .prev
    # backup taken above) so it stays byte-identical — the section re-roll only
    # rewrites the unlocked parts. song.mid is then rebuilt from the on-disk stems
    # (locked = old, unlocked = fresh) so playback matches.
    locked = [p for p in (req.locked_parts or []) if p in meta["parts"]]
    if locked:
        for part in locked:
            prev = output_dir / f"{part}.prev"
            if prev.exists():
                shutil.copy(prev, output_dir / f"{part}.mid")
        rebuild_combined_from_parts(
            output_dir, bpm, combined_name="song.mid",
            tempo_events=_song_tempo_map(section_results, bpm, ending_bars=1),
            markers=_section_markers(section_results, meta.get("key", "C")),
            key_signature=mido_key_signature(meta.get("key", "C"), meta.get("scale", "minor")),
            track_names=track_names)
        # Don't ask the client to reload a locked stem that didn't change.
        files = [f for f in files if f.part not in locked]

    meta["section_seeds"] = section_seeds
    meta_path.write_text(_json_module.dumps(meta))
    (output_dir / "song_structure.json").write_text(_json_module.dumps(section_results, indent=2))
    return files
