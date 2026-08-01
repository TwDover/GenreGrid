# GenreGrid — a style-based MIDI generator.
# Copyright (C) 2026 Tw Dover
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. Distributed WITHOUT ANY WARRANTY. See the GNU General Public License
# <https://www.gnu.org/licenses/> for details.

"""Song-builder core — arrangement engine extracted from routes_song.py.

The template->sections loop (`_generate_song_sections`), its motif/voice-leading
helpers, the section-marker + combined-MIDI writer, and the bridge-escape
progression. Keeps the Song Builder endpoints thin: they parse the request and
call in here. Depends on the generation service + generators/arrangement — never
on a route module."""
import logging
import random


from app.models.schemas import (GenerateRequest, FileInfo)
from app.services.style_loader import load_style
from app.services.midi_writer import (NoteEvent, write_midi, write_combined_midi,
                                      mido_key_signature)
from app.services.library import build_scoring_style
from app.generators.counter_melody import generate_counter_melody
from app.theory.chords import roman_to_chord
from app.core.constants import DRUM_MAP
from app.core.meter import Meter, DEFAULT_METER, parse_meter
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
from app.services.generation import (
    _run_attempt, _choose_progression, _all_green,
    _MAX_QUALITY_ATTEMPTS, _final_chord_voicing,
)

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

    `fixed_section_seeds` — a list of per-section seeds (or `None` per-entry).
    An entry with a definite seed replays that exact winning attempt instead of
    re-deriving and re-searching, so non-regenerated sections come out
    byte-identical to what's already on disk (regenerate_song_part,
    regenerate_song_section). An entry that is `None` (or the whole list is
    `None`) runs the normal quality-gated search — used for brand-new sections
    in a rearrange that have no prior seed to replay.

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

    # The song's meter drives every bar→beat conversion below (section offsets,
    # tease/outro windows, the ending bar) and is threaded into each section's
    # generation request. 4/4 → bar_beats 4.0, so all arithmetic stays identical.
    meter = parse_meter(getattr(req, "time_signature", None))
    bb = meter.bar_beats

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
            time_signature=str(meter),   # every section inherits the song's meter
        )

        # Choruses develop the verse's motif; other section types keep their own
        # ideas. In melody-import mode every melodic section develops the HOOK's
        # motif instead, so the whole song grows out of the user's idea.
        if hook_melody:
            sec_motif = _hook_motif if sec_type in ("verse", "chorus", "bridge") else None
        else:
            sec_motif = verse_motif if sec_type == "chorus" else None

        # Per-section fixed-vs-search: an entry can be None inside an otherwise
        # fixed list (a rearrange mixing carried-over sections that replay their
        # original seed with brand-new/duplicated sections that need a fresh
        # quality-searched seed, like a normal build).
        use_fixed = (fixed_section_seeds is not None and sec_i < len(fixed_section_seeds)
                     and fixed_section_seeds[sec_i] is not None)
        if use_fixed:
            # Replay: reuse the exact seed the original build_song call landed on
            # for this section — no re-search, so untouched parts stay identical.
            winning_seed = fixed_section_seeds[sec_i]
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
            # quality check at all. Also the path for brand-new/duplicated
            # sections in a rearrange (no prior seed to replay).
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

        sec_quality = best_total if (not use_fixed and best_total >= 0) else (
            _qraw.get("total") if use_fixed and _qraw else None)

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
                _q = round((_o % bb) * 4) / 4
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
            "parts_mode": parts_mode,
            "chorus_key": bool(sec_def.get("chorus_key", False)),
            "bridge_key": bool(sec_def.get("bridge_key", False)),
            "style_id": sec_def.get("style_id"),
        })
        ramp_sections.append({
            "offset": beat_offset, "bars": sec_bars,
            "dynamic": SECTION_PROFILES.get(sec_type, {}).get("velocity_scale", 1.0),
        })
        beat_offset += sec_bars * bb
        total_bars  += sec_bars

    # Smooth velocity jumps at section boundaries (verse→chorus lift, etc.). This
    # previously only ran inside a single _run_attempt's own internal auto-arc
    # sections and never across the song builder's independently-generated
    # sections, so every Verse→Chorus/Chorus→Bridge transition was a hard jump.
    if len(ramp_sections) > 1:
        _apply_section_ramp(song_events, ramp_sections, meter=meter)

    # ── Intro hook tease ─────────────────────────────────────────────────────
    # The intro previews the chorus melody: thinned to its structural notes,
    # softer, and transposed back to the home key if the chorus modulates.
    # Deterministic — derived entirely from the cached chorus theme.
    if tease_intro and "melody" in song_events:
        chorus_mel = type_theme.get("chorus", {}).get("melody") or []
        if chorus_mel:
            limit = tease_intro["bars"] * bb
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
                               dynamics=req.dynamics, meter=meter)
    # Pickups run AFTER dynamics so they lead into melody that survived the
    # dropouts (and can sing across a full-band stop).
    apply_melodic_pickups(song_events, section_results, base_seed, req.scale, style, meter=meter)

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
            o_start = _outro_sec["start_bar"] * bb
            o_beats = _outro_sec["bars"] * bb
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
    ending_start = float(total_bars * bb)
    tonic_roman = "i" if req.scale in ("minor", "dorian", "phrygian", "harmonic_minor",
                                       "pentatonic_minor", "blues", "locrian") else "I"
    tonic = roman_to_chord(tonic_roman, req.key, req.scale, octave=4)
    # Cold stop: the band hits the final chord staccato and it's over — no ring.
    ring = 0.35 if _ending_style == "cold" else bb
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


def _section_markers(section_results: list[dict], home_key: str,
                     meter: Meter = DEFAULT_METER) -> list[tuple[float, str]]:
    """MIDI section markers for the DAW timeline; sections that modulate away
    from the home key carry the key in the label (e.g. "Final Chorus (B)")."""
    return [
        (float(s["start_bar"] * meter.bar_beats),
         s["name"] if s.get("key", home_key) == home_key else f"{s['name']} ({s['key']})")
        for s in section_results
    ]


def _write_song_output(song_events: dict, output_dir, gen_id: str, bpm: int, style: dict,
                       programs: dict, parts: list[str], total_bars: int,
                       section_results: list[dict], key: str = "C",
                       scale: str = "minor",
                       meter: Meter = DEFAULT_METER,
                       tempo_automation: float = 0.5) -> list[FileInfo]:
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

    tempo_map = _song_tempo_map(section_results, bpm, ending_bars=1, meter=meter, intensity=tempo_automation)
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
                   tempo_events=tempo_map, track_name=track_names.get(part), meter=meter)
        files.append(FileInfo(part=part, filename=fname, url=f"/exports/{gen_id}/{fname}"))

    if len([p for p, e in song_events.items() if e]) > 1:
        clean_all = {p: _drop_quiet(_scale_velocity(e, p, _sid)) for p, e in song_events.items() if e}
        write_combined_midi(clean_all, output_dir / "song.mid", bpm=bpm, programs=programs,
                            cc_parts=song_cc, pb_parts=song_pb, tempo_events=tempo_map,
                            markers=_section_markers(section_results, key, meter),
                            key_signature=mido_key_signature(key, scale),
                            track_names=track_names, meter=meter)
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
